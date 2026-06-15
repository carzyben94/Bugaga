import os
import time
import logging
import json
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ВРЕМЯ ЗАПУСКА =====
with open("start_time.txt", "w") as f:
    f.write(str(time.time()))

# ===== API КЛЮЧИ =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== ПОДКЛЮЧАЕМ СТАТУС ИЗ ОТДЕЛЬНОГО ФАЙЛА =====
try:
    from status import register_status_full
    register_status_full(bot)
    logger.info("✅ Модуль status загружен")
except ImportError as e:
    logger.warning(f"❌ Не удалось загрузить status: {e}")

# ===== ЛОГИРОВАНИЕ ДЕЙСТВИЙ =====
def log_action(action, details=None, status="info"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open("agent_actions.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        logger.info(f"[ЛОГ] {action}: {details}")
    except Exception as e:
        logger.error(f"Ошибка записи лога: {e}")

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start', 'help', 'menu'])
def menu_command(message):
    log_action("command_menu", f"user_id={message.from_user.id}")
    menu_text = """📋 **МЕНЮ БОТА**

**🧠 ИИ И ПОИСК**
/ai [вопрос] — спросить ИИ

**📊 МОНИТОРИНГ**
/status_full — полный статус бота

💡 Напиши /status_full для полной статистики"""
    bot.reply_to(message, menu_text, parse_mode="Markdown")

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "❌ Напиши вопрос после /ai\nПример: /ai Как работает ИИ?")
        return
    
    log_action("command_ai", f"user_id={message.from_user.id}, query={user_text[:50]}")
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    if not OPENROUTER_API_KEY:
        bot.edit_message_text("❌ OPENROUTER_API_KEY не настроен", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    try:
        import requests
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": user_text}],
            "max_tokens": 500
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                                 headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            answer = response.json()["choices"][0]["message"]["content"]
            bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)
        else:
            bot.edit_message_text(f"❌ Ошибка API: {response.status_code}", 
                                  chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return 'error', 500

@app.route('/health')
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
