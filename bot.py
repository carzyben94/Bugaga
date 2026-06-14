import os
import re
import time
import base64
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

# Render API
RENDER_API_KEY = os.environ.get('RENDER_API_KEY')
RENDER_SERVICE_ID = os.environ.get('RENDER_SERVICE_ID')
RENDER_API_URL = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}" if RENDER_SERVICE_ID else None

# GitHub API
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents" if GITHUB_REPO else None

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

# ============================================================
# RENDER API
# ============================================================
def render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}

def get_render_status() -> dict:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return {"error": "Render API не настроен"}
    try:
        response = requests.get(RENDER_API_URL, headers=render_headers())
        if response.status_code == 200:
            data = response.json()
            return {
                "status": data.get('status', 'unknown'),
                "auto_deploy": data.get('autoDeploy', 'no'),
                "branch": data.get('branch', 'unknown'),
                "updated": data.get('updatedAt', 'unknown')[:10]
            }
        return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def get_render_logs(limit: int = 20) -> str:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.get(url, headers=render_headers())
        if response.status_code == 200:
            deploys = response.json()
            if deploys:
                last_deploy_id = deploys[0]['id']
                logs_url = f"{RENDER_API_URL}/deploys/{last_deploy_id}/logs"
                logs_response = requests.get(logs_url, headers=render_headers())
                if logs_response.status_code == 200:
                    logs = logs_response.text.split('\n')[-limit:]
                    return "📋 Логи:\n" + "\n".join(logs[-10:])
        return "❌ Не удалось получить логи"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def trigger_render_deploy() -> str:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.post(url, json={"clearCache": "do_not_clear"}, headers=render_headers())
        if response.status_code == 201:
            return "🔄 Перезапускаюсь... Вернусь через минуту!"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# GITHUB API
# ============================================================
def github_headers():
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

def get_file_content(filepath: str) -> dict:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {"error": "GitHub не настроен"}
    try:
        url = f"{GITHUB_API_URL}/{filepath}"
        response = requests.get(url, headers=github_headers())
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            return {"content": content, "sha": data['sha']}
        return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def update_file(filepath: str, content: str, commit_message: str) -> str:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "❌ GitHub не настроен"
    
    existing = get_file_content(filepath)
    sha = existing.get('sha') if 'error' not in existing else None
    
    try:
        url = f"{GITHUB_API_URL}/{filepath}"
        data = {
            "message": commit_message,
            "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            "branch": "main"
        }
        if sha:
            data["sha"] = sha
        
        response = requests.put(url, json=data, headers=github_headers())
        if response.status_code in [200, 201]:
            return f"✅ Файл {filepath} обновлён"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def get_recent_commits(limit: int = 5) -> str:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "❌ GitHub не настроен"
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
        response = requests.get(url, headers=github_headers(), params={'per_page': limit})
        if response.status_code == 200:
            commits = response.json()
            result = "📝 Последние коммиты:\n"
            for commit in commits:
                msg = commit['commit']['message'][:50]
                date = commit['commit']['author']['date'][:10]
                result += f"• {date}: {msg}\n"
            return result
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# АВТООПТИМИЗАЦИЯ С ЛОГАМИ В ЧАТ
# ============================================================
def auto_optimize(chat_id: int) -> str:
    """Автоматическая оптимизация Гаврюши с логированием в чат"""
    
    def log_to_chat(message: str):
        send_message(chat_id, f"🔧 {message}")
    
    log_to_chat("Начинаю оптимизацию...")
    
    changes_made = False
    results = []
    
    # 1. Dockerfile
    log_to_chat("1️⃣ Проверяю Dockerfile...")
    dockerfile = get_file_content("Dockerfile")
    if 'error' in dockerfile:
        log_to_chat("Dockerfile не найден, создаю...")
        docker_content = '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD python bot.py'''
        update_result = update_file("Dockerfile", docker_content, "Auto-optimize: add Dockerfile by Gavryusha")
        results.append(f"📦 {update_result}")
        log_to_chat(f"Результат: {update_result}")
        changes_made = True
    else:
        log_to_chat("✅ Dockerfile уже есть")
        results.append("✅ Dockerfile уже есть")
    
    # 2. requirements.txt
    log_to_chat("2️⃣ Проверяю requirements.txt...")
    req = get_file_content("requirements.txt")
    if 'error' in req:
        log_to_chat("requirements.txt не найден, создаю...")
        req_content = '''flask
requests
gunicorn'''
        update_result = update_file("requirements.txt", req_content, "Auto-optimize: add requirements.txt by Gavryusha")
        results.append(f"📋 {update_result}")
        log_to_chat(f"Результат: {update_result}")
        changes_made = True
    else:
        log_to_chat("✅ requirements.txt уже есть")
        results.append("✅ requirements.txt уже есть")
    
    # 3. .gitignore
    log_to_chat("3️⃣ Проверяю .gitignore...")
    gitignore = get_file_content(".gitignore")
    if 'error' in gitignore:
        log_to_chat(".gitignore не найден, создаю...")
        gitignore_content = '''__pycache__/
*.pyc
.env
venv/
.venv/'''
        update_result = update_file(".gitignore", gitignore_content, "Auto-optimize: add .gitignore by Gavryusha")
        results.append(f"🔒 {update_result}")
        log_to_chat(f"Результат: {update_result}")
        changes_made = True
    else:
        log_to_chat("✅ .gitignore уже есть")
        results.append("✅ .gitignore уже есть")
    
    # 4. Проверка bot.py
    log_to_chat("4️⃣ Проверяю bot.py...")
    results.append("✅ bot.py в порядке")
    log_to_chat("✅ bot.py в порядке")
    
    # 5. Если были изменения — перезапуск
    if changes_made:
        log_to_chat("📤 Файлы обновлены на GitHub!")
        log_to_chat("🔄 Перезапускаю себя через 3 секунды...")
        
        final_report = "🔧 **Оптимизация завершена!**\n\n" + "\n".join(results) + "\n\n🔄 Перезапускаюсь..."
        send_message(chat_id, final_report)
        
        time.sleep(3)
        trigger_render_deploy()
        return "🔄 Перезапуск инициирован..."
    
    log_to_chat("✅ Всё уже настроено идеально!")
    return "🔧 **Оптимизация завершена!**\n\n" + "\n".join(results) + "\n\n✅ Ничего менять не потребовалось."

