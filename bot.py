# bot.py 
import os
import time
import logging
import json
import requests
from flask import Flask, request
import telebot

from xposts import register_xposts
from crypto import register_crypto
from ai import register_ai
from browser_ai import register_browser_ai
from crawler_ai import register_crawler_ai

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
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
    register_xposts(bot)
except Exception as e:
    print(f"xposts error: {e}")

try:
    register_crypto(bot)
except Exception as e:
    print(f"crypto error: {e}")

try:
    register_ai(bot, AGNES_API_KEY)
except Exception as e:
    print(f"ai error: {e}")

try:
    register_browser_ai(bot, AGNES_API_KEY)
except Exception as e:
    print(f"browser_ai error: {e}")

try:
    register_crawler_ai(bot, AGNES_API_KEY)
except Exception as e:
    print(f"crawler_ai error: {e}")

# ===== ЛОГИ =====
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

# ===== RENDER УПРАВЛЕНИЕ =====
RENDER_API_URL = "https://api.render.com/v1"

def render_headers():
    return {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

@bot.message_handler(commands=['render_status'])
def render_status_command(message):
    """Показать статус сервиса на Render"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}"
        resp = requests.get(url, headers=render_headers(), timeout=15)
        data = resp.json()
        
        status = data.get("status", "unknown")
        name = data.get("name", "unknown")
        type_ = data.get("type", "unknown")
        suspended = data.get("suspended", "unknown")
        
        msg = (
            f"📊 <b>Render Status</b>\n\n"
            f"Имя: <code>{name}</code>\n"
            f"Тип: <code>{type_}</code>\n"
            f"Статус: <code>{status}</code>\n"
            f"Приостановлен: <code>{suspended}</code>"
        )
        bot.reply_to(message, msg, parse_mode='HTML')
        log_action("render_status", f"user={message.from_user.id}, status={status}", "success")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_status", f"error: {e}", "error")

@bot.message_handler(commands=['render_suspend'])
def render_suspend_command(message):
    """Приостановить сервис на Render"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}/suspend"
        resp = requests.post(url, headers=render_headers(), timeout=15)
        
        if resp.status_code in (200, 202, 204):
            bot.reply_to(message, "⏸️ Сервис приостановлен")
            log_action("render_suspend", f"user={message.from_user.id}", "success")
        else:
            bot.reply_to(message, f"⚠️ Код ответа: {resp.status_code}\n{resp.text}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_suspend", f"error: {e}", "error")

@bot.message_handler(commands=['render_resume'])
def render_resume_command(message):
    """Возобновить сервис на Render"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}/resume"
        resp = requests.post(url, headers=render_headers(), timeout=15)
        
        if resp.status_code in (200, 202, 204):
            bot.reply_to(message, "▶️ Сервис возобновлён")
            log_action("render_resume", f"user={message.from_user.id}", "success")
        else:
            bot.reply_to(message, f"⚠️ Код ответа: {resp.status_code}\n{resp.text}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_resume", f"error: {e}", "error")

@bot.message_handler(commands=['render_restart'])
def render_restart_command(message):
    """Перезапустить сервис (deploy)"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}/deploys"
        payload = {"clearCache": "do_not_clear"}
        resp = requests.post(url, headers=render_headers(), json=payload, timeout=15)
        
        if resp.status_code in (200, 201, 202):
            data = resp.json()
            deploy_id = data.get("id", "unknown")
            bot.reply_to(message, f"🔄 Перезапуск запущен\nDeploy ID: <code>{deploy_id}</code>", parse_mode='HTML')
            log_action("render_restart", f"user={message.from_user.id}, deploy={deploy_id}", "success")
        else:
            bot.reply_to(message, f"⚠️ Код ответа: {resp.status_code}\n{resp.text}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_restart", f"error: {e}", "error")

@bot.message_handler(commands=['render_env'])
def render_env_command(message):
    """Показать переменные окружения сервиса"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}/env-vars"
        resp = requests.get(url, headers=render_headers(), timeout=15)
        data = resp.json()
        
        env_list = []
        for item in data:
            name = item.get("envVar", {}).get("key", "unknown")
            value = item.get("envVar", {}).get("value", "")
            # Маскируем значения
            masked = value[:2] + "***" if len(value) > 3 else "***"
            env_list.append(f"  <code>{name}</code> = {masked}")
        
        msg = "🔧 <b>Переменные окружения:</b>\n\n" + "\n".join(env_list[:20])
        bot.reply_to(message, msg, parse_mode='HTML')
        log_action("render_env", f"user={message.from_user.id}, count={len(env_list)}", "success")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_env", f"error: {e}", "error")

@bot.message_handler(commands=['render_logs'])
def render_logs_command(message):
    """Показать последние логи сервиса"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    try:
        url = f"{RENDER_API_URL}/services/{RENDER_SERVICE_ID}/logs"
        resp = requests.get(url, headers=render_headers(), timeout=15)
        data = resp.json()
        
        logs = data.get("logs", [])[:10]
        if not logs:
            bot.reply_to(message, "📭 Логи пусты")
            return
        
        log_text = "\n".join([f"<code>{l.get('message', '')[:100]}</code>" for l in logs])
        bot.reply_to(message, f"📋 <b>Последние логи:</b>\n\n{log_text}", parse_mode='HTML')
        log_action("render_logs", f"user={message.from_user.id}", "success")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        log_action("render_logs", f"error: {e}", "error")

# ===== ОБЩЕЕ МЕНЮ =====
MENU_TEXT = (
    "🤖 <b>BUGAGA BOT</b>\n"
    "Твой агент для ИИ, новостей и крипты\n\n"
    
    "🧠 <b>Искусственный интеллект</b>\n"
    "  ├ /ai — Задать вопрос ИИ\n"
    "  ├ /browser_ai — ИИ читает сайт\n"
    "  └ /crawler_ai — Собрать новости\n\n"
    
    "📰 <b>Новости</b>\n"
    "  └ /xposts — Посты из X\n\n"
    
    "💰 <b>Финансы</b>\n"
    "  └ /crypto — Курсы BTC и ETH\n\n"
    
    "🔧 <b>Render</b>\n"
    "  ├ /render_status — Статус сервиса\n"
    "  ├ /render_suspend — Остановить\n"
    "  ├ /render_resume — Запустить\n"
    "  ├ /render_restart — Перезапустить\n"
    "  ├ /render_env — Переменные окружения\n"
    "  └ /render_logs — Логи сервиса"
)

@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    try:
        log_action(message.text.lstrip('/'), f"user={message.from_user.id}", "info")
        bot.reply_to(message, MENU_TEXT, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

# ===== ТЕСТОВАЯ КОМАНДА =====
@bot.message_handler(commands=['test'])
def test_command(message):
    bot.reply_to(message, "✅ Бот работает!")

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        print(f"webhook error: {e}")
        return 'error', 500

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    
    print("🔄 Удаляю старый webhook...")
    try:
        bot.remove_webhook()
        time.sleep(2)
    except Exception as e:
        print(f"remove webhook error: {e}")
    
    print(f"🔄 Устанавливаю webhook: {url}/{TELEGRAM_TOKEN}")
    try:
        bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
        print("✅ Webhook установлен!")
    except Exception as e:
        print(f"set webhook error: {e}")
    
    try:
        info = bot.get_webhook_info()
        print(f"📊 Webhook info: {info}")
    except Exception as e:
        print(f"get webhook info error: {e}")
    
    log_action("bot_start", "Бот запущен", "success")
    app.run(host='0.0.0.0', port=port)
