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

def get_joystick_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("⬆️", callback_data="move_up"),
        InlineKeyboardButton("🔄", callback_data="refresh_screen")
    )
    keyboard.row(
        InlineKeyboardButton("⬅️", callback_data="move_left"),
        InlineKeyboardButton("💪 КЛИК", callback_data="click_cursor"),
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
    keyboard.row(
        InlineKeyboardButton("🎯 CLICK (960,380)", callback_data="click_coords_960_380")
    )
    keyboard.row(
        InlineKeyboardButton("🔍 FIND", callback_data="find_elements")
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
        result = browser.driver.execute_script(f"""
            var el = document.elementFromPoint({x}, {y});
            if (el) {{
                el.scrollIntoView({{block: 'center'}});
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
                           "💪 КЛИК — клик по позиции курсора\n"
                           "🎯 CLICK (960,380) — клик по кнопке\n"
                           "🔍 FIND — найти все элементы\n"
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
    
    elif call.data == "click_coords_960_380":
        try:
            x, y = 960, 380
            bot.answer_callback_query(call.id, f"🖱️ Клик по ({x}, {y})")
            
            result = browser.driver.execute_script(f"""
                var el = document.elementFromPoint({x}, {y});
                if (el) {{
                    el.scrollIntoView({{block: 'center'}});
                    el.click();
                    return true;
                }}
                return false;
            """)
            
            if result:
                bot.send_message(chat_id, f"✅ Клик по ({x}, {y}) выполнен")
            else:
                browser.driver.execute_script(f"""
                    var el = document.elementFromPoint({x}, {y});
                    if (el) {{
                        el.click();
                    }}
                """)
                bot.send_message(chat_id, f"✅ Принудительный клик по ({x}, {y})")
            
            screenshot = browser.take_screenshot(f"click_960_380_{user_id}.png")
            if screenshot:
                with open(screenshot, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption=f"📸 Клик по ({x}, {y})", reply_markup=get_joystick_keyboard())
                os.remove(screenshot)
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}")
            bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
    
    elif call.data == "find_elements":
        try:
            elements = browser.find_all_elements_js()
            result = "🔍 **Найденные элементы:**\n\n"
            count = 0
            for elem in elements:
                if elem['text'] and len(elem['text']) > 2:
                    count += 1
                    visible = '✅' if elem['visible'] else '👻'
                    result += f"{count}. [{elem['tag']}] {visible} '{elem['text'][:50]}'\n"
            if count == 0:
                result += "❌ Элементы не найдены"
            bot.send_message(chat_id, result, parse_mode='Markdown')
            bot.answer_callback_query(call.id, "🔍 Найдено элементов: " + str(count))
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}")
    
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
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Привет!\n\n"
        "📋 Команды:\n"
        "/check - Проверить установку\n"
        "/login логин пароль - Обычный вход\n"
        "/logingoogle email пароль - Вход через Google\n"
        "/joystick - Джойстик с кнопками\n"
        "/screen_now - Скриншот с курсором\n"
        "/stop_x - Остановить джойстик\n"
        "/log - Показать логи\n"
        "/getlog - Скачать лог-файл\n"
        "/status - Статус сессии\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер"
    )

# ... остальные команды без изменений