import os
import logging
import threading
import time
import asyncio
import random
import re
import json
from io import BytesIO
import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from playwright.async_api import async_playwright
from PIL import Image

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
    
    await context.add_cookies([
        {"name": "_ga", "value": "GA1.2.1234567890.1234567890", "domain": ".x.com", "path": "/"}
    ])
    
    await context.set_geolocation({"latitude": 55.7558, "longitude": 37.6173})
    await context.grant_permissions(["geolocation"])
    
    page = await context.new_page()
    
    # Полная маскировка
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
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
        
        Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
            }
        };
        
        delete Object.getPrototypeOf(navigator).webdriver;
        
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter(parameter);
        };
        
        Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
        Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
        Object.defineProperty(screen, 'width', { get: () => 1920 });
        Object.defineProperty(screen, 'height', { get: () => 1080 });
        
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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"✅ {url} загружен")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки {url}: {e}")
        raise e

# ============ ACTIONCHAINS ============

async def human_move(page, x: int, y: int, steps: int = 10):
    """Реалистичное движение мыши"""
    try:
        current = await page.evaluate("""
            ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        
        for i in range(steps):
            progress = (i + 1) / steps
            ease = 1 - (1 - progress) ** 3
            target_x = current["x"] + (x - current["x"]) * ease + random.randint(-2, 2)
            target_y = current["y"] + (y - current["y"]) * ease + random.randint(-2, 2)
            await page.mouse.move(target_x, target_y)
            await page.wait_for_timeout(random.randint(20, 60))
        
        await page.mouse.move(x, y)
        await page.wait_for_timeout(random.randint(50, 150))
        return True
    except Exception as e:
        print(f"❌ Ошибка движения: {e}")
        return False

async def human_click(page, x: int, y: int, button: str = "left"):
    """Реалистичный клик"""
    try:
        await human_move(page, x, y, steps=8)
        await page.wait_for_timeout(random.randint(100, 300))
        await page.mouse.down(button=button)
        await page.wait_for_timeout(random.randint(50, 150))
        await page.mouse.up(button=button)
        return True
    except Exception as e:
        print(f"❌ Ошибка клика: {e}")
        return False

async def human_type(page, text: str, delay: int = 50):
    """Реалистичный ввод текста"""
    try:
        for i, char in enumerate(text):
            wait_time = delay + random.randint(-20, 30)
            if char.isupper() or char in '!@#$%^&*()_+':
                wait_time += random.randint(20, 50)
            await page.keyboard.type(char, delay=wait_time)
            
            if random.random() < 0.02 and len(text) > 5:
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(random.randint(50, 150))
                await page.keyboard.type(char, delay=wait_time)
        
        await page.wait_for_timeout(random.randint(200, 500))
        return True
    except Exception as e:
        print(f"❌ Ошибка ввода: {e}")
        return False

# ============ СКРИНШОТ С ОГРАНИЧЕНИЕМ РАЗМЕРА ============
async def human_screenshot(page, x: int, y: int) -> bytes:
    """Скриншот с курсором и автоматическим сжатием"""
    try:
        # Добавляем курсор
        await page.evaluate(f"""
            const cursor = document.createElement('div');
            cursor.id = 'telegram-cursor';
            cursor.style.cssText = `
                position: fixed;
                left: {x}px;
                top: {y}px;
                width: 28px;
                height: 28px;
                pointer-events: none;
                z-index: 99999;
                transform: translate(-50%, -50%);
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
            `;
            cursor.innerHTML = `
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <path d="M6 4L22 14L6 24V4Z" fill="#FF0000" stroke="white" stroke-width="2"/>
                    <circle cx="6" cy="14" r="2" fill="white"/>
                </svg>
            `;
            document.body.appendChild(cursor);
            setTimeout(() => {{
                cursor.style.transform = 'translate(-50%, -50%) scale(1.1)';
            }}, 100);
            setTimeout(() => {{
                cursor.style.transform = 'translate(-50%, -50%) scale(1)';
            }}, 200);
            setTimeout(() => cursor.remove(), 500);
        """)
        
        await page.wait_for_timeout(200)
        
        # Делаем скриншот (не full_page, чтобы избежать слишком больших размеров)
        screenshot_bytes = await page.screenshot(full_page=False, type="png")
        
        # Проверяем размер
        if len(screenshot_bytes) > 8 * 1024 * 1024:  # Если больше 8MB
            # Сжимаем
            img = Image.open(BytesIO(screenshot_bytes))
            
            # Уменьшаем размер если слишком большой
            if img.width > 2000 or img.height > 2000:
                img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            
            # Сохраняем с сжатием
            output = BytesIO()
            img.save(output, format='PNG', optimize=True, compress_level=9)
            screenshot_bytes = output.getvalue()
            
            # Если всё ещё слишком большой - конвертируем в JPEG
            if len(screenshot_bytes) > 8 * 1024 * 1024:
                output = BytesIO()
                # Конвертируем в RGB если нужно
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(output, format='JPEG', quality=70, optimize=True)
                screenshot_bytes = output.getvalue()
        
        return screenshot_bytes
        
    except Exception as e:
        print(f"Ошибка скриншота: {e}")
        try:
            screenshot = await page.screenshot(full_page=False, type="png")
            return screenshot
        except:
            return b""

# ============ УМНЫЙ КЛИК ============
async def smart_click(page, x: int, y: int):
    try:
        for frame in page.frames:
            try:
                selectors = [
                    'text="Continue with Google"',
                    '[aria-label*="Google"]',
                    'div:has-text("Continue with Google")',
                    'button:has-text("Google")'
                ]
                for selector in selectors:
                    try:
                        elements = await frame.locator(selector).all()
                        for el in elements:
                            if await el.is_visible():
                                box = await el.bounding_box()
                                if box:
                                    cx = box['x'] + box['width'] // 2
                                    cy = box['y'] + box['height'] // 2
                                    await human_click(page, cx, cy)
                                else:
                                    await el.click()
                                return True
                    except:
                        continue
            except:
                continue
        
        selectors = ['text="Continue with Google"', 'button:has-text("Google")']
        for selector in selectors:
            try:
                elements = await page.locator(selector).all()
                for el in elements:
                    if await el.is_visible():
                        box = await el.bounding_box()
                        if box:
                            cx = box['x'] + box['width'] // 2
                            cy = box['y'] + box['height'] // 2
                            await human_click(page, cx, cy)
                        else:
                            await el.click()
                        return True
            except:
                continue
        
        await human_click(page, x, y)
        return True
        
    except Exception as e:
        print(f"❌ Ошибка клика: {e}")
        try:
            await human_click(page, x, y)
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
    
    screenshot = await human_screenshot(page, current_x, current_y)
    
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
            media=InputMediaPhoto(media=screenshot, caption=text),
            reply_markup=get_joystick_keyboard(mode)
        )
    except Exception as e:
        print(f"Ошибка редактирования: {e}")

# ============ АВТОВХОД В GOOGLE ============
async def login_google(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = context.args
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/login email@gmail.com пароль\n\n"
            "Пример:\n"
            "/login myemail@gmail.com mypassword123"
        )
        return
    
    email = args[0]
    password = ' '.join(args[1:])
    
    session = user_sessions[user_id]
    page = session["page"]
    
    await update.message.reply_text("🔐 Начинаю вход в Google...")
    
    try:
        await update.message.reply_text("🌐 Открываю accounts.google.com...")
        await goto_url(page, "https://accounts.google.com")
        await page.wait_for_timeout(8000)
        
        await update.message.reply_text("🔍 Ищу поле для email...")
        
        email_found = False
        
        try:
            el = await page.get_by_role("textbox", name=re.compile(r"(Email|телефон|Username|Эл. почта)", re.IGNORECASE)).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(300)
                await el.fill(email)
                email_found = True
                print("✅ Email через get_by_role")
        except:
            pass
        
        if not email_found:
            try:
                el = await page.get_by_placeholder(re.compile(r"(Email|телефон|Username|Эл. почта|Адрес)", re.IGNORECASE)).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(300)
                    await el.fill(email)
                    email_found = True
                    print("✅ Email через get_by_placeholder")
            except:
                pass
        
        if not email_found:
            css_selectors = [
                'input[type="email"]',
                'input[name="identifier"]',
                'input[autocomplete="username"]',
                'input[autocomplete="email"]',
                'input[aria-label*="Email" i]',
                'input[aria-label*="телефон" i]',
                'input[jsname="YPqjbf"]',
                'input.whsOnd',
                'input.zHQkBf',
            ]
            
            for selector in css_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2000)
                    el = await page.locator(selector).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.click()
                        await page.wait_for_timeout(300)
                        await el.fill(email)
                        email_found = True
                        print(f"✅ Email через CSS: {selector}")
                        break
                except:
                    continue
        
        if not email_found:
            try:
                inputs = await page.locator('input').all()
                for inp in inputs:
                    if await inp.is_visible():
                        inp_type = await inp.get_attribute('type') or ''
                        inp_name = await inp.get_attribute('name') or ''
                        inp_id = await inp.get_attribute('id') or ''
                        inp_class = await inp.get_attribute('class') or ''
                        
                        email_keywords = ['email', 'mail', 'user', 'login', 'identifier', 'username']
                        is_email = False
                        for kw in email_keywords:
                            if kw in inp_name.lower() or kw in inp_id.lower() or kw in inp_class.lower():
                                is_email = True
                                break
                        
                        if is_email or inp_type == 'email' or inp_type == 'text':
                            box = await inp.bounding_box()
                            if box:
                                x = box['x'] + box['width'] // 2
                                y = box['y'] + box['height'] // 2
                                await human_click(page, x, y)
                                await page.wait_for_timeout(300)
                                await inp.fill(email)
                                email_found = True
                                print("✅ Email через первый подходящий input")
                                break
            except:
                pass
        
        if not email_found:
            screenshot = await page.screenshot(full_page=True, type="png")
            await update.message.reply_photo(
                photo=screenshot,
                caption="❌ **Не найдено поле для email**\n\nПопробуй ввести вручную через джойстик"
            )
            return
        
        await page.wait_for_timeout(1000)
        
        await update.message.reply_text("⏭️ Нажимаю 'Далее'...")
        
        next_clicked = False
        next_selectors = [
            'button:has-text("Далее")',
            'button:has-text("Next")',
            'button:has-text("Продолжить")',
            '#identifierNext',
            '[jsname="V67aGc"]',
            'button[jsname="LgbsSe"]',
            '//span[text()="Далее"]/parent::button',
            '//span[text()="Next"]/parent::button',
            '//span[text()="Продолжить"]/parent::button',
        ]
        
        for selector in next_selectors:
            try:
                if selector.startswith('//'):
                    el = await page.locator(f'xpath={selector}').first
                else:
                    el = await page.locator(selector).first
                    
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    next_clicked = True
                    print(f"✅ Нажато 'Далее': {selector}")
                    break
            except:
                continue
        
        if not next_clicked:
            await page.keyboard.press("Enter")
        
        await update.message.reply_text("⏳ Жду появления поля для пароля...")
        await page.wait_for_timeout(5000)
        
        await update.message.reply_text("🔑 Ищу поле для пароля...")
        
        password_found = False
        password_element = None
        
        try:
            el = await page.get_by_placeholder(re.compile(r"(Password|пароль|Пароль)", re.IGNORECASE)).first
            if await el.count() > 0 and await el.is_visible():
                password_element = el
                password_found = True
                print("✅ Пароль через get_by_placeholder")
        except:
            pass
        
        if not password_found:
            css_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[autocomplete="current-password"]',
                'input[aria-label*="Password" i]',
                'input[aria-label*="пароль" i]',
                'input[jsname="YPqjbf"]',
            ]
            
            for selector in css_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2000)
                    el = await page.locator(selector).first
                    if await el.count() > 0 and await el.is_visible():
                        password_element = el
                        password_found = True
                        print(f"✅ Пароль через CSS: {selector}")
                        break
                except:
                    continue
        
        if not password_found:
            try:
                inputs = await page.locator('input[type="password"]').all()
                for inp in inputs:
                    if await inp.is_visible():
                        password_element = inp
                        password_found = True
                        print("✅ Пароль через input[type=password]")
                        break
            except:
                pass
        
        if not password_found:
            current_url = page.url
            if "myaccount.google.com" in current_url or "mail.google.com" in current_url:
                screenshot = await human_screenshot(page, 100, 100)
                await update.message.reply_photo(
                    photo=screenshot,
                    caption="✅ **Вход уже выполнен!** 🎉"
                )
                return
            
            screenshot = await page.screenshot(full_page=True, type="png")
            await update.message.reply_photo(
                photo=screenshot,
                caption="❌ **Не найдено поле для пароля**\n\nВведи вручную через джойстик"
            )
            return
        
        await password_element.click()
        await page.wait_for_timeout(500)
        await human_type(page, password)
        print("✅ Пароль введён")
        
        await page.wait_for_timeout(1000)
        
        await update.message.reply_text("⏭️ Завершаю вход...")
        
        next_clicked = False
        for selector in next_selectors:
            try:
                if selector.startswith('//'):
                    el = await page.locator(f'xpath={selector}').first
                else:
                    el = await page.locator(selector).first
                    
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    next_clicked = True
                    break
            except:
                continue
        
        if not next_clicked:
            await page.keyboard.press("Enter")
        
        await page.wait_for_timeout(5000)
        
        current_url = page.url
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        if "myaccount.google.com" in current_url or "mail.google.com" in current_url:
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ **Вход в Google выполнен успешно!** 🎉\n\n"
                        "Теперь:\n"
                        "🔗 /twitter - открыть X.com\n"
                        "🔘 /google_btn - нажать 'Continue with Google'\n"
                        "🔘 /continue - нажать 'Continue as Babe'"
            )
        else:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Текущая страница\n\nПроверь статус: /status"
            )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        try:
            screenshot = await page.screenshot(full_page=True, type="png")
            await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот для диагностики")
        except:
            pass

# ============ ОТКРЫТЬ TWITTER/X ============
async def twitter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        await update.message.reply_text("🌐 Открываю X.com...")
        await goto_url(page, "https://x.com")
        session["current_url"] = "https://x.com"
        
        await page.wait_for_timeout(3000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ **X.com открыт!**\n\n"
                    "🔘 /google_btn - нажать 'Continue with Google'\n"
                    "🔘 /continue - нажать 'Continue as Babe'\n"
                    "🎮 /joystick - управлять вручную"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ НАЖАТЬ "CONTINUE WITH GOOGLE" ============
async def google_login_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    await update.message.reply_text("🔍 Ищу кнопку 'Continue with Google'...")
    
    try:
        clicked = False
        
        for frame in page.frames:
            try:
                selectors = [
                    'text="Continue with Google"',
                    'button:has-text("Continue with Google")',
                    'div:has-text("Continue with Google")',
                    'span:has-text("Continue with Google")',
                    '[aria-label*="Google"]',
                ]
                
                for selector in selectors:
                    try:
                        el = await frame.locator(selector).first
                        if await el.count() > 0 and await el.is_visible():
                            box = await el.bounding_box()
                            if box:
                                x = box['x'] + box['width'] // 2
                                y = box['y'] + box['height'] // 2
                                await human_click(page, x, y)
                            else:
                                await el.click()
                            clicked = True
                            await update.message.reply_text("✅ Нажата кнопка 'Continue with Google'")
                            break
                    except:
                        continue
                if clicked:
                    break
            except:
                continue
        
        if not clicked:
            await update.message.reply_text(
                "❌ Кнопка не найдена\n\n"
                "Попробуй через джойстик: /joystick"
            )
            return
        
        await page.wait_for_timeout(3000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ **Кнопка нажата!**\n\n"
                    "🔘 /continue - нажать 'Continue as Babe'"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ НАЖАТЬ "CONTINUE AS BABE" ============
async def continue_as_google(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    await update.message.reply_text("🔍 Ищу кнопку 'Continue as...' во всех iframe...")
    
    try:
        clicked = False
        button_text = ""
        
        frames = page.frames
        await update.message.reply_text(f"📦 Найдено iframe: {len(frames)}")
        
        for idx, frame in enumerate(frames):
            try:
                selectors = [
                    'text="Continue as"',
                    'text="Продолжить как"',
                    'text="Continue with Google"',
                    'button:has-text("Continue as")',
                    'button:has-text("Продолжить как")',
                    'div:has-text("Continue as")',
                    'div:has-text("Продолжить как")',
                    'div[role="button"]',
                    '[jsname]',
                    '[data-testid]',
                ]
                
                for selector in selectors:
                    try:
                        elements = await frame.locator(selector).all()
                        for el in elements:
                            if await el.is_visible():
                                text = await el.text_content() or ""
                                if any(keyword in text for keyword in ['Continue as', 'Продолжить как', 'Google', 'babe']):
                                    box = await el.bounding_box()
                                    if box:
                                        x = box['x'] + box['width'] // 2
                                        y = box['y'] + box['height'] // 2
                                        await human_click(page, x, y)
                                    else:
                                        await el.click()
                                    clicked = True
                                    button_text = text[:50]
                                    await update.message.reply_text(f"✅ Нажата кнопка в iframe {idx}: {button_text}")
                                    break
                    except:
                        continue
                if clicked:
                    break
            except Exception as e:
                print(f"Ошибка в iframe {idx}: {e}")
                continue
        
        if not clicked:
            await update.message.reply_text("🔍 Ищу на основной странице...")
            selectors = [
                'text="Continue as"',
                'text="Продолжить как"',
                'button:has-text("Continue as")',
                'button:has-text("Продолжить как")',
                'div:has-text("Continue as")',
                'div:has-text("Продолжить как")',
                'div[role="button"]',
            ]
            
            for selector in selectors:
                try:
                    elements = await page.locator(selector).all()
                    for el in elements:
                        if await el.is_visible():
                            text = await el.text_content() or ""
                            if any(keyword in text for keyword in ['Continue as', 'Продолжить как', 'Google']):
                                box = await el.bounding_box()
                                if box:
                                    x = box['x'] + box['width'] // 2
                                    y = box['y'] + box['height'] // 2
                                    await human_click(page, x, y)
                                else:
                                    await el.click()
                                clicked = True
                                button_text = text[:50]
                                await update.message.reply_text(f"✅ Нажата кнопка на странице: {button_text}")
                                break
                except:
                    continue
        
        if not clicked:
            cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
            screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
            await update.message.reply_photo(
                photo=screenshot,
                caption="❌ **Кнопка не найдена**\n\n"
                        "Попробуй через джойстик:\n"
                        "1. /joystick\n"
                        "2. Наведи на кнопку\n"
                        "3. Нажми ЛКМ"
            )
            return
        
        await page.wait_for_timeout(5000)
        
        current_url = page.url
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        cookies = await page.context.cookies()
        has_session = any(c['name'] in ['auth_token', 'ct0', 'twid'] for c in cookies)
        
        if "x.com" in current_url and "login" not in current_url and has_session:
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ **Вход в Twitter выполнен успешно!** 🎉\n\n"
                        "Ты в аккаунте! 🥳"
            )
        elif "x.com" in current_url and "login" in current_url:
            await update.message.reply_photo(
                photo=screenshot,
                caption="⚠️ **Кнопка нажата, но вход не выполнен**\n\n"
                        "Попробуй:\n"
                        "1. Нажать 'Войти' вручную через джойстик\n"
                        "2. /joystick → наведи на 'Войти' → ЛКМ\n"
                        "3. Потом снова /continue"
            )
        elif "accounts.google.com" in current_url:
            await update.message.reply_photo(
                photo=screenshot,
                caption="🔐 **Открылось окно Google**\n\n"
                        "Бот уже вошёл в Google.\n"
                        "Нажми /twitter и попробуй снова."
            )
        else:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Текущая страница: {current_url[:60]}\n\n"
                        "Проверь статус: /status"
            )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        try:
            screenshot = await page.screenshot(full_page=True, type="png")
            await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот для диагностики")
        except:
            pass

# ============ РАБОТА С КУКАМИ ============

async def load_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    if not update.message.document:
        await update.message.reply_text(
            "❌ Отправь файл cookies.json\n\n"
            "Формат:\n"
            '[{"name":"auth_token","value":"...","domain":".x.com","path":"/"}]'
        )
        return
    
    document = update.message.document
    if not document.file_name.endswith('.json'):
        await update.message.reply_text("❌ Файл должен быть .json")
        return
    
    file = await context.bot.get_file(document.file_id)
    file_path = f"/tmp/cookies_{user_id}.json"
    await file.download_to_drive(file_path)
    
    try:
        with open(file_path, 'r') as f:
            cookies_data = json.load(f)
        
        session = user_sessions[user_id]
        page = session["page"]
        context_browser = session["context"]
        
        await context_browser.clear_cookies()
        await context_browser.add_cookies(cookies_data)
        
        await update.message.reply_text(f"✅ Загружено {len(cookies_data)} кук")
        
        await page.reload()
        await page.wait_for_timeout(2000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Куки загружены! Страница перезагружена."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

async def save_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        cookies = await page.context.cookies()
        json_data = json.dumps(cookies, indent=2)
        
        buffer = BytesIO(json_data.encode('utf-8'))
        buffer.name = "cookies.json"
        
        await update.message.reply_document(
            document=buffer,
            filename="cookies.json",
            caption=f"📦 Куки сохранены ({len(cookies)} шт.)"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def set_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/setcookie auth_token=значение ct0=значение\n\n"
            "Пример:\n"
            "/setcookie auth_token=09fe982487255e... ct0=18f7448391062..."
        )
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    context_browser = session["context"]
    
    try:
        cookies_to_add = []
        i = 0
        while i < len(args):
            if "=" in args[i]:
                key, value = args[i].split("=", 1)
                cookies_to_add.append({"name": key, "value": value, "domain": ".x.com", "path": "/"})
            elif i + 1 < len(args):
                key = args[i]
                value = args[i + 1]
                cookies_to_add.append({"name": key, "value": value, "domain": ".x.com", "path": "/"})
                i += 1
            i += 1
        
        if not cookies_to_add:
            await update.message.reply_text("❌ Не найдены куки для установки")
            return
        
        await context_browser.add_cookies(cookies_to_add)
        
        await update.message.reply_text(f"✅ Установлено {len(cookies_to_add)} кук")
        
        await page.reload()
        await page.wait_for_timeout(2000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Куки установлены! Страница перезагружена."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ СТАТУС ============
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Браузер не открыт. Используй: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    url = page.url
    
    cookies = await page.context.cookies()
    has_cookie = any(c['name'] in ['auth_token', 'ct0', 'twid'] for c in cookies)
    
    status_text = f"📊 **Статус браузера**\n\n"
    status_text += f"🌐 Текущий URL: {url[:60]}\n"
    status_text += f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
    
    if "x.com" in url:
        status_text += "📱 На сайте: Twitter/X\n"
        status_text += f"✅ **Вы {'вошли' if has_cookie else 'НЕ вошли'} в Twitter!**\n"
    elif "google" in url:
        status_text += "📱 На сайте: Google\n"
    else:
        status_text += f"📱 Сайт: {url[:30]}\n"
    
    cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
    screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
    
    await update.message.reply_photo(photo=screenshot, caption=status_text)

# ============ ПОКАЗАТЬ ВСЕ IFRAME ============
async def show_frames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        frames = page.frames
        await update.message.reply_text(f"📦 Найдено iframe: {len(frames)}")
        
        for i, frame in enumerate(frames):
            try:
                url = frame.url
                await update.message.reply_text(f"🔹 iframe {i}: {url[:80]}")
            except:
                await update.message.reply_text(f"🔹 iframe {i}: <недоступно>")
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот страницы")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ НАЖАТЬ "ВОЙТИ" ============
async def click_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    await update.message.reply_text("🔍 Ищу кнопку 'Войти'...")
    
    try:
        clicked = False
        
        selectors = [
            'text="Войти"',
            'text="Sign in"',
            'text="Log in"',
            'a:has-text("Войти")',
            'a:has-text("Sign in")',
            'div[role="button"]:has-text("Войти")',
            '[data-testid="loginButton"]',
        ]
        
        for selector in selectors:
            try:
                el = await page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    box = await el.bounding_box()
                    if box:
                        x = box['x'] + box['width'] // 2
                        y = box['y'] + box['height'] // 2
                        await human_click(page, x, y)
                    else:
                        await el.click()
                    clicked = True
                    await update.message.reply_text("✅ Нажата кнопка 'Войти'")
                    break
            except:
                continue
        
        if not clicked:
            await update.message.reply_text("❌ Кнопка 'Войти' не найдена")
            return
        
        await page.wait_for_timeout(3000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Страница входа открыта\n\n"
                    "Теперь нажми /google_btn"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ ПЕРЕЙТИ НА СТРАНИЦУ ВХОДА ============
async def goto_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    try:
        await update.message.reply_text("🌐 Перехожу на страницу входа X.com...")
        await goto_url(page, "https://x.com/login")
        
        await page.wait_for_timeout(3000)
        
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Страница входа открыта\n\n"
                    "Теперь нажми /google_btn"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я бот с управлением браузером!\n\n"
        "🌐 /browser - Открыть браузер\n"
        "🔐 /login email pass - Войти в Google (автоматически)\n"
        "🍪 /setcookie key=value - Установить куки вручную\n"
        "📄 /loadcookies - Загрузить куки из файла\n"
        "💾 /savecookies - Сохранить текущие куки\n"
        "🐦 /twitter - Открыть X.com\n"
        "🔘 /login_btn - Нажать 'Войти'\n"
        "🔘 /google_btn - Нажать 'Continue with Google'\n"
        "🔘 /continue - Нажать 'Continue as Babe'\n"
        "📦 /frames - Показать все iframe\n"
        "🎮 /joystick - Открыть джойстик\n"
        "📊 /status - Проверить статус\n"
        "📸 /screenshot - Сделать скриншот\n"
        "❌ /close - Закрыть браузер\n\n"
        "🚀 Быстрый вход с куками:\n"
        "/browser → /setcookie auth_token=... → /twitter"
    )

async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    await update.message.reply_text("🌐 Открываю браузер...")
    
    try:
        await get_user_browser(user_id)
        await update.message.reply_text(
            "✅ Браузер готов!\n\n"
            "🍪 /setcookie ключ=значение - установить куки\n"
            "🐦 /twitter - открыть X.com\n"
            "🎮 /joystick - открыть джойстик"
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
        
        screenshot = await human_screenshot(page, VIEWPORT["width"] // 2, VIEWPORT["height"] // 2)
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
        
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
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
    
    screenshot = await human_screenshot(page, current_x, current_y)
    
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

# ============ ОБРАБОТЧИК КНОПОК ============
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
    
    if data.startswith("move_"):
        parts = data.split("_")
        dx = int(parts[1])
        dy = int(parts[2])
        
        try:
            new_x = max(0, min(VIEWPORT["width"], current_x + dx))
            new_y = max(0, min(VIEWPORT["height"], current_y + dy))
            
            cursor_positions[user_id] = {"x": new_x, "y": new_y}
            
            await human_move(page, new_x, new_y, steps=5)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ Движение → ({new_x}, {new_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка движения: {e}")
    
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
    
    elif data == "click_right":
        try:
            await human_click(page, current_x, current_y, button="right")
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ ПКМ ({current_x}, {current_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка ПКМ: {e}")
    
    elif data == "click_center":
        try:
            await human_click(page, current_x, current_y)
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                f"🖱️ Клик ({current_x}, {current_y})"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка клика: {e}")
    
    elif data == "press_enter":
        try:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "⌨️ Enter"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка Enter: {e}")
    
    elif data == "refresh":
        try:
            await page.reload()
            await page.wait_for_timeout(500)
            
            await update_joystick_message(
                query, page, user_id, mode,
                "🔄 Обновлено"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка обновления: {e}")
    
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
    
    elif data == "screenshot":
        try:
            await update_joystick_message(
                query, page, user_id, mode,
                "📸 Скриншот"
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка скриншота: {e}")
    
    elif data == "close_browser":
        await close_user_browser(user_id)
        await query.edit_message_text("❌ Браузер закрыт", reply_markup=None)
        if user_id in joystick_messages:
            del joystick_messages[user_id]
    
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
            f"🔄 {mode_label}"
        )
    
    elif data == "change_url":
        await query.edit_message_text(
            "🔗 Введи URL: /go <url>",
            reply_markup=None
        )
        if user_id in joystick_messages:
            del joystick_messages[user_id]
    
    elif data == "hide_joystick":
        if user_id in joystick_messages:
            del joystick_messages[user_id]
        if user_id in joystick_states:
            del joystick_states[user_id]
        
        await query.edit_message_text(
            "✅ Джойстик закрыт\n\n🎮 /joystick - открыть заново",
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
    bot_app.add_handler(CommandHandler("status", status_command))
    bot_app.add_handler(CommandHandler("login", login_google))
    bot_app.add_handler(CommandHandler("twitter", twitter_command))
    bot_app.add_handler(CommandHandler("login_btn", click_login))
    bot_app.add_handler(CommandHandler("google_btn", google_login_button))
    bot_app.add_handler(CommandHandler("continue", continue_as_google))
    bot_app.add_handler(CommandHandler("loadcookies", load_cookies))
    bot_app.add_handler(CommandHandler("savecookies", save_cookies))
    bot_app.add_handler(CommandHandler("setcookie", set_cookies))
    bot_app.add_handler(CommandHandler("frames", show_frames))
    bot_app.add_handler(CommandHandler("gologin", goto_login))
    
    bot_app.add_handler(CallbackQueryHandler(joystick_callback))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()