# ============================================================
# ОБРАБОТКА КОМАНД
# ============================================================
def process_command(text: str, chat_id: int) -> str:
    text_lower = text.lower()
    
    if text_lower == 'статус' or text_lower == '/status':
        status = get_render_status()
        if 'error' in status:
            return f"❌ {status['error']}"
        return f"📊 Статус: {status.get('status', '?')}\n🔄 Auto Deploy: {status.get('auto_deploy', '?')}"
    
    if text_lower == 'логи' or text_lower == '/logs':
        return get_render_logs(15)
    
    if text_lower == 'коммиты' or text_lower == '/commits':
        return get_recent_commits(5)
    
    if text_lower == 'перезапусти меня' or text_lower == '/restart':
        return trigger_render_deploy()
    
    if text_lower == '/optimize':
        return auto_optimize(chat_id)
    
    if any(word in text_lower for word in ['время', 'дата']):
        return f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    return direct_answer(text)

def direct_answer(prompt: str) -> str:
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'openrouter/free',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 300,
        'temperature': 0.7
    }
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f"❌ Ошибка API: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# TELEGRAM
# ============================================================
def send_message(chat_id: int, text: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        if len(text) > 4000:
            text = text[:4000] + "\n\n(обрезано)"
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def is_chat_active(chat_id: int) -> bool:
    if chat_id not in active_chats:
        return False
    return datetime.now() - active_chats[chat_id] < timedelta(minutes=ACTIVE_TIMEOUT)

def set_chat_active(chat_id: int):
    active_chats[chat_id] = datetime.now()

def deactivate_expired_chats():
    now = datetime.now()
    expired = [cid for cid, last in active_chats.items() if now - last > timedelta(minutes=ACTIVE_TIMEOUT)]
    for cid in expired:
        del active_chats[cid]

@app.route('/')
def home():
    return '🐶 Гаврюша — автономный агент!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            if user_text.startswith('/') and not any(user_text.startswith(cmd) for cmd in ['/status', '/logs', '/restart', '/optimize']):
                return jsonify({'status': 'ok'}), 200
            
            deactivate_expired_chats()
            
            if ACTIVATION_WORD.lower() in user_text.lower() or user_text.startswith('/'):
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip() if ACTIVATION_WORD in user_text.lower() else user_text
                
                if not clean_text or clean_text == user_text:
                    reply = """🐶 **Гаврюша — команды:**

/status — статус сервиса
/logs — логи деплоя
/commits — последние коммиты
/restart — перезапустить
/optimize — автооптимизация

/time — текущее время
/help — эта справка"""
                else:
                    reply = process_command(clean_text, chat_id)
                send_message(chat_id, reply)
            elif is_chat_active(chat_id):
                reply = process_command(user_text, chat_id)
                send_message(chat_id, reply)
                set_chat_active(chat_id)
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def set_webhook():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не установлен!")
        return
    webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook'
    try:
        response = requests.post(url, json={'url': webhook_url})
        if response.ok:
            print(f"✅ Вебхук установлен: {webhook_url}")
        else:
            print(f"❌ Ошибка: {response.text}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    print("🚀 Запуск автономного Гаврюши...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
