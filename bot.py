import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from unbrowser import Client

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

ACTIVATION_WORD = "гаврюша"

# Храним активные чаты и время последнего сообщения
active_chats = {}  # chat_id -> время последней активности
ACTIVE_TIMEOUT = 10  # минут активности после последнего сообщения

# ============================================================
# ФУНКЦИИ
# ============================================================
def fetch_url(url: str) -> str:
    try:
        with Client() as ub:
            result = ub.navigate(url)
            if hasattr(result, 'blockmap') and result.blockmap:
                return result.blockmap[:2000]
            return "Не удалось получить содержимое"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def extract_urls(text: str):
    return re.findall(r'https?://[^\s]+', text)

def call_llm(prompt: str) -> str:
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    payload = {
        'model': 'openrouter/free',
        'messages': [
            {'role': 'system', 'content': f'Ты — Гаврюша, умный помощник. Сегодня {current_time}. Отвечай дружелюбно и полезно.'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f"❌ Ошибка API: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def process_message(text: str) -> str:
    urls = extract_urls(text)
    if urls:
        print(f"🌐 Открываю сайт: {urls[0]}")
        page_content = fetch_url(urls[0])
        
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': 'openrouter/free',
            'messages': [
                {'role': 'user', 'content': f"""Пользователь попросил: {text}

Содержимое сайта {urls[0]}:
{page_content}

Ответь на вопрос пользователя, используя информацию с этой страницы."""}
            ],
            'max_tokens': 1000,
            'temperature': 0.7
        }
        try:
            response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return f"📄 Содержимое сайта:\n\n{page_content}"
        except Exception as e:
            return f"📄 Содержимое сайта:\n\n{page_content}\n\n(Ошибка ИИ: {str(e)})"
    
    return call_llm(text)

# ============================================================
# TELEGRAM С СОСТОЯНИЕМ АКТИВНОСТИ
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
    """Проверяет, активен ли чат"""
    if chat_id not in active_chats:
        return False
    last_active = active_chats[chat_id]
    return datetime.now() - last_active < timedelta(minutes=ACTIVE_TIMEOUT)

def set_chat_active(chat_id: int):
    """Делает чат активным"""
    active_chats[chat_id] = datetime.now()

def deactivate_expired_chats():
    """Очищает неактивные чаты"""
    now = datetime.now()
    expired = [chat_id for chat_id, last_active in active_chats.items() 
               if now - last_active > timedelta(minutes=ACTIVE_TIMEOUT)]
    for chat_id in expired:
        del active_chats[chat_id]

@app.route('/')
def home():
    return '🤖 Гаврюша ждёт активации!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            if user_text.startswith('/'):
                return jsonify({'status': 'ok'}), 200
            
            # Очищаем неактивные чаты
            deactivate_expired_chats()
            
            # Проверяем активацию
            if ACTIVATION_WORD.lower() in user_text.lower():
                # Активируем чат
                set_chat_active(chat_id)
                # Убираем слово активации
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip()
                if not clean_text:
                    reply = "🐶 Гаврюша активирован! Теперь просто пиши мне, не нужно повторять 'Гаврюша'. Чем могу помочь?"
                else:
                    reply = process_message(clean_text)
                send_message(chat_id, reply)
            
            elif is_chat_active(chat_id):
                # Чат активен — отвечаем
                reply = process_message(user_text)
                send_message(chat_id, reply)
                # Обновляем время активности
                set_chat_active(chat_id)
            else:
                # Не активен и нет ключевого слова — молчим
                print(f"🔇 Бот проигнорировал (чат не активен): {user_text[:50]}")
        
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
    print("🚀 Запуск Гаврюши с сохранением активности...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
