import os
import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__) # Исправлено: __name__

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
        f"Я бот, работающий на Railway 🚀\n"
        f"Мой ID: {user.id}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы бота"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /ping"""
    await update.message.reply_text("🏓 Pong! Бот работает!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    # Отправляем сообщение пользователю, если ошибка не критична
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Произошла ошибка. Попробуйте позже."
        )

def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота...")
    
    try:
        # Создаем приложение
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Добавляем обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("ping", ping))
        
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

if __name__ == "__main__": # Исправлено: __name__ и "__main__"
    main()