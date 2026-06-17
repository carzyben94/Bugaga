# bot.py
import os
import time
import logging
import json
from flask import Flask, request
import telebot

from xposts import register_xposts
from crypto import register_crypto
from ai import register_ai

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

register_xposts(bot)
register_crypto(bot)
register_ai(bot, OPENROUTER_API_KEY)

def send_log_to_admin(action, details=None, status="info"):
    if not ADMIN_CHAT_ID:
        return
    emoji = "✅" if status == "success" else "🔴" if status == "error" else "ℹ️"
    timestamp = time.strftime("%H:%M:%S")
    try:
        bot.send_message(ADMIN_CHAT_ID, f"{emoji} [{timestamp}] {action}: {details}")
    except:
        pass

def log_action(action, details=None, status="info", send=True):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open("agent_actions.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except:
        pass
    if send:
        send_log_to_admin(action, details, status)

@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    log_action("menu", f"user={message.from_user.id}", "info")
    bot.reply_to(message, (
        "📋 МЕНЮ БОТА\n\n"
        "🤖 ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/xposts - посты из X\n\n"
        "💰 ФИНАНСЫ\n"
        "/crypto - курсы криптовалют"
    ))

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        log_action("webhook_error", str(e), "error")
        return 'error', 500

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    bot.remove_webhook()
    bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
    log_action("bot_start", "Бот запущен", "success")
    app.run(host='0.0.0.0', port=port)