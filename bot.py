import os
import re
import time
import base64
import json
import requests
import websocket
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
# LIGHTPANDA БРАУЗЕР
# ============================================================
class LightpandaClient:
    def __init__(self, host='localhost', port=9222):
        self.ws_url = f"ws://{host}:{port}/devtools/browser"
        self.ws = None
        self.msg_id = 0
    
    def connect(self):
        try:
            self.ws = websocket.create_connection(self.ws_url, timeout=10)
            return True
        except:
            return False
    
    def search(self, query):
        if not self.ws and not self.connect():
            return "❌ Браузер не доступен"
        url = f"https://lite.duckduckgo.com/lite/?q={query.replace(' ', '+')}"
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": "Page.navigate", "params": {"url": url}}
        self.ws.send(json.dumps(msg))
        self.ws.recv()
        time.sleep(2)
        
        self.msg_id += 1
        msg2 = {"id": self.msg_id, "method": "Runtime.evaluate", "params": {"expression": "document.body.innerText"}}
        self.ws.send(json.dumps(msg2))
        result = json.loads(self.ws.recv())
        text = result.get('result', {}).get('value', '')
        
        lines = text.split('\n')
        results = []
        for line in lines:
            if 'http' in line and len(line) > 10:
                results.append(f"• {line[:150]}")
                if len(results) >= 5:
                    break
        if results:
            return "🔍 Результаты поиска:\n\n" + "\n".join(results)
        return f"😕 Ничего не найдено: {query}"

browser = LightpandaClient()

def search_with_browser(query: str) -> str:
    """Поиск через Lightpanda браузер"""
    return browser.search(query)

# ============================================================
# САМОУЛУЧШЕНИЕ
# ============================================================
def analyze_self(chat_id: int) -> dict:
    """Анализирует состояние Гаврюши"""
    issues = []
    improvements = []
    
    dockerfile = get_file_content("Dockerfile")
    if 'error' in dockerfile:
        issues.append("❌ Dockerfile отсутствует")
        improvements.append("📦 Добавить Dockerfile")
    
    req = get_file_content("requirements.txt")
    if 'error' in req:
        issues.append("❌ requirements.txt отсутствует")
        improvements.append("📋 Добавить requirements.txt")
    
    report = f"🔍 **Самоанализ:**\n• Проблем: {len(issues)}\n• Улучшений: {len(improvements)}\n\n"
    if improvements:
        report += "**Нужно:**\n" + "\n".join(f"• {i}" for i in improvements)
    else:
        report += "✅ Всё хорошо!"
    
    return {"issues": issues, "improvements": improvements, "report": report}

def execute_improvement(improvement: str, chat_id: int) -> dict:
    """Выполняет одно улучшение"""
    if "Dockerfile" in improvement:
        content = '''FROM lightpanda/browser:nightly
WORKDIR /app
RUN apt-get update && apt-get install -y python3 python3-pip
COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
COPY bot.py .
CMD lightpanda serve --host 0.0.0.0 --port 9222 & sleep 3 && python3 bot.py'''
        result = update_file("Dockerfile", content, "Self-improve: add Dockerfile")
        return {"success": "✅" in result, "message": result}
    
    if "requirements.txt" in improvement:
        content = "flask\nrequests\ngunicorn\nwebsocket-client"
        result = update_file("requirements.txt", content, "Self-improve: add requirements.txt")
        return {"success": "✅" in result, "message": result}
    
    return {"success": False, "message": "Неизвестное улучшение"}

def self_improve_step(chat_id: int) -> str:
    """Один шаг самоулучшения"""
    analysis = analyze_self(chat_id)
    if not analysis["improvements"]:
        return "✅ Гаврюша уже в идеальном состоянии!"
    
    imp = analysis["improvements"][0]
    send_message(chat_id, f"🔧 Выполняю: {imp}")
    result = execute_improvement(imp, chat_id)
    
    if result["success"]:
        if "Dockerfile" in imp:
            trigger_render_deploy()
            return f"✅ {result['message']}\n🔄 Перезапускаюсь..."
        return f"✅ {result['message']}\n📝 Напиши /step для следующего шага"
    return f"❌ {result['message']}"

