import os
import logging
import requests
from flask import Flask, request
import telebot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== АКТУАЛЬНЫЕ БЕСПЛАТНЫЕ МОДЕЛИ (июнь 2026) =====
FREE_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "poolside/laguna-m1:free",
    "poolside/laguna-xs2:free",
    "z-ai/glm-4.5-air:free",
    "moonshotai/kimi-k2.6:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
]

def ask_ai(prompt, model_index=0):
    if model_index >= len(FREE_MODELS):
        return "😵 Все бесплатные модели временно недоступны. Попробуйте позже."
    
    model = FREE_MODELS[model_index]
    logger.info(f"Пробуем модель: {model}")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.7,
    }
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45)
        
        if response.status_code == 200:
            answer = response.json()["choices"][0]["message"]["content"]
            logger.info(f"✅ Модель {model} ответила успешно")
            return answer
        
        elif response.status_code == 429:
            logger.warning(f"⚠️ Модель {model}: лимит, переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        elif response.status_code == 402:
            logger.warning(f"⚠️ Модель {model}: требуется оплата, переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        else:
            logger.warning(f"⚠️ Модель {model}: ошибка {response.status_code}, переключаем...")
            return ask_ai(prompt, model_index + 1)
            
    except requests.exceptions.Timeout:
        logger.warning(f"⚠️ Модель {model}: таймаут, переключаем...")
        return ask_ai(prompt, model_index + 1)
    except Exception as e:
        logger.error(f"❌ Модель {model}: ошибка {e}, переключаем...")
        return ask_ai(prompt, model_index + 1)


# ===== МЕНЮ В ОДНОМ ОКНЕ =====
MENU_TEXT = """
🤖 **Бот с ИИ работает!**

📌 **Команды:**

/ai [вопрос] - спросить ИИ
/models - список доступных моделей

🔄 При лимите бот сам переключит модель

---

**Примеры:**
/ai Как работает ИИ?
/ai Напиши стих про кота
/ai Объясни квантовую физику

**Модели:** openrouter/free, Llama 3.3 70B, Nemotron 3 Ultra, GPT-OSS-120B, Gemma 4 31B и ещё 11 моделей
"""

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, MENU_TEXT, parse_mode="Markdown")

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "❌ Напиши вопрос после /ai\n\nПример: /ai Как работает ИИ?")
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    answer = ask_ai(user_text)
    
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['models'])
def models_command(message):
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(
        message,
        f"🤖 **Доступные модели (июнь 2026):**\n\n{models_list}\n\n"
        f"📊 Всего: {len(FREE_MODELS)} моделей\n"
        f"🔄 При лимите автоматическое переключение"
    )


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
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
