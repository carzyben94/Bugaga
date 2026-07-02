# test_bot.py - browser-use 0.5.2 + Agnes
import os
import sys
import subprocess
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ФУНКЦИИ УСТАНОВКИ ==========

def install_package(package, version=None):
    """Устанавливает пакет через pip с указанной версией"""
    try:
        cmd = [sys.executable, '-m', 'pip', 'install']
        if version:
            cmd.append(f"{package}=={version}")
        else:
            cmd.append(package)
            
        print(f"⏳ Устанавливаю {' '.join(cmd)}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {package} установлен")
            return True
        else:
            print(f"❌ Ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def install_playwright():
    """Устанавливает Playwright браузер"""
    try:
        print("⏳ Устанавливаю Playwright браузер...")
        result = subprocess.run([
            sys.executable, '-m', 'playwright', 'install', 'chromium'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Playwright браузер установлен")
            return True
        else:
            print(f"❌ Ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# ========== ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ ==========

def check_and_install_dependencies():
    """Проверяет и устанавливает все зависимости"""
    # Базовые пакеты
    packages = [
        'langchain-openai',
        'playwright'
    ]
    
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} уже установлен")
        except ImportError:
            print(f"⚠️ {package} не найден, устанавливаю...")
            install_package(package)
    
    # Устанавливаем browser-use 0.5.2
    try:
        import browser_use
        from browser_use import Agent
        print(f"✅ browser-use уже установлен (версия: {browser_use.__version__ if hasattr(browser_use, '__version__') else 'unknown'})")
    except ImportError:
        print("⚠️ browser-use не найден, устанавливаю 0.5.2...")
        install_package('browser-use', '0.5.2')
    
    # Устанавливаем playwright браузер
    try:
        import playwright
        install_playwright()
    except ImportError:
        print("⚠️ Playwright не установлен, устанавливаю...")
        install_package('playwright')
        install_playwright()

# Запускаем проверку
check_and_install_dependencies()

# ========== AGNES ==========
AGNES_AVAILABLE = False
agnes_llm = None

def init_agnes():
    global AGNES_AVAILABLE, agnes_llm
    try:
        from langchain_openai import ChatOpenAI
        
        api_key = os.environ.get("AGNES_API_KEY", "")
        if not api_key:
            print("⚠️ AGNES_API_KEY не установлен")
            return False
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=api_key,
        )
        
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes загружена")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
    return False

init_agnes()

# ========== BROWSER-USE ==========
BROWSER_USE_AVAILABLE = False
BROWSER_USE_VERSION = None

def check_browser_use():
    global BROWSER_USE_AVAILABLE, BROWSER_USE_VERSION
    try:
        import browser_use
        from browser_use import Agent
        
        if hasattr(browser_use, '__version__'):
            BROWSER_USE_VERSION = browser_use.__version__
        else:
            BROWSER_USE_VERSION = 'unknown'
            
        BROWSER_USE_AVAILABLE = True
        print(f"✅ browser-use загружен (версия: {BROWSER_USE_VERSION})")
        return True
    except ImportError:
        BROWSER_USE_AVAILABLE = False
        print("⚠️ browser-use не найден")
        return False

check_browser_use()

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version_info = f"v{BROWSER_USE_VERSION}" if BROWSER_USE_VERSION else "❌"
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
        f"browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'} {version_info}\n\n"
        f"/browse <задача> — выполнить в браузере\n"
        f"/agnes — статус Agnes\n"
        f"/install — установить зависимости"
    )

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if AGNES_AVAILABLE:
        await update.message.reply_text("✅ Agnes готова!")
    else:
        await update.message.reply_text(
            "❌ Agnes не доступна\n\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

async def install(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная установка зависимостей"""
    msg = await update.message.reply_text("⏳ Устанавливаю зависимости...")
    
    try:
        await msg.edit_text("⏳ Удаляю старую версию browser-use...")
        subprocess.run([
            sys.executable, '-m', 'pip', 'uninstall', 'browser-use', '-y'
        ], capture_output=True)
        
        await msg.edit_text("⏳ Устанавливаю browser-use 0.5.2...")
        install_package('browser-use', '0.5.2')
        
        await msg.edit_text("⏳ Проверяю установку...")
        check_browser_use()
        init_agnes()
        
        status = (
            f"✅ Установка завершена!\n\n"
            f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
            f"browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'} v{BROWSER_USE_VERSION if BROWSER_USE_VERSION else 'unknown'}\n\n"
            f"Попробуй: /browse открой google.com"
        )
        await msg.edit_text(status)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ /browse <задача>\nПример: /browse открой google.com")
        return
    
    if not AGNES_AVAILABLE:
        await update.message.reply_text("❌ Agnes не доступна. Проверь /agnes")
        return
    
    if not BROWSER_USE_AVAILABLE:
        await update.message.reply_text(
            "❌ browser-use не установлен.\n"
            "Используй /install для установки"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    try:
        from browser_use import Agent
        
        # Для версии 0.5.2 используем стандартные параметры
        agent = Agent(
            task=task,
            llm=agnes_llm,
        )
        
        await msg.edit_text(f"🧠 Agnes работает...")
        result = await agent.run()
        
        # Извлекаем результат
        if hasattr(result, 'content'):
            result_text = result.content[:1500]
        elif hasattr(result, 'text'):
            result_text = result.text[:1500]
        elif isinstance(result, str):
            result_text = result[:1500]
        else:
            result_text = str(result)[:1500]
        
        response = f"✅ **Результат:**\n\n{result_text if result_text else 'Готово'}"
        await msg.edit_text(response)
        
    except Exception as e:
        error_msg = str(e)
        if "Screenshot" in error_msg:
            await msg.edit_text(
                "❌ Ошибка screenshot в browser-use\n\n"
                "Попробуй:\n"
                "1. /install — переустановить зависимости\n"
                "2. Или вернись на версию 0.1.0"
            )
        else:
            await msg.edit_text(f"❌ Ошибка: {error_msg[:200]}")
        logger.error(f"Error: {e}", exc_info=True)


# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("agnes", agnes))
    app.add_handler(CommandHandler("install", install))
    app.add_handler(CommandHandler("browse", browse))
    
    print("✅ Бот запущен!")
    print(f"🤖 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print(f"🧠 browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'} v{BROWSER_USE_VERSION if BROWSER_USE_VERSION else 'unknown'}")
    print("Команды: /start, /agnes, /install, /browse")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()