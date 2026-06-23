import asyncio
import os
import time
import threading
from datetime import datetime
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from PIL import Image, ImageDraw
import io

# Импорт вашего класса с Playwright
from browser_playwright import AntiDetectBrowser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = AsyncTeleBot(TOKEN)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
browser = None
browser_lock = asyncio.Lock()
user_cursor = {}
active_tasks = {}


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


async def make_screenshot_with_cursor(browser_instance, user_id, filename="screenshot.png"):
    """Делает скриншот с курсором"""
    try:
        cursor = user_cursor.get(user_id, {'x': 960, 'y': 400})
        
        # Сохраняем скриншот через Playwright
        await browser_instance.page.screenshot(path=filename, full_page=True)
        
        # Рисуем курсор
        img = Image.open(filename)
        draw = ImageDraw.Draw(img)
        x, y = cursor['x'], cursor['y']
        
        # Красный крестик
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
    """Перемещает курсор"""
    if user_id not in user_cursor:
        user_cursor[user_id] = {'x': 960, 'y': 400}
    
    viewport = browser.page.viewport_size if browser else None
    max_x = viewport['width'] if viewport else 1920
    max_y = viewport['height'] if viewport else 1080
    
    user_cursor[user_id]['x'] = max(0, min(max_x, user_cursor[user_id]['x'] + dx))
    user_cursor[user_id]['y'] = max(0, min(max_y, user_cursor[user_id]['y'] + dy))
    return user_cursor[user_id]['x'], user_cursor[user_id]['y']


# === /START ===
@bot.message_handler(commands=['start'])
async def send_welcome(message):
    await bot.reply_to(message,
        "👋 Команды:\n"
        "/logingoogle email пароль — Вход в Google\n"
        "/loginx — Войти в X.com (Google уже залогинен)\n"
        "/joystick — Управление\n"
        "/screenshot — Скриншот\n"
        "/close — Закрыть всё"
    )


# === /LOGINGOOGLE ===
@bot.message_handler(commands=['logingoogle'])
async def handle_login_google(message):
    global browser
    
    chat_id = message.chat.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await bot.reply_to(message, "❌ /logingoogle email пароль")
        return
    
    email, password = parts[1], parts[2]
    msg = await bot.reply_to(message, "🔄 Google...")
    
    async with browser_lock:
        if browser:
            try:
                await browser.close()
            except:
                pass
            browser = None
        
        try:
            browser = AntiDetectBrowser(headless=True)
            await browser.setup_driver()
            ok = await browser.login_google(email, password)
            
            if ok:
                await bot.edit_message_text("✅ Google OK. /loginx", chat_id=chat_id, message_id=msg.message_id)
            else:
                await bot.edit_message_text("❌ Google fail", chat_id=chat_id, message_id=msg.message_id)
                await browser.close()
                browser = None
                
        except Exception as e:
            await bot.edit_message_text(f"❌ {str(e)[:100]}", chat_id=chat_id, message_id=msg.message_id)
            browser = None


# === /LOGINX ===
@bot.message_handler(commands=['loginx'])
async def handle_login_x(message):
    global browser
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not browser or not browser.page:
        await bot.reply_to(message, "❌ Сначала /logingoogle")
        return
    
    msg = await bot.reply_to(message, "🔄 X.com...")
    
    try:
        async with browser_lock:
            # Переход на X
            await browser.page.goto("https://x.com", timeout=30000)
            await browser.wait_for_page_load(timeout=30)
            
            url = browser.page.url
            if "home" in url:
                await bot.reply_to(message, "✅ X уже залогинен!")
                return
            
            # Ищем кнопку через mega_click
            result = await browser.mega_click(text="Continue as")
            
            if result:
                time.sleep(3)
                url = browser.page.url
                if "home" in url:
                    await bot.reply_to(message, "✅ X OK! /joystick")
                    return
            
            # Если не сработало — скрин для джойстика
            screenshot = await make_screenshot_with_cursor(browser, user_id, "x_fail.png")
            if screenshot:
                with open(screenshot, "rb") as f:
                    await bot.send_photo(chat_id, f, caption="⚠️ Нужен джойстик")
                os.remove(screenshot)
            
            await bot.reply_to(message, "⚠️ /joystick для ручного клика")
            
    except Exception as e:
        await bot.reply_to(message, f"❌ {str(e)[:100]}")


# === /JOYSTICK ===
@bot.message_handler(commands=['joystick'])
async def handle_joystick(message):
    global browser
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not browser or not browser.page:
        await bot.reply_to(message, "❌ Нет сессии. /logingoogle")
        return
    
    async with browser_lock:
        user_cursor[user_id] = {'x': 960, 'y': 400}
        
        try:
            fn = await make_screenshot_with_cursor(browser, user_id, f"joy_{user_id}.png")
            if fn:
                with open(fn, "rb") as f:
                    await bot.send_photo(chat_id, f, reply_markup=get_joystick_keyboard())
                os.remove(fn)
        except Exception as e:
            await bot.reply_to(message, f"❌ {e}")


