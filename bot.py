import os
import logging
import threading
import time
import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from playwright.async_api import async_playwright

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Настройки джойстика
JOYSTICK_STEP = 50
JOYSTICK_SLOW_STEP = 20
JOYSTICK_FAST_STEP = 150

# Хранилища
user_sessions = {}
joystick_states = {}

# ============ FLASK ============
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ БРАУЗЕР ============
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

async def get_browser_page():
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-accelerated-2d-canvas',
            '--disable-pdf-viewer',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--mute-audio',
            '--no-first-run',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
    )
    
    await context.set_geolocation({"latitude": 55.7558, "longitude": 37.6173})
    await context.grant_permissions(["geolocation"])
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
        window.chrome = {
            runtime: {}
        };
    """)
    
    return page, browser, context

async def get_user_browser(user_id: int):
    if user_id not in user_sessions:
        page, browser, context = await get_browser_page()
        user_sessions[user_id] = {
            "page": page,
            "browser": browser,
            "context": context,
            "current_url": "about:blank"
        }
        await page.goto("about:blank")
        return user_sessions[user_id]
    return user_sessions[user_id]

async def close_user_browser(user_id: int):
    if user_id in user_sessions:
        await user_sessions[user_id]["browser"].close()
        del user_sessions[user_id]

async def screenshot_with_cursor(page, x: int, y: int) -> bytes:
    try:
        await page.evaluate(f"""
            const cursor = document.createElement('div');
            cursor.id = 'telegram-cursor';
            cursor.style.cssText = `
                position: fixed;
                left: {x}px;
                top: {y}px;
                width: 24px;
                height: 24px;
                pointer-events: none;
                z-index: 99999;
                transform: translate(-50%, -50%);
            `;
            cursor.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M5.5 3.5L19.5 12L5.5 20.5V3.5Z" fill="red" stroke="white" stroke-width="2"/>
                </svg>
            `;
            document.body.appendChild(cursor);
            setTimeout(() => cursor.remove(), 300);
        """)
        
        await page.wait_for_timeout(100)
        screenshot = await page.screenshot(full_page=True, type="png")
        return screenshot
        
    except Exception as e:
        print(f"Ошибка курсора: {e}")
        return await page.screenshot(full_page=True, type="png")

# ============ ДЖОЙСТИК ============
def get_joystick_keyboard(mode="normal"):
    if mode == "fast":
        step = JOYSTICK_FAST_STEP
        label = "⚡ БЫСТРЫЙ"
    elif mode == "slow":
        step = JOYSTICK_SLOW_STEP
        label = "🐢 МЕДЛЕННЫЙ"
    else:
        step = JOYSTICK_STEP
        label = "🔄 НОРМАЛЬНЫЙ"
    
    keyboard = [
        [
            InlineKeyboardButton("↖️", callback_data=f"move_-{step}_-{step}"),
            InlineKeyboardButton("⬆️", callback_data=f"move_0_-{step}"),
            InlineKeyboardButton("↗️", callback_data=f"move_{step}_-{step}"),
        ],
        [
            InlineKeyboardButton("⬅️", callback_data=f"move_-{step}_0"),
            InlineKeyboardButton("🎯", callback_data="click_center"),
            InlineKeyboardButton("➡️", callback_data=f"move_{step}_0"),
        ],
        [
            InlineKeyboardButton("↙️", callback_data=f"move_-{step}_{step}"),
            InlineKeyboardButton("⬇️", callback_data=f"move_0_{step}"),
            InlineKeyboardButton("↘️", callback_data=f"move_{step}_{step}"),
        ],
        [
            InlineKeyboardButton("🔄", callback_data="refresh"),
            InlineKeyboardButton("⬅️ Назад", callback_data="go_back"),
            InlineKeyboardButton("➡️ Вперёд", callback_data="go_forward"),
        ],
        [
            InlineKeyboardButton("🖱️ ЛКМ", callback_data="click_left"),
            InlineKeyboardButton("🖱️ ПКМ", callback_data="click_right"),
            InlineKeyboardButton("⌨️ Enter", callback_data="press_enter"),
        ],
        [
            InlineKeyboardButton("📸 Скрин", callback_data="screenshot"),
            InlineKeyboardButton("🗑️ Закрыть", callback_data="close_browser"),
        ],
        [
            InlineKeyboardButton(label, callback_data="toggle_mode"),
            InlineKeyboardButton("🔀 Сменить сайт", callback_data="change_url"),
        ],
        [
            InlineKeyboardButton("❌ Закрыть джойстик", callback_data="hide_joystick"),
        ],
    ]
    
    return InlineKeyboardMarkup(keyboard)

# ============ КОМАНДЫ БОТА ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я бот с управлением браузером!\n\n"
        "🌐 /browser - Открыть браузер\n"
        "🎮 /joystick - Открыть джойстик\n"
        "🔗 /go <url> - Перейти на сайт\n"
        "📸 /screenshot - Сделать скриншот\n"
        "❌ /close - Закрыть браузер"
    )

async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    await update.message.reply_text("🌐 Открываю браузер...")
    
    try:
        await get_user_browser(user_id)
        await update.message.reply_text(
            "✅ Браузер готов!\n\n"
            "🎮 Открой джойстик: /joystick\n"
            "🔗 Перейти на сайт: /go google.com"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Укажите URL: /go google.com")
        return
    
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    
    try:
        session = await get_user_browser(user_id)
        page = session["page"]
        
        await update.message.reply_text(f"🌐 Перехожу на {url}...")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        session["current_url"] = url
        
        screenshot = await screenshot_with_cursor(page, 100, 100)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"✅ {url}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    try:
        session = user_sessions[user_id]
        page = session["page"]
        
        screenshot = await page.screenshot(full_page=True, type="png")
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    await update.message.reply_text("❌ Браузер закрыт")

# ============ ДЖОЙСТИК КОМАНДА ============
async def joystick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    joystick_states[user_id] = {"mode": "normal"}
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        coords = await page.evaluate("""
            ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        current_x = int(coords["x"])
        current_y = int(coords["y"])
    except:
        current_x = 0
        current_y = 0
    
    await update.message.reply_text(
        f"🎮 ДЖОЙСТИК 🎮\n\n"
        f"📍 Координаты: ({current_x}, {current_y})\n"
        f"📏 Шаг: {JOYSTICK_STEP}px\n"
        f"🔄 Режим: НОРМАЛЬНЫЙ\n\n"
        f"Используй кнопки для управления:",
        reply_markup=get_joystick_keyboard("normal")
    )

# ============ ОБРАБОТЧИК КНОПОК ДЖОЙСТИКА ============
async def joystick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if user_id not in user_sessions:
        await query.edit_message_text(
            "⚠️ Браузер закрыт. Открой: /browser",
            reply_markup=None
        )
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    mode = joystick_states.get(user_id, {}).get("mode", "normal")
    
    # Получаем текущие координаты курсора
    try:
        coords = await page.evaluate("""
            ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        current_x = int(coords["x"])
        current_y = int(coords["y"])
    except:
        current_x = 0
        current_y = 0
    
    # ДВИЖЕНИЕ
    if data.startswith("move_"):
        parts = data.split("_")
        dx = int(parts[1])
        dy = int(parts[2])
        
        try:
            new_x = current_x + dx
            new_y = current_y + dy
            
            await page.mouse.move(new_x, new_y, steps=5)
            await page.wait_for_timeout(100)
            
            screenshot = await screenshot_with_cursor(page, new_x, new_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"📍 Координаты: ({new_x}, {new_y})\n"
                    f"📏 Шаг: {abs(dx)}px\n"
                    f"🔄 Режим: {mode.upper()}",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(
                photo=screenshot,
                caption=f"🖱️ ({new_x}, {new_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # КЛИК ПО ЦЕНТРУ
    elif data == "click_center":
        try:
            viewport = page.viewport_size
            x = viewport['width'] // 2
            y = viewport['height'] // 2
            
            await page.mouse.move(x, y, steps=3)
            await page.wait_for_timeout(100)
            await page.mouse.click(x, y)
            await page.wait_for_timeout(200)
            
            screenshot = await screenshot_with_cursor(page, x, y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"🖱️ Клик по центру ({x}, {y})",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption=f"✅ Клик ({x}, {y})")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ЛКМ
    elif data == "click_left":
        try:
            await page.mouse.click(current_x, current_y, button="left")
            await page.wait_for_timeout(200)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"🖱️ ЛКМ в ({current_x}, {current_y})",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption=f"✅ ЛКМ ({current_x}, {current_y})")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ПКМ
    elif data == "click_right":
        try:
            await page.mouse.click(current_x, current_y, button="right")
            await page.wait_for_timeout(200)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"🖱️ ПКМ в ({current_x}, {current_y})",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption=f"✅ ПКМ ({current_x}, {current_y})")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ENTER
    elif data == "press_enter":
        try:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"⌨️ Нажат Enter",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption="⌨️ Enter")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ОБНОВИТЬ
    elif data == "refresh":
        try:
            await page.reload()
            await page.wait_for_timeout(500)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"🔄 Страница обновлена",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption="🔄 Обновлено")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # НАЗАД
    elif data == "go_back":
        try:
            await page.go_back()
            await page.wait_for_timeout(300)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"⬅️ Назад",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption="⬅️ Назад")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ВПЕРЁД
    elif data == "go_forward":
        try:
            await page.go_forward()
            await page.wait_for_timeout(300)
            
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"➡️ Вперёд",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption="➡️ Вперёд")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # СКРИНШОТ
    elif data == "screenshot":
        try:
            screenshot = await screenshot_with_cursor(page, current_x, current_y)
            
            try:
                await query.edit_message_text(
                    f"🎮 ДЖОЙСТИК 🎮\n\n"
                    f"📸 Скриншот сделан\n"
                    f"📍 ({current_x}, {current_y})",
                    reply_markup=get_joystick_keyboard(mode)
                )
            except:
                pass
            
            await query.message.reply_photo(photo=screenshot, caption=f"📸 ({current_x}, {current_y})")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_joystick_keyboard(mode))
    
    # ЗАКРЫТЬ БРАУЗЕР
    elif data == "close_browser":
        await close_user_browser(user_id)
        await query.edit_message_text("❌ Браузер закрыт", reply_markup=None)
    
    # ПЕРЕКЛЮЧЕНИЕ РЕЖИМА
    elif data == "toggle_mode":
        current_mode = joystick_states.get(user_id, {}).get("mode", "normal")
        
        if current_mode == "normal":
            new_mode = "fast"
            mode_label = "⚡ БЫСТРЫЙ"
            step = JOYSTICK_FAST_STEP
        elif current_mode == "fast":
            new_mode = "slow"
            mode_label = "🐢 МЕДЛЕННЫЙ"
            step = JOYSTICK_SLOW_STEP
        else:
            new_mode = "normal"
            mode_label = "🔄 НОРМАЛЬНЫЙ"
            step = JOYSTICK_STEP
        
        joystick_states[user_id]["mode"] = new_mode
        
        try:
            await query.edit_message_text(
                f"🎮 ДЖОЙСТИК 🎮\n\n"
                f"📏 Шаг: {step}px\n"
                f"🔄 Режим: {mode_label}\n"
                f"📍 ({current_x}, {current_y})",
                reply_markup=get_joystick_keyboard(new_mode)
            )
        except:
            pass
        
        screenshot = await screenshot_with_cursor(page, current_x, current_y)
        await query.message.reply_photo(photo=screenshot, caption=f"🔄 {mode_label}")
    
    # СМЕНИТЬ САЙТ
    elif data == "change_url":
        await query.edit_message_text(
            f"🔗 Введи новый URL командой:\n/go <url>\n\n"
            f"Пример: /go google.com\n\n"
            f"После ввода вернись в джойстик: /joystick",
            reply_markup=None
        )
    
    # СКРЫТЬ ДЖОЙСТИК
    elif data == "hide_joystick":
        await query.edit_message_text(
            "✅ Джойстик скрыт\n\nВернуть: /joystick",
            reply_markup=None
        )

# ============ ЗАПУСК ============
def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("browser", browser_command))
    bot_app.add_handler(CommandHandler("go", go_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("close", close_command))
    bot_app.add_handler(CommandHandler("joystick", joystick_command))
    
    # Обработчик кнопок
    bot_app.add_handler(CallbackQueryHandler(joystick_callback))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()