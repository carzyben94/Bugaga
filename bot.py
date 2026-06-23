import telebot
import os
import time
from browser import AntiDetectBrowser, check_installation
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# === ДЖОЙСТИК (кнопки остаются только здесь) ===
def get_joystick_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("⬆️", callback_data="move_up"),
        InlineKeyboardButton("🔄", callback_data="refresh_screen")
    )
    keyboard.row(
        InlineKeyboardButton("⬅️", callback_data="move_left"),
        InlineKeyboardButton("💣 КЛИК", callback_data="mega_click"),
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

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Привет!\n\n"
        "📋 Команды :\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/joystick - Джойстик управления\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер"
    )

# === КОМАНДА /LOGINGOOGLE ===
@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.text is None:
        bot.reply_to(message, "❌ Используйте: /logingoogle email пароль")
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
    
    def screenshot_callback(filename, caption):
        try:
            with open(filename, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"📸 {caption}")
            os.remove(filename)
        except:
            pass
    
    browser = AntiDetectBrowser(
        headless=True,
        screenshot_callback=screenshot_callback
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
                    bot.send_photo(chat_id, photo, caption="✅ Вход выполнен!\n\nИспользуйте /joystick")
                os.remove(screenshot)
            bot.edit_message_text("✅ Вход выполнен!\n\nИспользуйте /joystick", chat_id=chat_id, message_id=msg.message_id)
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
        screenshot = make_screenshot_with_cursor(browser, user_id, f"joystick_{user_id}.png")
        if screenshot:
            with open(screenshot, 'rb') as photo:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption="🎮 **Джойстик управления**\n\n"
                           "⬆️ ⬇️ ⬅️ ➡️ — двигать курсор\n"
                           "💣 КЛИК — нажать\n"
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
        bot.answer_callback_query(call.id, "🖱️ Клик!")
        
        try:
            browser.mega_click(x=960, y=380, text="Continue as")
            screenshot = browser.take_screenshot(f"click_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="🖱️ Клик выполнен", reply_markup=get_joystick_keyboard())
                os.remove(screenshot)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard())
    
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
            bot.edit_message_text("✅ **Браузер закрыт**", chat_id=chat_id, message_id=message_id)
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка")
    
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=get_joystick_keyboard())
    except:
        pass

# === КОМАНДА /SCREENSHOT ===
@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        bot.reply_to(message, "❌ Нет активной сессии")
        return
    try:
        browser = user_sessions[user_id]
        screenshot = make_screenshot_with_cursor(browser, user_id, f"ss_{user_id}.png")
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
            if user_id in user_cursor:
                del user_cursor[user_id]
            bot.reply_to(message, "✅ Браузер закрыт")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")
    else:
        bot.reply_to(message, "❌ Нет активной сессии")

# === ЭХО ===
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(
        message,
        "Используйте /start для списка команд"
    )

# === ЗАПУСК ===
if __name__ == '__main__':
    print("🤖 Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=1)
    except Exception as e:
        print(f"❌ Ошибка polling: {e}")
