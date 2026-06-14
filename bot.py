import os
import re
import time
import base64
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ============================================================
# КОНФИГУРАЦИЯ (все API)
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

# ============================================================
# LIGHTPANDA НАСТРОЙКИ
# ============================================================
LIGHTPANDA_DOCKERFILE = '''FROM lightpanda/browser:nightly

WORKDIR /app

RUN apt-get update && apt-get install -y python3 python3-pip -y

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY bot.py .

CMD lightpanda serve --host 0.0.0.0 --port 9222 & sleep 5 && python3 bot.py'''

LIGHTPANDA_REQUIREMENTS = '''flask
requests
gunicorn
websocket-client'''

# ============================================================
# RENDER API
# ============================================================
def render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}

def trigger_render_deploy() -> str:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.post(url, json={"clearCache": "do_not_clear"}, headers=render_headers())
        if response.status_code == 201:
            return "🔄 Перезапускаюсь..."
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
            return f"✅ {filepath} обновлён"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# ПОИСК ЧЕРЕЗ БРАУЗЕР
# ============================================================
def search_with_browser(query: str) -> str:
    """Поиск через Lightpanda браузер"""
    try:
        import websocket
        import json
        
        ws_url = "ws://localhost:9222/devtools/browser"
        ws = websocket.create_connection(ws_url, timeout=10)
        
        search_url = f"https://lite.duckduckgo.com/lite/?q={query.replace(' ', '+')}"
        
        msg_id = 1
        ws.send(json.dumps({"id": msg_id, "method": "Page.navigate", "params": {"url": search_url}}))
        ws.recv()
        time.sleep(2)
        
        msg_id += 1
        ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": "document.body.innerText"}}))
        result = json.loads(ws.recv())
        text = result.get('result', {}).get('value', '')
        ws.close()
        
        lines = text.split('\n')
        results = []
        for line in lines:
            if 'http' in line and len(line) > 10:
                results.append(f"• {line[:150]}")
                if len(results) >= 5:
                    break
        
        if results:
            return "🔍 **Результаты поиска:**\n\n" + "\n".join(results)
        return f"😕 Ничего не найдено: {query}"
        
    except Exception as e:
        return f"❌ Браузер не установлен. Напиши /install_panda\nОшибка: {str(e)}"

# ============================================================
# ИИ ОТВЕТЫ
# ============================================================
def ask_ai(prompt: str) -> str:
    headers = {'Authorization': f'Bearer {OPENROUTER_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': 'openrouter/free', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 500}
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f"Ошибка API: {response.status_code}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

# ============================================================
# УСТАНОВКА LIGHTPANDA
# ============================================================
def install_lightpanda(chat_id: int) -> str:
    """Устанавливает Lightpanda браузер"""
    
    send_message(chat_id, "🔧 Устанавливаю Lightpanda браузер...")
    
    changes = []
    
    # 1. Обновляем Dockerfile
    result = update_file("Dockerfile", LIGHTPANDA_DOCKERFILE, "Install Lightpanda browser")
    changes.append(f"📦 {result}")
    
    # 2. Обновляем requirements.txt
    result2 = update_file("requirements.txt", LIGHTPANDA_REQUIREMENTS, "Add websocket-client for Lightpanda")
    changes.append(f"📋 {result2}")
    
    # 3. Перезапускаем
    time.sleep(2)
    trigger_render_deploy()
    
    result_msg = f"✅ **Lightpanda браузер установлен!**\n\n"
    result_msg += "\n".join(changes)
    result_msg += "\n\n🔄 Перезапускаюсь для применения...\n\nПосле перезапуска используй: `Гаврюша G запрос`"
    
    return result_msg

def send_message(chat_id: int, text: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        if len(text) > 4000:
            text = text[:4000] + "\n\n(обрезано)"
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
    except Exception as e:
        print(f"Ошибка: {e}")

# ============================================================
# ОСНОВНОЙ ВЕБХУК
# ============================================================
@app.route('/')
def home():
    return '🐶 Гаврюша со всеми API и установкой браузера!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            # ========== КОМАНДА /INSTALL_PANDA ==========
            if user_text.lower() == '/install_panda':
                reply = install_lightpanda(chat_id)
                send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            # ========== КОМАНДА "ГАВРЮША G" (ПОИСК) ==========
            if user_text.lower().startswith('гаврюша g'):
                search_query = user_text[9:].strip()
                if search_query:
                    reply = search_with_browser(search_query)
                else:
                    reply = "🔍 Напиши что искать после 'Гаврюша G'"
                send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            # ========== ОБЫЧНЫЕ КОМАНДЫ ==========
            if user_text.startswith('/'):
                if user_text.lower() in ['/help', '/start']:
                    reply = """🐶 **Гаврюша — команды:**

🔧 **Установка:**
/install_panda — установить Lightpanda браузер

🔍 **Поиск (после установки):**
Гаврюша G запрос

💬 **Обычный диалог:**
Гаврюша привет
"""
                    send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            # ========== АКТИВАЦИЯ "ГАВРЮША" ==========
            if ACTIVATION_WORD.lower() in user_text.lower():
                clean = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip()
                if not clean:
                    reply = "🐶 Гаврюша здесь! Чем могу помочь?"
                else:
                    reply = ask_ai(clean)
                send_message(chat_id, reply)
        
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
    print("🚀 Запуск Гаврюши с установкой браузера...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
