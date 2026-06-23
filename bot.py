import telebot
import os
import time
import pickle
from browser import AntiDetectBrowser, check_installation
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw
from selenium.webdriver.common.by import By

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)

# === ФАЙЛЫ СЕССИЙ ===
GOOGLE_SESSION_FILE = "google_session.pkl"
X_SESSION_FILE = "x_session.pkl"

# === ГЛОБАЛЬНЫЕ СЕССИИ ===
google_browser = None  # Один браузер для Google
x_browsers = {}        # user_id -> browser для X
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

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        "👋 Команды:\n"
        "/logingoogle email пароль — Вход в Google (сохраняет сессию)\n"
        "/status_google — Проверить Google-сессию\n"
        "/loginx — Войти в X.com через Google\n"
        "/joystick — Управление X\n"
        "/screenshot — Скриншот X\n"
        "/close — Закрыть всё"
    )

# === /LOGINGOOGLE — только Google, сохраняет куки ===
@bot.message_handler(commands=['logingoogle'])
def handle_login_google(message):
    global google_browser
    
    chat_id = message.chat.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ /logingoogle email пароль")
        return
    
    email, password = parts[1], parts[2]
    msg = bot.reply_to(message, "🔄 Google...")
    
    # Закрываем старый если есть
    if google_browser:
        try:
            google_browser.close()
        except:
            pass
    
    google_browser = AntiDetectBrowser(headless=True)
    
    try:
        google_browser.setup_driver()
        ok = google_browser.login_google(email, password)
        
        if ok:
            # Сохраняем куки
            try:
                cookies = google_browser.driver.get_cookies()
                with open(GOOGLE_SESSION_FILE, "wb") as f:
                    pickle.dump(cookies, f)
            except:
                pass
            
            bot.edit_message_text("✅ Google OK", chat_id=chat_id, message_id=msg.message_id)
        else:
            bot.edit_message_text("❌ Google fail", chat_id=chat_id, message_id=msg.message_id)
            google_browser.close()
            google_browser = None
            
    except Exception as e:
        bot.edit_message_text(f"❌ {str(e)[:100]}", chat_id=chat_id, message_id=msg.message_id)
        google_browser = None

# === /STATUS_GOOGLE — проверяет/восстанавливает сессию ===
@bot.message_handler(commands=['status_google'])
def handle_status_google(message):
    global google_browser
    
    chat_id = message.chat.id
    
    if not google_browser or not google_browser.driver:
        bot.reply_to(message, "❌ Нет сессии. /logingoogle")
        return
    
    try:
        # Проверяем что Google помнит нас
        google_browser.driver.get("https://accounts.google.com/")
        time.sleep(2)
        url = google_browser.driver.current_url
        
        if "myaccount" in url or "signin" not in url:
            bot.reply_to(message, "✅ Google активен")
        else:
            # Пробуем восстановить из куки
            try:
                if os.path.exists(GOOGLE_SESSION_FILE):
                    with open(GOOGLE_SESSION_FILE, "rb") as f:
                        cookies = pickle.load(f)
                    for c in cookies:
                        try:
                            google_browser.driver.add_cookie(c)
                        except:
                            pass
                    google_browser.driver.get("https://accounts.google.com/")
                    time.sleep(2)
                    url = google_browser.driver.current_url
                    
                    if "myaccount" in url or "signin" not in url:
                        bot.reply_to(message, "✅ Google восстановлен из куки")
                        return
            except:
                pass
            
            bot.reply_to(message, "⚠️ Google вышел. /logingoogle заново")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")

