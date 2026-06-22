import telebot
import os
import time
import threading
from browser import AntiDetectBrowser, check_installation

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)
user_sessions = {}

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Привет!\n\n"
        "📋 Команды:\n"
        "/install - Установить Chrome\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер"
    )

# === КОМАНДА /INSTALL ===
@bot.message_handler(commands=['install'])
def handle_install(message):
    msg = bot.reply_to(message, "🔄 Установка Chrome... 1-2 минуты")
    
    try:
        browser = AntiDetectBrowser(headless=True)
        chrome_path = browser.install_chrome_local()
        
        if chrome_path:
            bot.edit_message_text(
                f"✅ Chrome установлен!\n📍 {chrome_path}",
                chat_id=msg.chat.id,
                message_id=msg.message_id
            )
        else:
            bot.edit_message_text(
                "❌ Ошибка установки Chrome",
                chat_id=msg.chat.id,
                message_id=msg.message_id
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}",
            chat_id=msg.chat.id,
            message_id=msg.message_id
        )

# === КОМАНДА /CHECK ===
@bot.message_handler(commands=['check'])
def handle_check(message):
    check = check_installation()
    
    if check['chrome']:
        bot.reply_to(message, f"✅ Chrome установлен:\n📍 {check['chrome_path']}")
    else:
        bot.reply_to(message, "❌ Chrome не установлен\nИспользуйте /install")

# === КОМАНДА /LOGINGOOGLE ===
@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # === ДИАГНОСТИКА ===
    print(f"📩 Получено сообщение: {message}")
    print(f"📩 Текст: {message.text}")
    print(f"📩 ID пользователя: {user_id}")
    # ====================
    
    # Проверяем что текст есть
    if message.text is None:
        bot.reply_to(message, "❌ Ошибка: команда не содержит текст\nИспользуйте: /logingoogle email@gmail.com password")
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    # Разбираем команду
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /logingoogle <email> <пароль>")
        return
    
    email = parts[1]
    password = parts[2]
    
    msg = bot.reply_to(message, "🔄 Вход через Google... 30-50 секунд")
    
    browser = AntiDetectBrowser(headless=True)
    
    try:
        browser.setup_driver()
        result = browser.login_google_first_then_twitter(email, password)
        
        if result:
            user_sessions[user_id] = browser
            
            screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ Вход выполнен!")
                os.remove(screenshot)
            
            bot.edit_message_text(
                "✅ Вход выполнен успешно!",
                chat_id=chat_id,
                message_id=msg.message_id
            )
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ Ошибка входа")
                os.remove(screenshot)
            
            bot.edit_message_text(
                "❌ Ошибка входа\nПроверьте email и пароль",
                chat_id=chat_id,
                message_id=msg.message_id
            )
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}",
            chat_id=chat_id,
            message_id=msg.message_id
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
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен! Используйте /install")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>")
        return
    
    username = parts[1]
    password = parts[2]
    
    msg = bot.reply_to(message, "🔄 Выполняется вход...")
    
    browser = AntiDetectBrowser(headless=True)
    
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
            
            bot.edit_message_text(
                "✅ Вход выполнен успешно!",
                chat_id=chat_id,
                message_id=msg.message_id
            )
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ Ошибка входа")
                os.remove(screenshot)
            
            bot.edit_message_text(
                "❌ Ошибка входа",
                chat_id=chat_id,
                message_id=msg.message_id
            )
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}",
            chat_id=chat_id,
            message_id=msg.message_id
        )
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
            bot.reply_to(message, f"✅ Сессия активна\n🔗 {url}")
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
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(user_id, photo, caption="📸 Скриншот")
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

# === ЭХО ===
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "Используйте /start для списка команд")

# === ЗАПУСК ===
if __name__ == '__main__':
    print("🤖 Бот запущен (polling)...")
    try:
        bot.polling(none_stop=True, interval=1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")