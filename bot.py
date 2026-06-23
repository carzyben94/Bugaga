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

# === ГЛОБАЛЬНЫЙ БРАУЗЕР ===
browser = None
user_cursor = {}

try:
    bot.remove_webhook()
    print("✅ Webhook сброшен")
except Exception as e:
    print(f"⚠️ Ошибка сброса webhook: {e}")

# === ДЖОЙСТИК ===
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
        InlineKeyboardButton("📸 Скрин", callback_data="take_screenshot"),
        InlineKeyboardButton("📍 Позиция", callback_data="show_position")
    )
    return keyboard

def make_screenshot_with_cursor(browser, user_id, filename="screenshot.png"):
    try:
        cursor = user_cursor.get(user_id, {'x': 960, 'y': 400})
        browser.driver.save_screenshot(filename)
        img = Image.open(filename)
        draw = ImageDraw.Draw(img)
        x, y = cursor['x'], cursor['y']
        draw.line((x-20, y, x+20, y), fill="red", width=3)
        draw.line((x, y-20, x, y+20), fill="red", width=3)
        draw.ellipse((x-5, y-5, x+5, y+5), fill="red")
        draw.text((x+25, y-10), f"({x},{y})", fill="red")
        img.save(filename)
        return filename
    except Exception as e:
        print(f"❌ Скрин: {e}")
        return None

def move_cursor(user_id, dx, dy):
    if user_id not in user_cursor:
        user_cursor[user_id] = {'x': 960, 'y': 400}
    user_cursor[user_id]['x'] = max(0, min(1920, user_cursor[user_id]['x'] + dx))
    user_cursor[user_id]['y'] = max(0, min(1080, user_cursor[user_id]['y'] + dy))
    return user_cursor[user_id]['x'], user_cursor[user_id]['y']

# === /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        "👋 Команды:\n"
        "/logingoogle email пароль — Вход в Google\n"
        "/loginx — Войти в X.com (Google уже залогинен)\n"
        "/joystick — Управление\n"
        "/screenshot — Скриншот\n"
        "/close — Закрыть всё"
    )

# === /LOGINGOOGLE ===
@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    global browser
    
    chat_id = message.chat.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ /logingoogle email пароль")
        return
    
    email, password = parts[1], parts[2]
    msg = bot.reply_to(message, "🔄 Google...")
    
    if browser:
        try:
            browser.close()
        except:
            pass
        browser = None
    
    try:
        browser = AntiDetectBrowser(headless=True)
        browser.setup_driver()
        ok = browser.login_google(email, password)
        
        if ok:
            bot.edit_message_text("✅ Google OK. /loginx", chat_id=chat_id, message_id=msg.message_id)
        else:
            bot.edit_message_text("❌ Google fail", chat_id=chat_id, message_id=msg.message_id)
            browser.close()
            browser = None
            
    except Exception as e:
        bot.edit_message_text(f"❌ {str(e)[:100]}", chat_id=chat_id, message_id=msg.message_id)
        browser = None

# === /LOGINX ===
@bot.message_handler(commands=['loginx'])
def handle_login_x(message):
    global browser
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not browser or not browser.driver:
        bot.reply_to(message, "❌ Сначала /logingoogle")
        return
    
    msg = bot.reply_to(message, "🔄 X.com...")
    
    try:
        browser.driver.get("https://x.com")
        time.sleep(5)
        
        url = browser.driver.current_url
        if "home" in url:
            bot.reply_to(message, "✅ X уже залогинен!")
            return
        
        # Ищем Google-кнопку
        btn = None
        for sel in [
            "//span[contains(text(), 'Continue as')]",
            "//span[contains(text(), 'Sign in with Google')]",
            "//div[contains(text(), 'Google')]",
            "//button[contains(., 'Google')]",
        ]:
            try:
                els = browser.driver.find_elements(By.XPATH, sel)
                for el in els:
                    if el.is_displayed():
                        btn = el
                        break
                if btn:
                    break
            except:
                continue
        
        if btn:
            browser.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(browser.driver).move_to_element(btn).pause(0.3).click().perform()
            
            time.sleep(5)
            url = browser.driver.current_url
            
            if "home" in url:
                bot.reply_to(message, "✅ X OK! /joystick")
                return
        
        # Не получилось — скрин для джойстика
        browser.driver.save_screenshot("x_fail.png")
        with open("x_fail.png", "rb") as f:
            bot.send_photo(chat_id, f, caption="⚠️ Нужен джойстик")
        os.remove("x_fail.png")
        
        bot.reply_to(message, "⚠️ /joystick для ручного клика")
        
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")

