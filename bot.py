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
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def get_ai_response(prompt):
    """Отправляет запрос к DeepSeek R1 через OpenRouter"""
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': WEBHOOK_URL,
    }
    
    payload = {
        'model': 'deepseek/deepseek-r1:free',   # ← DeepSeek R1
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"OpenRouter ошибка: {e}")
        return "Извините, сейчас проблема с подключением к ИИ. Попробуйте позже."

def send_telegram_message(chat_id, text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram ошибка: {e}")

def set_webhook():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не установлен!")
        return
    webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook'
    response = requests.post(url, json={'url': webhook_url})
    if response.ok:
        print(f"✅ Вебхук установлен: {webhook_url}")
    else:
        print(f"❌ Ошибка: {response.text}")

if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
