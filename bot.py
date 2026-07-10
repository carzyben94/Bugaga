import asyncio
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

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
    # Создаем объект настроек ChromiumOptions
    options = ChromiumOptions()
    
    # Указываем путь к бинарному файлу Google Chrome
    options.binary_location = CHROME_PATH
    
    # Добавляем аргументы для работы в Docker/Railway
    options.add_argument('--headless=new')           # Запуск в фоновом режиме
    options.add_argument('--no-sandbox')             # Обход ограничений в контейнере
    options.add_argument('--disable-dev-shm-usage')  # Обход проблем с памятью в Docker
    options.add_argument('--disable-gpu')            # Отключаем GPU (не нужно в headless)
    options.add_argument('--disable-blink-features=AutomationControlled')  # Скрываем автоматизацию
    
    # Увеличиваем таймаут для надежности (по умолчанию 10 секунд)
    options.start_timeout = 30
    
    # Логируем настройки
    logger.info(f"Запуск браузера по пути: {CHROME_PATH}")
    logger.info("Аргументы: --headless=new, --no-sandbox, --disable-dev-shm-usage, --disable-gpu")
    
    # Создаем экземпляр браузера с настройками
    browser = Chrome(options=options)
    
    # Используем контекстный менеджер для автоматического управления
    async with browser:
        # Запускаем браузер и получаем вкладку
        tab = await browser.start()
        
        logger.info("✅ Браузер успешно запущен!")
        
        # Переходим на сайт
        await tab.go_to("https://example.com")
        
        # Получаем заголовок страницы
        title = await tab.title
        logger.info(f"Заголовок страницы: {title}")
        
        # Получаем текущий URL через метод get_url() или свойство
        # В документации pydoll используется метод или свойство
        try:
            # Пробуем получить URL через свойство url
            current_url = await tab.url
            logger.info(f"Текущий URL: {current_url}")
        except AttributeError:
            # Если свойства url нет, пробуем через метод get_url()
            try:
                current_url = await tab.get_url()
                logger.info(f"Текущий URL: {current_url}")
            except AttributeError:
                # Если и метода нет, просто пропускаем
                logger.warning("Метод получения URL не найден, пропускаем")
        
        return title

# --- КОНЕЦ БЛОКА РАБОТЫ С БРАУЗЕРОМ ---

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()

        # Регистрируем команду /start
        application.add_handler(CommandHandler("start", start))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info(f"📁 Используемый браузер: {CHROME_PATH}")
        logger.info("ℹ️ Ожидаю команды...")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()