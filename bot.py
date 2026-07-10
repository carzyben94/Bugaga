import asyncio
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser import Chrome

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Путь к браузеру Google Chrome
CHROME_PATH = "/usr/bin/google-chrome"

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот на Railway.\n"
        "🚀 Запускаю браузер Google Chrome..."
    )

    try:
        # Запускаем асинхронную задачу с Pydoll
        result = await open_browser_and_fetch()
        await update.message.reply_text(f"✅ Готово! Заголовок страницы: {result}")
    except Exception as e:
        logger.error(f"Ошибка при работе браузера: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

# --- БЛОК РАБОТЫ С БРАУЗЕРОМ (по документации pydoll) ---

async def open_browser_and_fetch():
    """
    Запускает Google Chrome, переходит на сайт и возвращает заголовок страницы.
    Используется контекстный менеджер для автоматического запуска и остановки.
    """
    # Создаем экземпляр Chrome с явным указанием пути
    # В документации pydoll: Chrome(browser_path="/путь/к/chrome")
    browser = Chrome(browser_path=CHROME_PATH)
    
    # Используем контекстный менеджер для автоматического управления
    async with browser:
        # Получаем объект вкладки
        tab = await browser.start()
        
        # Логируем успешный запуск
        logger.info(f"Браузер запущен по пути: {CHROME_PATH}")
        
        # Переходим на сайт
        await tab.go_to("https://example.com")
        
        # Получаем заголовок страницы
        title = await tab.title
        logger.info(f"Заголовок страницы: {title}")
        
        # Можно также получить URL
        current_url = await tab.url
        logger.info(f"Текущий URL: {current_url}")
        
        return title

# --- КОНЕЦ БЛОКА РАБОТЫ С БРАУЗЕРОМ ---

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен!")
    logger.info(f"Используемый браузер: {CHROME_PATH}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()