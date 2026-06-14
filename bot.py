import os
import re
import asyncio
import gc
import requests
from flask import Flask, request, jsonify
from datetime import datetime
from playwright.async_api import async_playwright

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

# ============================================================
# ОПТИМИЗИРОВАННЫЙ БРАУЗЕР
# ============================================================
async def browse_website(url: str, wait_for: str = None) -> str:
    """Максимально оптимизированный браузер для Render"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-first-run',
                    '--no-sandbox',
                    '--disable-accelerated-2d-canvas',
                    '--disable-webgl',
                    '--max_old_space_size=64'
                ]
            )
            page = await browser.new_page()
            await page.set_viewport_size({"width": 800, "height": 600})
            await page.goto(url, timeout=20000, wait_until='domcontentloaded')
            
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=5000)
                except:
                    pass
            
            text = await page.evaluate('document.body.innerText')
            text = text[:1500]
            
            await browser.close()
            gc.collect()
            
            return f"🌐 Содержимое сайта {url}:\n\n{text}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def extract_urls(text: str):
    """Находит все ссылки в тексте"""
    url_pattern = r'https?://[^\s]+'
    return re.findall(url_pattern, text)

# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================
def get_ai_response(prompt, chat_id=None):
    urls = extract_urls(prompt)
    
    if urls:
        url = urls[0]
        print(f"🌐 Открываю: {url}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        page_content = loop.run_until_complete(browse_website(url))
        loop.close()
        
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'model': 'google/gemma-4-31b-it:free',
            'messages': [
                {'role': 'user', 'content': f"""Пользователь отправил ссылку: {prompt}

Содержимое страницы:
{page_content}

Ответь на вопрос, используя информацию с этой страницы. Если информации нет — скажи честно."""}
            ],
            'max_tokens': 1000,
            'temperature': 0.7
        }
        
        try:
            response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            return f"{page_content}"
        except:
            return page_content
    
    # Обычный ответ
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    payload = {
        'model': 'google/gemma-4-31b-it:free',
        'messages': [
            {'role': 'system', 'content': f'Ты — помощник. Сегодня {current_time}. Отвечай кратко и по делу.'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
        if response.status_code != 200:
            return f"❌ Ошибка API ({response.status_code})"
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# TELEGRAM
# ============================================================
@app.route('/')
def home():
    return '🤖 Оптимизированный агент работает!'

@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if 'message' in data and 'text' in data['message']:
            chat_id = data['message']['chat']['id']
            user_text = data['message']['text']
            
            if user_text.startswith('/'):
                return jsonify({'status': 'ok'}), 200
            
            bot_reply = get_ai_response(user_text, chat_id)
            send_telegram_message(chat_id, bot_reply)
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'status': 'error'}), 500

def send_telegram_message(chat_id, text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text[:4000], 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        print(f"Telegram ошибка: {e}")

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
    print("🚀 Запуск оптимизированного агента...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
