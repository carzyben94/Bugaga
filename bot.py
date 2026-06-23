import telebot
import os
import time
from browser import AntiDetectBrowser, check_installation
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)

LOG_FILE = "bot.log"

try:
    bot.remove_webhook()
    print("✅ Webhook сброшен")
except Exception as e:
    print(f"⚠️ Ошибка сброса webhook: {e}")

user_sessions = {}
user_buttons = {}

def send_log_to_chat(chat_id, log_entry):
    try:
        if any(x in log_entry for x in ["✅", "❌", "⚠️", "🎉", "🔐", "📱", "⌨️"]):
            bot.send_message(chat_id, log_entry)
    except:
        pass

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Привет!\n\n"
        "📋 Команды:\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/analyze - Показать все кнопки на странице\n"
        "/click <номер> - Нажать кнопку по номеру\n"
        "/clickpos X Y - Кликнуть по координатам\n"
        "/log - Показать логи\n"
        "/getlog - Скачать лог-файл\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер"
    )

@bot.message_handler(commands=['check'])
def handle_check(message):
    result = "🔍 **Проверка компонентов:**\n\n"
    
    try:
        import selenium
        result += f"✅ Selenium: {selenium.__version__}\n"
    except ImportError:
        result += "❌ Selenium: не установлен\n"
    
    check = check_installation()
    if check['chrome']:
        result += f"✅ Chrome: {check['chrome_path']}\n"
    else:
        result += "❌ Chrome: не найден\n"
    
    result += "\n---\n"
    if check['chrome']:
        result += "✅ **ВСЕ ГОТОВО К РАБОТЕ!**\n"
        result += "Используйте /logingoogle для входа"
    else:
        result += "⚠️ Chrome не установлен в Dockerfile"
    
    bot.reply_to(message, result, parse_mode='Markdown')

@bot.message_handler(commands=['log'])
def handle_log(message):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = f.read()
            
            if len(logs) > 4000:
                parts = [logs[i:i+3500] for i in range(0, len(logs), 3500)]
                for part in parts[:3]:
                    bot.send_message(
                        message.chat.id,
                        f"📋 **Логи:**\n```\n{part}\n```",
                        parse_mode='Markdown'
                    )
            else:
                bot.reply_to(
                    message,
                    f"📋 **Логи:**\n```\n{logs}\n```",
                    parse_mode='Markdown'
                )
        else:
            bot.reply_to(message, "📋 Логов пока нет")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['getlog'])
def handle_get_log(message):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'rb') as f:
                bot.send_document(
                    message.chat.id,
                    f,
                    caption=f"📋 Лог-файл от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    visible_file_name="bot.log"
                )
            bot.send_message(message.chat.id, "✅ Лог-файл отправлен!")
        else:
            bot.reply_to(message, "📋 Логов пока нет")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(commands=['analyze'])
