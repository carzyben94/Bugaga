import telebot
from flask import Flask, request
import os
import time
import requests

# === БЕРЁМ ТОКЕН ИЗ ПЕРЕМЕННОЙ ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден! Добавьте в переменные окружения.")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === КОМАНДЫ БОТА ===

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я простой бот. Вот что я умею:\n"
        "/help - список команд\n"
        "/time - текущее время\n"
        "/echo <текст> - повторю ваше сообщение\n"
        "Просто отправь мне сообщение - я отвечу!"
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(
        message,
        "📋 Доступные команды:\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/time - Текущее время\n"
        "/echo <текст> - Повторить текст\n\n"
        "Или просто напиши что-нибудь!"
    )

@bot.message_handler(commands=['time'])
def send_time(message):
    current_time = time.strftime("%H:%M:%S", time.localtime())
    bot.reply_to(message, f"🕐 Текущее время: {current_time}")

@bot.message_handler(commands=['echo'])
def echo_message(message):
    text = message.text.replace('/echo', '').strip()
    if text:
        bot.reply_to(message, f"🔊 Эхо: {text}")
    else:
        bot.reply_to(message, "❌ Напиши текст после команды, например: /echo Привет!")

# === ОТВЕТ НА ЛЮБОЕ СООБЩЕНИЕ ===
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message,
        f"📩 Ты написал: *{message.text}*\n\n"
        "Используй /help для списка команд",
        parse_mode='Markdown'
    )

# === WEBHOOK ДЛЯ RENDER ===
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

# === УСТАНОВКА WEBHOOK ===
def set_webhook():
    """Автоматически устанавливает webhook при запуске на Render"""
    render_url = os.getenv("RENDER_URL")  # Добавьте эту переменную!
    if not render_url:
        # Автоматически определяем URL
        render_url = f"https://{os.getenv('RENDER_SERVICE_NAME', 'telegram-bot')}.onrender.com"
    
    webhook_url = f"{render_url}/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    
    try:
        response = requests.get(url)
        result = response.json()
        if result.get('ok'):
            print(f"✅ Webhook установлен: {webhook_url}")
        else:
            print(f"❌ Ошибка webhook: {result}")
    except Exception as e:
        print(f"❌ Не удалось установить webhook: {e}")

# === ТОЧКА ВХОДА ===
if __name__ == '__main__':
    if os.getenv("RENDER"):
        # Настройка webhook
        set_webhook()
        
        # Запуск Flask
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Бот запущен на порту {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        # Локально - polling
        print("🤖 Бот запущен в режиме polling...")
        bot.polling(none_stop=True)