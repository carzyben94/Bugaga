import subprocess
import sys

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

import telebot
from flask import Flask, request
import os
import time
import requests
import threading
from browser import AntiDetectBrowser, check_installation
from selenium.webdriver.common.by import By
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_sessions = {}
install_status = {}
user_logs = {}

# === ЛОГИ ===
def add_log(user_id, message, level="INFO"):
    if user_id not in user_logs:
        user_logs[user_id] = []
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    user_logs[user_id].append(log_entry)
    if len(user_logs[user_id]) > 100:
        user_logs[user_id] = user_logs[user_id][-100:]
    return log_entry

def clear_logs(user_id):
    if user_id in user_logs:
        user_logs[user_id] = []
        return True
    return False

def send_step_screenshot(bot_instance, chat_id, filename, caption, user_id=None):
    try:
        if os.path.exists(filename):
            if user_id:
                add_log(user_id, f"📸 {caption}", "STEP")
            with open(filename, 'rb') as photo:
                bot_instance.send_photo(chat_id, photo, caption=f"📸 {caption}")
            os.remove(filename)
            return True
    except Exception as e:
        print(f"Ошибка отправки скриншота: {e}")
    return False

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Бот для входа в X.com**\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome\n"
        "/check - Проверить установку\n"
        "/test - Открыть X.com\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/log - Показать логи\n"
        "/clearlog - Очистить логи\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер"
    )

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    user_id = message.from_user.id
    
    if user_id in install_status and install_status[user_id].get('running', False):
        bot.reply_to(message, "⏳ Установка уже выполняется...")
        return
    
    msg = bot.reply_to(
        message,
        "🔄 **Установка Chrome...**\n⏳ 1-2 минуты"
    )
    
    install_status[user_id] = {'running': True}
    
    thread = threading.Thread(
        target=run_installation,
        args=(user_id, msg.chat.id, msg.message_id)
    )
    thread.start()

def run_installation(user_id, chat_id, message_id):
    try:
        browser = AntiDetectBrowser(headless=True)
        
        update_status(chat_id, message_id, "📦 Установка Chrome в /tmp...")
        chrome_path = browser.install_chrome_local()
        
        if chrome_path:
            update_status(
                chat_id,
                message_id,
                f"✅ **Установка завершена!**\n\n"
                f"📍 Chrome: {chrome_path}\n\n"
                "Теперь можно использовать:\n"
                "/test - Посмотреть X.com\n"
                "/logingoogle email пароль - Вход через Google"
            )
            install_status[user_id] = {'running': False, 'completed': True}
        else:
            update_status(chat_id, message_id, "❌ Ошибка установки Chrome")
            install_status[user_id] = {'running': False, 'error': 'Chrome не установлен'}
        
    except Exception as e:
        update_status(chat_id, message_id, f"❌ Ошибка: {str(e)[:200]}")
        install_status[user_id] = {'running': False, 'error': str(e)}

def update_status(chat_id, message_id, text):
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    except:
        pass

# === КОМАНДА /CHECK ===
@bot.message_handler(commands=['check'])
def handle_check(message):
    result = "🔍 **Проверка:**\n\n"
    
    try:
        import selenium
        result += f"✅ Selenium: {selenium.__version__}\n"
    except ImportError:
        result += "❌ Selenium не установлен\n"
    
    try:
        import webdriver_manager
        result += "✅ webdriver-manager установлен\n"
    except ImportError:
        result += "❌ webdriver-manager не установлен\n"
    
    check = check_installation()
    
    if check['chrome']:
        result += f"✅ Chrome: {check['chrome_path']}\n"
    else:
        result += "❌ Chrome не найден\n"
        result += "   Используйте /install\n"
    
    result += "\n---\n"
    if check['chrome']:
        result += "✅ **ГОТОВО К РАБОТЕ!**\n"
        result += "Используйте /logingoogle"
    else:
        result += "⚠️ Нужно выполнить /install"
    
    bot.reply_to(message, result)

