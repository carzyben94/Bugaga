import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from browser import cdp_client

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "📸 /screenshot - Сделать скриншот X.com\n"
        "❓ /help - Помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📋 Доступные команды:\n\n"
        "/start - Приветствие\n"
        "/help - Справка\n"
        "/screenshot - Сделать скриншот X.com\n"
        "/status - Статус браузера"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status"""
    status_text = "✅ Бот работает!\n"
    
    # Проверяем состояние браузера
    if cdp_client.ws:
        status_text += "✅ Браузер запущен\n"
        status_text += f"🔗 CDP: {cdp_client.ws_url}\n"
    else:
        status_text += "❌ Браузер не запущен\n"
    
    await update.message.reply_text(status_text)

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screenshot"""
    await update.message.reply_text("📸 Запускаю браузер и делаю скриншот X.com...")
    
    try:
        # Запускаем браузер если не запущен
        if not cdp_client.ws:
            await cdp_client.connect_cdp()
        
        # Делаем скриншот
        screenshot_b64 = await cdp_client.take_screenshot()
        
        # Отправляем в чат
        await update.message.reply_photo(
            photo=screenshot_b64,
            caption="📸 X.com"
        )
        
        logger.info(f"✅ Скриншот отправлен пользователю {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}\n\n"
            "Попробуй позже или /status для проверки."
        )

async def screenshot_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screenshot_full - скриншот всей страницы"""
    await update.message.reply_text("📸 Делаю полный скриншот страницы...")
    
    try:
        # Запускаем браузер если не запущен
        if not cdp_client.ws:
            await cdp_client.connect_cdp()
        
        # Делаем скриншот всей страницы
        screenshot_b64 = await cdp_client.take_screenshot(
            width=1280,
            height=720,
            full_page=True
        )
        
        # Отправляем в чат
        await update.message.reply_photo(
            photo=screenshot_b64,
            caption="📸 Полный скриншот X.com"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании полного скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot_jpeg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screenshot_jpeg - скриншот в JPEG"""
    await update.message.reply_text("📸 Делаю скриншот в формате JPEG...")
    
    try:
        # Запускаем браузер если не запущен
        if not cdp_client.ws:
            await cdp_client.connect_cdp()
        
        # Делаем скриншот в JPEG
        screenshot_b64 = await cdp_client.take_screenshot(
            format="jpeg",
            quality=80
        )
        
        # Отправляем в чат
        await update.message.reply_photo(
            photo=screenshot_b64,
            caption="📸 X.com (JPEG, качество 80%)"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании JPEG скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /shutdown - закрыть браузер"""
    await update.message.reply_text("🔄 Закрываю браузер...")
    
    try:
        await cdp_client.close()
        await update.message.reply_text("✅ Браузер закрыт")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def post_init(application: Application):
    """Запуск браузера при старте бота"""
    logger.info("🚀 Запуск браузера при старте бота...")
    try:
        await cdp_client.connect_cdp()
        logger.info("✅ Браузер успешно запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")

def main():
    """Запуск бота"""
    logger.info("Запуск бота...")
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("screenshot_full", screenshot_full))
    app.add_handler(CommandHandler("screenshot_jpeg", screenshot_jpeg))
    app.add_handler(CommandHandler("shutdown", shutdown))
    
    # Запускаем браузер при старте
    app.post_init = post_init
    
    # Запускаем поллинг
    logger.info("Бот запущен, ожидаем сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()