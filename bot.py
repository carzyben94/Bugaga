import os
import re
import json
import time
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from unbrowser import Client

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

# ============================================================
# РАСШИРЕННЫЕ ИНСТРУМЕНТЫ АГЕНТА
# ============================================================

def google_search(query: str) -> str:
    """Открывает Google, ищет запрос и возвращает результаты"""
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        print(f"🔍 Гаврюша открывает Google: {search_url}")
        
        with Client() as ub:
            result = ub.navigate(search_url)
            
            # Ждём загрузки результатов
            time.sleep(2)
            
            if hasattr(result, 'blockmap') and result.blockmap:
                content = result.blockmap
                # Извлекаем только результаты поиска (регуляркой)
                results_match = re.search(r'(?i)(about.*results|результатов.*найдено)(.+?)(?=\n\n|\Z)', content, re.DOTALL)
                if results_match:
                    return f"🔎 Результаты поиска Google по запросу '{query}':\n\n{results_match.group(2)[:1500]}"
                return f"🔎 Результаты поиска Google по запросу '{query}':\n\n{content[:1500]}"
        
        return f"Не удалось выполнить поиск в Google"
    except Exception as e:
        return f"Ошибка Google поиска: {str(e)}"

def search_web(query: str) -> str:
    """Универсальный поиск (DuckDuckGo, быстрее)"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={query}"
        with Client() as ub:
            result = ub.navigate(url)
            if hasattr(result, 'blockmap') and result.blockmap:
                return f"🔍 Результаты поиска '{query}':\n\n{result.blockmap[:1500]}"
        return f"Не удалось найти: {query}"
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

def open_url(url: str) -> str:
    """Открывает конкретный сайт"""
    try:
        with Client() as ub:
            result = ub.navigate(url)
            if hasattr(result, 'blockmap') and result.blockmap:
                return f"📄 Содержимое {url}:\n\n{result.blockmap[:2000]}"
            return "Не удалось получить содержимое"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def get_current_time() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

# ============================================================
# МОЗГ - ПРИНИМАЕТ РЕШЕНИЕ
# ============================================================
class Brain:
    def __init__(self):
        self.memory = {}
    
    def think(self, prompt: str, chat_id: int) -> str:
        # Проверяем, есть ли ссылка
        urls = re.findall(r'https?://[^\s]+', prompt)
        if urls:
            return open_url(urls[0])
        
        # Проверяем явные команды
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ['время', 'дата', 'который час']):
            return get_current_time()
        
        # Для поиска пробуем Google
        if any(word in prompt_lower for word in ['найди', 'поищи', 'загугли', 'найди в интернете', 'google', 'новости']):
            # Убираем слова-команды
            clean_query = prompt
            for word in ['найди', 'поищи', 'загугли', 'найди в интернете', 'google']:
                clean_query = clean_query.lower().replace(word, '').strip()
            if not clean_query:
                clean_query = prompt
            
            print(f"🧠 Мозг решил: поискать в Google '{clean_query}'")
            return google_search(clean_query)
        
        # Обычный ответ через ИИ
        return self.direct_answer(prompt)
    
    def direct_answer(self, prompt: str) -> str:
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        payload = {
            'model': 'openrouter/free',
            'messages': [
                {'role': 'system', 'content': f'Ты — Гаврюша, умный помощник. Сегодня {current_time}. Отвечай кратко, 2-3 предложения.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 300,
            'temperature': 0.7
        }
        try:
            response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return f"Ошибка: {response.status_code}"
        except Exception as e:
            return f"Ошибка: {str(e)}"

brain = Brain()

# ============================================================
# АГЕНТ ГАВРЮША
# ============================================================
def process_message(text: str, chat_id: int) -> str:
    print(f"🐶 Гаврюша обрабатывает: {text[:50]}...")
    return brain.think(text, chat_id)

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
    expired = [chat_id for chat_id, last_active in active_chats.items() 
               if now - last_active > timedelta(minutes=ACTIVE_TIMEOUT)]
    for chat_id in expired:
        del active_chats[chat_id]

@app.route('/')
def home():
    return '🐶 Гаврюша с Google поиском!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            if user_text.startswith('/'):
                return jsonify({'status': 'ok'}), 200
            
            deactivate_expired_chats()
            
            if ACTIVATION_WORD.lower() in user_text.lower():
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip()
                if not clean_text:
                    reply = "🐶 Гаврюша здесь! Могу искать в Google, открывать сайты, отвечать на вопросы. Что нужно?"
                else:
                    reply = process_message(clean_text, chat_id)
                send_message(chat_id, reply)
            elif is_chat_active(chat_id):
                reply = process_message(user_text, chat_id)
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
    print("🚀 Запуск Гаврюши с Google поиском...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
