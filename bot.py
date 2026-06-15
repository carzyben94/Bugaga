import os
import logging
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import asyncio
import threading

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask приложение
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False)

# Telegram бот
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context):
    logger.info(f"Получена команда start от {update.effective_user.username}")
    await update.message.reply_text('Бот работает! 🤖')

async def echo(update: Update, context):
    logger.info(f"Получено сообщение: {update.message.text}")
    await update.message.reply_text(f'Вы написали: {update.message.text}')

async def main():
    if not TOKEN:
        logger.error("ТОКЕН НЕ НАЙДЕН!")
        return
    
    logger.info("Запуск Telegram бота...")
    bot_app = Application.builder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    logger.info("Бот запущен и слушает сообщения")
    await bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота (основной поток)
    asyncio.run(main())
