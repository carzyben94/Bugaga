import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chromium import Chrome

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот с Pydoll")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю браузер...")
    
    try:
        # Указываем путь к Chromium явно
        browser = Chrome(executable_path='/usr/bin/chromium')
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