# === /LOGINX — вход в X через Google-сессию ===
@bot.message_handler(commands=['loginx'])
def handle_login_x(message):
    global google_browser
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not google_browser or not google_browser.driver:
        bot.reply_to(message, "❌ Сначала /logingoogle")
        return
    
    msg = bot.reply_to(message, "🔄 X.com...")
    
    # Создаём новый браузер для X, но копируем куки Google
    x_browser = AntiDetectBrowser(headless=True)
    
    try:
        x_browser.setup_driver()
        
        # Копируем Google-куки
        try:
            cookies = google_browser.driver.get_cookies()
            x_browser.driver.get("https://google.com")
            time.sleep(1)
            for c in cookies:
                try:
                    x_browser.driver.add_cookie(c)
                except:
                    pass
        except:
            pass
        
        # Идём на X
        x_browser.driver.get("https://x.com")
        time.sleep(5)
        
        # Ищем кнопку Google
        x_browser.log("🔍 Поиск Google-кнопки...")
        btn = None
        
        for sel in [
            "//span[contains(text(), 'Continue as')]",
            "//span[contains(text(), 'Sign in with Google')]",
            "//div[contains(text(), 'Google')]",
            "//button[contains(., 'Google')]",
        ]:
            try:
                els = x_browser.driver.find_elements(By.XPATH, sel)
                for el in els:
                    if el.is_displayed():
                        btn = el
                        break
                if btn:
                    break
            except:
                continue
        
        if btn:
            x_browser.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(x_browser.driver).move_to_element(btn).pause(0.3).click().perform()
            except:
                x_browser.driver.execute_script("arguments[0].click();", btn)
            
            x_browser.log("✅ Клик по Google")
            time.sleep(5)
            
            url = x_browser.driver.current_url
            if "home" in url:
                x_browsers[user_id] = x_browser
                bot.edit_message_text("✅ X OK! /joystick", chat_id=chat_id, message_id=msg.message_id)
                return
        
        # Если не получилось — скрин и джойстик
        x_browser.driver.save_screenshot("x_fail.png")
        with open("x_fail.png", "rb") as f:
            bot.send_photo(chat_id, f, caption="⚠️ Нужен джойстик")
        os.remove("x_fail.png")
        
        x_browsers[user_id] = x_browser
        bot.edit_message_text("⚠️ /joystick для ручного клика", chat_id=chat_id, message_id=msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ {str(e)[:100]}", chat_id=chat_id, message_id=msg.message_id)
        try:
            x_browser.close()
        except:
            pass

# === /JOYSTICK — только для X ===
@bot.message_handler(commands=['joystick'])
def handle_joystick(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id not in x_browsers:
        bot.reply_to(message, "❌ Нет сессии X. /loginx")
        return
    
    browser = x_browsers[user_id]
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
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if user_id not in x_browsers:
        bot.answer_callback_query(call.id, "❌ Нет сессии")
        return
    
    browser = x_browsers[user_id]
    
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
            del x_browsers[user_id]
            del user_cursor[user_id]
        except:
            pass
        bot.answer_callback_query(call.id, "Закрыт")
        bot.edit_message_text("✅ Закрыт", chat_id=chat_id, message_id=msg_id)
        return
    
    # Обновляем скрин
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
    user_id = message.from_user.id
    if user_id not in x_browsers:
        bot.reply_to(message, "❌ Нет сессии")
        return
    try:
        fn = x_browsers[user_id].take_screenshot(f"ss_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.send_photo(user_id, f)
            os.remove(fn)
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")

# === /CLOSE — закрывает всё ===
@bot.message_handler(commands=['close'])
def handle_close(message):
    global google_browser
    user_id = message.from_user.id
    
    # Закрываем X
    if user_id in x_browsers:
        try:
            x_browsers[user_id].close()
        except:
            pass
        del x_browsers[user_id]
    
    # Закрываем Google
    if google_browser:
        try: 
            google_browser.close()
        except:
            pass
        google_browser = None
    
    if user_id in user_cursor:
        del user_cursor[user_id]
    
    bot.reply_to(message, "✅ Всё закрыто")

# === ЭХО ===
@bot.message_handler(func=lambda m: True)
def echo(m):
    bot.reply_to(m, "/start для списка команд")

if __name__ == '__main__':
    print("🤖 Бот запущен...")
    bot.polling(none_stop=True, interval=1)
