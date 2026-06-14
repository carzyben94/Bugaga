import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime
from unbrowser import Client

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

# Ключевая фраза для активации
ACTIVATION_PHRASE = "гаврюша ко мне"

# ============================================================
# ЛЁГКИЙ БРАУЗЕР ЧЕРЕЗ UNBROWSER
# ============================================================
def fetch_url(url: str) -> str:
    """Получает содержимое сайта через Unbrowser"""
    try:
        with Client() as ub:
            result = ub.navigate(url)
            if hasattr(result, 'blockmap') and result.blockmap:
                return result.blockmap[:2000]
            elif hasattr(result, 'text') and result.text:
                return result.text[:2000]
            return f"Не удалось извлечь содержимое с {url}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def extract_urls(text: str):
    """Находит ссылки в тексте"""
    url_pattern = r'https?://[^\s]+'
    return re.findall(url_pattern, text)

# ============================================================
# ПРОВЕРКА АКТИВАЦИИ
# ============================================================
def is_activated(message: str) -> bool:
    """Проверяет, позвали ли бота"""
    return ACTIVATION_PHRASE.lower() in message.lower()

def remove_activation_phrase(message: str) -> str:
    """Убирает фразу активации из сообщения"""
    pattern = re.compile(re.escape(ACTIVATION_PHRASE), re.IGNORECASE)
    return pattern.sub('', message).strip()

# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================
def get_ai_response(prompt: str) -> str:
    # Проверяем, есть ли ссылка
    urls = extract_urls(prompt)
    if urls:
        url = urls[0]
        print(f"🌐 Открываю: {url}")
        page_content = fetch_url(url)
        
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': 'nvidia/nemotron-3-ultra:free',
            'messages': [
                {'role': 'user', 'content': f"""Пользователь отправил: {prompt}

Содержимое сайта {url}:
{page_content}

Ответь на вопрос, используя информацию с этой страницы."""}
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
    
    # Обычный ответ без ссылки
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    payload = {
        'model': 'nvidia/nemotron-3-ultra:free',
        'messages': [
            {'role': 'system', 'content': f'Ты — помощник по имени Гаврюша. Сегодня {current_time}. Отвечай дружелюбно и по делу.'},
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

# ============================================================
# TELEGRAM С АКТИВАЦИЕЙ
# ============================================================
@app.route('/')
def home():
    return '🤖 Гаврюша ждёт команду "гаврюша ко мне"'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            # Игнорируем команды
            if user_text.startswith('/'):
                return jsonify({'status': 'ok'}), 200
            
            # Проверяем, позвали ли бота
            if is_activated(user_text):
                # Убираем фразу активации
                clean_text = remove_activation_phrase(user_text)
                if not clean_text:
                    reply = "🐶 Гаврюша здесь! Чем могу помочь?"
                else:
                    reply = get_ai_response(clean_text)
                send_message(chat_id, reply)
            else:
                # Не позвали — молчим
                print(f"🔇 Бот проигнорировал: {user_text[:50]}")
                pass
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def send_message(chat_id: int, text: str):
    """Отправляет сообщение в Telegram"""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        if len(text) > 4000:
            text = text[:4000] + "\n\n(обрезано)"
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def set_webhook():
    """Устанавливает вебхук"""
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
    print("🚀 Запуск Гаврюши на модели Nemotron-3 Ultra...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