# === /JOYSTICK ===
@bot.message_handler(commands=['joystick'])
def handle_joystick(message):
    global browser
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not browser or not browser.driver:
        bot.reply_to(message, "❌ Нет сессии. /logingoogle")
        return
    
    user_cursor[user_id] = {'x': 960, 'y': 400}
    
    try:
        fn = make_screenshot_with_cursor(browser, user_id, f"joy_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.send_photo(chat_id, f, reply_markup=get_joystick_keyboard())
            os.remove(fn)
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

# === ОБРАБОТЧИК КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    global browser
    
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if not browser or not browser.driver:
        bot.answer_callback_query(call.id, "❌ Нет сессии")
        return
    
    if call.data == "move_up":
        x, y = move_cursor(user_id, 0, -30)
        bot.answer_callback_query(call.id, f"({x},{y})")
    elif call.data == "move_down":
        x, y = move_cursor(user_id, 0, 30)
        bot.answer_callback_query(call.id, f"({x},{y})")
    elif call.data == "move_left":
        x, y = move_cursor(user_id, -30, 0)
        bot.answer_callback_query(call.id, f"({x},{y})")
    elif call.data == "move_right":
        x, y = move_cursor(user_id, 30, 0)
        bot.answer_callback_query(call.id, f"({x},{y})")
    elif call.data == "move_center":
        user_cursor[user_id] = {'x': 960, 'y': 400}
        bot.answer_callback_query(call.id, "Центр")
    elif call.data == "mega_click":
        bot.answer_callback_query(call.id, "Клик!")
        x, y = user_cursor.get(user_id, {'x': 960, 'y': 400}).values()
        browser.mega_click(x=x, y=y, text="Continue")
    elif call.data == "take_screenshot":
        bot.answer_callback_query(call.id, "Скрин...")
        try:
            fn = browser.take_screenshot(f"ss_{user_id}.png")
            if fn:
                with open(fn, "rb") as f:
                    bot.send_photo(chat_id, f)
                os.remove(fn)
        except:
            pass
        return
    elif call.data == "refresh_screen":
        bot.answer_callback_query(call.id, "Обновление...")
    elif call.data == "show_position":
        c = user_cursor.get(user_id, {'x': 960, 'y': 400})
        bot.answer_callback_query(call.id, f"({c['x']},{c['y']})")
        return
    elif call.data == "stop_joystick":
        try:
            browser.close()
            browser = None
            if user_id in user_cursor:
                del user_cursor[user_id]
        except:
            pass
        bot.answer_callback_query(call.id, "Закрыт")
        bot.edit_message_text("✅ Закрыт", chat_id=chat_id, message_id=msg_id)
        return
    
    try:
        fn = make_screenshot_with_cursor(browser, user_id, f"upd_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=msg_id,
                    media=telebot.types.InputMediaPhoto(f),
                    reply_markup=get_joystick_keyboard()
                )
            os.remove(fn)
    except:
        pass

# === /SCREENSHOT ===
@bot.message_handler(commands=['screenshot'])
def handle_screenshot(message):
    global browser
    
    user_id = message.from_user.id
    if not browser or not browser.driver:
        bot.reply_to(message, "❌ Нет сессии")
        return
    try:
        fn = browser.take_screenshot(f"ss_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.send_photo(user_id, f)
            os.remove(fn)
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")

# === /CLOSE ===
@bot.message_handler(commands=['close'])
def handle_close(message):
    global browser
    
    user_id = message.from_user.id
    
    if browser:
        try:
            browser.close()
        except:
            pass
        browser = None
    
    if user_id in user_cursor:
        del user_cursor[user_id]
    
    bot.reply_to(message, "✅ Закрыто")

# === ЭХО ===
@bot.message_handler(func=lambda m: True)
def echo(m):
    bot.reply_to(m, "/start для списка команд")

if __name__ == '__main__':
    print("🤖 Бот запущен...")
    bot.polling(none_stop=True, interval=1)
