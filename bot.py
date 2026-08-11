import os
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== ЗАПУСК CHROME ====================
CHROME_PATH = "/usr/bin/chromium"

def start_chrome():
    """Запускает Chromium в headless-режиме"""
    try:
        subprocess.Popen([
            CHROME_PATH,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ])
        logger.info("✅ Chrome/Chromium успешно запущен")
        return True
    except FileNotFoundError:
        logger.error("❌ Chrome не найден по пути: %s", CHROME_PATH)
        return False
    except Exception as e:
        logger.error("❌ Ошибка запуска Chrome: %s", e)
        return False

# ==================== ТОКЕН БОТА ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /start"""
    await update.message.reply_text(
        "👋 Привет! Бот запущен и работает.\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение"
    )

# ==================== ЗАПУСК БОТА ====================
def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Chrome
    start_chrome()
    
    # Создаём и настраиваем приложение
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # Запускаем поллинг
    logger.info("✅ Бот успешно запущен! Ожидание команд...")
    app.run_polling()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    main()