import telebot
import os
import time
from browser import AntiDetectBrowser, check_installation
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

def send_log_to_chat(chat_id, log_entry):
    try:
        if any(x in log_entry for x in ["✅", "❌", "⚠️", "🎉", "🔐", "📱", "⌨️"]):
            bot.send_message(chat_id, log_entry)
    except:
        pass

# === КНОПКИ ДЖОЙСТИКА ===
def get_joystick_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("⬆️", callback_data="move_up"),
        InlineKeyboardButton("🔄", callback_data="refresh_screen")
    )
    keyboard.row(
        InlineKeyboardButton("⬅️", callback_data="move_left"),
        InlineKeyboardButton("🖱️ КЛИК", callback_data="click_cursor"),
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
        success = browser.click_by_coordinates(x, y)
        return success, f"✅ Клик по ({x}, {y})" if success else f"❌ Ошибка клика по ({x}, {y})"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"

# === КОМАНДА /JOYSTICK ===
@bot.message_handler(commands=['joystick'])
def handle_joystick(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /logingoogle")
        return
    
    browser = user_sessions[user_id]
    user_cursor[user_id] = {'x': 960, 'y': 400}
    
    try:
        screenshot = browser.take_screenshot(f"joystick_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption="🎮 **Джойстик управления**\n\n"
                           "⬆️ ⬇️ ⬅️ ➡️ — двигать курсор\n"
                           "🖱️ КЛИК — нажать (скриншот автоматически)\n"
                           "🔄 — обновить экран\n"
                           "📍 — позиция курсора\n"
                           "📸 — скриншот\n"
                           "🏠 — центр\n"
                           "⏹️ СТОП — закрыть браузер",
                    reply_markup=get_joystick_keyboard(),
                    parse_mode='Markdown'
                )
            os.remove(screenshot)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# === ОБРАБОТЧИК КНОПОК ===
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
        
    elif call.data == "move_down":
        x, y = move_cursor(user_id, 0, 30)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        
    elif call.data == "move_left":
        x, y = move_cursor(user_id, -30, 0)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        
    elif call.data == "move_right":
        x, y = move_cursor(user_id, 30, 0)
        bot.answer_callback_query(call.id, f"📍 ({x}, {y})")
        
    elif call.data == "move_center":
        user_cursor[user_id] = {'x': 960, 'y': 400}
        bot.answer_callback_query(call.id, "📍 Центр (960, 400)")
    
    elif call.data == "click_cursor":
        success, msg = click_at_cursor(user_id)
        bot.answer_callback_query(call.id, msg)
        
        screenshot = browser.take_screenshot(f"after_click_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                x = user_cursor[user_id]['x']
                y = user_cursor[user_id]['y']
                bot.send_photo(
                    chat_id, 
                    photo, 
                    caption=f"🖱️ Клик по ({x}, {y})\n{msg}",
                    reply_markup=get_joystick_keyboard()
                )
            os.remove(screenshot)
        else:
            bot.send_message(chat_id, "❌ Не удалось сделать скриншот", reply_markup=get_joystick_keyboard())
    
    elif call.data == "take_screenshot":
        screenshot = browser.take_screenshot(f"ss_{user_id}.png")
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
        screenshot = browser.take_screenshot(f"refresh_{user_id}.png")
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

# === КОМАНДА /SCREEN_NOW ===
@bot.message_handler(commands=['screen_now'])
def handle_screen_now(message):
    """Сделать скриншот текущей страницы"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии. Используйте /logingoogle")
        return
    
    browser = user_sessions[user_id]
    
    try:
        screenshot = browser.take_screenshot(f"screen_now_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption=f"📸 **Текущий экран**\n📍 URL: {browser.driver.current_url}",
                    parse_mode='Markdown'
                )
            os.remove(screenshot)
        else:
            bot.reply_to(message, "❌ Не удалось сделать скриншот")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")

# === КОМАНДА /STOP_X ===
@bot.message_handler(commands=['stop_x'])
def handle_stop_x(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
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
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")

# === ОСТАЛЬНЫЕ КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Привет!\n\n"
        "📋 Команды:\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/joystick - Управление курсором\n"
        "/screen_now - Скриншот текущей страницы\n"
        "/stop_x - Остановить джойстик\n"
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
    
    def log_callback(log_text