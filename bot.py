import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')

RENDER_API_KEY = os.environ.get('RENDER_API_KEY')
RENDER_SERVICE_ID = os.environ.get('RENDER_SERVICE_ID')
RENDER_API_URL = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}" if RENDER_SERVICE_ID else None

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

def render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}

def get_render_status() -> str:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        response = requests.get(RENDER_API_URL, headers=render_headers())
        if response.status_code == 200:
            data = response.json()
            return f"📊 **Статус:** {data.get('status', 'unknown')}\n🔄 Auto Deploy: {data.get('autoDeploy', 'no')}"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def trigger_restart() -> str:
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

def handle_command(cmd: str) -> str:
    cmd_lower = cmd.lower()
    if cmd_lower == '/status':
        return get_render_status()
    if cmd_lower == '/restart':
        return trigger_restart()
    if cmd_lower == '/time':
        return f"🕐 {get_current_time()}"
    if cmd_lower == '/help' or cmd_lower == '/start':
        return "🐶 **Гаврюша:**\n/status — статус\n/restart — перезапуск\n/time — время\n/help — справка"
    return None

def process_message(text: str) -> str:
    if any(word in text.lower() for word in ['время', 'дата']):
        return f"🕐 {get_current_time()}"
    return direct_answer(text)

def send_message(chat_id: int, text: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
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
    return '🐶 Гаврюша работает!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            deactivate_expired_chats()
            
            if user_text.startswith('/'):
                reply = handle_command(user_text)
                if reply:
                    send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            if ACTIVATION_WORD.lower() in user_text.lower():
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip()
                if not clean_text:
                    reply = "🐶 Гаврюша здесь! /help"
                else:
                    reply = process_message(clean_text)
                send_message(chat_id, reply)
            elif is_chat_active(chat_id):
                reply = process_message(user_text)
                send_message(chat_id, reply)
                set_chat_active(chat_id)
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def set_webhook():
    if TELEGRAM_TOKEN:
        webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook', json={'url': webhook_url})

if __name__ == '__main__':
    print("🚀 Запуск...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
