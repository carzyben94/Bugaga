import os
import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем наш модуль управления браузером
from browser import browser_manager

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
    sys.exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        f"Я бот, работающий на Railway с Chromium (CDP) 🚀\n"
        f"Твой ID: {user.id}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы бота\n"
        "/web <url> - Получить заголовок страницы через CDP"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /ping"""
    await update.message.reply_text("🏓 Pong! Бот работает!")

async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /web - проверка работы CDP"""
    if not context.args:
        await update.message.reply_text("Использование: /web <url>\nНапример: /web https://example.com")
        return

    url = context.args[0]
    # Добавляем http:// если пользователь забыл
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    await update.message.reply_text(f"⏳ Открываю {url} через CDP...")
    
    try:
        title = await browser_manager.get_page_title(url)
        await update.message.reply_text(f"📄 Заголовок страницы:\n{title}")
    except Exception as e:
        logger.error(f"Ошибка в команде /web: {e}")
        await update.message.reply_text("⚠️ Не удалось получить данные со страницы.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Исключение при обработке обновления: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Произошла ошибка. Попробуйте позже."
        )

async def post_init(application: Application):
    """Вызывается после инициализации бота, но до начала поллинга"""
    await browser_manager.start()

async def post_shutdown(application: Application):
    """Вызывается при остановке бота"""
    await browser_manager.stop()

def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота...")
    
    try:
        # Создаем приложение и привязываем хуки жизненного цикла
        app = Application.builder() \
            .token(TELEGRAM_TOKEN) \
            .post_init(post_init) \
            .post_shutdown(post_shutdown) \
            .build()
        
        # Добавляем обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("ping", ping))
        app.add_handler(CommandHandler("web", web_command))
        
        # Добавляем глобальный обработчик ошибок
        app.add_error_handler(error_handler)
        
        # Запускаем поллинг с настройками для стабильности
        logger.info("✅ Бот запущен, ожидаем сообщения...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Пропускает старые обновления при перезапуске
            timeout=30  # Таймаут в секундах
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()