import subprocess
import sys

# === АВТОУСТАНОВКА SELENIUM ===
def install_selenium():
    try:
        import selenium
        print(f"✅ Selenium уже установлен")
        return True
    except ImportError:
        print("📦 Устанавливаю Selenium...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "selenium==4.15.2",
            "webdriver-manager==4.0.1"
        ])
        print("✅ Selenium установлен!")
        return True

install_selenium()

# === ОСНОВНОЙ КОД ===
import telebot
from flask import Flask, request
import os
import time
import requests
import threading
from browser import AntiDetectBrowser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_sessions = {}
install_status = {}

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    """Установка Chrome в /tmp через бота"""
    user_id = message.from_user.id
    
    if user_id in install_status and install_status[user_id].get('running', False):
        bot.reply_to(message, "⏳ Установка уже выполняется... Подождите!")
        return
    
    msg = bot.reply_to(
        message,
        "🔄 **Установка Chrome в /tmp...**\n"
        "⏳ Это может занять 2-3 минуты\n\n"
        "📦 Скачивается ~100 MB\n"
        "📍 Папка: /tmp/chrome_bot/\n\n"
        "⚠️ Root права НЕ требуются"
    )
    
    install_status[user_id] = {'running': True}
    
    thread = threading.Thread(
        target=run_installation,
        args=(user_id, msg.chat.id, msg.message_id)
    )
    thread.start()

def run_installation(user_id, chat_id, message_id):
    """Установка в фоне"""
    try:
        browser = AntiDetectBrowser(headless=True)
        
        # ШАГ 1: Проверка Selenium
        update_status(chat_id, message_id, "🔍 Проверка Selenium...")
        try:
            import selenium
            selenium_version = selenium.__version__
            update_status(chat_id, message_id, f"✅ Selenium {selenium_version} установлен")
        except ImportError:
            update_status(chat_id, message_id, "📦 Устанавливаю Selenium...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "selenium==4.15.2",
                "webdriver-manager==4.0.1"
            ])
            update_status(chat_id, message_id, "✅ Selenium установлен!")
        
        # ШАГ 2: Установка Chrome
        update_status(chat_id, message_id, "📦 Установка Chrome в /tmp...")
        chrome_path = browser.install_chrome_local()
        
        if chrome_path:
            update_status(chat_id, message_id, "✅ Chrome установлен!")
        else:
            update_status(chat_id, message_id, "❌ Ошибка установки Chrome")
            install_status[user_id] = {'running': False, 'error': 'Chrome не установлен'}
            return
        
        # ШАГ 3: Установка ChromeDriver
        update_status(chat_id, message_id, "📦 Установка ChromeDriver в /tmp...")
        driver_path = browser.install_chromedriver_local()
        
        if driver_path:
            update_status(chat_id, message_id, "✅ ChromeDriver установлен!")
        else:
            update_status(chat_id, message_id, "❌ Ошибка установки ChromeDriver")
            install_status[user_id] = {'running': False, 'error': 'ChromeDriver не установлен'}
            return
        
        # ШАГ 4: Проверка всех компонентов
        update_status(chat_id, message_id, "🔍 Проверка всех компонентов...")
        
        # Проверяем Chrome
        chrome_dir = "/tmp/chrome_bot/chrome_local"
        chrome_ok = os.path.exists(chrome_dir) and len(os.listdir(chrome_dir)) > 0
        
        # Проверяем ChromeDriver
        driver_dir = "/tmp/chrome_bot/chromedriver_local"
        driver_ok = os.path.exists(driver_dir) and len(os.listdir(driver_dir)) > 0
        
        # Проверяем Selenium
        selenium_ok = False
        try:
            import selenium
            selenium_ok = True
            selenium_version = selenium.__version__
        except:
            selenium_ok = False
        
        # ШАГ 5: Итог
        if chrome_ok and driver_ok and selenium_ok:
            update_status(
                chat_id,
                message_id,
                f"✅ **Установка завершена успешно!**\n\n"
                f"📍 Chrome: /tmp/chrome_bot/chrome_local/\n"
                f"📍 ChromeDriver: /tmp/chrome_bot/chromedriver_local/\n"
                f"📦 Selenium: {selenium_version}\n\n"
                "Теперь можно использовать:\n"
                "/login логин пароль - Войти в X.com\n"
                "/screenshot - Скриншот\n"
                "/status - Статус сессии"
            )
            install_status[user_id] = {'running': False, 'completed': True}
        else:
            error_msg = "❌ **Ошибка установки:**\n\n"
            if not chrome_ok:
                error_msg += "❌ Chrome не установлен\n"
            if not driver_ok:
                error_msg += "❌ ChromeDriver не установлен\n"
            if not selenium_ok:
                error_msg += "❌ Selenium не установлен\n"
            error_msg += "\nПопробуйте еще раз: /install"
            
            update_status(chat_id, message_id, error_msg)
            install_status[user_id] = {'running': False, 'error': 'Не все компоненты установлены'}
        
    except Exception as e:
        update_status(
            chat_id,
            message_id,
            f"❌ **Ошибка установки:**\n```\n{str(e)[:200]}\n```"
        )
        install_status[user_id] = {'running': False, 'error': str(e)}