# === ОБРАБОТЧИК КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
async def handle_callback(call):
    global browser
    
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if not browser or not browser.page:
        await bot.answer_callback_query(call.id, "❌ Нет сессии")
        return
    
    async with browser_lock:
        try:
            if call.data == "move_up":
                x, y = move_cursor(user_id, 0, -30)
                await bot.answer_callback_query(call.id, f"({x},{y})")
                
            elif call.data == "move_down":
                x, y = move_cursor(user_id, 0, 30)
                await bot.answer_callback_query(call.id, f"({x},{y})")
                
            elif call.data == "move_left":
                x, y = move_cursor(user_id, -30, 0)
                await bot.answer_callback_query(call.id, f"({x},{y})")
                
            elif call.data == "move_right":
                x, y = move_cursor(user_id, 30, 0)
                await bot.answer_callback_query(call.id, f"({x},{y})")
                
            elif call.data == "move_center":
                viewport = browser.page.viewport_size
                user_cursor[user_id] = {
                    'x': viewport['width'] // 2 if viewport else 960,
                    'y': viewport['height'] // 2 if viewport else 400
                }
                await bot.answer_callback_query(call.id, "Центр")
                
            elif call.data == "mega_click":
                await bot.answer_callback_query(call.id, "💣 Клик...")
                x, y = user_cursor.get(user_id, {'x': 960, 'y': 400}).values()
                
                # Запускаем мега-клик
                result = await browser.mega_click(x=int(x), y=int(y), text="Continue")
                if result:
                    await bot.answer_callback_query(call.id, "✅ Клик успешен!")
                else:
                    await bot.answer_callback_query(call.id, "❌ Клик не сработал")
                    
            elif call.data == "take_screenshot":
                await bot.answer_callback_query(call.id, "📸 Скрин...")
                try:
                    fn = f"ss_{user_id}.png"
                    await browser.page.screenshot(path=fn, full_page=True)
                    if os.path.exists(fn):
                        with open(fn, "rb") as f:
                            await bot.send_photo(chat_id, f)
                        os.remove(fn)
                except Exception as e:
                    await bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}")
                return
                
            elif call.data == "refresh_screen":
                await bot.answer_callback_query(call.id, "🔄 Обновление...")
                
            elif call.data == "show_position":
                c = user_cursor.get(user_id, {'x': 960, 'y': 400})
                await bot.answer_callback_query(call.id, f"📍 ({c['x']},{c['y']})")
                return
                
            elif call.data == "stop_joystick":
                try:
                    await browser.close()
                    browser = None
                    if user_id in user_cursor:
                        del user_cursor[user_id]
                except:
                    pass
                await bot.answer_callback_query(call.id, "⏹️ Закрыт")
                await bot.edit_message_text("✅ Браузер закрыт", chat_id=chat_id, message_id=msg_id)
                return
            
            # Обновляем скриншот после движения
            fn = await make_screenshot_with_cursor(browser, user_id, f"upd_{user_id}.png")
            if fn:
                with open(fn, "rb") as f:
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=msg_id,
                        media=InputMediaPhoto(f),
                        reply_markup=get_joystick_keyboard()
                    )
                os.remove(fn)
                
        except Exception as e:
            await bot.answer_callback_query(call.id, f"❌ {str(e)[:30]}")


# === /SCREENSHOT ===
@bot.message_handler(commands=['screenshot'])
async def handle_screenshot(message):
    global browser
    
    user_id = message.from_user.id
    if not browser or not browser.page:
        await bot.reply_to(message, "❌ Нет сессии")
        return
    
    try:
        async with browser_lock:
            fn = f"ss_{user_id}.png"
            await browser.page.screenshot(path=fn, full_page=True)
            if os.path.exists(fn):
                with open(fn, "rb") as f:
                    await bot.send_photo(user_id, f)
                os.remove(fn)
    except Exception as e:
        await bot.reply_to(message, f"❌ {str(e)[:100]}")


# === /CLOSE ===
@bot.message_handler(commands=['close'])
async def handle_close(message):
    global browser
    
    user_id = message.from_user.id
    
    async with browser_lock:
        if browser:
            try:
                await browser.close()
            except:
                pass
            browser = None
        
        if user_id in user_cursor:
            del user_cursor[user_id]
    
    await bot.reply_to(message, "✅ Закрыто")


# === ЭХО ===
@bot.message_handler(func=lambda m: True)
async def echo(message):
    await bot.reply_to(message, "/start для списка команд")


# === ЗАПУСК ===
async def main():
    print("🤖 Бот запущен (асинхронный)...")
    try:
        await bot.polling(non_stop=True, interval=1)
    except KeyboardInterrupt:
        print("\n⏹️ Остановка...")
        if browser:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())