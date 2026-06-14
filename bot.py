import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# URL вебхука (ваш адрес на Render)
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

@app.route('/')
def home():
    return '🤖 Бот работает! Отправьте сообщение в Telegram.'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Принимает сообщения из Telegram"""
    try:
        data = request.get_json()
        
        # Проверяем, что это сообщение от пользователя
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            # Получаем ответ от DeepSeek
            bot_reply = get_deepseek_response(user_text)
            
            # Отправляем ответ в Telegram
            send_telegram_message(chat_id, bot_reply)
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def get_deepseek_response(prompt):
    """Отправляет запрос к DeepSeek API"""
    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'stream': False
    }
    
    try:
        response = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"DeepSeek ошибка: {e}")
        return "Извините, я сейчас не могу ответить. Попробуйте позже."

def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def set_webhook():
    """Устанавливает вебхук при запуске"""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не установлен!")
        return
    
    webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook'
    
    response = requests.post(url, json={'url': webhook_url})
    if response.ok:
        print(f"✅ Вебхук установлен: {webhook_url}")
    else:
        print(f"❌ Ошибка установки вебхука: {response.text}")

if __name__ == '__main__':
    # Устанавливаем вебхук при запуске
    set_webhook()
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
