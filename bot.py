import os
import logging
import threading
import time
import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
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
joystick_messages = {}
cursor_positions = {}

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

# ============ БРАУЗЕР С ПОЛНОЙ МАСКИРОВКОЙ ============
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
            '--disable-features=BlockInsecurePrivateNetworkRequests',
            '--disable-features=OutOfBlinkCors',
            '--disable-background-networking',
            '--disable-sync',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-component-update',
            '--disable-domain-reliability',
            '--disable-client-side-phishing-detection',
            '--disable-crash-reporter',
            '--disable-breakpad',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        java_script_enabled=True,
        bypass_csp=True,
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    
    # Добавляем куки
    await context.add_cookies([
        {
            "name": "_ga",
            "value": "GA1.2.1234567890.1234567890",
            "domain": ".x.com",
            "path": "/"
        }
    ])
    
    await context.set_geolocation({"latitude": 55.7558, "longitude": 37.6173})
    await context.grant_permissions(["geolocation"])
    
    page = await context.new_page()
    
    # ============ ПОЛНАЯ МАСКИРОВКА ============
    await page.add_init_script("""
        // Маскируем webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Маскируем plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ];
                plugins.item = (i) => plugins[i];
                plugins.namedItem = (name) => plugins.find(p => p.name === name);
                return plugins;
            }
        });
        
        // Маскируем languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
        
        // Маскируем platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Маскируем hardwareConcurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        // Маскируем deviceMemory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        // Добавляем chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {
                isInstalled: false,
                InstallState: {
                    DISABLED: 'disabled',
                    INSTALLED: 'installed',
                    NOT_INSTALLED: 'not_installed'
                },
                RunningState: {
                    CANNOT_RUN: 'cannot_run',
                    READY_TO_RUN: 'ready_to_run',
                    RUNNING: 'running'
                }
            }
        };
        
        // Удаляем webdriver
        delete Object.getPrototypeOf(navigator).webdriver;
        
        // Маскируем WebGL
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter(parameter);
        };
        
        // Маскируем screen
        Object.defineProperty(screen, 'availWidth', {
            get: () => 1920
        });
        Object.defineProperty(screen, 'availHeight', {
            get: () => 1080
        });
        Object.defineProperty(screen, 'width', {
            get: () => 1920
        });
        Object.defineProperty(screen, 'height', {
            get: () => 1080
        });
        
        console.log('✅ Полная маскировка браузера включена');
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
        cursor_positions[user_id] = {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2}
        return user_sessions[user_id]
    return user_sessions[user_id]

async def close_user_browser(user_id: int):
    if user_id in user_sessions:
        await user_sessions[user_id]["browser"].close()
        del user_sessions[user_id]
        if user_id in joystick_messages:
            del joystick_messages[user_id]
        if user_id in joystick_states:
            del joystick_states[user_id]
        if user_id in cursor_positions:
            del cursor_positions[user_id]

async def goto_url(page, url: str):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print(f"✅ {url} загружен")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки {url}: {e}")
        raise e

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

# ============ УМНЫЙ КЛИК (РАБОТАЕТ С IFRAME) ============
async def smart_click(page, x: int, y: int):
    """Умный клик: ищет кнопки в iframe и на странице"""
    try:
        # 1. Ищем кнопку "Continue with Google" во всех iframe
        for frame in page.frames:
            try:
                selectors = [
                    'text="Continue with Google"',
                    'text="Continue with Google"',
                    '[aria-label*="Google"]',
                    'div:has-text("Continue with Google")',
                    'button:has-text("Google")',
                    'span:has-text("Google")'
                ]
                
                for selector in selectors:
                    try:
                        elements = await frame.locator(selector).all()
                        for el in elements:
                            if await el.is_visible():
                                await el.click()
                                print(f"✅ Клик по '{selector}' в iframe")
                                return True
                    except:
                        continue
            except:
                continue
        
        # 2. Ищем на самой странице
        selectors = [
            'text="Continue with Google"',
            'button:has-text("Google")',
            'div:has-text("Continue with Google")'
        ]
        
        for selector in selectors:
            try:
                elements = await page.locator(selector).all()
                for el in elements:
                    if await el.is_visible():
                        await el.click()
                        print(f"✅ Клик по '{selector}' на странице")
                        return True
            except:
                continue
        
        # 3. Если ничего не нашли - клик по координатам
        await page.mouse.click(x, y, button="left")
        print(f"✅ Клик по координатам ({x}, {y})")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка клика: {e}")
        try:
            await page.mouse.click(x, y, button="left")
            return True
        except:
            return False

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

async def update_joystick_message(query, page, user_id, mode, caption=""):
    cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
    current_x = cursor["x"]
    current_y = cursor["y"]
    
    if mode == "fast":
        step = JOYSTICK_FAST_STEP
        mode_label = "⚡ БЫСТРЫЙ"
    elif mode == "slow":
        step = JOYSTICK_SLOW_STEP
        mode_label = "🐢 МЕДЛЕННЫЙ"
    else:
        step = JOYSTICK_STEP
        mode_label = "🔄 НОРМАЛЬНЫЙ"
    
    screenshot = await screenshot_with_cursor(page, current_x, current_y)
    
    text = (
        f"🎮 ДЖОЙСТИК 🎮\n\n"
        f"📍 Координаты: ({current_x}, {current_y})\n"
        f"📏 Шаг: {step}px\n"
        f"🔄 Режим: {mode_label}\n"
    )
    if caption:
        text += f"\n{caption}"
    
    try:
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=screenshot,
                caption=text
            ),
            reply_markup=get_joystick_keyboard(mode)
        )
    except Exception as e:
        print(f"Ошибка редактирования: {e}")

# ============ КОМАНДЫ БОТА ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я бот с управлением браузером!\n\n"
        "🌐 /browser - Открыть браузер\n"
        "🎮 /joystick - Открыть джойстик\n"
        "🔗 /go <url> - Перейти на сайт\n"
        "📸 /screenshot - Сделать скриншот\n"
        "❌ /close - Закрыть браузер\n"
        "🔐 /twitter - Войти в Twitter/X"
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
        
        await goto_url(page, url)
        session["current_url"] = url
        
        cursor_positions[user_id] = {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2}
        
        await page.wait_for_timeout(2000)
        
        screenshot = await screenshot_with_cursor(page, VIEWPORT["width"] // 2, VIEWPORT["height"] // 2)
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
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        
        screenshot = await screenshot_with_cursor(page, cursor["x"], cursor["y"])
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Скриншот ({cursor['x']}, {cursor['y']})"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    await update.message.reply_text("❌ Браузер закрыт")

# ============ ВХОД В TWITTER/X ============
async def twitter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        await update.message.reply_text("🔐 Открываю страницу входа в Twitter/X...")
        
        await goto_url(page, "https://x.com/login")
        await page.wait_for_timeout(3000)
        
        await update.message.reply_text("🔍 Ищу кнопку 'Continue with Google'...")
        
        found = False
        
        # Ищем в iframe
        for frame in page.frames:
            try:
                elements = await frame.locator('text="Continue with Google"').all()
                for el in elements:
                    if await el.is_visible():
                        await el.click()
                        found = True
                        await update.message.reply_text("✅ Нажата кнопка в iframe")
                        break
                if found:
                    break
            except:
                continue
        
        if not found:
            # Ищем на странице
            try:
                elements = await page.locator('text="Continue with Google"').all()
                for el in elements:
                    if await el.is_visible():
                        await el.click()
                        found = True
                        await update.message.reply_text("✅ Нажата кнопка на странице")
                        break
            except:
                pass
        
        if found:
            await page.wait_for_timeout(3000)
            
            cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
            screenshot = await screenshot_with_cursor(page, cursor["x"], cursor["y"])
            
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ Открылось окно входа в Google"
            )
        else:
            await update.message.reply_text("❌ Кнопка 'Continue with Google' не найдена")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ ДЖОЙСТИК КОМАНДА ============
async def joystick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    if user_id in joystick_messages:
        await update.message.reply_text("🎮 Джойстик уже открыт!")
        return
    
    joystick_states[user_id] = {"mode": "normal"}
    
    session = user_sessions[user_id]
    page = session["page"]
    
    cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
    current_x = cursor["x"]
    current_y = cursor["y"]
    
    screenshot = await screenshot_with_cursor(page, current_x, current_y)
    
    msg = await update.message.reply_photo(
        photo=screenshot,
        caption=(
            f"🎮 ДЖОЙСТИК 🎮\n\n"
            f"📍 Координаты: ({current_x}, {current_y})\n"
            f"📏 Шаг: {JOYSTICK_STEP}px\n"
            f"🔄 Режим: НОРМАЛЬНЫЙ\n\n"
            f"Используй кнопки для управления:"
        ),
        reply_markup=get_joystick_keyboard("normal")
    )
    
    joystick_messages[user_id] = msg.message_id

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
        if user_id in joystick_messages:
            del joystick_messages[user_id]
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    mode = joystick_states.get(user_id, {}).get("mode", "normal")
    
    cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
    current_x = cursor["x"]
    current_y = cursor["y"]
    
    # ============ ДВИЖЕНИЕ ============
    if data.startswith("move_"):
        parts = data.split("_")
        dx = int(parts[1])
        dy = int(parts[2])
        
        try:
            new_x = current_x + dx
            new_y = current_y + dy
            
            new_x = max(0, min(VIEWPORT["width"], new_x))
            new_y = max(0, min(VIEWPORT["height"], new_y))
            
            cursor_positions[user_id] = {"x": new_x, "y": new_y}
            
            await page.mouse.move(new_x, new_y, steps=5)
            await page.wait_for_timeout(100)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ Движение: ({dx}, {dy}) → ({new_x}, {new_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка движения: {e}")
    
    # ============ ЛКМ ============
    elif data == "click_left":
        try:
            await smart_click(page, current_x, current_y)
            await page.wait_for_timeout(500)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ ЛКМ ({current_x}, {current_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка ЛКМ: {e}")
    
    # ============ ПКМ ============
    elif data == "click_right":
        try:
            await page.mouse.click(current_x, current_y, button="right")
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ ПКМ ({current_x}, {current_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка ПКМ: {e}")
    
    # ============ КЛИК ПО КУРСОРУ ============
    elif data == "click_center":
        try:
            await page.mouse.click(current_x, current_y, button="left")
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ Клик по курсору ({current_x}, {current_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка клика: {e}")
    
    # ============ ENTER ============
    elif data == "press_enter":
        try:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "⌨️ Нажат Enter"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка Enter: {e}")
    
    # ============ ОБНОВИТЬ ============
    elif data == "refresh":
        try:
            await page.reload()
            await page.wait_for_timeout(500)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "🔄 Страница обновлена"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка обновления: {e}")
    
    # ============ НАЗАД ============
    elif data == "go_back":
        try:
            await page.go_back()
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "⬅️ Назад"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка назад: {e}")
    
    # ============ ВПЕРЁД ============
    elif data == "go_forward":
        try:
            await page.go_forward()
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "➡️ Вперёд"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка вперёд: {e}")
    
    # ============ СКРИНШОТ ============
    elif data == "screenshot":
        try:
            await update_joystick_message(
                query, page, user_id, mode,
                "📸 Скриншот обновлён"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка скриншота: {e}")
    
    # ============ ЗАКРЫТЬ БРАУЗЕР ============
    elif data == "close_browser":
        await close_user_browser(user_id)
        await query.edit_message_text("❌ Браузер закрыт", reply_markup=None)
        if user_id in joystick_messages:
            del joystick_messages[user_id]
    
    # ============ ПЕРЕКЛЮЧЕНИЕ РЕЖИМА ============
    elif data == "toggle_mode":
        current_mode = joystick_states.get(user_id, {}).get("mode", "normal")
        
        if current_mode == "normal":
            new_mode = "fast"
            mode_label = "⚡ БЫСТРЫЙ"
        elif current_mode == "fast":
            new_mode = "slow"
            mode_label = "🐢 МЕДЛЕННЫЙ"
        else:
            new_mode = "normal"
            mode_label = "🔄 НОРМАЛЬНЫЙ"
        
        joystick_states[user_id]["mode"] = new_mode
        
        await update_joystick_message(
            query, page, user_id, new_mode,
            f"🔄 Режим: {mode_label}"
        )
    
    # ============ СМЕНИТЬ САЙТ ============
    elif data == "change_url":
        await query.edit_message_text(
            f"🔗 Введи новый URL командой:\n/go <url>\n\n"
            f"Пример: /go google.com\n\n"
            f"После ввода вернись в джойстик: /joystick",
            reply_markup=None
        )
        if user_id in joystick_messages:
            del joystick_messages[user_id]
    
    # ============ СКРЫТЬ ДЖОЙСТИК ============
    elif data == "hide_joystick":
        if user_id in joystick_messages:
            del joystick_messages[user_id]
        if user_id in joystick_states:
            del joystick_states[user_id]
        
        await query.edit_message_text(
            "✅ Джойстик закрыт\n\n"
            "🎮 Открыть заново: /joystick\n"
            "🌐 Браузер всё ещё работает",
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
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("browser", browser_command))
    bot_app.add_handler(CommandHandler("go", go_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("close", close_command))
    bot_app.add_handler(CommandHandler("joystick", joystick_command))
    bot_app.add_handler(CommandHandler("twitter", twitter_command))
    
    bot_app.add_handler(CallbackQueryHandler(joystick_callback))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()