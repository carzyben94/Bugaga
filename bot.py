import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Импорт Phantomwright с правильным путем
try:
    from phantomwright import Phantomwright
    from phantomwright.driver import Driver
    logger.info("✅ Phantomwright импортирован успешно")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта Phantomwright: {e}")
    Phantomwright = None
    Driver = None

# Глобальная переменная для Phantomwright
pw = None

# Функция инициализации Phantomwright
def init_phantomwright():
    global pw
    try:
        if Phantomwright:
            pw = Phantomwright()
            logger.info("✅ Phantomwright инициализирован успешно")
            return True
        else:
            logger.error("❌ Phantomwright не доступен")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Phantomwright: {e}")
        pw = None
        return False

# Инициализируем при старте
init_phantomwright()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот на Railway.\n\n"
        "📸 Отправь URL для скриншота\n"
        "Пример: https://google.com\n\n"
        "Команды:\n"
        "/help - Справка\n"
        "/status - Статус бота\n"
        "/screenshot <url> - Скриншот"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Команды:\n"
        "/start - Приветствие\n"
        "/help - Справка\n"
        "/status - Статус Phantomwright\n"
        "/screenshot <url> - Скриншот\n"
        "/restart - Переинициализировать Phantomwright\n\n"
        "Или просто отправь URL"
    )

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pw
    
    status_text = "🤖 Статус бота:\n"
    status_text += "✅ Бот работает\n"
    
    if pw:
        status_text += "✅ Phantomwright инициализирован\n"
    else:
        status_text += "❌ Phantomwright НЕ инициализирован\n"
        status_text += "\n🔄 Попробуйте /restart для перезапуска"
    
    await update.message.reply_text(status_text)

# Команда /restart - перезапуск Phantomwright
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pw
    
    await update.message.reply_text("🔄 Переинициализация Phantomwright...")
    
    # Очищаем старый экземпляр
    pw = None
    
    # Создаем новый
    if init_phantomwright():
        await update.message.reply_text("✅ Phantomwright переинициализирован успешно!")
    else:
        await update.message.reply_text("❌ Не удалось переинициализировать Phantomwright")

# Команда /screenshot
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pw
    
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /screenshot https://google.com")
        return
    
    url = context.args[0]
    
    # Проверяем URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await take_screenshot(update, url)

# Функция скриншота
async def take_screenshot(update: Update, url: str):
    global pw
    
    # Проверяем инициализацию
    if not pw:
        # Пытаемся переинициализировать
        if not init_phantomwright():
            await update.message.reply_text(
                "❌ Phantomwright не инициализирован.\n"
                "Попробуйте команду /restart"
            )
            return
    
    try:
        msg = await update.message.reply_text("📸 Делаю скриншот...")
        
        # Запускаем браузер
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
            
            # Переходим по URL
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Даем время на загрузку
            await asyncio.sleep(2)
            
            # Делаем скриншот
            screenshot = await page.screenshot(full_page=True)
            
            # Отправляем
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ Скриншот: {url[:50]}..."
            )
            
            # Удаляем сообщение "Делаю скриншот..."
            await msg.delete()
            
            logger.info(f"✅ Скриншот сделан для {url}")
            
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Превышено время загрузки страницы")
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)[:150]}\n"
            "Попробуйте другой URL или /restart"
        )

# Обработка текста
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Добавляем https если нет
    if text.startswith(('http://', 'https://')):
        await take_screenshot(update, text)
    elif '.' in text and ' ' not in text:
        # Возможно это домен без протокола
        await take_screenshot(update, 'https://' + text)
    else:
        await update.message.reply_text(
            "Отправьте URL (например: google.com или https://example.com)\n"
            "Или используйте /help"
        )

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте /restart"
            )
        except:
            pass

def main():
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    try:
        app = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("screenshot", screenshot_command))
        app.add_handler(CommandHandler("restart", restart_command))
        
        # Обработчик текста
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        app.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен успешно!")
        logger.info(f"📊 Phantomwright статус: {'✅' if pw else '❌'}")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()