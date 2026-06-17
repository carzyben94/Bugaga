import os
import time
import logging
import json
import requests
import threading
from flask import Flask, request
import telebot
from datetime import datetime

# Импорт модулей
from xposts import register_xposts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("start_time.txt", "w") as f:
    f.write(str(time.time()))

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

# ===== РЕГИСТРАЦИЯ МОДУЛЕЙ =====
try:
    from status import register_status_full
    register_status_full(bot)
    print("Status module loaded")
except Exception as e:
    print(f"Status not loaded: {e}")

# Регистрируем /xposts
register_xposts(bot)

# ===== ЛОГИ В ЧАТ =====
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

# ===== КРИПТОВАЛЮТЫ =====
@bot.message_handler(commands=['crypto'])
def crypto_command(message):
    status_msg = bot.reply_to(message, "💰 Узнаю курсы криптовалют...")
    
    def do_crypto():
        try:
            r1 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "BTCUSDT"}, timeout=10)
            
            r2 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "ETHUSDT"}, timeout=10)
            
            if r1.status_code != 200 or r2.status_code != 200:
                bot.edit_message_text("❌ Ошибка Binance API", 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
                return
            
            btc_usd = float(r1.json().get('price', 0))
            eth_usd = float(r2.json().get('price', 0))
            
            r3 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "USDRUB"}, timeout=10)
            
            if r3.status_code == 200:
                usd_rub = float(r3.json().get('price', 95))
            else:
                usd_rub = 95
            
            btc_rub = round(btc_usd * usd_rub, 2)
            eth_rub = round(eth_usd * usd_rub, 2)
            
            btc_usd_str = f"${btc_usd:,.2f}"
            btc_eur_str = f"€{btc_usd * 0.92:,.2f}"
            btc_rub_str = f"{btc_rub:,.2f} ₽"
            
            eth_usd_str = f"${eth_usd:,.2f}"
            eth_eur_str = f"€{eth_usd * 0.92:,.2f}"
            eth_rub_str = f"{eth_rub:,.2f} ₽"
            
            result = (
                "🟡 BITCOIN (BTC):\n"
                f"  • USD: {btc_usd_str}\n"
                f"  • EUR: {btc_eur_str}\n"
                f"  • RUB: {btc_rub_str}\n\n"
                "🔷 ETHEREUM (ETH):\n"
                f"  • USD: {eth_usd_str}\n"
                f"  • EUR: {eth_eur_str}\n"
                f"  • RUB: {eth_rub_str}"
            )
            
            bot.edit_message_text(result, 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
            log_action("crypto", "курсы получены (Binance)", "success")
            
        except Exception as e:
            log_action("crypto_error", str(e), "error")
            bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
    
    thread = threading.Thread(target=do_crypto, daemon=True)
    thread.start()

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    log_action("menu", f"user={message.from_user.id}", "info")
    
    menu_text = (
        "📋 МЕНЮ БОТА\n\n"
        "🤖 ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/xposts - посты из X\n\n"
        "💰 ФИНАНСЫ\n"
        "/crypto - курсы криптовалют"
    )
    
    bot.reply_to(message, menu_text)

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "🤖 Введите вопрос после /ai\nПример: /ai что такое нейросеть")
        return
    
    log_action("ai", f"user={message.from_user.id} запрос: {user_text[:50]}", "info")
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    if not OPENROUTER_API_KEY:
        log_action("ai_error", "OpenRouter key not set", "error")
        bot.edit_message_text("❌ OpenRouter API ключ не настроен", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": user_text}],
            "max_tokens": 500
        }
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            answer = r.json()["choices"][0]["message"]["content"]
            bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)
            log_action("ai_response", "ответ отправлен", "success")
        else:
            log_action("ai_api_error", f"status {r.status_code}", "error")
            bot.edit_message_text(f"❌ Ошибка API: {r.status_code}", chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        log_action("ai_exception", str(e), "error")
        bot.edit_message_text(f"❌ Ошибка: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== ВЕБХУК =====
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