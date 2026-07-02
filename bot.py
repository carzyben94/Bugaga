import asyncio
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from cdp_use import CDP
import requests

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Глобальный экземпляр браузера
browser = None
cdp = None

async def init_browser():
    """Инициализация браузера через cdp-use"""
    global browser, cdp
    
    try:
        # Запускаем браузер
        browser = await CDP.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']  # Важно для Railway
        )
        
        # Создаём новую вкладку
        cdp = await browser.new_page()
        
        logger.info("✅ Браузер успешно запущен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🤖 Привет! Я бот с браузером.\n\n"
        "Доступные команды:\n"
        "/screenshot <url> - сделать скриншот страницы\n"
        "/html <url> - получить HTML код страницы\n"
        "/status - проверить статус браузера"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - проверка статуса"""
    if cdp and browser:
        await update.message.reply_text("✅ Браузер работает")
    else:
        await update.message.reply_text("❌ Браузер не инициализирован")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /screenshot <url>"""
    if not context.args:
        await update.message.reply_text("⚠️ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        # Переходим по URL
        await cdp.goto(url, wait_until='networkidle')
        
        # Делаем скриншот
        screenshot_data = await cdp.screenshot(full_page=True)
        
        # Отправляем фото
        await update.message.reply_photo(
            photo=screenshot_data,
            caption=f"Скриншот: {url}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /html <url> - получить HTML"""
    if not context.args:
        await update.message.reply_text("⚠️ Укажите URL: /html https://example.com")
        return
    
    url = context.args[0]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        await cdp.goto(url, wait_until='networkidle')
        
        # Получаем HTML
        html_content = await cdp.content()
        
        # Обрезаем если слишком длинный
        if len(html_content) > 4000:
            html_content = html_content[:4000] + "\n... (обрезано)"
        
        await update.message.reply_text(
            f"📄 HTML страницы {url}:\n\n```html\n{html_content}\n```",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def post_init(application: Application):
    """Инициализация при запуске бота"""
    logger.info("🚀 Запуск браузера...")
    success = await init_browser()
    
    if not success:
        logger.error("❌ Не удалось запустить браузер")

def main():
    """Основная функция"""
    if not TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в .env")
    
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("html", html))
    
    # Запускаем инициализацию браузера после старта
    app.post_init = post_init
    
    # Запуск бота
    logger.info("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()