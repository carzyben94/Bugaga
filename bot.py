import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chrome import Chrome  # ← импорт из chrome, не chromium!
from pydoll.browser.options import Options  # ← импорт Options

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот с Pydoll")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю браузер...")
    
    try:
        options = Options()
        # Указываем путь к Chromium
        options.binary_location = '/usr/bin/chromium'
        # Ключевые аргументы для Docker/Railway
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--headless')  # Без GUI
        
        browser = Chrome(options=options)
        tab = await browser.start()
        await tab.go_to('https://example.com')
        
        title = await tab.title
        
        await browser.close()
        await update.message.reply_text(f"✅ Заголовок: {title}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", parse))
    app.run_polling()

if __name__ == "__main__":
    main()