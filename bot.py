import os
import time
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ТОКЕН ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ========== ФАЙЛОВЫЙ ЛОГГЕР ==========
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    file_logger.log(f"User {user.id} (@{user.username}) started bot")
    
    await update.message.reply_text(
        "👋 Привет! Я бот-логгер.\n\n"
        "Доступные команды:\n"
        "/logs - Получить файл с логами"
    )

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("❌ Файл с логами пока не создан.")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename="bot_logs.txt",
                caption="📋 Логи бота"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при отправке логов: {e}")

# ========== ЗАПУСК ==========
def main() -> None:
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs))
    
    logger.info("🚀 Бот запущен!")
    file_logger.log("Bot started", "INFO")
    app.run_polling()

if __name__ == "__main__":
    main()