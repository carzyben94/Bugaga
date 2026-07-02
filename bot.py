import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Правильный импорт для Phantomwright
try:
    from phantomwright import Phantomwright
    from phantomwright.driver import Driver
except ImportError as e:
    logging.error(f"Ошибка импорта Phantomwright: {e}")
    Phantomwright = None
    Driver = None

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Инициализация Phantomwright с обработкой ошибок
pw = None
if Phantomwright:
    try:
        pw = Phantomwright()
        logger.info("Phantomwright инициализирован")
    except Exception as e:
        logger.error(f"Ошибка инициализации Phantomwright: {e}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот на Railway с Phantomwright.\n\n"
        "📸 Отправь URL, и я сделаю скриншот!\n"
        "Пример: https://example.com\n\n"
        "Команды:\n"
        "/help - Справка\n"
        "/status - Статус бота"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/status - Статус Phantomwright\n"
        "/screenshot <url> - Сделать скриншот\n\n"
        "Или просто отправь URL и получи скриншот"
    )

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = "✅ Бот работает\n"
    if pw:
        status_text += "✅ Phantomwright доступен\n"
    else:
        status_text += "❌ Phantomwright НЕ доступен\n"
    
    await update.message.reply_text(status_text)

# Команда /screenshot
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await take_screenshot(update, url)

# Функция создания скриншота
async def take_screenshot(update: Update, url: str):
    if not pw:
        await update.message.reply_text(
            "❌ Phantomwright не инициализирован. Проверьте логи."
        )
        return
    
    try:
        await update.message.reply_text("📸 Делаю скриншот... Подождите немного.")
        
        # Запускаем браузер с правильными параметрами для Railway
        async with pw.start(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080'
            ]
        ) as app:
            driver = Driver(app)
            page = await driver.new_page()
            
            # Устанавливаем таймаут
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Делаем скриншот
            screenshot = await page.screenshot(full_page=True)
            
            # Отправляем фото
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ Скриншот: {url[:50]}..."
            )
            
            logger.info(f"Скриншот сделан для {url}")
            
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Превышено время ожидания загрузки страницы.")
    except Exception as e:
        logger.error(f"Ошибка при создании скриншота: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)[:200]}\n"
            "Проверьте URL и попробуйте снова."
        )

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Проверяем URL
    if text.startswith(('http://', 'https://')):
        await take_screenshot(update, text)
    else:
        await update.message.reply_text(
            "Отправьте URL (начинается с http:// или https://)\n"
            "Или используйте команду /help для справки."
        )

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже."
            )
        except:
            pass

def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    try:
        # Создаем приложение
        app = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("screenshot", screenshot_command))
        
        # Обработчик текста
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        app.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен с Phantomwright 1.58.3")
        
        # Запуск через polling
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")
        raise

if __name__ == "__main__":
    main()