import asyncio
import logging
import os
import base64
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

# Глобальная переменная для хранения экземпляра браузера
browser_instance = None
tab_instance = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def normalize_url(url: str) -> str:
    """Добавляет https:// если протокол не указан"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БРАУЗЕРОМ ---

def get_browser_options():
    """Создает и возвращает настроенный объект ChromiumOptions"""
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    """Открывает браузер и создает новую вкладку"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер успешно открыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже открыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при открытии браузера: {e}")
        return False

async def close_browser():
    """Закрывает браузер"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер успешно закрыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже закрыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии браузера: {e}")
        return False

async def take_screenshot():
    """Делает скриншот всей страницы"""
    global tab_instance
    
    try:
        if tab_instance is None:
            return None, "❌ Браузер не открыт. Используйте /open_bw"
        
        # Делаем скриншот всей страницы через правильный метод take_screenshot
        screenshot_data = await tab_instance.take_screenshot(
            beyond_viewport=True,  # Вся страница
            as_base64=True         # Возвращаем в формате base64
        )
        
        logger.info("📸 Скриншот всей страницы сделан")
        return screenshot_data, None
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        return None, str(e)

# --- КОМАНДЫ БОТА ---

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд"""
    await update.message.reply_text(
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/screen - Скриншот всей страницы\n"
        "/go <URL> - Перейти на сайт"
    )

# Команда /open_bw
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает браузер"""
    await update.message.reply_text("🌐 Открываю браузер...")
    
    success = await open_browser()
    if success:
        await update.message.reply_text("✅ Браузер успешно открыт!")
    else:
        await update.message.reply_text("❌ Не удалось открыть браузер. Проверьте логи.")

# Команда /close_bw
async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    await update.message.reply_text("❌ Закрываю браузер...")
    
    success = await close_browser()
    if success:
        await update.message.reply_text("✅ Браузер успешно закрыт!")
    else:
        await update.message.reply_text("❌ Не удалось закрыть браузер. Проверьте логи.")

# Команда /screen
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот всей страницы"""
    await update.message.reply_text("📸 Делаю скриншот всей страницы...")
    
    screenshot_data, error = await take_screenshot()
    
    if error:
        await update.message.reply_text(f"❌ {error}")
    elif screenshot_data:
        try:
            if isinstance(screenshot_data, str):
                screenshot_bytes = base64.b64decode(screenshot_data)
            else:
                screenshot_bytes = screenshot_data
            
            await update.message.reply_photo(
                screenshot_bytes,
                caption="📸 Скриншот всей страницы"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке скриншота: {e}")
            await update.message.reply_text(f"❌ Ошибка при отправке скриншота: {str(e)}")
    else:
        await update.message.reply_text("❌ Не удалось сделать скриншот")

# Команда /go
async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переходит на указанный URL"""
    global tab_instance
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL.\n"
            "Пример: /go https://example.com"
        )
        return
    
    # Нормализуем URL - добавляем https:// если нужно
    url = normalize_url(context.args[0])
    
    await update.message.reply_text(f"🔗 Перехожу на {url}...")
    
    try:
        if tab_instance is None:
            await update.message.reply_text("❌ Браузер не открыт. Используйте /open_bw")
            return
        
        await tab_instance.go_to(url)
        title = await tab_instance.title
        await update.message.reply_text(f"✅ Перешел на {url}\n📄 Заголовок: {title}")
    except Exception as e:
        logger.error(f"Ошибка при переходе: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ---

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info(f"📁 Используемый браузер: {CHROME_PATH}")
        logger.info("ℹ️ Доступные команды: /start, /open_bw, /close_bw, /screen, /go")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()