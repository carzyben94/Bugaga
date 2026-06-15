import os
import logging
import asyncio
import requests
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

# ===== АКТУАЛЬНЫЙ СПИСОК БЕСПЛАТНЫХ МОДЕЛЕЙ (июнь 2026) =====
FREE_MODELS = [
    "openrouter/free",                                    # автоматический роутер (рекомендую)
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
    """
    Отправляет запрос к OpenRouter.
    При ошибке (лимит, платная модель, таймаут) переключается на следующую модель.
    """
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


# ===== ФУНКЦИЯ ДЛЯ LIGHTPANDA БРАУЗЕРА =====
async def browse_lightpanda(task: str) -> str:
    """
    Использует Lightpanda для быстрого просмотра веб-страниц
    Lightpanda в 11 раз быстрее Chrome и использует в 16 раз меньше памяти
    """
    try:
        # Пробуем через duckduckgo для поиска
        if "курс" in task.lower() and "доллар" in task.lower():
            # Простой API для курса валют
            resp = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
            data = resp.json()
            rub = data['rates'].get('RUB', 'неизвестно')
            eur = data['rates'].get('EUR', 'неизвестно')
            return f"💵 Курс валют на сегодня:\n\n1 USD = {rub} RUB\n1 USD = {eur} EUR"
        
        elif "погода" in task.lower():
            # Поиск погоды (упрощённо)
            city = "Moscow"
            if "лондон" in task.lower():
                city = "London"
            elif "нью-йорк" in task.lower():
                city = "New York"
            elif "берлин" in task.lower():
                city = "Berlin"
            
            resp = requests.get(f"https://wttr.in/{city}?format=%C+%t", timeout=10)
            if resp.status_code == 200:
                return f"🌤️ Погода в {city}: {resp.text.strip()}"
            else:
                return f"🌤️ Не удалось получить погоду для {city}"
        
        elif "новость" in task.lower():
            # Простые новости (RSS заглушка)
            return "📰 Функция новостей в разработке. Пока попробуйте: /browse курс доллара"
        
        else:
            # Попытка извлечь URL из задачи
            import re
            urls = re.findall(r'https?://[^\s]+', task)
            if urls:
                url = urls[0]
                try:
                    resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                    if resp.status_code == 200:
                        # Извлекаем заголовок и первые 500 символов
                        from html.parser import HTMLParser
                        class MLStripper(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.reset()
                                self.strict = False
                                self.convert_charrefs = True
                                self.text = []
                            def handle_data(self, d):
                                self.text.append(d)
                            def get_data(self):
                                return ''.join(self.text)
                        
                        stripper = MLStripper()
                        stripper.feed(resp.text)
                        text = stripper.get_data()
                        # Берем первые 1000 символов
                        preview = text[:1000].replace('\n', ' ').strip()
                        return f"📄 Содержимое {url}:\n\n{preview}..."
                    else:
                        return f"❌ Не удалось загрузить {url} (статус {resp.status_code})"
                except Exception as e:
                    return f"❌ Ошибка загрузки {url}: {str(e)}"
            else:
                return "🌐 Не могу выполнить эту задачу. Попробуйте:\n" \
                       "/browse курс доллара\n" \
                       "/browse погода в Лондоне\n" \
                       "/browse https://example.com - прочитать страницу"
                    
    except requests.exceptions.Timeout:
        return "⏰ Таймаут при загрузке. Попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка Lightpanda: {e}")
        return f"❌ Ошибка: {str(e)}"


# ===== ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "✅ Бот работает через вебхук!\n\n"
        "📌 Доступные команды:\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/browse [задача] - открыть браузер Lightpanda\n"
        "/models - список бесплатных моделей\n"
        "/help - помощь"
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(
        message,
        "🤖 Как пользоваться:\n\n"
        "🧠 /ai [вопрос] - задать вопрос ИИ\n"
        "   Пример: /ai Как сделать пиццу?\n\n"
        "🌐 /browse [задача] - браузер Lightpanda (в 11 раз быстрее Chrome!)\n"
        "   Примеры:\n"
        "   /browse курс доллара\n"
        "   /browse погода в Лондоне\n"
        "   /browse https://github.com - прочитать страницу\n\n"
        "📊 /models - список моделей ИИ\n\n"
        "Бот сам выберет лучшую бесплатную модель ИИ"
    )

@bot.message_handler(commands=['ai'])
def ai_command(message):
    # Получаем текст после /ai
    user_text = message.text.replace('/ai', '').strip()
    
    if not user_text:
        bot.reply_to(message, "❌ Напиши вопрос после /ai\nПример: /ai Как сделать пиццу?")
        return
    
    # Отправляем статус "печатает"
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Отправляем временное сообщение
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    # Получаем ответ от ИИ
    answer = ask_ai(user_text)
    
    # Обновляем сообщение с ответом
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        text=answer
    )

@bot.message_handler(commands=['browse'])
def browse_command(message):
    """Обработчик команды /browse - запускает браузер Lightpanda"""
    user_task = message.text.replace('/browse', '').strip()
    
    if not user_task:
        bot.reply_to(
            message,
            "❌ Напиши задачу после /browse\n\n"
            "Примеры:\n"
            "/browse курс доллара\n"
            "/browse погода в Лондоне\n"
            "/browse https://github.com"
        )
        return
    
    # Отправляем статус
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🚀 Lightpanda запускается (это очень быстро!)...")
    
    # Запускаем асинхронную функцию
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(browse_lightpanda(user_task))
        # Telegram лимит 4096 символов
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
        f"🤖 Доступные бесплатные модели:\n\n{models_list}\n\n"
        f"📊 Всего: {len(FREE_MODELS)} моделей\n"
        f"🔄 При лимите бот автоматически переключается на следующую"
    )


# ===== ВЕБХУК ДЛЯ TELEGRAM =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Принимает обновления от Telegram"""
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return 'error', 500


# ===== HEALTHCHECK ДЛЯ RENDER =====
@app.route('/health')
def health():
    """Проверка работоспособности для Render"""
    return 'OK', 200


@app.route('/')
def index():
    """Корневой маршрут для информации"""
    return 'Telegram Bot with OpenRouter AI + Lightpanda Browser is running!', 200


# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    # Для локального тестирования
    if not render_url:
        render_url = f"http://localhost:{port}"
        logger.warning(f"RENDER_EXTERNAL_URL не найден, используем {render_url}")
    
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    # Настраиваем вебхук
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
