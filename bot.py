import os
import logging
import asyncio
import requests
import re
from urllib.parse import quote_plus
from html.parser import HTMLParser
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ПРОВЕРКА КЛЮЧЕЙ =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")
if not OPENROUTER_API_KEY:
    logger.warning("⚠️ OPENROUTER_API_KEY не задан! Команда /ai не будет работать")

# ===== СОЗДАНИЕ БОТА И FLASK =====
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== АКТУАЛЬНЫЙ СПИСОК БЕСПЛАТНЫХ МОДЕЛЕЙ =====
FREE_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "z-ai/glm-4.5-air:free",
    "poolside/laguna-m1:free",
    "poolside/laguna-xs2:free",
    "moonshotai/kimi-k2.6:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni:free",
    "qwen/qwen3-coder:free",
]

# ===== ФУНКЦИЯ ЗАПРОСА К OPENROUTER (С АВТОПЕРЕКЛЮЧЕНИЕМ) =====
def ask_ai(prompt, model_index=0):
    if model_index >= len(FREE_MODELS):
        return "😵 Извините, все бесплатные модели временно недоступны. Попробуйте позже."
    
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
            result = response.json()
            answer = result["choices"][0]["message"]["content"]
            logger.info(f"✅ Модель {model} ответила успешно")
            return answer
        
        elif response.status_code == 429:
            logger.warning(f"⚠️ Модель {model}: лимит запросов (429), переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        elif response.status_code == 402:
            logger.warning(f"⚠️ Модель {model}: требуется оплата (402), переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        else:
            logger.warning(f"⚠️ Модель {model}: ошибка {response.status_code}, переключаем...")
            return ask_ai(prompt, model_index + 1)
            
    except requests.exceptions.Timeout:
        logger.warning(f"⚠️ Модель {model}: таймаут, переключаем...")
        return ask_ai(prompt, model_index + 1)
    except Exception as e:
        logger.error(f"❌ Модель {model}: исключение {e}, переключаем...")
        return ask_ai(prompt, model_index + 1)


# ===== ФУНКЦИЯ ДЛЯ БРАУЗЕРА =====
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ' '.join(self.text)


async def browse_lightpanda(task: str) -> str:
    """Работает с любым запросом: URL, поиск, вопрос"""
    try:
        # 1. Если это URL - открываем страницу
        urls = re.findall(r'https?://[^\s]+', task)
        if urls:
            url = urls[0]
            resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                stripper = MLStripper()
                stripper.feed(resp.text)
                text = stripper.get_data()
                text = ' '.join(text.split())[:2000]
                return f"📄 Содержимое {url}:\n\n{text}..."
            return f"❌ Ошибка загрузки {url}"
        
        # 2. Если не URL - делаем поиск через DuckDuckGo
        query = quote_plus(task)
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        resp = requests.get(search_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        
        if resp.status_code == 200:
            titles = re.findall(r'<a class="result__a"[^>]*>([^<]+)</a>', resp.text)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>([^<]+)</a>', resp.text)
            
            results = []
            for i in range(min(3, len(titles))):
                title = titles[i] if i < len(titles) else ""
                snippet = snippets[i] if i < len(snippets) else ""
                if title:
                    results.append(f"🔹 {title}\n   {snippet[:150]}...")
            
            if results:
                return f"🔍 Результаты поиска:\n\n" + "\n\n".join(results)
        
        # 3. Если поиск не дал результатов - используем ИИ
        return await ai_fallback(task)
        
    except Exception as e:
        logger.error(f"Ошибка в browse: {e}")
        return await ai_fallback(task)


async def ai_fallback(task: str) -> str:
    """Резервный ответ через ИИ"""
    if not OPENROUTER_API_KEY:
        return f"🌐 Не удалось обработать запрос. API ключ не настроен."
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": task}],
            "max_tokens": 500,
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            answer = resp.json()["choices"][0]["message"]["content"]
            return f"🤖 {answer}"
        return f"❌ Не удалось обработать запрос"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


# ===== ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "✅ Бот работает!\n\n"
        "📌 Команды:\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/browse [запрос] - поиск в интернете\n"
        "/models - список моделей ИИ\n"
        "/help - помощь"
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(
        message,
        "🤖 Как пользоваться:\n\n"
        "/ai [вопрос] - задать вопрос ИИ\n"
        "/browse [запрос] - поиск в интернете или открыть сайт\n"
        "/models - список доступных моделей ИИ"
    )

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    
    if not user_text:
        bot.reply_to(message, "❌ Напиши вопрос после /ai")
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    answer = ask_ai(user_text)
    
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        text=answer
    )

@bot.message_handler(commands=['browse'])
def browse_command(message):
    user_task = message.text.replace('/browse', '').strip()
    
    if not user_task:
        bot.reply_to(
            message,
            "❌ Напиши запрос после /browse"
        )
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🔍 Ищу...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(browse_lightpanda(user_task))
        if len(result) > 4000:
            result = result[:4000] + "..."
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=result
        )
    except Exception as e:
        logger.error(f"Ошибка в browse_command: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=f"❌ Ошибка: {str(e)}"
        )
    finally:
        loop.close()

@bot.message_handler(commands=['models'])
def models_command(message):
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(
        message,
        f"🤖 Доступные модели:\n\n{models_list}\n\n"
        f"📊 Всего: {len(FREE_MODELS)} моделей\n"
        f"🔄 При лимите автоматическое переключение"
    )


# ===== ВЕБХУК ДЛЯ TELEGRAM =====
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


@app.route('/')
def index():
    return 'Telegram Bot with AI + Browser is running!', 200


# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not render_url:
        render_url = f"http://localhost:{port}"
        logger.warning(f"RENDER_EXTERNAL_URL не найден, используем {render_url}")
    
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
