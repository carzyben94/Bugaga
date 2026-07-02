import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from phantomwright import Phantomwright
from phantomwright.driver import Driver

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Инициализация Phantomwright
pw = Phantomwright()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с Phantomwright на Railway.\n"
        "Отправь URL, и я сделаю скриншот страницы!\n"
        "Пример: https://example.com"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/screenshot <url> - Сделать скриншот\n"
        "/info - Информация о боте\n"
        "Или просто отправь URL"
    )

# Команда /screenshot
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await take_screenshot(update, url)

# Функция создания скриншота
async def take_screenshot(update: Update, url: str):
    try:
        await update.message.reply_text("📸 Делаю скриншот...")
        
        # Запускаем браузер
        async with pw.start() as app:
            driver = Driver(app)
            
            # Открываем страницу
            page = await driver.new_page()
            await page.goto(url, wait_until="networkidle")
            
            # Делаем скриншот
            screenshot = await page.screenshot()
            
            # Отправляем фото
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ Скриншот {url}"
            )
            
    except Exception as e:
        logger.error(f"Ошибка при создании скриншота: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)[:200]}\n"
            "Проверьте URL и попробуйте снова."
        )

# Обработка текстовых сообщений (URL)
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Проверяем, является ли сообщение URL
    if text.startswith(('http://', 'https://')):
        await take_screenshot(update, text)
    else:
        await update.message.reply_text(
            "Отправьте URL (начинается с http:// или https://)\n"
            "Или используйте команду /screenshot <url>"
        )

# Команда /info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Бот с Phantomwright\n"
        f"Ваш ID: {update.effective_user.id}\n"
        f"Имя: {update.effective_user.first_name}\n"
        f"Версия Phantomwright: 1.58.3"
    )

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже."
        )

def main():
    app = Application.builder().token(TOKEN).build()

    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("info", info))
    
    # Обработчик текста (для URL)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    app.add_error_handler(error_handler)

    # Запуск через polling (проще для Railway)
    logger.info("Бот запущен с Phantomwright 1.58.3")
    app.run_polling()

if __name__ == "__main__":
    main()