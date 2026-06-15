import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Flask для keep-alive
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# Telegram бот
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context):
    await update.message.reply_text('Бот работает!')

async def echo(update: Update, context):
    await update.message.reply_text(update.message.text)

def run_bot():
    if not TOKEN:
        logging.error("Токен не найден!")
        return
    
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    bot_app.run_polling()

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    Thread(target=run_flask).start()
    # Запускаем бота
    run_bot()
