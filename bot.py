import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

@app.route('/')
def home():
    return '🤖 Бот работает! Отправьте сообщение в Telegram.'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            bot_reply = get_ai_response(user_text)
            send_telegram_message(chat_id, bot_reply)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка в webhook: {e}")
        return jsonify({'status': 'error'}), 500

def get_ai_response(prompt):
    """Отправляет запрос к OpenRouter и возвращает ответ"""
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'model': 'google/gemma-4-31b-it:free',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    
    try:
        print(f"📤 Отправка запроса к OpenRouter...")
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
        
        print(f"📥 Статус ответа: {response.status_code}")
        
        # Если статус не 200 — возвращаем ошибку
        if response.status_code != 200:
            return f"❌ Ошибка API ({response.status_code}): {response.text[:300]}"
        
        # Парсим JSON
        result = response.json()
        
        # Проверяем структуру ответа
        if 'choices' not in result:
            return f"❌ Неожиданный ответ API: {str(result)[:300]}"
        
        if len(result['choices']) == 0:
            return "❌ API вернул пустой ответ"
        
        # Получаем текст ответа
        message = result['choices'][0].get('message', {})
        content = message.get('content', '')
        
        if not content:
            return "❌ Ответ от API пустой"
        
        return content
        
    except requests.exceptions.Timeout:
        return "❌ Таймаут: OpenRouter не ответил за 60 секунд"
    except requests.exceptions.ConnectionError:
        return "❌ Ошибка подключения к OpenRouter"
    except Exception as e:
        return f"❌ Ошибка: {type(e).__name__}: {str(e)}"

def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Ошибка отправки в Telegram: {response.text}")
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def set_webhook():
    """Устанавливает вебхук при запуске"""
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
            print(f"❌ Ошибка установки вебхука: {response.text}")
    except Exception as e:
        print(f"❌ Ошибка при установке вебхука: {e}")

if __name__ == '__main__':
    print("🚀 Запуск бота...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    print(f"📡 Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
