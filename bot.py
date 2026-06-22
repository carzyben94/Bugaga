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

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_sessions = {}
install_status = {}

# === ФУНКЦИЯ ДЛЯ ОТПРАВКИ СКРИНШОТОВ ===
def send_step_screenshot(bot_instance, chat_id, filename, caption):
    try:
        if os.path.exists(filename):
            with open(filename, 'rb') as photo:
                bot_instance.send_photo(chat_id, photo, caption=f"📸 {caption}")
            os.remove(filename)
            return True
    except Exception as e:
        print(f"Ошибка отправки: {e}")
    return False

# === КОМАНДА /TEST ===
@bot.message_handler(commands=['test'])
def handle_test(message):
    """Просто открывает X.com и показывает скриншоты"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    check = check_installation()
    
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    if not check['chromedriver']:
        bot.reply_to(message, "❌ ChromeDriver не установлен! Используйте /install")
        return
    
    status_msg = bot.reply_to(
        message,
        "🔄 **Открываю X.com...**\n"
        "📸 Сейчас сделаю скриншоты страницы\n"
        "⏳ Это может занять 10-15 секунд"
    )
    
    browser = AntiDetectBrowser(headless=True)
    
    try:
        browser.setup_driver()
        
        # Шаг 1: Открываем X.com
        bot.edit_message_text(
            "🌐 Открываю x.com...",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
        browser.driver.get("https://x.com")
        time.sleep(3)
        browser.take_screenshot("test_xcom_home.png")
        send_step_screenshot(bot, chat_id, "test_xcom_home.png", "🌐 Главная страница X.com")
        
        # Шаг 2: Скриншот прокрученной страницы
        bot.edit_message_text(
            "📸 Делаю скриншот страницы...",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
        browser.driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(1)
        browser.take_screenshot("test_xcom_scroll.png")
        send_step_screenshot(bot, chat_id, "test_xcom_scroll.png", "📸 Прокрученная страница")
        
        # Шаг 3: Ищем кнопки
        bot.edit_message_text(
            "🔍 Ищу кнопки на странице...",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
        
        buttons = browser.driver.find_elements(By.TAG_NAME, "button")
        button_info = "🔍 **Найденные кнопки:**\n\n"
        button_texts = []
        
        for i, btn in enumerate(buttons[:20]):
            try:
                text = btn.text.strip()[:30] if btn.text else "без текста"
                if text:
                    button_texts.append(f"{i+1}. `{text}`")
            except:
                pass
        
        if button_texts:
            button_info += "\n".join(button_texts)
            if len(buttons) > 20:
                button_info += f"\n\n... и еще {len(buttons) - 20} кнопок"
        else:
            button_info += "❌ Кнопки с текстом не найдены\n"
            button_info += f"Всего найдено элементов button: {len(buttons)}"
        
        # Шаг 4: Скриншот с кнопками
        browser.take_screenshot("test_xcom_buttons.png")
        send_step_screenshot(bot, chat_id, "test_xcom_buttons.png", "🔘 Кнопки на странице")
        
        # Шаг 5: Информация
        current_url = browser.driver.current_url
        page_title = browser.driver.title
        
        browser.close()
        
        # Итоговое сообщение
        bot.edit_message_text(
            f"✅ **Тест завершен!**\n\n"
            f"📌 **URL:** {current_url}\n"
            f"📄 **Заголовок:** {page_title}\n\n"
            f"📊 **Найдено кнопок:** {len(buttons)}\n\n"
            f"{button_info}\n\n"
            f"💡 Теперь можно использовать:\n"
            f"/login - для входа в X.com\n"
            f"/screenshot - для скриншота",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ **Ошибка:** {str(e)[:200]}",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
        try:
            browser.close()
        except:
            pass

# === КОМАНДА /LOGIN ===
@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    check = check_installation()
    
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    if not check['chromedriver']:
        bot.reply_to(message, "❌ ChromeDriver не установлен! Используйте /install")
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
    
    status_msg = bot.reply_to(
        message, 
        "🔄 **Выполняется вход в X.com...**\n\n"
        "📸 Будет отправлено несколько скриншотов шагов\n"
        "⏳ Это может занять 15-30 секунд"
    )
    
    def screenshot_callback(filename, caption):
        send_step_screenshot(bot, chat_id, filename, caption)
    
    browser = AntiDetectBrowser(headless=True, screenshot_callback=screenshot_callback)
    
    try:
        browser.setup_driver()
        result = browser.login_twitter(username, password)
        
        if result:
            user_sessions[user_id] = browser
            
            final_screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if final_screenshot and os.path.exists(final_screenshot):
                with open(final_screenshot, 'rb') as photo:
                    bot.send_photo(
                        chat_id,
                        photo,
                        caption="✅ **Вход выполнен успешно!**\n\nМожете использовать /screenshot для новых скриншотов"
                    )
                os.remove(final_screenshot)
            
            bot.edit_message_text(
                "✅ **Вход выполнен успешно!**",
                chat_id=chat_id,
                message_id=status_msg.message_id
            )
        else:
            error_screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if error_screenshot and os.path.exists(error_screenshot):
                with open(error_screenshot, 'rb') as photo:
                    bot.send_photo(
                        chat_id,
                        photo,
                        caption="❌ **Ошибка входа**\n\nПроверьте логин и пароль"
                    )
                os.remove(error_screenshot)
            
            bot.edit_message_text(
                "❌ **Ошибка входа**\n\nПроверьте логин и пароль",
                chat_id=chat_id,
                message_id=status_msg.message_id
            )
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ **Ошибка:** {str(e)[:200]}",
            chat_id=chat_id,
            message_id=status_msg.message_id
        )
        try:
            browser.close()
        except:
            pass

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    user_id = message.from_user.id
    
    if user_id in install_status and install_status[user_id].get('running', False):
        bot.reply_to(message, "⏳ Установка уже выполняется... Подождите!")
        return
    
    msg = bot.reply_to(
        message,
        "🔄 **Установка Chrome в /tmp...**\n"
        "⏳ Это может занять 1-2 минуты\n\n"
        "📦 Скачивается ~90 MB\n"
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
    try:
        browser = AntiDetectBrowser(headless=True)
        
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
        
        update_status(chat_id, message_id, "📦 Установка Chrome в /tmp...")
        chrome_path = browser.install_chrome_local()
        
        if chrome_path:
            update_status(chat_id, message_id, "✅ Chrome установлен!")
        else:
            update_status(chat_id, message_id, "❌ Ошибка установки Chrome")
            install_status[user_id] = {'running': False, 'error': 'Chrome не установлен'}
            return
        
        update_status(chat_id, message_id, "📦 Установка ChromeDriver в /tmp...")
        driver_path = browser.install_chromedriver_local()
        
        if driver_path:
            update_status(chat_id, message_id, "✅ ChromeDriver установлен!")
        else:
            update_status(chat_id, message_id, "❌ Ошибка установки ChromeDriver")
            install_status[user_id] = {'running': False, 'error': 'ChromeDriver не установлен'}
            return
        
        update_status(chat_id, message_id, "🔍 Проверка всех компонентов...")
        check = check_installation()
        
        if check['chrome'] and check['chromedriver']:
            update_status(
                chat_id,
                message_id,
                f"✅ **Установка завершена успешно!**\n\n"
                f"📍 Chrome: {check['chrome_path']}\n"
                f"📍 ChromeDriver: {check['driver_path']}\n"
                f"📦 Selenium: {selenium_version}\n\n"
                "Теперь можно использовать:\n"
                "/test - Посмотреть X.com\n"
                "/login логин пароль - Войти в X.com\n"
                "/screenshot - Скриншот"
            )
            install_status[user_id] = {'running': False, 'completed': True}
        else:
            error_msg = "❌ **Ошибка установки:**\n\n"
            if not check['chrome']:
                error_msg += "❌ Chrome не установлен\n"
            if not check['chromedriver']:
                error_msg += "❌ ChromeDriver не установлен\n"
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
    result = "🔍 **Проверка компонентов:**\n\n"
    
    try:
        import selenium
        result += f"✅ Selenium: {selenium.__version__}\n"
    except ImportError:
        result += "❌ Selenium: не установлен\n"
        result += "   /install для установки\n"
    
    try:
        import webdriver_manager
        result += "✅ webdriver-manager установлен\n"
    except ImportError:
        result += "❌ webdriver-manager не установлен\n"
    
    check = check_installation()
    
    if check['chrome']:
        result += f"✅ Chrome: {check['chrome_path']}\n"
    else:
        result += "❌ Chrome: не найден\n"
        result += "   /install для установки\n"
    
    if check['chromedriver']:
        result += f"✅ ChromeDriver: {check['driver_path']}\n"
    else:
        result += "❌ ChromeDriver: не найден\n"
        result += "   /install для установки\n"
    
    result += "\n---\n"
    if check['chrome'] and check['chromedriver']:
        try:
            import selenium
            result += "✅ **ВСЕ ГОТОВО К РАБОТЕ!**\n"
            result += "Используйте /test для просмотра X.com\n"
            result += "Используйте /login для входа"
        except:
            result += "⚠️ Selenium не установлен\n"
            result += "   /install для установки"
    else:
        result += "⚠️ Нужно выполнить /install"
    
    bot.reply_to(message, result, parse_mode='Markdown')

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Бот с браузером в /tmp**\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome + Selenium в /tmp\n"
        "/check - Проверить установку\n"
        "/test - Открыть X.com и показать скриншоты\n"
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
        "/install - Установить Chrome + Selenium в /tmp (1-2 минуты)\n"
        "/check - Проверить установку\n"
        "/test - Открыть X.com и показать скриншоты\n"
        "/login логин пароль - Войти в X.com (с скриншотами)\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n\n"
        "📂 Chrome: /tmp/chrome_bot/\n"
        "📸 Скриншоты отправляются в чат"
    )

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
            bot.send_photo(user_id, photo, caption=f"📸 **Скриншот**\nURL: {browser.driver.current_url}")
        os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

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
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

# === ОБРАБОТКА ВСЕХ СООБЩЕНИЙ ===
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