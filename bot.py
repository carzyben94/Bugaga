# test_bot.py - browser-use + Agnes с автоустановкой
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

def install_package(package):
    """Устанавливает пакет через pip"""
    try:
        print(f"⏳ Устанавливаю {package}...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', package
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {package} установлен")
            return True
        else:
            print(f"❌ Ошибка установки {package}: {result.stderr}")
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
    packages = [
        'langchain-openai',
        'browser-use',
        'playwright'
    ]
    
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} уже установлен")
        except ImportError:
            print(f"⚠️ {package} не найден, устанавливаю...")
            if install_package(package):
                print(f"✅ {package} установлен")
            else:
                print(f"❌ Не удалось установить {package}")
    
    # Устанавливаем Playwright браузер
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

def check_browser_use():
    global BROWSER_USE_AVAILABLE
    try:
        from browser_use import Agent
        BROWSER_USE_AVAILABLE = True
        print("✅ browser-use загружен")
        return True
    except ImportError:
        BROWSER_USE_AVAILABLE = False
        print("⚠️ browser-use не найден")
        return False

check_browser_use()

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
        f"browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'}\n\n"
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
        check_and_install_dependencies()
        # Перепроверяем browser-use
        check_browser_use()
        # Перепроверяем Agnes
        init_agnes()
        
        status = (
            f"✅ Установка завершена!\n\n"
            f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
            f"browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'}"
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
        
        agent = Agent(
            task=task,
            llm=agnes_llm,
        )
        
        await msg.edit_text(f"🧠 Agnes работает...")
        result = await agent.run()
        
        response = f"✅ **Результат:**\n\n{result[:1500] if result else 'Готово'}"
        await msg.edit_text(response)
        
    except Exception as e:
        error_msg = str(e)
        if "Screenshot" in error_msg:
            await msg.edit_text(
                "❌ Ошибка screenshot в browser-use\n\n"
                "Попробуй:\n"
                "1. /install — обновить зависимости\n"
                "2. Или понизь версию: pip install browser-use==0.1.0"
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
    print(f"🧠 browser-use: {'✅' if BROWSER_USE_AVAILABLE else '❌'}")
    print("Команды: /start, /agnes, /install, /browse")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()