# === КОМАНДА /TEST ===
@bot.message_handler(commands=['test'])
def handle_test(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    status_msg = bot.reply_to(message, "🔄 Открываю X.com...")
    
    browser = AntiDetectBrowser(headless=True)
    
    try:
        browser.setup_driver()
        browser.driver.get("https://x.com")
        time.sleep(3)
        
        browser.take_screenshot("test_xcom.png")
        with open("test_xcom.png", 'rb') as photo:
            bot.send_photo(chat_id, photo, caption="🌐 X.com")
        os.remove("test_xcom.png")
        
        buttons = browser.driver.find_elements(By.TAG_NAME, "button")
        button_texts = []
        for btn in buttons[:10]:
            try:
                text = btn.text.strip()
                if text:
                    button_texts.append(f"• {text[:30]}")
            except:
                pass
        
        result = "✅ **Тест завершен!**\n\n"
        result += f"📊 Найдено кнопок: {len(buttons)}\n"
        if button_texts:
            result += "\n🔍 Кнопки:\n" + "\n".join(button_texts)
        
        browser.close()
        bot.edit_message_text(result, chat_id=chat_id, message_id=status_msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=status_msg.message_id)
        try:
            browser.close()
        except:
            pass

# === КОМАНДА /LOGINGOOGLE ===
@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    clear_logs(user_id)
    add_log(user_id, "🚀 Запуск входа через Google", "INFO")
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    try:
        import selenium
    except ImportError:
        bot.reply_to(message, "❌ Selenium не установлен! Используйте /install")
        return
    
    args = message.text.split()[1:]
    if len(args) < 2:
        bot.reply_to(message, "❌ Используйте: /logingoogle <email> <пароль>")
        return
    
    email = args[0]
    password = args[1]
    
    status_msg = bot.reply_to(
        message,
        "🔄 **Вход через Google...**\n"
        "⏳ 30-50 секунд"
    )
    
    def screenshot_callback(filename, caption):
        send_step_screenshot(bot, chat_id, filename, caption, user_id)
    
    browser = AntiDetectBrowser(
        headless=True,
        screenshot_callback=screenshot_callback
    )
    
    try:
        browser.setup_driver()
        result = browser.login_google_first_then_twitter(email, password)
        
        if result:
            user_sessions[user_id] = browser
            final_screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if final_screenshot and os.path.exists(final_screenshot):
                with open(final_screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ **Вход выполнен!**")
                os.remove(final_screenshot)
            
            bot.edit_message_text("✅ **Вход выполнен успешно!**", chat_id=chat_id, message_id=status_msg.message_id)
        else:
            error_screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if error_screenshot and os.path.exists(error_screenshot):
                with open(error_screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ **Ошибка входа**")
                os.remove(error_screenshot)
            
            bot.edit_message_text("❌ **Ошибка входа**\n\nПроверьте email и пароль", chat_id=chat_id, message_id=status_msg.message_id)
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=status_msg.message_id)
        try:
            browser.close()
        except:
            pass

# === КОМАНДА /LOGIN ===
@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    clear_logs(user_id)
    add_log(user_id, "🚀 Запуск обычного входа", "INFO")
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    try:
        import selenium
    except ImportError:
        bot.reply_to(message, "❌ Selenium не установлен! Используйте /install")
        return
    
    args = message.text.split()[1:]
    if len(args) < 2:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = args[0]
    password = args[1]
    
    status_msg = bot.reply_to(message, "🔄 Выполняется вход...")
    
    def screenshot_callback(filename, caption):
        send_step_screenshot(bot, chat_id, filename, caption, user_id)
    
    browser = AntiDetectBrowser(headless=True, screenshot_callback=screenshot_callback)
    
    try:
        browser.setup_driver()
        result = browser.login_twitter(username, password)
        
        if result:
            user_sessions[user_id] = browser
            final_screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if final_screenshot and os.path.exists(final_screenshot):
                with open(final_screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ **Вход выполнен!**")
                os.remove(final_screenshot)
            
            bot.edit_message_text("✅ **Вход выполнен успешно!**", chat_id=chat_id, message_id=status_msg.message_id)
        else:
            error_screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if error_screenshot and os.path.exists(error_screenshot):
                with open(error_screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ **Ошибка входа**")
                os.remove(error_screenshot)
            
            bot.edit_message_text("❌ **Ошибка входа**\n\nПроверьте логин и пароль", chat_id=chat_id, message_id=status_msg.message_id)
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=status_msg.message_id)
        try:
            browser.close()
        except:
            pass

# === КОМАНДА /STATUS ===
@bot.message_handler(commands=['status'])
def handle_status(message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            url = browser.driver.current_url
            status = "✅ Авторизован" if "home" in url else "⚠️ Не авторизован"
            bot.reply_to(message, f"✅ **Сессия активна**\n🔗 URL: {url}\n📊 Статус: {status}")
        except:
            bot.reply_to(message, "⚠️ Сессия неактивна")
            del user_sessions[user_id]
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

# === КОМАНДА /SCREENSHOT ===
@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    try:
        browser = user_sessions[user_id]
        screenshot = browser.take_screenshot(f"ss_{user_id}.png")
        with open(screenshot, 'rb') as photo:
            bot.send_photo(user_id, photo, caption=f"📸 **Скриншот**")
        os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

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
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

# === КОМАНДА /LOG ===
@bot.message_handler(commands=['log'])
def handle_log(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    try:
        browser = user_sessions[user_id]
        logs = browser.get_detailed_logs()
        if logs:
            if len(logs) > 4000:
                for part in [logs[i:i+3500] for i in range(0, len(logs), 3500)][:3]:
                    bot.send_message(user_id, f"📋 **Логи:**\n```\n{part}\n```", parse_mode='Markdown')
            else:
                bot.reply_to(message, f"📋 **Логи:**\n```\n{logs}\n```", parse_mode='Markdown')
        else:
            bot.reply_to(message, "📋 Логов пока нет")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

# === КОМАНДА /CLEARLOG ===
@bot.message_handler(commands=['clearlog'])
def handle_clear_log(message):
    user_id = message.from_user.id
    if clear_logs(user_id):
        bot.reply_to(message, "🧹 Логи очищены")
    else:
        bot.reply_to(message, "❌ Логов нет")

# === ЭХО ===
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
    if os.getenv("PORT") or os.getenv("RAILWAY") or os.getenv("RENDER"):
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Бот запущен на порту {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        print("🤖 Бот запущен...")
        bot.polling(none_stop=True)