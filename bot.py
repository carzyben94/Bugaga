import telebot
import os
import time
from browser import AntiDetectBrowser, check_installation
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from PIL import Image, ImageDraw
from selenium.webdriver.common.by import By

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
user_cursor = {}

# === ОСНОВНОЕ МЕНЮ ===
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📊 /check"),
        KeyboardButton("🔑 /login"),
        KeyboardButton("🌐 /logingoogle"),
        KeyboardButton("🎮 /joystick"),
        KeyboardButton("📸 /screen_now"),
        KeyboardButton("🛑 /stop_x"),
        KeyboardButton("📋 /log"),
        KeyboardButton("📥 /getlog"),
        KeyboardButton("ℹ️ /status"),
        KeyboardButton("❌ /close")
    )
    return keyboard

def get_joystick_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("⬆️", callback_data="move_up"),
        InlineKeyboardButton("🔄", callback_data="refresh_screen")
    )
    keyboard.row(
        InlineKeyboardButton("⬅️", callback_data="move_left"),
        InlineKeyboardButton("💣 МЕГА-КЛИК", callback_data="mega_click"),
        InlineKeyboardButton("➡️", callback_data="move_right")
    )
    keyboard.row(
        InlineKeyboardButton("⬇️", callback_data="move_down"),
        InlineKeyboardButton("🏠", callback_data="move_center"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop_joystick")
    )
    keyboard.row(
        InlineKeyboardButton("📸 Скриншот", callback_data="take_screenshot"),
        InlineKeyboardButton("📍 Позиция", callback_data="show_position")
    )
    return keyboard

def send_log_to_chat(chat_id, log_entry):
    try:
        if any(x in log_entry for x in ["✅", "❌", "⚠️", "🎉", "🔐", "📱", "⌨️"]):
            bot.send_message(chat_id, log_entry)
    except:
        pass

def make_screenshot_with_cursor(browser, user_id, filename="screenshot.png"):
    try:
        if user_id in user_cursor:
            cursor_x = user_cursor[user_id]['x']
            cursor_y = user_cursor[user_id]['y']
        else:
            cursor_x = 960
            cursor_y = 400
        
        browser.driver.save_screenshot(filename)
        
        img = Image.open(filename)
        draw = ImageDraw.Draw(img)
        
        size = 20
        draw.line((cursor_x - size, cursor_y, cursor_x + size, cursor_y), fill="red", width=3)
        draw.line((cursor_x, cursor_y - size, cursor_x, cursor_y + size), fill="red", width=3)
        draw.ellipse((cursor_x - 5, cursor_y - 5, cursor_x + 5, cursor_y + 5), fill="red")
        draw.text((cursor_x + 25, cursor_y - 10), f"({cursor_x}, {cursor_y})", fill="red")
        
        img.save(filename)
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def move_cursor(user_id, dx, dy):
    if user_id not in user_cursor:
        user_cursor[user_id] = {'x': 960, 'y': 400}
    
    user_cursor[user_id]['x'] += dx
    user_cursor[user_id]['y'] += dy
    
    user_cursor[user_id]['x'] = max(0, min(1920, user_cursor[user_id]['x']))
    user_cursor[user_id]['y'] = max(0, min(1080, user_cursor[user_id]['y']))
    
    return user_cursor[user_id]['x'], user_cursor[user_id]['y']

def click_at_cursor(user_id):
    if user_id not in user_sessions:
        return False, "❌ Нет активной сессии"
    
    if user_id not in user_cursor:
        user_cursor[user_id] = {'x': 960, 'y': 400}
    
    browser = user_sessions[user_id]
    x = user_cursor[user_id]['x']
    y = user_cursor[user_id]['y']
    
    try:
        result = browser.driver.execute_script(f"""
            var el = document.elementFromPoint({x}, {y});
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        """)
        
        if result:
            return True, f"✅ Клик по ({x}, {y}) выполнен"
        else:
            browser.driver.execute_script(f"""
                var el = document.elementFromPoint({x}, {y});
                if (el) {{
                    el.click();
                }}
            """)
            return True, f"✅ Принудительный клик по ({x}, {y})"
            
    except Exception as e:
        return False, f"❌ Ошибка: {e}"

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 **Привет! Я бот для автоматизации X.com**\n\n"
        "📋 **Основные команды:**\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/joystick - Джойстик управления\n"
        "/screen_now - Скриншот с курсором\n"
        "/stop_x - Остановить джойстик\n"
        "/log - Показать логи\n"
        "/getlog - Скачать лог-файл\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n\n"
        "💡 **Нажмите /help для подробной справки**",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# === КОМАНДА /HELP ===
@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(
        message,
        "📖 **Справка по командам:**\n\n"
        "🔧 **Установка:**\n"
        "/check - Проверить установку Chrome\n\n"
        "🔑 **Вход:**\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n\n"
        "🎮 **Управление:**\n"
        "/joystick - Открыть джойстик\n"
        "/screen_now - Скриншот с курсором\n"
        "/stop_x - Остановить джойстик\n\n"
        "📋 **Логи:**\n"
        "/log - Показать логи\n"
        "/getlog - Скачать лог-файл\n\n"
        "ℹ️ **Информация:**\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# === ОБРАБОТЧИК ТЕКСТОВЫХ КОМАНД (для кнопок) ===
@bot.message_handler(func=lambda message: message.text.startswith('/'))
def handle_text_commands(message):
    """Перенаправляет текстовые команды с кнопок"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Разбираем команду
    text = message.text
    if text.startswith('/'):
        # Создаем объект message для обработчиков
        class FakeMessage:
            pass
        fake_msg = FakeMessage()
        fake_msg.text = text
        fake_msg.from_user = message.from_user
        fake_msg.chat = message.chat
        
        # Перенаправляем
        if text.startswith('/check'):
            handle_check(fake_msg)
        elif text.startswith('/login'):
            handle_login(fake_msg)
        elif text.startswith('/logingoogle'):
            handle_login_google(fake_msg)
        elif text.startswith('/joystick'):
            handle_joystick(fake_msg)
        elif text.startswith('/screen_now'):
            handle_screen_now(fake_msg)
        elif text.startswith('/stop_x'):
            handle_stop_x(fake_msg)
        elif text.startswith('/log'):
            handle_log(fake_msg)
        elif text.startswith('/getlog'):
            handle_get_log(fake_msg)
        elif text.startswith('/status'):
            handle_status(fake_msg)
        elif text.startswith('/screenshot'):
            handle_screenshot(fake_msg)
        elif text.startswith('/close'):
            handle_close(fake_msg)
        else:
            bot.reply_to(message, "❌ Неизвестная команда. Используйте /help", reply_markup=get_main_keyboard())

# === КОМАНДА /CHECK ===
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
    
    bot.reply_to(message, result, parse_mode='Markdown', reply_markup=get_main_keyboard())

# === КОМАНДА /LOG ===
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

# === КОМАНДА /GETLOG ===
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

# === КОМАНДА /JOYSTICK ===
@bot.message_handler(commands=['joystick'])
def handle_joystick(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /logingoogle", reply_markup=get_main_keyboard())
        return
    
    browser = user_sessions[user_id]
    user_cursor[user_id] = {'x': 960, 'y': 400}
    
    try:
        screenshot = make_screenshot_with_cursor(browser, user_id, f"joystick_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption="🎮 **Джойстик управления**\n\n"
                           "⬆️ ⬇️ ⬅️ ➡️ — двигать курсор\n"
                           "💣 МЕГА-КЛИК — пробует 15 методов\n"
                           "🔄 — обновить экран\n"
                           "📍 — позиция курсора\n"
                           "📸 — скриншот\n"
                           "🏠 — центр\n"
                           "⏹️ СТОП — закрыть браузер\n\n"
                           "🔴 Красный крест — позиция курсора",
                    reply_markup=get_joystick_keyboard(),
                    parse_mode='Markdown'
                )
            os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# === ОБРАБОТЧИК КНОПОК ДЖОЙСТИКА ===
@bot.callback_query_handler(func=lambda call: True)
def handle_joystick_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if user_id not in user_sessions:
        bot.answer_callback_query(call.id, "❌ Нет активной сессии")
        return
    
    browser = user_sessions[user_id]
    
    if call.data == "move_up":
        x, y = move_cursor(user_id, 0, -30)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        screenshot = make_screenshot_with_cursor(browser, user_id, f"move_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📍 Курсор: ({x}, {y})", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        
    elif call.data == "move_down":
        x, y = move_cursor(user_id, 0, 30)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        screenshot = make_screenshot_with_cursor(browser, user_id, f"move_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📍 Курсор: ({x}, {y})", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        
    elif call.data == "move_left":
        x, y = move_cursor(user_id, -30, 0)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        screenshot = make_screenshot_with_cursor(browser, user_id, f"move_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📍 Курсор: ({x}, {y})", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        
    elif call.data == "move_right":
        x, y = move_cursor(user_id, 30, 0)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        screenshot = make_screenshot_with_cursor(browser, user_id, f"move_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📍 Курсор: ({x}, {y})", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        
    elif call.data == "move_center":
        user_cursor[user_id] = {'x': 960, 'y': 400}
        bot.answer_callback_query(call.id, "📍 Центр (960, 400)")
        screenshot = make_screenshot_with_cursor(browser, user_id, f"center_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="📍 Центр (960, 400)", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
    
    elif call.data == "mega_click":
        bot.answer_callback_query(call.id, "💣 МЕГА-КЛИК запущен!")
        bot.send_message(chat_id, "💣 Запущен МЕГА-КЛИК...")
        
        try:
            result = browser.mega_click(x=960, y=380, text="Continue as")
            if result:
                bot.send_message(chat_id, "✅ МЕГА-КЛИК сработал!")
                screenshot = browser.take_screenshot(f"mega_click_{user_id}.png")
                if screenshot:
                    with open(screenshot, 'rb') as photo:
                        bot.send_photo(chat_id, photo, caption="📸 После МЕГА-КЛИКА", reply_markup=get_joystick_keyboard())
                    os.remove(screenshot)
            else:
                bot.send_message(chat_id, "❌ МЕГА-КЛИК не сработал", reply_markup=get_joystick_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard())
    
    elif call.data == "click_cursor":
        success, msg = click_at_cursor(user_id)
        bot.answer_callback_query(call.id, msg)
        
        screenshot = make_screenshot_with_cursor(browser, user_id, f"after_click_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                x = user_cursor[user_id]['x']
                y = user_cursor[user_id]['y']
                bot.send_photo(
                    chat_id, 
                    photo, 
                    caption=f"💪 Клик по ({x}, {y})\n{msg}",
                    reply_markup=get_joystick_keyboard()
                )
            os.remove(screenshot)
        else:
            bot.send_message(chat_id, "❌ Не удалось сделать скриншот", reply_markup=get_joystick_keyboard())
    
    elif call.data == "take_screenshot":
        screenshot = make_screenshot_with_cursor(browser, user_id, f"ss_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="📸 Скриншот", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        bot.answer_callback_query(call.id, "📸 Готово")
    
    elif call.data == "show_position":
        if user_id in user_cursor:
            x = user_cursor[user_id]['x']
            y = user_cursor[user_id]['y']
            bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        else:
            bot.answer_callback_query(call.id, "📍 Курсор не инициализирован")
    
    elif call.data == "refresh_screen":
        screenshot = make_screenshot_with_cursor(browser, user_id, f"refresh_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="🔄 Обновленный экран", reply_markup=get_joystick_keyboard())
            os.remove(screenshot)
        bot.answer_callback_query(call.id, "🔄 Обновлено")
    
    elif call.data == "stop_joystick":
        try:
            browser.close()
            del user_sessions[user_id]
            if user_id in user_cursor:
                del user_cursor[user_id]
            bot.answer_callback_query(call.id, "✅ Браузер закрыт")
            bot.edit_message_text(
                "✅ **Браузер закрыт**\n\nДжойстик остановлен.",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown'
            )
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка")
    
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=get_joystick_keyboard())
    except:
        pass

# === ОСТАЛЬНЫЕ КОМАНДЫ ===
@bot.message_handler(commands=['login'])
def handle_login(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>", reply_markup=get_main_keyboard())
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен!", reply_markup=get_main_keyboard())
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /login <логин> <пароль>", reply_markup=get_main_keyboard())
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
    
    bot.send_message(chat_id, "📋 Используйте /log для логов", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /logingoogle email@gmail.com password", reply_markup=get_main_keyboard())
        return
    
    check = check_installation()
    if not check['chrome']:
        bot.reply_to(message, "❌ Chrome не установлен!", reply_markup=get_main_keyboard())
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Используйте: /logingoogle <email> <пароль>", reply_markup=get_main_keyboard())
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
        
        xcom_ok = browser.go_to_xcom()
        
        if xcom_ok:
            user_sessions[user_id] = browser
            screenshot = browser.take_screenshot(f"final_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="✅ Вход в Google выполнен!\n\nИспользуйте /joystick для управления")
                os.remove(screenshot)
            bot.edit_message_text("✅ Вход в Google выполнен!\n\nИспользуйте /joystick для управления", chat_id=chat_id, message_id=msg.message_id)
        else:
            screenshot = browser.take_screenshot(f"error_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="❌ Ошибка")
                os.remove(screenshot)
            bot.edit_message_text("❌ Ошибка входа", chat_id=chat_id, message_id=msg.message_id)
            browser.close()
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=chat_id, message_id=msg.message_id)
        try:
            browser.close()
        except:
            pass
    
    bot.send_message(chat_id, "📋 Используйте /joystick для управления", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['screen_now'])
def handle_screen_now(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /logingoogle", reply_markup=get_main_keyboard())
        return
    
    browser = user_sessions[user_id]
    
    try:
        screenshot = make_screenshot_with_cursor(browser, user_id, f"screen_now_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                if user_id in user_cursor:
                    x = user_cursor[user_id]['x']
                    y = user_cursor[user_id]['y']
                    caption = f"📸 **Текущий экран**\n📍 URL: {browser.driver.current_url}\n🎯 Курсор: ({x}, {y})"
                else:
                    caption = f"📸 **Текущий экран**\n📍 URL: {browser.driver.current_url}"
                bot.send_photo(chat_id, photo, caption=caption, parse_mode='Markdown', reply_markup=get_main_keyboard())
            os.remove(screenshot)
        else:
            bot.reply_to(message, "❌ Не удалось сделать скриншот", reply_markup=get_main_keyboard())
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['stop_x'])
def handle_stop_x(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии", reply_markup=get_main_keyboard())
        return
    
    browser = user_sessions[user_id]
    
    try:
        browser.close()
        del user_sessions[user_id]
        if user_id in user_cursor:
            del user_cursor[user_id]
        bot.reply_to(
            message,
            "✅ **Браузер закрыт**\n\nДжойстик остановлен.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['status'])
def handle_status(message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            bot.reply_to(message, f"✅ Сессия активна\n🔗 {browser.driver.current_url}", reply_markup=get_main_keyboard())
        except:
            bot.reply_to(message, "⚠️ Сессия неактивна", reply_markup=get_main_keyboard())
            del user_sessions[user_id]
    else:
        bot.reply_to(message, "❌ Нет активной сессии", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии", reply_markup=get_main_keyboard())
        return
    try:
        browser = user_sessions[user_id]
        screenshot = make_screenshot_with_cursor(browser, user_id, f"ss_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(user_id, photo, caption="📸 Скриншот с курсором", reply_markup=get_main_keyboard())
            os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['close'])
def handle_close(message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]
            browser.close()
            del user_sessions[user_id]
            if user_id in user_cursor:
                del user_cursor[user_id]
            bot.reply_to(message, "✅ Браузер закрыт", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())
    else:
        bot.reply_to(message, "❌ Нет активной сессии", reply_markup=get_main_keyboard())

# === ЭХО ===
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message,
        "📩 Используйте /start для меню или /help для справки",
        reply_markup=get_main_keyboard()
    )

# === ЗАПУСК ===
if __name__ == '__main__':
    print("🤖 Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=1)
    except Exception as e:
        print(f"❌ Ошибка polling: {e}")