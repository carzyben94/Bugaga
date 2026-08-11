import os
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# Запускаем Chrome/Chromium
CHROME_PATH = "/usr/bin/chromium"
try:
    subprocess.Popen([CHROME_PATH, "--headless", "--disable-gpu", "--no-sandbox"])
    logging.info("✅ Chrome/Chromium запущен")
except Exception as e:
    logging.error(f"❌ Ошибка запуска Chrome: {e}")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Бот запущен и работает.")

def main():
    print("🚀 Бот запускается...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("✅ Бот успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()