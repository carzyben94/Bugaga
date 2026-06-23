import os
import asyncio
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from PIL import Image, ImageDraw
from browser import Browser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
browser = None
user_cursor = {}
loop = None
chat_id_log = None


def run_async(coro):
    global loop
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def log_callback(message):
    print(message)
    if chat_id_log:
        try:
            bot.send_message(chat_id_log, f"📋 {message}")
        except:
            pass


# === КЛАВИАТУРА ДЖОЙСТИКА ===
def get_joystick():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("⬆️", callback_data="up"),
        InlineKeyboardButton("🔄", callback_data="refresh")
    )
    keyboard.row(
        InlineKeyboardButton("⬅️", callback_data="left"),
        InlineKeyboardButton("💣 КЛИК", callback_data="click"),
        InlineKeyboardButton("➡️", callback_data="right")
    )
    keyboard.row(
        InlineKeyboardButton("⬇️", callback_data="down"),
        InlineKeyboardButton("🏠", callback_data="center"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop")
    )
    keyboard.row(
        InlineKeyboardButton("📸 Скрин", callback_data="screenshot"),
        InlineKeyboardButton("📍 Позиция", callback_data="position")
    )
    return keyboard


# === СКРИНШОТ С КУРСОРОМ ===
def screenshot_with_cursor(user_id, filename="screen.png", page=None):
    try:
        cursor = user_cursor.get(user_id, {'x': 960, 'y': 400})
        
        if page:
            run_async(page.screenshot(path=filename, full_page=True))
        else:
            run_async(browser.screenshot(filename))
        
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


# === КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def start(message):
    global chat_id_log
    chat_id_log = message.chat.id
    
    bot.reply_to(message,
        "👋 Команды:\n"
        "/browser — Запустить браузер\n"
        "/open url — Открыть сайт\n"
        "/loginx email password — Войти в X через Google\n"
        "/joy — Джойстик\n"
        "/screen — Скриншот\n"
        "/close — Закрыть браузер\n"
        "\n📋 Логи будут приходить сюда"
    )


@bot.message_handler(commands=['browser'])
def start_browser(message):
    global browser, chat_id_log
    
    if browser:
        bot.reply_to(message, "✅ Браузер уже запущен")
        return
    
    chat_id_log = message.chat.id
    msg = bot.reply_to(message, "🔄 Запуск браузера...")
    
    try:
        browser = Browser(headless=True, log_callback=log_callback)
        run_async(browser.start())
        bot.edit_message_text("✅ Браузер запущен!\n/open google.com", chat_id=message.chat.id, message_id=msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", chat_id=message.chat.id, message_id=msg.message_id)


@bot.message_handler(commands=['loginx'])
def login_x(message):
    global browser, chat_id_log
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ /loginx email password")
        return
    
    email, password = parts[1], parts[2]
    chat_id_log = message.chat.id
    
    bot.reply_to(message, "🔄 Вход в X через Google...\n📋 Следите за логами...")
    
    try:
        # Открываем X
        run_async(browser.goto("https://x.com"))
        
        # Вход через Google
        success = run_async(browser.login_google_via_popup(email, password))
        
        if success:
            bot.send_message(message.chat.id, "✅ Вход в X выполнен!\n/joy для управления")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка входа")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(commands=['open'])
def open_url(message):
    global browser, chat_id_log
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    chat_id_log = message.chat.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ /open google.com")
        return
    
    url = parts[1]
    bot.reply_to(message, f"🔄 Открываю {url}...\n📋 Следите за логами...")
    
    try:
        success = run_async(browser.goto(url))
        
        if success:
            bot.send_message(message.chat.id, f"✅ Открыто: {url}\n/joy для управления")
        else:
            bot.send_message(message.chat.id, f"⚠️ Ошибка открытия {url}")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(commands=['joy'])
def joystick(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    user_id = message.from_user.id
    user_cursor[user_id] = {'x': 960, 'y': 400}
    
    try:
        fn = screenshot_with_cursor(user_id, f"joy_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.send_photo(
                    message.chat.id, 
                    f, 
                    caption="🎮 Управление курсором",
                    reply_markup=get_joystick()
                )
            os.remove(fn)
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")


@bot.message_handler(commands=['screen'])
def screenshot(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    try:
        fn = f"screen_{message.from_user.id}.png"
        run_async(browser.screenshot(fn))
        
        with open(fn, "rb") as f:
            bot.send_photo(message.chat.id, f, caption="📸 Скриншот")
        
        os.remove(fn)
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")


@bot.message_handler(commands=['close'])
def close_browser(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Браузер не запущен")
        return
    
    try:
        run_async(browser.close())
        browser = None
        user_cursor.clear()
        bot.reply_to(message, "✅ Браузер закрыт")
    except Exception as e:
        bot.reply_to(message, f"❌ {str(e)[:100]}")


# === ОБРАБОТЧИК КНОПОК ДЖОЙСТИКА ===
@bot.callback_query_handler(func=lambda call: True)
def joystick_callback(call):
    global browser
    
    if not browser:
        bot.answer_callback_query(call.id, "❌ Нет браузера")
        return
    
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    try:
        if call.data == "up":
            x, y = move_cursor(user_id, 0, -30)
            bot.answer_callback_query(call.id, f"⬆️ ({x},{y})")
        
        elif call.data == "down":
            x, y = move_cursor(user_id, 0, 30)
            bot.answer_callback_query(call.id, f"⬇️ ({x},{y})")
        
        elif call.data == "left":
            x, y = move_cursor(user_id, -30, 0)
            bot.answer_callback_query(call.id, f"⬅️ ({x},{y})")
        
        elif call.data == "right":
            x, y = move_cursor(user_id, 30, 0)
            bot.answer_callback_query(call.id, f"➡️ ({x},{y})")
        
        elif call.data == "center":
            user_cursor[user_id] = {'x': 960, 'y': 400}
            bot.answer_callback_query(call.id, "🏠 Центр")
        
        elif call.data == "click":
            bot.answer_callback_query(call.id, "💣 Клик...")
            x, y = user_cursor.get(user_id, {'x': 960, 'y': 400}).values()
            
            result = run_async(browser.mega_click(x=int(x), y=int(y), text="Continue"))
            
            if result:
                bot.answer_callback_query(call.id, "✅ Клик успешен!")
                time.sleep(2)
                url = run_async(browser.get_url())
                bot.send_message(chat_id, f"📍 URL: {url}")
            else:
                bot.answer_callback_query(call.id, "❌ Не сработал")
        
        elif call.data == "screenshot":
            bot.answer_callback_query(call.id, "📸...")
            fn = f"ss_{user_id}.png"
            run_async(browser.screenshot(fn))
            with open(fn, "rb") as f:
                bot.send_photo(chat_id, f)
            os.remove(fn)
            return
        
        elif call.data == "position":
            c = user_cursor.get(user_id, {'x': 960, 'y': 400})
            bot.answer_callback_query(call.id, f"📍 ({c['x']},{c['y']})")
            return
        
        elif call.data == "refresh":
            bot.answer_callback_query(call.id, "🔄 Обновление...")
        
        elif call.data == "stop":
            try:
                run_async(browser.close())
                browser = None
                user_cursor.clear()
            except:
                pass
            bot.answer_callback_query(call.id, "⏹️ Закрыт")
            bot.edit_message_text("✅ Браузер закрыт", chat_id=chat_id, message_id=msg_id)
            return
        
        # Обновляем картинку
        fn = screenshot_with_cursor(user_id, f"upd_{user_id}.png")
        if fn:
            with open(fn, "rb") as f:
                bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=msg_id,
                    media=InputMediaPhoto(f),
                    reply_markup=get_joystick()
                )
            os.remove(fn)
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {str(e)[:30]}")


@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, "Используй /start")


if __name__ == '__main__':
    print("🤖 Бот запущен!")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.polling(non_stop=True, interval=1)