def handle_analyze(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Сначала выполните /logingoogle")
        return
    
    browser = user_sessions[user_id]
    
    try:
        all_buttons = browser.driver.find_elements(By.TAG_NAME, "button")
        result = "🔍 **Найденные кнопки:**\n\n"
        
        button_list = []
        for idx, btn in enumerate(all_buttons):
            try:
                btn_text = btn.text.strip()
                if btn_text:
                    button_list.append(f"{idx+1}. '{btn_text}'")
                    result += f"{idx+1}. `{btn_text[:50]}`\n"
            except:
                continue
        
        if not button_list:
            bot.reply_to(message, "❌ Кнопки не найдены")
            return
        
        result += f"\n📊 Всего кнопок: {len(button_list)}"
        result += "\n\n💡 Используйте /click <номер> для нажатия"
        
        user_buttons[user_id] = {
            'buttons': all_buttons,
            'list': button_list
        }
        
        bot.reply_to(message, result, parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")

@bot.message_handler(commands=['click'])
def handle_click(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /click <номер>")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Используйте: /click <номер>")
        return
    
    try:
        number = int(parts[1]) - 1
    except ValueError:
        bot.reply_to(message, "❌ Введите номер кнопки")
        return
    
    if user_id not in user_buttons:
        bot.reply_to(message, "❌ Сначала выполните /analyze")
        return
    
    buttons_data = user_buttons[user_id]
    if number < 0 or number >= len(buttons_data['buttons']):
        bot.reply_to(message, f"❌ Введите номер от 1 до {len(buttons_data['buttons'])}")
        return
    
    browser = user_sessions[user_id]
    btn = buttons_data['buttons'][number]
    
    try:
        btn_text = btn.text.strip()
        bot.reply_to(message, f"🔄 Нажимаю кнопку: '{btn_text}'")
        
        actions = ActionChains(browser.driver)
        actions.move_to_element(btn)
        time.sleep(0.3)
        actions.click()
        time.sleep(0.2)
        actions.perform()
        
        bot.send_message(chat_id, f"✅ Нажата кнопка: '{btn_text}'")
        
        screenshot = browser.take_screenshot(f"click_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="📸 После нажатия")
            os.remove(screenshot)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")

@bot.message_handler(commands=['clickpos'])
def handle_clickpos(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /clickpos X Y")
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /clickpos X Y")
        return
    
    try:
        x = int(parts[1])
        y = int(parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Введите числа: /clickpos 500 300")
        return
    
    browser = user_sessions[user_id]
    
    try:
        bot.reply_to(message, f"🖱️ Кликаю по координатам: ({x}, {y})")
        
        actions = ActionChains(browser.driver)
        actions.move_by_offset(x, y)
        time.sleep(0.3)
        actions.click()
        time.sleep(0.2)
        actions.perform()
        
        bot.send_message(chat_id, f"✅ Клик выполнен по ({x}, {y})")
        
        screenshot = browser.take_screenshot(f"clickpos_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📸 Клик по ({x}, {y})")
            os.remove(screenshot)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")

@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /logingoogle email@gmail.com password")
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен!")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /logingoogle <email> <пароль>")
        return
    
    email = parts[1]
    password = parts[2]
    
    msg = bot.reply_to(message, "🔄 Вход через Google... 30-50 секунд")
    
    def log_callback(log_text, level):
        send_log_to_chat(chat_id, log_text)
    
    def screenshot_callback(filename, caption):
        try:
            with open(filename, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📸 {caption}")
            os.remove(filename)
        except:
            pass
    
    browser = AntiDetectBrowser(
        headless=True,
        screenshot_callback=screenshot_callback,
        log_callback=log_callback
    )
    
    try:
        browser.setup_driver()
        
        google_ok = browser.login_google(email, password)
        if not google_ok:
            bot.edit_message_text("❌ Ошибка входа в Google", chat_id=chat_id, message_id=msg.message_id)
            browser.close()
            return
        
        xcom_ok = browser.go_to_xcom(bot=bot, chat_id=chat_id, user_id=user_id)
        
        if xcom_ok:
            user_sessions[user_id] = browser
            screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ Вход выполнен!")
                os.remove(screenshot)
            bot.edit_message_text("✅ Вход выполнен успешно!", chat_id=chat_id, message_id=msg.message_id)
            bot.send_message(chat_id, "📋 Используйте /getlog для скачивания полного лога")
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ Ошибка входа")
                os.remove(screenshot)
            bot.edit_message_text("❌ Ошибка входа\nПроверьте email и пароль", chat_id=chat_id, message_id=msg.message_id)
            bot.send_message(chat_id, "📋 Используйте /getlog для скачивания логов")
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=msg.message_id)
        try:
            browser.close()
        except:
            pass

@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен!")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = parts[1]
    password = parts[2]
    
    msg = bot.reply_to(message, "🔄 Выполняется вход...")
    
    def log_callback(log_text, level):
        send_log_to_chat(chat_id, log_text)
    
    def screenshot_callback(filename, caption):
        try:
            with open(filename, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📸 {caption}")
            os.remove(filename)
        except:
            pass
    
    browser = AntiDetectBrowser(
        headless=True,
        screenshot_callback=screenshot_callback,
        log_callback=log_callback
    )
    
    try:
        browser.setup_driver()
        result = browser.login_twitter(username, password)
        
        if result:
            user_sessions[user_id] = browser
            screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ Вход выполнен!")
                os.remove(screenshot)
            bot.edit_message_text("✅ Вход выполнен успешно!", chat_id=chat_id, message_id=msg.message_id)
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ Ошибка входа")
                os.remove(screenshot)
            bot.edit_message_text("❌ Ошибка входа", chat_id=chat_id, message_id=msg.message_id)
            browser.close()
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=msg.message_id)
        try:
            browser.close()
        except:
            pass

@bot.message_handler(commands=['status'])
def handle_status(message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            bot.reply_to(message, f"✅ Сессия активна\n🔗 {browser.driver.current_url}")
        except:
            bot.reply_to(message, "⚠️ Сессия неактивна")
            del user_sessions[user_id]
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    try:
        browser = user_sessions[user_id]
        screenshot = browser.take_screenshot(f"ss_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(user_id, photo, caption="📸 Скриншот")
            os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

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
    bot.reply_to(message, "Используйте /start для списка команд")

if __name__ == '__main__':
    print("🤖 Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=1)
    except Exception as e:
        print(f"❌ Ошибка polling: {e}")