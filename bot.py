import telebot
from flask import Flask, request
import os
import logging

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-domain.com/webhook")
PORT = int(os.getenv("PORT", 5000))

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========== ОБРАБОТЧИКИ ==========
@bot.message_handler(commands=["start"])
def start_message(message):
    """Приветственное сообщение"""
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Я бот на pyTelegramBotAPI + Flask"
    )

# ========== WEBHOOK ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    """Эндпоинт для вебхуков Telegram"""
    try:
        json_str = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_str)
        
        if update:
            bot.process_new_updates([update])
            logger.info("Update processed successfully")
            return "OK", 200
        return "No update", 400
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route("/", methods=["GET"])
def health_check():
    """Проверка работоспособности"""
    return "Bot is running", 200

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    if os.getenv("ENV") == "production":
        # Production: вебхук
        logger.info(f"Starting webhook mode on port {PORT}")
        
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
        
        app.run(host="0.0.0.0", port=PORT)
    else:
        # Development: long-polling
        logger.info("Starting polling mode (development)")
        bot.remove_webhook()
        bot.infinity_polling(timeout=30, long_polling_timeout=30)