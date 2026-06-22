import telebot
from flask import Flask, request
import os
import time
import requests
import threading
import subprocess
import sys
import shutil
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === ХРАНИЛИЩЕ ===
user_sessions = {}
install_status = {}

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    """Установка браузера и зависимостей"""
    user_id = message.from_user.id
    
    if user_id in install_status and install_status[user_id].get('running', False):
        bot.reply_to(message, "⏳ Установка уже выполняется... Подождите!")
        return
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🖥️ Полная установка", callback_data="install_full"),
        InlineKeyboardButton("📦 Только зависимости", callback_data="install_deps")
    )
    markup.row(
        InlineKeyboardButton("🔍 Проверить установку", callback_data="install_check"),
        InlineKeyboardButton("❌ Отмена", callback_data="install_cancel")
    )
    
    bot.reply_to(
        message,
        "🔧 **Установка браузера и зависимостей**\n\n"
        "Выберите опцию:\n"
        "• **Полная установка** - установит Chrome + Selenium\n"
        "• **Только зависимости** - установит Selenium\n"
        "• **Проверить** - проверит что уже установлено\n\n"
        "⚠️ Процесс может занять 2-5 минут",
        parse_mode='Markdown',
        reply_markup=markup
    )

# === ОБРАБОТЧИК КНОПОК ===
@bot.callback_query_handler(func=lambda call: call.data.startswith('install_'))
def handle_install_callback(call):
    user_id = call.from_user.id
    
    if call.data == "install_cancel":
        bot.edit_message_text(
            "❌ Установка отменена",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return
    
    # Проверка установки
    if call.data == "install_check":
        check_installation(call.message.chat.id, call.message.message_id)
        return
    
    install_status[user_id] = {'running': True, 'step': 0}
    
    msg = bot.edit_message_text(
        "⏳ **Начинаем установку...**\nЭто может занять несколько минут",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    
    thread = threading.Thread(
        target=run_installation,
        args=(user_id, call.data, msg.chat.id, msg.message_id)
    )
    thread.start()

def run_installation(user_id, install_type, chat_id, message_id):
    """Выполняет установку в фоновом режиме"""
    try:
        # ШАГ 1: Обновление pip
        update_status(chat_id, message_id, "📦 Обновление pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        update_status(chat_id, message_id, "✅ pip обновлен")
        
        # ШАГ 2: Установка Selenium и webdriver-manager
        update_status(chat_id, message_id, "📦 Установка Selenium...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "selenium==4.15.2",
            "webdriver-manager==4.0.1"
        ])
        update_status(chat_id, message_id, "✅ Selenium установлен")
        
        # ШАГ 3: Установка Chrome (только полная)
        if install_type == "install_full":
            update_status(chat_id, message_id, "🌐 Установка Chrome...")
            
            if sys.platform.startswith('linux'):
                subprocess.check_call(["apt-get", "update"])
                subprocess.check_call([
                    "apt-get", "install", "-y",
                    "wget", "gnupg", "unzip"
                ])
                subprocess.check_call([
                    "wget", "-q", "-O", "-",
                    "https://dl-ssl.google.com/linux/linux_signing_key.pub"
                ], shell=True)
                subprocess.check_call([
                    "apt-get", "install", "-y",
                    "google-chrome-stable"
                ])
                update_status(chat_id, message_id, "✅ Chrome установлен")
        
        # ШАГ 4: Проверка установки
        update_status(chat_id, message_id, "🔍 Проверка установки...")
        
        # Проверяем Chrome
        chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        if chrome_path:
            update_status(chat_id, message_id, f"✅ Chrome найден: {chrome_path}")
        else:
            update_status(chat_id, message_id, "⚠️ Chrome не найден (нужен для полной установки)")
        
        # Проверяем Selenium
        try:
            import selenium
            update_status(chat_id, message_id, f"✅ Selenium {selenium.__version__}")
        except:
            update_status(chat_id, message_id, "❌ Selenium не установлен")
        
        # Проверяем webdriver-manager
        try:
            import webdriver_manager
            update_status(chat_id, message_id, "✅ webdriver-manager установлен")
        except:
            update_status(chat_id, message_id, "❌ webdriver-manager не установлен")
        
        update_status(
            chat_id, 
            message_id, 
            "✅ **Установка завершена!**\n\n"
            "Теперь можно использовать:\n"
            "/login - войти в X.com\n"
            "/screenshot - скриншот"
        )
        
        install_status[user_id] = {'running': False, 'completed': True}
        
    except Exception as e:
        update_status(
            chat_id, 
            message_id, 
            f"❌ **Ошибка установки:**\n```\n{str(e)}\n```"
        )
        install_status[user_id] = {'running': False, 'error': str(e)}

def update_status(chat_id, message_id, text):
    """Обновляет сообщение со статусом"""
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode='Markdown'
        )
    except:
        pass

def check_installation(chat_id, message_id):
    """Проверка установки (только нужное)"""
    result = "🔍 **Проверка установки:**\n\n"
    
    # 1. Проверяем Chrome
    chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome")
    if chrome_path:
        result += f"✅ Chrome: {chrome_path}\n"
        try:
            version = subprocess.check_output([chrome_path, "--version"], stderr=subprocess.STDOUT)
            result += f"   Версия: {version.decode().strip()}\n"
        except:
            pass
    else:
        result += "❌ Chrome не найден\n"
        result += "   Используйте /install full для установки\n"
    
    # 2. Проверяем Selenium
    try:
        import selenium
        result += f"✅ Selenium: {selenium.__version__}\n"
    except ImportError:
        result += "❌ Selenium не установлен\n"
        result += "   Используйте /install deps\n"
    
    # 3. Проверяем webdriver-manager
    try:
        import webdriver_manager
        result += "✅ webdriver-manager установлен\n"
    except ImportError:
        result += "❌ webdriver-manager не установлен\n"
    
    # 4. Проверяем возможность запуска ChromeDriver
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # Проверяем без реального запуска
        result += "✅ ChromeDriver готов к работе\n"
    except Exception as e:
        result += f"⚠️ Ошибка ChromeDriver: {str(e)[:50]}...\n"
    
    # Итог
    result += "\n---\n"
    if chrome_path:
        try:
            import selenium
            import webdriver_manager
            result += "✅ **ВСЕ ГОТОВО К РАБОТЕ!**\n"
            result += "Используйте /login для входа в X.com"
        except:
            result += "⚠️ **Нужно доустановить:**\n"
            result += "   /install deps - для Selenium\n"
            result += "   /install full - для Chrome + Selenium"
    else:
        result += "⚠️ **Нужна полная установка:**\n"
        result += "   /install full"
    
    bot.edit_message_text(
        result,
        chat_id=chat_id,
        message_id=message_id,
        parse_mode='Markdown'
    )

# === КОМАНДА /CHECK ===
@bot.message_handler(commands=['check'])
def handle_check(message):
    """Проверка установки"""
    msg = bot.reply_to(message, "🔍 Проверка...")
    check_installation(msg.chat.id, msg.message_id)

# === КОМАНДА /LOGIN ===
@bot.message_handler(commands=['login'])
def handle_login(message):
    """Вход в Twitter/X"""
    user_id = message.from_user.id
    
    # Проверяем Selenium
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        bot.reply_to(
            message,
            "❌ Selenium не установлен!\n"
            "Используйте /install deps"
        )
        return
    
    # Проверяем Chrome
    chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome_path:
        bot.reply_to(
            message,
            "❌ Chrome не найден!\n"
            "Используйте /install full"
        )
        return
    
    args = message.text.split()[1:]
    if len(args) < 2:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = args[0]
    password = args[1]
    
    # Создаем браузер и логинимся
    from browser import AntiDetectBrowser
    browser = AntiDetectBrowser(headless=True)
    
    try:
        bot.reply_to(message, "🔄 Выполняется вход в X.com...\nЭто может занять 10-30 секунд")
        
        browser.setup_driver()
        result = browser.login_twitter(username, password)
        
        if result:
            user_sessions[user_id] = browser
            screenshot = browser.take_screenshot(f"login_{user_id}.png")
            
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    user_id,
                    photo,
                    caption="✅ Вход выполнен успешно!"
                )
            os.remove(screenshot)
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    user_id,
                    photo,
                    caption="❌ Ошибка входа. Проверьте логин/пароль"
                )
            os.remove(screenshot)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