# ============================================================
# ГЕНЕРАЦИЯ НОВЫХ ФУНКЦИЙ
# ============================================================
def generate_new_function(description: str, chat_id: int) -> str:
    """Генерирует новую функцию через ИИ"""
    send_message(chat_id, f"🧠 Генерирую функцию: {description}")
    
    prompt = f"""Напиши функцию на Python для телеграм-бота.
Запрос: {description}

Функция должна:
- Принимать строку text (текст сообщения пользователя)
- Возвращать строку с ответом
- Иметь понятное имя (на английском)
- Содержать обработку ошибок

Верни ТОЛЬКО код функции, без пояснений.
Начинай с def и заканчивай return."""
    
    headers = {'Authorization': f'Bearer {OPENROUTER_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': 'openrouter/free', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 800}
    
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            new_function = response.json()['choices'][0]['message']['content']
            
            bot_file = get_file_content("bot.py")
            if 'error' in bot_file:
                return "❌ Не найден bot.py на GitHub"
            
            # Добавляем функцию перед process_command
            old_code = bot_file['content']
            insert_point = old_code.find('def process_command')
            if insert_point == -1:
                insert_point = old_code.find('def direct_answer')
            
            new_code = old_code[:insert_point] + new_function + "\n\n" + old_code[insert_point:]
            result = update_file("bot.py", new_code, f"Add: {description[:50]}")
            
            if "✅" in result:
                send_message(chat_id, f"✅ Функция добавлена!\n```python\n{new_function[:300]}\n```")
                time.sleep(2)
                trigger_render_deploy()
                return "🔄 Перезапускаюсь... Новая функция появится через минуту."
            return f"❌ {result}"
        return f"❌ Ошибка ИИ: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# ОСНОВНЫЕ ФУНКЦИИ
# ============================================================
def get_current_time() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def direct_answer(prompt: str) -> str:
    headers = {'Authorization': f'Bearer {OPENROUTER_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': 'openrouter/free', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 300}
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f"❌ Ошибка API: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def process_command(text: str, chat_id: int) -> str:
    text_lower = text.lower()
    
    # Наблюдение
    if text_lower in ['/status', 'статус']:
        s = get_render_status()
        return f"📊 Статус: {s.get('status', '?')}" if 'error' not in s else f"❌ {s['error']}"
    
    if text_lower in ['/logs', 'логи']:
        return get_render_logs(15)
    
    if text_lower in ['/commits', 'коммиты']:
        return get_recent_commits(5)
    
    # Управление
    if text_lower in ['/restart', 'перезапусти меня']:
        return trigger_render_deploy()
    
    if text_lower in ['/step', 'шаг']:
        return self_improve_step(chat_id)
    
    if text_lower in ['/analyze', 'анализ']:
        return analyze_self(chat_id)['report']
    
    # Добавление функций
    if text_lower.startswith('/add '):
        desc = text[5:]
        return generate_new_function(desc, chat_id)
    
    # Поиск через браузер
    if any(word in text_lower for word in ['найди', 'поищи', 'загугли']):
        clean = re.sub(r'(?i)(найди|поищи|загугли)\s*', '', text).strip()
        if not clean:
            clean = text
        return search_with_browser(clean)
    
    # Время
    if any(word in text_lower for word in ['время', 'дата']):
        return f"🕐 {get_current_time()}"
    
    return direct_answer(text)

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
        print(f"Ошибка: {e}")

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
    return '🐶 Гаврюша — автономный агент с браузером!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            if user_text.startswith('/') and not any(user_text.startswith(cmd) for cmd in ['/status', '/logs', '/restart', '/step', '/add', '/analyze']):
                if user_text == '/help' or user_text == '/start':
                    send_message(chat_id, """🐶 **Гаврюша — команды:**

📊 **Наблюдение:**
/status — статус на Render
/logs — логи деплоя
/commits — последние коммиты
/analyze — анализ состояния

⚙️ **Управление:**
/restart — перезапустить
/step — шаг самоулучшения

➕ **Самообновление:**
/add описание — добавить новую функцию

🌐 **Поиск:**
найди, поищи, загугли — через браузер""")
                return jsonify({'status': 'ok'}), 200
            
            deactivate_expired_chats()
            
            if ACTIVATION_WORD.lower() in user_text.lower() or user_text.startswith('/'):
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip() if ACTIVATION_WORD in user_text.lower() else user_text
                
                if not clean_text or clean_text == user_text:
                    reply = "🐶 Гаврюша здесь! /help"
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
    print("🚀 Запуск Гаврюши с браузером и самообновлением...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
