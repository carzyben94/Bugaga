import os
import re
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://ваш-бот.onrender.com')

# Render API
RENDER_API_KEY = os.environ.get('RENDER_API_KEY')
RENDER_SERVICE_ID = os.environ.get('RENDER_SERVICE_ID')
RENDER_API_URL = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}" if RENDER_SERVICE_ID else None

ACTIVATION_WORD = "гаврюша"
active_chats = {}
ACTIVE_TIMEOUT = 10

# ============================================================
# RENDER API
# ============================================================
def render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}

def get_render_logs(limit: int = 20) -> str:
    """Получить последние логи деплоя"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен. Добавь RENDER_API_KEY и RENDER_SERVICE_ID в переменные."
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.get(url, headers=render_headers())
        if response.status_code == 200:
            deploys = response.json()
            if deploys:
                last_deploy_id = deploys[0]['id']
                logs_url = f"{RENDER_API_URL}/deploys/{last_deploy_id}/logs"
                logs_response = requests.get(logs_url, headers=render_headers())
                if logs_response.status_code == 200:
                    logs = logs_response.text.split('\n')[-limit:]
                    return "📋 **Последние логи:**\n```\n" + "\n".join(logs) + "\n```"
            return "❌ Нет деплоев"
        return f"❌ Ошибка API: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def get_render_status() -> str:
    """Получить статус сервиса"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        response = requests.get(RENDER_API_URL, headers=render_headers())
        if response.status_code == 200:
            data = response.json()
            return f"""📊 **Статус Гаврюши:**
• Статус: {data.get('status', 'unknown')}
• Auto Deploy: {data.get('autoDeploy', 'no')}
• Ветка: {data.get('branch', 'unknown')}
• Обновлён: {data.get('updatedAt', 'unknown')[:10]}"""
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def trigger_render_deploy() -> str:
    """Запустить деплой"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "❌ Render API не настроен"
    try:
        url = f"{RENDER_API_URL}/deploys"
        response = requests.post(url, json={"clearCache": "do_not_clear"}, headers=render_headers())
        if response.status_code == 201:
            return "🔄 Перезапускаюсь... Вернусь через минуту!"
        return f"❌ Ошибка: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def get_current_time() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def direct_answer(prompt: str) -> str:
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
        return f"❌ Ошибка API: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# ОБРАБОТЧИК КОМАНД (ОТДЕЛЬНО ОТ ОБЫЧНЫХ СООБЩЕНИЙ)
# ============================================================
def handle_command(cmd: str) -> str:
    """Обрабатывает только команды, начинающиеся с /"""
    cmd_lower = cmd.lower()
    
    if cmd_lower == '/status':
        return get_render_status()
    
    if cmd_lower == '/logs':
        return get_render_logs(20)
    
    if cmd_lower == '/restart':
        return trigger_render_deploy()
    
    if cmd_lower == '/time':
        return f"🕐 {get_current_time()}"
    
    if cmd_lower == '/start' or cmd_lower == '/help':
        return """🐶 **Гаврюша — команды:**

/status — статус сервиса на Render
/logs — последние логи деплоя
/restart — перезапустить бота
/time — текущее время
/help — эта справка

Активация: просто напиши **Гаврюша** перед вопросом
Пример: *Гаврюша найди новости*"""
    
    return None  # не распознана как команда

# ============================================================
# ОБРАБОТКА ОБЫЧНЫХ СООБЩЕНИЙ
# ============================================================
def process_message(text: str) -> str:
    text_lower = text.lower()
    
    # Время (без команды /time)
    if any(word in text_lower for word in ['время', 'дата', 'который час']):
        return f"🕐 {get_current_time()}"
    
    # Поиск
    if any(word in text_lower for word in ['найди', 'поищи', 'загугли', 'новости']):
        clean_query = text
        for word in ['найди', 'поищи', 'загугли', 'найди в интернете']:
            clean_query = re.sub(rf'(?i){word}\s*', '', clean_query).strip()
        if not clean_query:
            clean_query = text
        return f"🔍 Поиск '{clean_query}':\n(поиск временно использует ИИ)"
    
    # Обычный ответ
    return direct_answer(text)

# ============================================================
# TELEGRAM
# ============================================================
def send_message(chat_id: int, text: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        if len(text) > 4000:
            text = text[:4000] + "\n\n(обрезано)"
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
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
            
            # ========== ПРОВЕРКА НА КОМАНДЫ (ВСЕГДА) ==========
            if user_text.startswith('/'):
                reply = handle_command(user_text)
                if reply:
                    send_message(chat_id, reply)
                return jsonify({'status': 'ok'}), 200
            
            # ========== АКТИВАЦИЯ ПО СЛОВУ "ГАВРЮША" ==========
            if ACTIVATION_WORD.lower() in user_text.lower():
                set_chat_active(chat_id)
                clean_text = re.sub(re.escape(ACTIVATION_WORD), '', user_text, flags=re.IGNORECASE).strip()
                if not clean_text:
                    reply = "🐶 Гаврюша здесь! Напиши /help для списка команд"
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
    print("🚀 Запуск Гаврюши...")
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
