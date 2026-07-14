import os
import asyncio
import subprocess
import logging
import time
import requests
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from browser import BrowserManager
from ai import AgnesAI

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(sys.stdout)
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

# Альтернативные пути для разных ОС
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
    """Запуск Chrome с CDP"""
    try:
        if not os.path.exists(CHROME_PATH):
            logger.warning(f"⚠️ Chrome не найден по пути: {CHROME_PATH}")
            logger.warning("⚠️ Пробую 'google-chrome' из PATH")
            chrome_cmd = "google-chrome"
        else:
            chrome_cmd = CHROME_PATH
            logger.info(f"✅ Chrome найден: {CHROME_PATH}")
        
        subprocess.Popen([
            chrome_cmd,
            '--headless=new',
            '--remote-debugging-port=9222',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-setuid-sandbox',
            '--user-data-dir=/tmp/chrome-profile'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info("⏳ Ждём запуска Chrome...")
        time.sleep(3)
        
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=5)
            if resp.status_code == 200:
                logger.info("🚀 Chrome успешно запущен с CDP")
                return True
        except Exception as e:
            logger.error(f"❌ CDP не отвечает: {e}")
        
        logger.warning("⚠️ Chrome запущен, но CDP не отвечает")
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
    """Команда /start"""
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
            "/help - эта справка"
        )
        logger.info("✅ Ответ на /start отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    logger.info(f"📩 Получена команда /help от {update.effective_user.username}")
    try:
        await start(update, context)
    except Exception as e:
        logger.error(f"❌ Ошибка в /help: {e}")

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открыть URL"""
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
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот"""
    await update.message.reply_text("📸 Делаю скриншот...")
    try:
        screenshot = await browser.screenshot()
        await update.message.reply_photo(
            screenshot,
            caption="📸 Скриншот 1280x720"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Задать вопрос AI"""
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
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кликнуть по элементу"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /click #button")
        return
    
    selector = ' '.join(context.args)
    try:
        result = await browser.click_element(selector)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def eval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить JavaScript"""
    if not context.args:
        await update.message.reply_text("❌ Напиши JS: /eval document.title")
        return
    
    js = ' '.join(context.args)
    try:
        result = await browser.execute_script(js)
        await update.message.reply_text(f"📊 Результат:\n{str(result)[:4000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список вкладок"""
    try:
        result = await browser.list_tabs()
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def newtab_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новую вкладку"""
    url = context.args[0] if context.args else ""
    try:
        result = await browser.create_tab(url)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def closetab_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть текущую вкладку"""
    try:
        result = await browser.close_tab()
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def back_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад в истории"""
    try:
        await browser.go_back()
        await update.message.reply_text("⬅️ Назад")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def forward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вперёд в истории"""
    try:
        await browser.go_forward()
        await update.message.reply_text("➡️ Вперёд")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновить страницу"""
    try:
        await browser.refresh()
        await update.message.reply_text("🔄 Обновлено")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ОБРАБОТЧИК ТЕКСТА ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (AI)"""
    text = update.message.text
    logger.info(f"📩 Получен текст: {text[:50]}...")
    try:
        page_text = await browser.get_page_text()
        response = ai.ask(text, page_text)
        await update.message.reply_text(response[:4096])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========

def main():
    """Главная функция"""
    logger.info("🚀 ЗАПУСК БОТА")
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан!")
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")
    
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан! AI функции не будут работать")
    
    # Запускаем Chrome
    if start_chrome():
        logger.info("✅ Chrome готов к работе")
    else:
        logger.warning("⚠️ Chrome не запустился, проверь установку")
    
    # Создаём приложение
    try:
        logger.info("📱 Создаю Telegram приложение...")
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ Telegram приложение создано")
    except Exception as e:
        logger.error(f"❌ Ошибка создания приложения: {e}")
        raise
    
    # Регистрируем команды
    try:
        logger.info("📝 Регистрирую команды...")
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
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
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logger.info("✅ Команды зарегистрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации команд: {e}")
        raise
    
    # Запуск
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