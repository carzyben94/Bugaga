import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Flask для Render
app_flask = Flask(__name__)

@app_flask.route('/')
def health():
    return "Bot is running!", 200

# Telegram бот
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

async def start(update: Update, context):
    await update.message.reply_text("Бот работает! ✅")

# Новые команды
async def help_command(update: Update, context):
    await update.message.reply_text("Доступные команды:\n/start - Запуск\n/help - Помощь\n/info - Инфо\n/ping - Проверка")

async def info(update: Update, context):
    await update.message.reply_text("Бот на Python + Telegram API + Flask на Render")

async def ping(update: Update, context):
    await update.message.reply_text("🏓 Pong!")

async def echo(update: Update, context):
    await update.message.reply_text(f"Ты сказал: {update.message.text}")

def run_bot():
    app = Application.builder().token(TOKEN).build()
    
    # Все команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ Бот запущен и ждёт сообщения...")
    app.run_polling()

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask (нужен Render)
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
