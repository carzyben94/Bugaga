import os
import logging
import base64
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт браузера с обработкой ошибок
try:
    from browser import cdp_client
    BROWSER_AVAILABLE = True
except ImportError as e:
    BROWSER_AVAILABLE = False
    print(f"⚠️ Браузер не доступен: {e}")

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
        "🌐 /browser <url> - Открыть сайт\n"
        "📸 /screen - Сделать скриншот\n"
        "🔒 /close - Закрыть браузер"
    )

async def browser_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /browser - запуск браузера и переход по URL"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    # Получаем URL из аргументов
    url = context.args[0] if context.args else None
    
    if not url:
        await update.message.reply_text(
            "❌ Укажи URL.\n\n"
            "Пример: /browser https://x.com"
        )
        return
    
    # Добавляем https:// если нет протокола
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    await update.message.reply_text(f"🌐 Открываю {url}...")
    
    try:
        # Проверяем, запущен ли браузер
        if not cdp_client.ws:
            # Запускаем браузер (куки установятся автоматически)
            await cdp_client.connect_cdp(navigate_to_x=False)
        
        # Переходим по URL
        await cdp_client.navigate_to(url)
        
        await update.message.reply_text(f"✅ Страница загружена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screen - скриншот"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        # Проверяем, запущен ли браузер
        if not cdp_client.ws:
            await update.message.reply_text("⚠️ Браузер не запущен. Используй /browser <url>")
            return
        
        # Делаем скриншот
        screenshot_b64 = await cdp_client.take_screenshot()
        
        # Декодируем base64 в байты
        screenshot_bytes = base64.b64decode(screenshot_b64)
        
        # Создаем BytesIO объект
        photo_file = io.BytesIO(screenshot_bytes)
        photo_file.name = "screenshot.png"
        
        # Отправляем в чат
        await update.message.reply_photo(
            photo=photo_file,
            caption="📸 Скриншот"
        )
        
        logger.info(f"✅ Скриншот отправлен пользователю {update.effective_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def browser_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /close - закрыть браузер"""
    if not BROWSER_AVAILABLE:
        await update.message.reply_text("❌ Модуль браузера недоступен")
        return
    
    await update.message.reply_text("🔒 Закрываю браузер...")
    
    try:
        await cdp_client.close()
        await update.message.reply_text("✅ Браузер закрыт")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def post_init(application: Application):
    """Запуск браузера при старте бота с куками"""
    if not BROWSER_AVAILABLE:
        logger.warning("⚠️ Браузер недоступен, пропускаем запуск")
        return
    
    logger.info("🚀 Запуск браузера при старте бота...")
    try:
        # Запускаем браузер и сразу устанавливаем куки
        await cdp_client.connect_cdp(navigate_to_x=False)
        logger.info("✅ Браузер успешно запущен, куки установлены")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")

def main():
    """Запуск бота"""
    logger.info("Запуск бота...")
    
    # Проверяем доступность браузера
    if not BROWSER_AVAILABLE:
        logger.warning("⚠️ Браузер не доступен, некоторые функции будут отключены")
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_start))
    app.add_handler(CommandHandler("screen", screenshot))
    app.add_handler(CommandHandler("close", browser_close))
    
    # Запускаем браузер при старте
    app.post_init = post_init
    
    # Запускаем поллинг
    logger.info("Бот запущен, ожидаем сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()