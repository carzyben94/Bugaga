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
# Render API v1: https://api-docs.render.com/reference

def render_headers():
    return {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def render_api_call(method, endpoint, payload=None):
    """Универсальная функция для вызова Render API"""
    url = f"https://api.render.com/v1{endpoint}"
    headers = render_headers()
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
        else:
            return None, f"Unsupported method: {method}"
        
        print(f"[Render API] {method} {url}")
        print(f"[Render API] Status: {resp.status_code}")
        print(f"[Render API] Body: {resp.text[:500]}")
        
        if resp.status_code == 404:
            return None, "404 — эндпоинт не найден. Проверь RENDER_SERVICE_ID и права API ключа."
        if resp.status_code == 401:
            return None, "401 — неверный API ключ. Создай новый в Render Dashboard → Account Settings."
        if resp.status_code == 403:
            return None, "403 — доступ запрещён. Нужен API ключ с правами owner/admin."
        
        content_type = resp.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            return None, f"HTTP {resp.status_code} (не JSON): {resp.text[:200]}"
        
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        
        return resp.json(), None
        
    except requests.exceptions.JSONDecodeError as e:
        return None, f"JSON decode error: {e}\nResponse: {resp.text[:300]}"
    except Exception as e:
        return None, f"Request error: {e}"

@bot.message_handler(commands=['render_status'])
def render_status_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    # Правильный эндпоинт для Render API v1
    data, error = render_api_call("GET", f"/services/{RENDER_SERVICE_ID}")
    if error:
        bot.reply_to(message, f"❌ {error}")
        log_action("render_status", f"error: {error}", "error")
        return
    
    # Ответ обёрнут в массив или объект — обрабатываем оба варианта
    service = data if isinstance(data, dict) else data[0] if isinstance(data, list) and len(data) > 0 else {}
    if not service:
        bot.reply_to(message, "❌ Не удалось получить данные сервиса")
        return
    
    # Иногда данные вложены в "service"
    svc = service.get("service", service)
    
    status = svc.get("status", "unknown")
    name = svc.get("name", "unknown")
    type_ = svc.get("type", "unknown")
    suspended = svc.get("suspended", "unknown")
    url = svc.get("serviceDetails", {}).get("url", "—")
    
    msg = (
        f"📊 <b>Render Status</b>\n\n"
        f"Имя: <code>{name}</code>\n"
        f"Тип: <code>{type_}</code>\n"
        f"Статус: <code>{status}</code>\n"
        f"Приостановлен: <code>{suspended}</code>\n"
        f"URL: <code>{url}</code>"
    )
    bot.reply_to(message, msg, parse_mode='HTML')
    log_action("render_status", f"user={message.from_user.id}, status={status}", "success")

@bot.message_handler(commands=['render_suspend'])
def render_suspend_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    # Render API v1: suspend через обновление сервиса
    payload = {"suspended": "suspended"}
    data, error = render_api_call("POST", f"/services/{RENDER_SERVICE_ID}/suspend", payload)
    if error:
        # Пробуем альтернативный метод — PATCH
        data, error = render_api_call("POST", f"/services/{RENDER_SERVICE_ID}", {"suspended": "suspended"})
        if error:
            bot.reply_to(message, f"❌ {error}\n\nВозможно, suspend/resume недоступны для вашего плана. Попробуйте /render_restart.")
            log_action("render_suspend", f"error: {error}", "error")
            return
    
    bot.reply_to(message, "⏸️ Сервис приостановлен")
    log_action("render_suspend", f"user={message.from_user.id}", "success")

@bot.message_handler(commands=['render_resume'])
def render_resume_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    payload = {"suspended": "not_suspended"}
    data, error = render_api_call("POST", f"/services/{RENDER_SERVICE_ID}/resume", payload)
    if error:
        data, error = render_api_call("POST", f"/services/{RENDER_SERVICE_ID}", {"suspended": "not_suspended"})
        if error:
            bot.reply_to(message, f"❌ {error}\n\nВозможно, suspend/resume недоступны для вашего плана. Попробуйте /render_restart.")
            log_action("render_resume", f"error: {error}", "error")
            return
    
    bot.reply_to(message, "▶️ Сервис возобновлён")
    log_action("render_resume", f"user={message.from_user.id}", "success")

@bot.message_handler(commands=['render_restart'])
def render_restart_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    # Создаём новый deploy — это перезапускает сервис
    payload = {"clearCache": "do_not_clear"}
    data, error = render_api_call("POST", f"/services/{RENDER_SERVICE_ID}/deploys", payload)
    if error:
        bot.reply_to(message, f"❌ {error}")
        log_action("render_restart", f"error: {error}", "error")
        return
    
    deploy = data.get("deploy", data) if isinstance(data, dict) else {}
    deploy_id = deploy.get("id", "unknown") if isinstance(deploy, dict) else "unknown"
    status = deploy.get("status", "unknown") if isinstance(deploy, dict) else "unknown"
    
    bot.reply_to(message, f"🔄 Перезапуск запущен\nDeploy ID: <code>{deploy_id}</code>\nСтатус: <code>{status}</code>", parse_mode='HTML')
    log_action("render_restart", f"user={message.from_user.id}, deploy={deploy_id}", "success")

@bot.message_handler(commands=['render_env'])
def render_env_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    data, error = render_api_call("GET", f"/services/{RENDER_SERVICE_ID}/env-vars")
    if error:
        bot.reply_to(message, f"❌ {error}")
        log_action("render_env", f"error: {error}", "error")
        return
    
    # Ответ может быть массивом или объектом с "envVars"
    env_vars = data if isinstance(data, list) else data.get("envVars", [])
    
    if not env_vars:
        bot.reply_to(message, "📭 Переменные окружения не найдены")
        return
    
    env_list = []
    for item in env_vars:
        # Разные форматы ответа
        env_var = item.get("envVar", item) if isinstance(item, dict) else item
        name = env_var.get("key", "unknown") if isinstance(env_var, dict) else "unknown"
        value = env_var.get("value", "") if isinstance(env_var, dict) else ""
        masked = value[:2] + "***" if len(value) > 3 else "***"
        env_list.append(f"  <code>{name}</code> = {masked}")
    
    msg = "🔧 <b>Переменные окружения:</b>\n\n" + "\n".join(env_list[:20])
    bot.reply_to(message, msg, parse_mode='HTML')
    log_action("render_env", f"user={message.from_user.id}, count={len(env_list)}", "success")

@bot.message_handler(commands=['render_logs'])
def render_logs_command(message):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        bot.reply_to(message, "❌ RENDER_API_KEY или RENDER_SERVICE_ID не настроены")
        return
    
    # Логи в Render API v1 — через отдельный эндпоинт или невозможны через API
    # Пробуем стандартный, если не работает — сообщаем
    data, error = render_api_call("GET", f"/services/{RENDER_SERVICE_ID}/logs")
    if error:
        bot.reply_to(message, f"❌ {error}\n\nЛоги через API могут быть недоступны. Смотрите в Render Dashboard.")
        log_action("render_logs", f"error: {error}", "error")
        return
    
    logs = data.get("logs", [])[:10] if isinstance(data, dict) else []
    if not logs:
        bot.reply_to(message, "📭 Логи пусты")
        return
    
    log_text = "\n".join([f"<code>{l.get('message', str(l))[:100]}</code>" for l in logs])
    bot.reply_to(message, f"📋 <b>Последние логи:</b>\n\n{log_text}", parse_mode='HTML')
    log_action("render_logs", f"user={message.from_user.id}", "success")

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
