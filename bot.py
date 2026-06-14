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
GITHUB_REPO = os.environ.get('GITHUB_REPO')  # формат: "username/repo"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents" if GITHUB_REPO else None

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

# ============================================================
# RENDER API (НАБЛЮДЕНИЕ И УПРАВЛЕНИЕ)
# ============================================================
def render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}

def get_render_status() -> dict:
    """Получить статус сервиса"""
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
    """Получить последние логи деплоя"""
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
    """Запустить деплой"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.post(url, json={"clearCache": "do_not_clear"}, headers=render_headers())
        if response.status_code == 201:
            return "🔄 Гаврюша перезапускается... Вернусь через минуту!"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# GITHUB API (ВНЕСЕНИЕ ПРАВОК)
# ============================================================
def github_headers():
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

def get_file_content(filepath: str) -> dict:
    """Получить содержимое файла из репозитория"""
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
    """Обновить файл на GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "❌ GitHub не настроен"
    
    # Получаем текущий SHA
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
            return f"✅ Файл {filepath} обновлён на GitHub"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def get_recent_commits(limit: int = 5) -> str:
    """Получить последние коммиты"""
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
# ГАВРЮША — АНАЛИЗ И ПРИНЯТИЕ РЕШЕНИЙ
# ============================================================
def analyze_self() -> str:
    """Гаврюша анализирует своё состояние"""
    status = get_render_status()
    if 'error' in status:
        return f"❌ {status['error']}"
    
    result = f"📊 **Состояние Гаврюши:**\n"
    result += f"• Статус: {status.get('status', '?')}\n"
    result += f"• Auto Deploy: {status.get('auto_deploy', '?')}\n"
    result += f"• Ветка: {status.get('branch', '?')}\n"
    result += f"• Обновлён: {status.get('updated', '?')}\n"
    
    return result

def auto_fix_common_issues() -> str:
    """Гаврюша пытается исправить частые проблемы"""
    status = get_render_status()
    
    if status.get('status') == 'deploy_failed':
        logs = get_render_logs(10)
        if 'ModuleNotFoundError' in logs:
            return "⚠️ Обнаружена ошибка импорта. Попробуй: /fix_requirements"
        if 'GLIBC' in logs:
            return "⚠️ Проблема с GLIBC. Нужно перейти на Docker. Скажи /migrate_docker"
    
    if status.get('auto_deploy') == 'no':
        return "⚠️ Auto Deploy выключен. Скажи /enable_autodeploy чтобы включить"
    
    return "✅ Все системы работают нормально"

def suggest_improvements() -> str:
    """Гаврюша предлагает улучшения"""
    status = get_render_status()
    
    suggestions = []
    if status.get('status') == 'live':
        suggestions.append("✓ Всё работает стабильно")
    
    # Проверяем, есть ли Dockerfile
    dockerfile = get_file_content("Dockerfile")
    if 'error' in dockerfile:
        suggestions.append("📦 Рекомендую добавить Dockerfile для стабильности")
    
    if not suggestions:
        suggestions.append("💡 Попробуй команду /optimize для настройки")
    
    return "💡 **Советы:**\n• " + "\n• ".join(suggestions)

# ============================================================
# ОБРАБОТКА КОМАНД
# ============================================================
def process_command(text: str, chat_id: int) -> str:
    text_lower = text.lower()
    
    # Наблюдение за собой
    if text_lower == 'статус' or text_lower == '/status':
        return analyze_self()
    
    if text_lower == 'логи' or text_lower == '/logs':
        return get_render_logs(15)
    
    if text_lower == 'коммиты' or text_lower == '/commits':
        return get_recent_commits(5)
    
    if text_lower == 'диагностика' or text_lower == '/health':
        return auto_fix_common_issues()
    
    if text_lower == 'советы' or text_lower == '/advice':
        return suggest_improvements()
    
    # Управление собой
    if text_lower == 'перезапусти меня' or text_lower == '/restart':
        return trigger_render_deploy()
    
    # Внесение правок
    if text_lower.startswith('/update '):
        # /update bot.py "новый код"
        parts = text.split(' ', 2)
        if len(parts) >= 3:
            filepath = parts[1]
            new_content = parts[2].strip('"')
            return update_file(filepath, new_content, f"Auto-update by Гаврюша at {datetime.now()}")
        return "❌ Формат: /update bot.py 'новое содержимое'"
    
    if text_lower == '/optimize':
        return auto_optimize()
    
    # Время
    if any(word in text_lower for word in ['время', 'дата']):
        return f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    # Обычный ответ через ИИ
    return direct_answer(text)

def auto_optimize() -> str:
    """Автоматическая оптимизация Гаврюши"""
    result = "🔧 **Оптимизация:**\n"
    
    # Проверяем и предлагаем добавить Dockerfile
    dockerfile = get_file_content("Dockerfile")
    if 'error' in dockerfile:
        docker_content = '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY bot.py .
CMD python bot.py'''
        result += "\n• Предлагаю добавить Dockerfile для стабильности"
        result += f"\n  /update Dockerfile '{docker_content}'"
    
    # Проверяем requirements.txt
    req = get_file_content("requirements.txt")
    if 'error' in req:
        result += "\n• Создай requirements.txt с зависимостями"
    
    return result

def direct_answer(prompt: str) -> str:
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'openrouter/free',
        'messages': [
            {'role': 'system', 'content': f'Ты — Гаврюша, самообучающийся агент. Отвечай кратко.'},
            {'role': 'user', 'content': prompt}
        ],
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
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=10)
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
            
            if user_text.startswith('/') and not any(user_text.startswith(cmd) for cmd in ['/status', '/logs', '/restart', '/update', '/commits', '/health', '/advice', '/optimize']):
                return jsonify({'status': 'ok'}), 200
            
            deactivate_expired_chats()
            
            if ACTIVATION_WORD.lower() in user_text.lower() or user_text.startswith('/'):
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip() if ACTIVATION_WORD in user_text.lower() else user_text
                
                if not clean_text or clean_text == user_text:
                    reply = """🐶 **Гаврюша — автономный агент**

**Наблюдение:**
/status — статус сервиса
/logs — логи деплоя
/commits — последние коммиты
/health — диагностика

**Управление:**
/restart — перезапустить
/update bot.py 'код' — обновить файл

**Советы:**
/advice — рекомендации
/optimize — автоптимизация
"""
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