def update_status(chat_id, message_id, text):
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
    except:
        pass

# === КОМАНДА /CHECK ===
@bot.message_handler(commands=['check'])
def handle_check(message):
    """Проверка всех компонентов"""
    result = "🔍 **Проверка компонентов:**\n\n"
    
    # Проверяем Selenium
    try:
        import selenium
        result += f"✅ Selenium: {selenium.__version__}\n"
    except ImportError:
        result += "❌ Selenium: не установлен\n"
        result += "   /install для установки\n"
    
    # Проверяем webdriver-manager
    try:
        import webdriver_manager
        result += "✅ webdriver-manager установлен\n"
    except ImportError:
        result += "❌ webdriver-manager не установлен\n"
    
    # Проверяем Chrome
    chrome_path = "/tmp/chrome_bot/chrome_local/chrome"
    if os.path.exists(chrome_path):
        result += f"✅ Chrome: {chrome_path}\n"
    else:
        result += "❌ Chrome: не найден\n"
        result += "   /install для установки\n"
    
    # Проверяем ChromeDriver
    driver_path = "/tmp/chrome_bot/chromedriver_local/chromedriver"
    if os.path.exists(driver_path):
        result += f"✅ ChromeDriver: {driver_path}\n"
    else:
        result += "❌ ChromeDriver: не найден\n"
        result += "   /install для установки\n"
    
    # Итог
    result += "\n---\n"
    if os.path.exists(chrome_path) and os.path.exists(driver_path):
        try:
            import selenium
            result += "✅ **ВСЕ ГОТОВО К РАБОТЕ!**\n"
            result += "Используйте /login для входа в X.com"
        except:
            result += "⚠️ Selenium не установлен\n"
            result += "   /install для установки"
    else:
        result += "⚠️ Нужно выполнить /install"
    
    bot.reply_to(message, result, parse_mode='Markdown')

# === ОСТАЛЬНЫЕ КОМАНДЫ ===

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Бот с браузером в /tmp**\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome + Selenium в /tmp\n"
        "/check - Проверить установку\n"
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
        "📋 **Команды:**\n\n"
        "/install - Установить Chrome + Selenium в /tmp (2-3 минуты)\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Войти в X.com\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n\n"
        "📂 Chrome устанавливается в: /tmp/chrome_bot/"
    )

@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    
    # Проверяем Chrome
    chrome_path = "/tmp/chrome_bot/chrome_local/chrome"
    if not os.path.exists(chrome_path):
        bot.reply_to(
            message,
            "❌ Chrome не установлен!\nИспользуйте /install для установки"
        )
        return
    
    # Проверяем Selenium
    try:
        import selenium
    except ImportError:
        bot.reply_to(
            message,
            "❌ Selenium не установлен!\nИспользуйте /install для установки"
        )
        return
    
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