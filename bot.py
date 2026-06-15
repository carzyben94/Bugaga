import os
import logging
from flask import Flask, request
import telebot

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Берем токен из переменных окружения Render
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не найден!")
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# Создаем бота и Flask-приложение
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ===== ОБРАБОТЧИКИ КОМАНД =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "✅ Бот работает через вебхук!")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "Напиши /start")

# ===== ВЕБХУК ДЛЯ TELEGRAM =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return 'error', 500

# ===== HEALTHCHECK ДЛЯ RENDER =====
@app.route('/health')
def health():
    return 'OK', 200

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    # Настраиваем вебхук
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not render_url:
        logger.warning("RENDER_EXTERNAL_URL не найден, используем localhost для теста")
        render_url = f"http://localhost:{port}"
    
    webhook_url = f"{render_url}/{TOKEN}"
    
    logger.info(f"Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"Запускаем Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
