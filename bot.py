import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from pylightpanda import LightpandaClient

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

# ============================================================
# БРАУЗЕР Lightpanda (через Python SDK)
# ============================================================
async def search_lightpanda(query: str) -> str:
    """Поиск через Lightpanda (быстро и легко)"""
    try:
        async with LightpandaClient() as client:
            session = await client.create_session()
            # Используем DuckDuckGo — Lightpanda с ним работает [citation:4]
            result = await session.navigate(f"https://html.duckduckgo.com/html/?q={query}")
            content = await session.get_content()
            await session.destroy()
            
            if content and content.text:
                return f"🔍 <b>Результаты поиска '{query}':</b>\n\n{content.text[:2000]}"
            return f"😕 Ничего не найдено по запросу: {query}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def open_url_lightpanda(url: str) -> str:
    """Открывает сайт через Lightpanda"""
    try:
        async with LightpandaClient() as client:
            session = await client.create_session()
            nav = await session.navigate(url)
            content = await session.get_content()
            await session.destroy()
            
            return f"📄 <b>Содержимое {url}:</b>\n\n{content.text[:1500]}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def get_current_time() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

# ============================================================
# МОЗГ (ИИ) — ПРИНИМАЕТ РЕШЕНИЯ, ГАВРЮША — ИСПОЛНЯЕТ
# ============================================================
class Brain:
    def __init__(self):
        self.memory = {}
    
    def think(self, prompt: str, chat_id: int) -> str:
        import asyncio
        prompt_lower = prompt.lower()
        
        # Время
        if any(word in prompt_lower for word in ['время', 'дата', 'который час']):
            return f"🕐 {get_current_time()}"
        
        # Ссылка
        urls = re.findall(r'https?://[^\s]+', prompt)
        if urls:
            return asyncio.run(open_url_lightpanda(urls[0]))
        
        # Поиск в интернете
        if any(word in prompt_lower for word in ['найди', 'поищи', 'загугли', 'новости']):
            clean_query = prompt
            for word in ['найди', 'поищи', 'загугли', 'найди в интернете']:
                clean_query = clean_query.lower().replace(word, '').strip()
            if not clean_query:
                clean_query = prompt
            return asyncio.run(search_lightpanda(clean_query))
        
        # Обычный ответ
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
                {'role': 'system', 'content': f'Ты — Гаврюша. Сегодня {current_time}. Отвечай кратко, 2-3 предложения.'},
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
    return '🐶 Гаврюша с Lightpanda браузером!'

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
                    reply = "🐶 Гаврюша здесь! Могу искать в интернете через Lightpanda, открывать сайты, отвечать на вопросы."
                else:
                    reply = brain.think(clean_text, chat_id)
                send_message(chat_id, reply)
            elif is_chat_active(chat_id):
                reply = brain.think(user_text, chat_id)
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
    print("🚀 Запуск Гаврюши с Lightpanda...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