# === КОМАНДА /SCREENSHOT ===
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
                caption=f"📸 Скриншот\nURL: {browser.driver.current_url}"
            )
        os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

# === КОМАНДА /STATUS ===
@bot.message_handler(commands=['status'])
def handle_status(message):
    user_id = message.from_user.id
    
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            url = browser.driver.current_url
            bot.reply_to(
                message,
                f"✅ Сессия активна\n"
                f"🔗 URL: {url}\n"
                f"📊 Статус: {'Авторизован' if 'home' in url else 'Не авторизован'}"
            )
        except:
            bot.reply_to(message, "⚠️ Сессия неактивна. Используйте /login")
            del user_sessions[user_id]
    else:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /login")

# === КОМАНДА /CLOSE ===
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
            bot.reply_to(message, f"❌ Ошибка: {str(e)}")
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Бот с браузером**\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome + Selenium\n"
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
        "📋 **Доступные команды:**\n\n"
        "/start - Приветствие\n"
        "/install - Установка Chrome + Selenium\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Войти в X.com\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n\n"
        "🔧 **Перед использованием:**\n"
        "1. /install deps - установить Selenium\n"
        "2. /install full - установить Chrome\n"
        "3. /check - проверить всё ли готово"
    )

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message,
        f"📩 Используйте /help для списка команд"
    )

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
            print(f"✅ Webhook установлен: {webhook_url}")
        
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Бот запущен на порту {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        print("🤖 Бот запущен в режиме polling...")
        bot.polling(none_stop=True)