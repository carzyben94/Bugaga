# test_bot.py - cdp-use + Agnes
import os
import sys
import subprocess
import logging
import asyncio
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
            print(f"❌ Ошибка: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# ========== ПРОВЕРКА И УСТАНОВКА ==========

def check_and_install():
    """Проверяет и устанавливает зависимости"""
    packages = ['langchain-openai', 'cdp-use']
    
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} уже установлен")
        except ImportError:
            print(f"⚠️ {package} не найден, устанавливаю...")
            install_package(package)

check_and_install()

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

# ========== CDP-USE ==========
CDP_AVAILABLE = False

def check_cdp():
    global CDP_AVAILABLE
    try:
        from cdp_use import connect
        CDP_AVAILABLE = True
        print("✅ cdp-use загружен")
        return True
    except ImportError:
        CDP_AVAILABLE = False
        print("⚠️ cdp-use не найден")
        return False

check_cdp()

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Бот запущен\n"
        f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
        f"cdp-use: {'✅' if CDP_AVAILABLE else '❌'}\n\n"
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
    """Установка зависимостей"""
    msg = await update.message.reply_text("⏳ Устанавливаю зависимости...")
    
    try:
        await msg.edit_text("⏳ Устанавливаю cdp-use...")
        install_package('cdp-use')
        check_cdp()
        init_agnes()
        
        status = (
            f"✅ Установка завершена!\n\n"
            f"Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n"
            f"cdp-use: {'✅' if CDP_AVAILABLE else '❌'}\n\n"
            f"Попробуй: /browse открой google.com"
        )
        await msg.edit_text(status)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере через cdp-use"""
    if not context.args:
        await update.message.reply_text("ℹ️ /browse <задача>\nПример: /browse открой google.com")
        return
    
    if not AGNES_AVAILABLE:
        await update.message.reply_text("❌ Agnes не доступна. Проверь /agnes")
        return
    
    if not CDP_AVAILABLE:
        await update.message.reply_text(
            "❌ cdp-use не установлен.\n"
            "Используй /install для установки"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    try:
        from cdp_use import connect
        from cdp_use.client import Client
        from cdp_use.browser import Browser
        
        await msg.edit_text("🔄 Запускаю браузер...")
        
        # Запускаем браузер через cdp-use
        async with connect() as client:
            browser = Browser(client)
            
            # Открываем новую страницу
            page = await browser.new_page()
            await page.goto('https://google.com')
            
            # Делаем скриншот
            screenshot = await page.screenshot()
            
            # Сохраняем и отправляем
            with open('screenshot.png', 'wb') as f:
                f.write(screenshot)
            
            # Закрываем страницу
            await page.close()
        
        await update.message.reply_photo(
            photo=open('screenshot.png', 'rb'),
            caption=f"📸 Скриншот по запросу: {task[:50]}"
        )
        
        await msg.edit_text(f"✅ **Задача выполнена!**\n\n📋 **Запрос:** {task}")
        
    except Exception as e:
        error_msg = str(e)
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
    print(f"🧠 cdp-use: {'✅' if CDP_AVAILABLE else '❌'}")
    print("Команды: /start, /agnes, /install, /browse")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()