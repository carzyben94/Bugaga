import os
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

# ============================================================
# 1. Функция поиска через DuckDuckGo (бесплатно)
# ============================================================
def web_search(query: str, max_results: int = 5) -> str:
    """Ищет в интернете через DuckDuckGo и возвращает результаты"""
    url = f"https://html.duckduckgo.com/html/?q={query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for result in soup.find_all('div', class_='result')[:max_results]:
            title_tag = result.find('a', class_='result__a')
            snippet_tag = result.find('a', class_='result__snippet')
            
            if title_tag:
                title = title_tag.get_text(strip=True)
                link = title_tag.get('href', '')
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''
                results.append(f"• {title}\n  {link}\n  {snippet[:300]}")
        
        if results:
            return "🔍 Результаты поиска:\n\n" + "\n\n".join(results)
        return f"Ничего не найдено по запросу: {query}"
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

# ============================================================
# 2. Основная функция ИИ с поддержкой поиска
# ============================================================
def get_ai_response(prompt):
    """Gemma 4 с возможностью поиска в интернете"""
    
    # Проверяем, просит ли пользователь найти что-то в интернете
    search_keywords = ['найди в интернете', 'поищи', 'загугли', 'найди информацию', 'посмотри в сети', 'найди в сети', 'search']
    need_search = any(keyword in prompt.lower() for keyword in search_keywords)
    
    # Если пользователь явно попросил поискать — сразу идём в DuckDuckGo
    if need_search:
        print(f"🔍 Пользователь запросил поиск: {prompt}")
        search_query = prompt
        for keyword in search_keywords:
            search_query = search_query.lower().replace(keyword, '').strip()
        if not search_query:
            search_query = prompt
        search_results = web_search(search_query)
        
        # Отправляем результаты в Gemma для ответа
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        final_payload = {
            'model': 'google/gemma-4-31b-it:free',
            'messages': [
                {'role': 'user', 'content': f"""Вопрос пользователя: {prompt}

Вот результаты поиска из интернета:
{search_results}

Пожалуйста, ответь на вопрос пользователя, используя информацию из результатов поиска. Дай понятный и структурированный ответ."""}
            ],
            'max_tokens': 1500,
            'temperature': 0.7
        }
        try:
            response = requests.post(OPENROUTER_URL, json=final_payload, headers=headers, timeout=60)
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            return f"❌ Ошибка: {str(e)}\n\nРезультаты поиска:\n{search_results}"
    
    # Если пользователь не просил искать — спрашиваем модель, нужен ли поиск
    check_prompt = f"""Ты — умный ассистент. Если для ответа на вопрос нужна свежая информация из интернета (новости, погода, спорт, текущие события, курсы валют, цены, актуальные данные) — напиши только слово "SEARCH". Если можешь ответить на основе своих знаний — напиши "ANSWER".

Вопрос: {prompt}

Твоё решение (только SEARCH или ANSWER):"""
    
    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'model': 'nvidia/nemotron-3-ultra:free',
        'messages': [{'role': 'user', 'content': check_prompt}],
        'max_tokens': 10,
        'temperature': 0
    }
    
    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=30)
        decision = response.json()['choices'][0]['message']['content'].strip()
        
        # Если нужен поиск — ищем и отдаём результаты модели
        if "SEARCH" in decision:
            print(f"🔍 Модель решила поискать: {prompt}")
            search_results = web_search(prompt)
            
            final_payload = {
                'model': 'google/gemma-4-31b-it:free',
                'messages': [
                    {'role': 'user', 'content': f"""Вопрос пользователя: {prompt}

Вот результаты поиска из интернета:
{search_results}

Пожалуйста, ответь на вопрос пользователя, используя информацию из результатов поиска. Если информация неполная — честно скажи об этом. Дай понятный и структурированный ответ."""}
                ],
                'max_tokens': 1500,
                'temperature': 0.7
            }
            final_response = requests.post(OPENROUTER_URL, json=final_payload, headers=headers, timeout=60)
            return final_response.json()['choices'][0]['message']['content']
        else:
            # Поиск не нужен — отвечаем сразу
            normal_payload = {
                'model': 'google/gemma-4-31b-it:free',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 1000,
                'temperature': 0.7
            }
            normal_response = requests.post(OPENROUTER_URL, json=normal_payload, headers=headers, timeout=45)
            return normal_response.json()['choices'][0]['message']['content']
            
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# 3. Telegram обработка
# ============================================================
@app.route('/')
def home():
    return '🤖 Бот работает с поиском! Напишите "найди в интернете ..."'

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
