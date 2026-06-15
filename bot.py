import os
import telebot
from flask import Flask, request

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # ← изменено
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Бот работает!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"Вы: {message.text}")

@app.route(f'/webhook/{TOKEN}', methods=['POST'])
def webhook():
    if request.json:
        update = telebot.types.Update.de_json(request.get_data().decode())
        bot.process_new_updates([update])
    return "ok", 200

@app.route('/')
def home():
    return "Bot is running"

if __name__ == '__main__':
    url = f"https://{os.getenv('RENDER_EXTERNAL_URL')}/webhook/{TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=url)
    app.run(host='0.0.0.0', port=8080)
