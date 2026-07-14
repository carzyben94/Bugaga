import os
import asyncio
import subprocess
import logging
import time
import requests
import sys
import io
import base64
import re
import json
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from browser import BrowserManager
from ai import AgnesAI

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
LOG_FILE = 'bot.log'

if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ========== КОНФИГ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.getenv("AI_MODEL", "agnes-2.0-flash")

logger.info(f"🔑 TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN else '❌'}")
logger.info(f"🔑 AGNES_API_KEY: {'✅' if AGNES_API_KEY else '❌'}")

CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")

if not os.path.exists(CHROME_PATH):
    if os.path.exists("/usr/bin/google-chrome"):
        CHROME_PATH = "/usr/bin/google-chrome"
    elif os.path.exists("/usr/bin/chromium-browser"):
        CHROME_PATH = "/usr/bin/chromium-browser"
    elif os.path.exists("/usr/bin/chromium"):
        CHROME_PATH = "/usr/bin/chromium"
    elif os.path.exists("C:/Program Files/Google/Chrome/Application/chrome.exe"):
        CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    elif os.path.exists("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"):
        CHROME_PATH = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"
    elif os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

logger.info(f"📂 Путь к Chrome: {CHROME_PATH}")

# ========== ЗАПУСК CHROME ==========
def start_chrome():
    try:
        temp_browser = BrowserManager()
        
        if not os.path.exists(CHROME_PATH):
            logger.warning(f"⚠️ Chrome не найден по пути: {CHROME_PATH}")
            chrome_cmd = "google-chrome"
        else:
            chrome_cmd = CHROME_PATH
        
        args = temp_browser.get_launch_args(chrome_cmd)
        
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        logger.info("⏳ Ждём запуска Chrome...")
        time.sleep(3)
        
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=5)
            if resp.status_code == 200:
                logger.info("🚀 Chrome запущен")
                return True
        except Exception as e:
            logger.error(f"❌ CDP не отвечает: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Chrome: {e}")
        return False

# ========== ИНИЦИАЛИЗАЦИЯ ==========
try:
    browser = BrowserManager()
    logger.info("✅ BrowserManager создан")
except Exception as e:
    logger.error(f"❌ Ошибка создания BrowserManager: {e}")
    browser = None

try:
    ai = AgnesAI()
    logger.info("✅ AgnesAI создан")
except Exception as e:
    logger.error(f"❌ Ошибка создания AgnesAI: {e}")
    ai = None

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /start от {update.effective_user.username}")
    try:
        await update.message.reply_text(
            "🤖 Бот для управления браузером\n\n"
            "Просто напиши что хочешь сделать в чат.\n\n"
            "📌 Примеры:\n"
            "• открой google.com\n"
            "• сделай скриншот\n"
            "• нажми на кнопку войти\n"
            "• введи test@gmail.com в поле email\n"
            "• какие кнопки есть на странице?\n"
            "• что здесь написано?\n"
            "• подожди загрузки\n\n"
            "Я сам пойму что тебе нужно! 🧠"
        )
        logger.info("✅ Ответ на /start отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /log от {update.effective_user.username}")
    try:
        log_content = ""
        
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                log_content = f.read()
        else:
            log_content = "⚠️ Лог-файл не найден\n"
        
        system_info = f"""
{'='*50}
📊 Системная информация:
Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Chrome путь: {CHROME_PATH}
Chrome существует: {os.path.exists(CHROME_PATH)}
CDP порт: 9222
"""
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=3)
            system_info += f"CDP статус: ✅ Работает ({resp.status_code})\n"
        except Exception as e:
            system_info += f"CDP статус: ❌ Не отвечает ({str(e)[:50]})\n"
        
        try:
            resp = requests.get("http://localhost:9222/json/list", timeout=3)
            pages = resp.json()
            system_info += f"Открытых вкладок: {len(pages)}\n"
        except Exception as e:
            system_info += f"Вкладки: ❌ Не удалось получить\n"
        
        full_log = log_content + system_info
        
        await update.message.reply_document(
            document=io.BytesIO(full_log.encode('utf-8')),
            filename=f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            caption="📋 Полные логи бота"
        )
        logger.info("✅ Логи отправлены")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /log: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"📩 {text[:50]}...")
    
    try:
        if text.lower().startswith('/log'):
            await log_command(update, context)
            return
        
        if text.lower().startswith('/start'):
            await start(update, context)
            return
        
        text_lower = text.lower()
        
        # 1. ОТКРЫТИЕ СТРАНИЦЫ
        if any(word in text_lower for word in ['открой', 'перейди', 'зайди', 'открыть', 'перейти']) and \
           any(ext in text for ext in ['.com', '.ru', '.org', '.net', '.io', 'http']):
            urls = re.findall(r'(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?', text)
            if urls:
                url = urls[0]
                if not url.startswith('http'):
                    url = 'https://' + url
                await update.message.reply_text(f"🌐 Открываю: {url}")
                await browser.open_page(url)
                title = await browser.get_page_title()
                await update.message.reply_text(f"✅ Открыто: {title}")
                return
        
        # 2. СКРИНШОТ
        if any(word in text_lower for word in ['скриншот', 'скрин', 'сфоткай', 'фото страницы']):
            await update.message.reply_text("📸 Делаю скриншот...")
            try:
                screenshot_base64 = await browser.screenshot()
                image_bytes = base64.b64decode(screenshot_base64)
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_bytes), filename="screenshot.png"),
                    caption="📸 Скриншот 1280x720"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
        
        # 3. ОСТАЛЬНОЕ — ЧЕРЕЗ AI
        await update.message.reply_text(f"🧠 Думаю...")
        result = await browser.ai_agent(text)
        await update.message.reply_text(result[:4096])
        
    except Exception as e:
        logger.error(f"❌ {str(e)[:200]}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========

def main():
    logger.info("🚀 ЗАПУСК БОТА")
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан!")
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")
    
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан! AI функции не будут работать")
    
    if start_chrome():
        logger.info("✅ Chrome готов")
    else:
        logger.warning("⚠️ Chrome не запустился")
    
    try:
        logger.info("📱 Создаю приложение...")
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ Приложение создано")
    except Exception as e:
        logger.error(f"❌ Ошибка создания приложения: {e}")
        raise
    
    try:
        logger.info("📝 Регистрирую команды...")
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("log", log_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logger.info("✅ Команды зарегистрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации команд: {e}")
        raise
    
    logger.info("🚀 Бот запущен!")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске polling: {e}")
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)