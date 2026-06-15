import os
import logging
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

app = Flask(__name__)
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

logging.basicConfig(level=logging.INFO)

def start(update, context):
    update.message.reply_text('Бот работает через webhook!')

def echo(update, context):
    update.message.reply_text(update.message.text)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(filters.TEXT, echo))

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok', 200

@app.route('/')
def health():
    return 'Bot is running', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
