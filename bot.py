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
# СПИСОК ДОСТУПНЫХ БРАУЗЕРОВ
# ============================================================
BROWSERS = {
    "1": {
        "name": "Lightpanda",
        "description": "Лёгкий браузер для AI-агентов, мало памяти (~30 MB)",
        "dockerfile": '''FROM lightpanda/browser:nightly

WORKDIR /app

RUN apt-get update && apt-get install -y python3 python3-pip -y

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY bot.py .

CMD lightpanda serve --host 0.0.0.0 --port 9222 & sleep 5 && python3 bot.py''',
        "requirements": "websocket-client"
    },
    "2": {
        "name": "Playwright",
        "description": "Мощный браузер, но тяжёлый (~500 MB памяти)",
        "dockerfile": '''FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y python3 python3-pip && pip3 install playwright && playwright install chromium

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY bot.py .

CMD python3 bot.py''',
        "requirements": "playwright"
    },
    "3": {
        "name": "Selenium",
        "description": "Классический браузер с Chrome",
        "dockerfile": '''FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y wget gnupg unzip curl
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list
RUN apt-get update && apt-get install -y google-chrome-stable
RUN pip3 install selenium webdriver-manager

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY bot.py .

CMD python3 bot.py''',
        "requirements": "selenium webdriver-manager"
    },
    "4": {
        "name": "BeautifulSoup",
        "description": "Только парсинг HTML, самый лёгкий (без браузера)",
        "dockerfile": '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY bot.py .

CMD python3 bot.py''',
        "requirements": "beautifulsoup4"
    }
}

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
# ОСНОВНАЯ ЛОГИКА (ИИ)
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
# УСТАНОВКА БРАУЗЕРОВ
# ============================================================
def show_browsers_list(chat_id: int) -> str:
    """Показывает список доступных браузеров"""
    message = "🌐 **Доступные браузеры для установки:**\n\n"
    for key, browser in BROWSERS.items():
        message += f"**{key}. {browser['name']}**\n"
        message += f"   {browser['description']}\n\n"
    message += "📝 **Как установить:**\n"
    message += "Напиши `/install 1` или `/install lightpanda`\n"
    message += "Например: `/install 1` — установит Lightpanda"
    return message

def install_browser(chat_id: int, choice: str) -> str:
    """Устанавливает выбранный браузер"""
    
    # Определяем выбор
    selected = None
    if choice in BROWSERS:
        selected = BROWSERS[choice]
    else:
        for key, browser in BROWSERS.items():
            if choice.lower() in browser['name'].lower():
                selected = browser
                break
    
    if not selected:
        return f"❌ Браузер '{choice}' не найден. Напиши /browsers для списка."
    
    send_message(chat_id, f"🔧 Устанавливаю {selected['name']}...")
    
    changes = []
    
    # 1. Обновляем Dockerfile
    result = update_file("Dockerfile", selected['dockerfile'], f"Install {selected['name']} browser")
    changes.append(f"📦 {result}")
    
    # 2. Обновляем requirements.txt
    req_content = f"flask\nrequests\ngunicorn\n{selected['requirements']}"
    result2 = update_file("requirements.txt", req_content, f"Add requirements for {selected['name']}")
    changes.append(f"📋 {result2}")
    
    # 3. Перезапускаем
    time.sleep(2)
    trigger_render_deploy()
    
    result_msg = f"✅ **{selected['name']} установлен!**\n\n"
    result_msg += "\n".join(changes)
    result_msg += "\n\n🔄 Перезапускаюсь для применения..."
    
    return result_msg

# ============================================================
# ОБРАБОТКА СООБЩЕНИЙ
# ============================================================
def handle_message(text: str, chat_id: int) -> str:
    text_lower = text.lower()
    
    # Команды
    if text_lower == '/browsers' or text_lower == 'список браузеров':
        return show_browsers_list(chat_id)
    
    if text_lower.startswith('/install '):
        choice = text[9:].strip()
        return install_browser(chat_id, choice)
    
    if text_lower in ['/help', '/start']:
        return """🐶 **Гаврюша — команды:**

🌐 **Браузеры:**
/browsers — показать список браузеров
/install номер_или_имя — установить браузер

📝 **Примеры:**
/install 1
/install lightpanda

💬 **Просто общение:**
Гаврюша привет — ИИ ответит
"""
    
    # Обычный ответ через ИИ
    return ask_ai(text)

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

@app.route('/')
def home():
    return '🐶 Гаврюша с установкой браузеров!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            # Обработка команд (всегда)
            if user_text.startswith('/'):
                reply = handle_message(user_text, chat_id)
                send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            # Активация по слову "Гаврюша"
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
    print("🚀 Запуск Гаврюши с установкой браузеров...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
