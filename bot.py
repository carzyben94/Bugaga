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

# === ХРАНИЛИЩЕ СЕССИЙ ===
user_sessions = {}
install_status = {}

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    """Установка браузера и зависимостей"""
    user_id = message.from_user.id
    
    # Проверяем, не выполняется ли уже установка
    if user_id in install_status and install_status[user_id].get('running', False):
        bot.reply_to(message, "⏳ Установка уже выполняется... Подождите!")
        return
    
    # Клавиатура для выбора
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
        "• **Полная установка** - установит Chrome + все зависимости\n"
        "• **Только зависимости** - установит Python пакеты\n"
        "• **Проверить** - проверит что уже установлено\n\n"
        "⚠️ Процесс может занять 2-5 минут",
        parse_mode='Markdown',
        reply_markup=markup
    )

# === ОБРАБОТЧИК КНОПОК /INSTALL ===
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
    
    # Создаем запись о статусе
    install_status[user_id] = {'running': True, 'step': 0}
    
    # Отправляем сообщение о начале
    msg = bot.edit_message_text(
        "⏳ **Начинаем установку...**\nЭто может занять несколько минут",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    
    # Запускаем установку в отдельном потоке
    thread = threading.Thread(
        target=run_installation,
        args=(user_id, call.data, msg.chat.id, msg.message_id)
    )
    thread.start()

def run_installation(user_id, install_type, chat_id, message_id):
    """Выполняет установку в фоновом режиме"""
    try:
        # Шаг 1: Обновление pip
        update_status(chat_id, message_id, "📦 Обновление pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        update_status(chat_id, message_id, "✅ pip обновлен")
        
        # Шаг 2: Установка зависимостей
        if install_type in ["install_full", "install_deps"]:
            update_status(chat_id, message_id, "📦 Установка Python зависимостей...")
            
            dependencies = [
                "selenium==4.15.2",
                "webdriver-manager==4.0.1",
                "pyTelegramBotAPI==4.14.0",
                "Flask==3.0.0",
                "requests==2.31.0",
                "pillow==10.1.0",
                "python-dotenv==1.0.0"
            ]
            
            for dep in dependencies:
                update_status(chat_id, message_id, f"   ⏳ Установка {dep}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            
            update_status(chat_id, message_id, "✅ Все зависимости установлены")
        
        # Шаг 3: Установка Chrome (только полная)
        if install_type == "install_full":
            update_status(chat_id, message_id, "🌐 Установка Chrome...")
            
            # Проверка ОС
            if sys.platform.startswith('linux'):
                # Linux (Render)
                subprocess.check_call([
                    "apt-get", "update"
                ])
                subprocess.check_call([
                    "apt-get", "install", "-y",
                    "wget",
                    "gnupg",
                    "unzip"
                ])
                subprocess.check_call([
                    "wget", "-q", "-O", "-",
                    "https://dl-ssl.google.com/linux/linux_signing_key.pub"
                ], shell=True)
                subprocess.check_call([
                    "apt-get", "install", "-y",
                    "google-chrome-stable"
                ])
                
            elif sys.platform.startswith('win'):
                # Windows - скачиваем Chrome
                update_status(chat_id, message_id, "   ⏳ Скачивание Chrome для Windows...")
                subprocess.check_call([
                    "powershell", "-Command",
                    "Invoke-WebRequest -Uri 'https://dl.google.com/chrome/install/latest/chrome_installer.exe' -OutFile 'chrome_installer.exe'"
                ])
                subprocess.check_call([
                    "chrome_installer.exe", "/silent", "/install"
                ])
                
            elif sys.platform.startswith('darwin'):
                # MacOS
                subprocess.check_call([
                    "brew", "install", "--cask", "google-chrome"
                ])
            
            update_status(chat_id, message_id, "✅ Chrome установлен")
        
        # Шаг 4: Проверка установки
        update_status(chat_id, message_id, "🔍 Проверка установки...")
        
        # Проверяем Chrome
        chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome")
        if chrome_path:
            update_status(chat_id, message_id, f"✅ Chrome найден: {chrome_path}")
        else:
            update_status(chat_id, message_id, "⚠️ Chrome не найден в PATH")
        
        # Проверяем Selenium
        try:
            import selenium
            update_status(chat_id, message_id, f"✅ Selenium версия: {selenium.__version__}")
        except:
            update_status(chat_id, message_id, "❌ Selenium не установлен")
        
        # Проверяем webdriver-manager
        try:
            import webdriver_manager
            update_status(chat_id, message_id, "✅ webdriver-manager установлен")
        except:
            update_status(chat_id, message_id, "❌ webdriver-manager не установлен")
        
        # Завершаем
        update_status(chat_id, message_id, "✅ **Установка завершена успешно!**\n\nТеперь можно использовать:\n/login - войти в X.com\n/screenshot - скриншот")
        
        install_status[user_id] = {'running': False, 'completed': True}
        
    except Exception as e:
        error_msg = f"❌ **Ошибка установки:**\n```\n{str(e)}\n```"
        update_status(chat_id, message_id, error_msg)
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

# === КОМАНДА /CHECK (проверка установки) ===
@bot.message_handler(commands=['check'])
def handle_check(message):
    """Проверяет установленные компоненты"""
    user_id = message.from_user.id
    
    result = "🔍 **Проверка установки:**\n\n"
    
    # Проверяем Chrome
    chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome")
    if chrome_path:
        result += f"✅ Chrome: {chrome_path}\n"
        
        # Версия Chrome
        try:
            import subprocess
            version = subprocess.check_output([chrome_path, "--version"], stderr=subprocess.STDOUT)
            result += f"   Версия: {version.decode().strip()}\n"
        except:
            pass
    else:
        result += "❌ Chrome не найден\n"
    
    # Проверяем Python пакеты
    packages = [
        "selenium",
        "webdriver_manager",
        "flask",
        "requests",
        "PIL"
    ]
    
    for pkg in packages:
        try:
            module = __import__(pkg)
            version = getattr(module, "__version__", "неизвестно")
            result += f"✅ {pkg}: {version}\n"
        except:
            result += f"❌ {pkg}: не установлен\n"
    
    # Проверяем Selenium
    try:
        from selenium import webdriver
        result += "✅ Selenium WebDriver готов\n"
    except:
        result += "❌ Selenium WebDriver не доступен\n"
    
    bot.reply_to(message, result, parse_mode='Markdown')

# === КОМАНДА /LOGIN (с проверкой установки) ===
@bot.message_handler(commands=['login'])
def handle_login(message):
    """Вход в Twitter/X"""
    user_id = message.from_user.id
    
    # Проверяем установку перед запуском
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as e:
        bot.reply_to(
            message,
            f"❌ Selenium не установлен! Используйте /install\n\nОшибка: {e}"
        )
        return
    
    # Проверяем Chrome
    chrome_path = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome")
    if not chrome_path:
        bot.reply_to(
            message,
            "❌ Chrome не найден! Используйте /install full\n\n"
            "Или установите вручную: apt-get install google-chrome-stable"
        )
        return
    
    args = message.text.split()[1:]
    if len(args) < 2:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = args[0]
    password = args[1]
    
    # Запускаем логин (код из предыдущего ответа)
    # ... (вставьте код логина из предыдущего ответа)

# === ОСТАЛЬНЫЕ КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Бот с браузером!\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome и зависимости\n"
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
        "📋 Доступные команды:\n"
        "/start - Приветствие\n"
        "/install - Установить Chrome и зависимости\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Войти в X.com\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n\n"
        "🔧 Перед использованием выполните /install"
    )

# === ОСТАЛЬНОЙ КОД (статус, скриншот, закрытие) ===
# ... (вставьте остальные функции из предыдущего ответа)

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
        # Установка webhook
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