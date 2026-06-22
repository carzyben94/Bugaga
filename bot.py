import telebot
from flask import Flask, request
import os
import time
import requests
import sys
import subprocess
import shutil
from browser import AntiDetectBrowser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_sessions = {}

# === КОМАНДЫ ===

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Бот готов к работе!**\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome (без root)\n"
        "/login логин пароль - Войти в X.com\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n"
        "/help - Справка"
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(
        message,
        "📋 **Доступные команды:**\n\n"
        "/install - Установить Chrome локально (без root)\n"
        "/login логин пароль - Войти в X.com\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n"
        "/help - Справка"
    )

@bot.message_handler(commands=['install'])
def handle_install(message):
    """Установка Chrome без root прав"""
    bot.reply_to(
        message,
        "🔄 **Установка Chrome в локальную папку...**\n"
        "Это может занять 2-3 минуты\n\n"
        "⚠️ Root права НЕ требуются"
    )
    
    try:
        browser = AntiDetectBrowser(headless=True)
        browser.install_chrome_local()
        browser.install_chromedriver_local()
        
        bot.reply_to(
            message,
            "✅ **Chrome установлен локально!**\n\n"
            "Теперь можно использовать /login"
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ **Ошибка установки:**\n```\n{str(e)[:200]}\n```"
        )

@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    
    args = message.text.split()[1:]
    if len(args) < 2:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = args[0]
    password = args[1]
    
    bot.reply_to(message, "🔄 Выполняется вход в X.com...\nЭто может занять 15-30 секунд")
    
    browser = AntiDetectBrowser(headless=True)
    
    try:
        browser.setup_driver()
        result = browser.login_twitter(username, password)
        
        if result:
            user_sessions[user_id] = browser
            screenshot = browser.take_screenshot(f"login_{user_id}.png")
            
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    user_id,
                    photo,
                    caption="✅ **Вход выполнен успешно!**"
                )
            os.remove(screenshot)
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    user_id,
                    photo,
                    caption="❌ **Ошибка входа**\n\nПроверьте логин и пароль"
                )
            os.remove(screenshot)
            browser.close()
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")
        try:
            browser.close()
        except:
            pass

@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /login")
        return
    
    try:
        browser = user_sessions[user_id]
        screenshot = browser.take_screenshot(f"ss_{user_id}.png")
        
        with open(screenshot, 'rb') as photo:
            bot.send_photo(
                user_id,
                photo,
                caption=f"📸 **Скриншот**\nURL: {browser.driver.current_url}"
            )
        os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['status'])
def handle_status(message):
    user_id = message.from_user.id
    
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            url = browser.driver.current_url
            status = "✅ Авторизован" if "home" in url else "⚠️ Не авторизован"
            bot.reply_to(
                message,
                f"✅ **Сессия активна**\n"
                f"🔗 URL: {url}\n"
                f"📊 Статус: {status}"
            )
        except:
            bot.reply_to(message, "⚠️ Сессия неактивна. Используйте /login")
            del user_sessions[user_id]
    else:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /login")

@bot.message_handler(commands=['close'])
def handle_close(message):
    user_id = message.from_user.id
    
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            browser.close()
            del user_sessions[user_id]
            bot.reply_to(message, "✅ Браузер закрыт")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "📩 Используйте /help для списка команд")

# === WEBHOOK ===
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

if __name__ == '__main__':
    if os.getenv("RENDER"):
        render_url = os.getenv("RENDER_URL")
        if render_url:
            webhook_url = f"{render_url}/webhook"
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
            requests.get(url)
            print(f"✅ Webhook: {webhook_url}")
        
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Бот запущен на порту {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        print("🤖 Бот запущен...")
        bot.polling(none_stop=True)