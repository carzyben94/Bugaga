import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Проверяем установку
try:
    import cdp_use
    logger.info(f"✅ cdp_use версия: {cdp_use.__version__ if hasattr(cdp_use, '__version__') else 'unknown'}")
except ImportError as e:
    logger.error(f"❌ cdp_use не установлен: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот работает!")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка установленных пакетов"""
    import sys
    import subprocess
    
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                          capture_output=True, text=True)
    
    await update.message.reply_text(f"📦 Установленные пакеты:\n{result.stdout[:500]}")

def main():
    if not TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в .env")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    
    logger.info("🤖 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()