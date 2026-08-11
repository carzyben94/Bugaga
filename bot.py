import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll import Pydoll

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот с Pydoll")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю браузер...")
    
    try:
        # Создаем экземпляр Pydoll
        browser = Pydoll()
        
        # Открываем страницу
        await browser.start()
        await browser.goto("https://example.com")
        
        # Получаем заголовок страницы
        title = await browser.get_title()
        
        # Закрываем браузер
        await browser.close()
        
        await update.message.reply_text(f"✅ Заголовок: {title}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", parse))  # Новая команда
    app.run_polling()

if __name__ == "__main__":
    main()