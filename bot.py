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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
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

logger.info(f"🔑 TELEGRAM_TOKEN: {'✅ Есть' if TELEGRAM_TOKEN else '❌ НЕТ!'}")
logger.info(f"🔑 AGNES_API_KEY: {'✅ Есть' if AGNES_API_KEY else '❌ НЕТ!'}")

# ПУТЬ К CHROME
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
    """Запуск Chrome с маскировкой"""
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
        
        logger.info("⏳ Ждём запуска Chrome с маскировкой...")
        time.sleep(3)
        
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=5)
            if resp.status_code == 200:
                logger.info("🚀 Chrome успешно запущен с маскировкой")
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
    logger.info(f"📩 Получена команда /start от {update.effective_user.username}")
    try:
        await update.message.reply_text(
            "🤖 Бот для управления браузером\n\n"
            "📌 Команды:\n"
            "/open <url> - открыть страницу\n"
            "/screenshot - скриншот (1280x720)\n"
            "/ask <вопрос> - вопрос по странице\n"
            "/click <селектор> - кликнуть элемент\n"
            "/eval <js> - выполнить JS\n"
            "/tabs - список вкладок\n"
            "/newtab <url> - создать вкладку\n"
            "/closetab - закрыть вкладку\n"
            "/back - назад\n"
            "/forward - вперёд\n"
            "/refresh - обновить\n"
            "/wait <селектор> - ожидать элемент\n"
            "/waittext <текст> - ожидать текст\n"
            "/geo - случайная геолокация\n"
            "/geo <ip> - гео по IP\n"
            "/geoset <lat> <lng> - установить координаты\n"
            "/timezone <зона> - установить таймзону\n"
            "/lang <язык> - установить язык\n"
            "/log - скачать логи\n"
            "/help - эта справка"
        )
        logger.info("✅ Ответ на /start отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Получена команда /log от {update.effective_user.username}")
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

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /open https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        await update.message.reply_text(f"🌐 Открываю: {url}")
        await browser.open_page(url)
        title = await browser.get_page_title()
        await update.message.reply_text(f"✅ Открыто: {title}")
    except Exception as e:
        logger.error(f"❌ Ошибка /open: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Получена команда /screenshot от {update.effective_user.username}")
    await update.message.reply_text("📸 Делаю скриншот...")
    try:
        screenshot_base64 = await browser.screenshot()
        image_bytes = base64.b64decode(screenshot_base64)
        
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(image_bytes), filename="screenshot.png"),
            caption="📸 Скриншот 1280x720"
        )
        logger.info("✅ Скриншот отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Напиши вопрос: /ask что видишь?")
        return
    
    question = ' '.join(context.args)
    await update.message.reply_text("🧠 Думаю...")
    
    try:
        page_text = await browser.get_page_text()
        response = ai.ask(question, page_text)
        await update.message.reply_text(response[:4096])
    except Exception as e:
        logger.error(f"❌ Ошибка /ask: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /click #button")
        return
    
    selector = ' '.join(context.args)
    try:
        result = await browser.click_element(selector)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /click: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def eval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Напиши JS: /eval document.title")
        return
    
    js = ' '.join(context.args)
    try:
        result = await browser.execute_script(js)
        await update.message.reply_text(f"📊 Результат:\n{str(result)[:4000]}")
    except Exception as e:
        logger.error(f"❌ Ошибка /eval: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await browser.list_tabs()
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /tabs: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def newtab_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    try:
        result = await browser.create_tab(url)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /newtab: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def closetab_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await browser.close_tab()
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /closetab: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def back_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await browser.go_back()
        await update.message.reply_text(result if isinstance(result, str) else "⬅️ Назад")
    except Exception as e:
        logger.error(f"❌ Ошибка /back: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def forward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await browser.go_forward()
        await update.message.reply_text(result if isinstance(result, str) else "➡️ Вперёд")
    except Exception as e:
        logger.error(f"❌ Ошибка /forward: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await browser.refresh()
        await update.message.reply_text(result if isinstance(result, str) else "🔄 Обновлено")
    except Exception as e:
        logger.error(f"❌ Ошибка /refresh: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== НОВЫЕ КОМАНДЫ ==========

async def wait_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидание элемента"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /wait #button")
        return
    
    selector = ' '.join(context.args)
    await update.message.reply_text(f"⏳ Жду элемент: {selector}")
    
    try:
        result = await browser.wait_for_selector(selector)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /wait: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def waittext_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидание текста"""
    if not context.args:
        await update.message.reply_text("❌ Укажи текст: /waittext Привет")
        return
    
    text = ' '.join(context.args)
    await update.message.reply_text(f"⏳ Жду текст: {text}")
    
    try:
        result = await browser.wait_for_text(text)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /waittext: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def geo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Геолокация"""
    logger.info(f"📩 Получена команда /geo от {update.effective_user.username}")
    
    try:
        if context.args:
            ip = context.args[0]
            result = await browser.setup_location_by_ip(ip)
            await update.message.reply_text(result)
        else:
            result = await browser.setup_location_by_ip()
            await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /geo: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def geoset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить координаты"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажи координаты: /geoset 55.7558 37.6173")
        return
    
    try:
        lat = float(context.args[0])
        lng = float(context.args[1])
        result = await browser.set_geolocation(lat, lng)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /geoset: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить таймзону"""
    if not context.args:
        await update.message.reply_text("❌ Укажи таймзону: /timezone Europe/London")
        return
    
    timezone = context.args[0]
    try:
        result = await browser.set_timezone(timezone)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /timezone: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить язык"""
    if not context.args:
        await update.message.reply_text("❌ Укажи язык: /lang ru-RU")
        return
    
    lang = context.args[0]
    try:
        result = await browser.set_language(lang)
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"❌ Ошибка /lang: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ОБРАБОТЧИК ТЕКСТА ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"📩 Получен текст: {text[:50]}...")
    try:
        page_text = await browser.get_page_text()
        response = ai.ask(text, page_text)
        await update.message.reply_text(response[:4096])
    except Exception as e:
        logger.error(f"❌ Ошибка handle_message: {e}")
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
        logger.info("✅ Chrome готов к работе")
    else:
        logger.warning("⚠️ Chrome не запустился, проверь установку")
    
    try:
        logger.info("📱 Создаю Telegram приложение...")
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ Telegram приложение создано")
    except Exception as e:
        logger.error(f"❌ Ошибка создания приложения: {e}")
        raise
    
    try:
        logger.info("📝 Регистрирую команды...")
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("log", log_command))
        app.add_handler(CommandHandler("open", open_command))
        app.add_handler(CommandHandler("screenshot", screenshot_command))
        app.add_handler(CommandHandler("ask", ask_command))
        app.add_handler(CommandHandler("click", click_command))
        app.add_handler(CommandHandler("eval", eval_command))
        app.add_handler(CommandHandler("tabs", tabs_command))
        app.add_handler(CommandHandler("newtab", newtab_command))
        app.add_handler(CommandHandler("closetab", closetab_command))
        app.add_handler(CommandHandler("back", back_command))
        app.add_handler(CommandHandler("forward", forward_command))
        app.add_handler(CommandHandler("refresh", refresh_command))
        app.add_handler(CommandHandler("wait", wait_command))
        app.add_handler(CommandHandler("waittext", waittext_command))
        app.add_handler(CommandHandler("geo", geo_command))
        app.add_handler(CommandHandler("geoset", geoset_command))
        app.add_handler(CommandHandler("timezone", timezone_command))
        app.add_handler(CommandHandler("lang", lang_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logger.info("✅ Команды зарегистрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации команд: {e}")
        raise
    
    logger.info("🚀 Бот запущен! Ожидаю сообщения...")
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