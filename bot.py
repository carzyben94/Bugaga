import os
import logging
from flask import Flask, request
import telebot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ВСЕ API КЛЮЧИ И ПЕРЕМЕННЫЕ =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = os.environ.get("PORT", 8080)

# ===== ПРОВЕРКА ОБЯЗАТЕЛЬНЫХ =====
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== БАЗОВАЯ КОМАНДА =====
@bot.message_handler(commands=['start', 'help'])
def start(message):
    status = f"""✅ Бот работает.

🔑 API ключи:
Telegram: {'✅' if TELEGRAM_TOKEN else '❌'}
OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}
GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}

📁 Репозиторий: {GITHUB_REPO}
🖥️ Сервис: {RENDER_SERVICE_ID or 'не задан'}"""
    bot.reply_to(message, status)

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return 'ok', 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(PORT)
    url = RENDER_EXTERNAL_URL or f"http://localhost:{port}"
    bot.remove_webhook()
    bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
    app.run(host='0.0.0.0', port=port)
