import os
import logging
import threading
import time
import asyncio
import random
import re
import json
import subprocess
import sys
from io import BytesIO
import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from playwright.async_api import async_playwright
from agnes_vision import vision_command, vision_click_command, vision_ask_command

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Хранилища
user_sessions = {}
cursor_positions = {}

# Файл для сохранения кук
COOKIES_FILE = "cookies_data.json"

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

# ============ РАБОТА С КУКАМИ ============
def load_saved_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_cookies_to_file(user_id: int, cookies: list):
    try:
        data = load_saved_cookies()
        data[str(user_id)] = cookies
        with open(COOKIES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка сохранения кук: {e}")
        return False

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
            '--disable-hang-monitor',
            '--disable-prompt-on-repost',
            '--disable-component-extensions-with-background-pages',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--force-color-profile=srgb',
            '--disable-site-isolation-trials',
            '--disable-software-rasterizer',
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
        if user_id in cursor_positions:
            del cursor_positions[user_id]

async def goto_url(page, url: str):
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        print(f"✅ {url} загружен")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки {url}: {e}")
        raise e

# ============ ACTIONCHAINS ============

async def human_move(page, x: int, y: int, steps: int = 10):
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

async def human_screenshot(page, x: int, y: int) -> bytes:
    try:
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
        screenshot = await page.screenshot(full_page=False, type="png")
        return screenshot
        
    except Exception as e:
        print(f"Ошибка скриншота: {e}")
        try:
            screenshot = await page.screenshot(full_page=False, type="png")
            return screenshot
        except:
            return b""

# ============ TWITTER MENU ============

def get_twitter_menu():
    keyboard = [
        [
            InlineKeyboardButton("🏠 Главная лента", callback_data="twitter_home"),
            InlineKeyboardButton("📈 Тренды", callback_data="twitter_trends"),
        ],
        [
            InlineKeyboardButton("👤 Мой профиль", callback_data="twitter_profile"),
            InlineKeyboardButton("📥 Закладки", callback_data="twitter_bookmarks"),
        ],
        [
            InlineKeyboardButton("❌ Закрыть меню", callback_data="twitter_close"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ КОМАНДА /START ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **КОМАНДЫ БОТА**\n\n"
        "🌐 **БРАУЗЕР**\n"
        "/browser — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/go url — Перейти на сайт\n"
        "/status — Статус браузера\n"
        "/screenshot — Скриншот\n\n"
        "🍪 **КУКИ**\n"
        "/setcookie — Установить куки\n"
        "/loadcookies — Загрузить куки из файла\n"
        "/loadsavedcookies — Загрузить saved куки\n"
        "/savecookies — Сохранить куки\n\n"
        "🐦 **X**\n"
        "/startxspeed — Быстрый старт (всё сразу)\n"
        "/xprofile — Инфо профиля\n"
        "/twittermenu — Открыть меню Twitter\n\n"
        "👁️ **МАШИННОЕ ЗРЕНИЕ**\n"
        "/vision — Описать страницу\n"
        "/vclick <описание> — Кликнуть по элементу\n"
        "/vask <вопрос> — Задать вопрос о странице",
        parse_mode="Markdown"
    )

# ============ КОМАНДА /BROWSER ============
async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер...")
    try:
        await get_user_browser(user_id)
        session = user_sessions[user_id]
        
        # Сохраняем page в context для команд машинного зрения
        context.user_data['page'] = session["page"]
        
        await update.message.reply_text("✅ Браузер готов!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДА /CLOSE ============
async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    if 'page' in context.user_data:
        del context.user_data['page']
    await update.message.reply_text("❌ Браузер закрыт")

# ============ КОМАНДА /GO ============
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
        await update.message.reply_photo(photo=screenshot, caption=f"✅ {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДА /STATUS ============
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
    status_text += f"🌐 URL: {url[:60]}\n"
    status_text += f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
    if "x.com" in url:
        status_text += f"📱 X.com - {'✅ Вошли' if has_cookie else '❌ Не вошли'}\n"
    cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
    screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
    await update.message.reply_photo(photo=screenshot, caption=status_text)

# ============ КОМАНДА /SCREENSHOT ============
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

# ============ КОМАНДА /SETCOOKIE ============
async def set_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/setcookie auth_token=значение ct0=значение"
        )
        return
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
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
        await update.message.reply_photo(photo=screenshot, caption="✅ Куки установлены! Страница перезагружена.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДА /LOADCOOKIES ============
async def load_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    if not update.message.document:
        await update.message.reply_text("❌ Отправь файл cookies.json")
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
        await update.message.reply_photo(photo=screenshot, caption="✅ Куки загружены!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

# ============ КОМАНДА /LOADSAVEDCOOKIES ============
async def load_saved_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    try:
        saved_cookies_data = load_saved_cookies()
        cookies_to_load = saved_cookies_data.get(str(user_id), [])
        if not cookies_to_load:
            await update.message.reply_text("❌ Нет сохранённых кук. Сначала используй /startxspeed или /xprofile")
            return
        session = user_sessions[user_id]
        page = session["page"]
        context_browser = session["context"]
        await context_browser.clear_cookies()
        await context_browser.add_cookies(cookies_to_load)
        await update.message.reply_text(f"✅ Загружено {len(cookies_to_load)} кук из файла")
        await page.reload()
        await page.wait_for_timeout(2000)
        cursor = cursor_positions.get(user_id, {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2})
        screenshot = await human_screenshot(page, cursor["x"], cursor["y"])
        await update.message.reply_photo(photo=screenshot, caption="✅ Сохранённые куки загружены!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДА /SAVECOOKIES ============
async def save_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

# ============ КОМАНДА /STARTXSPEED ============
async def start_x_com(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🚀 Запускаю X.com с куками...")
    try:
        await get_user_browser(user_id)
        session = user_sessions[user_id]
        context.user_data['page'] = session["page"]
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка открытия браузера: {e}")
        return
    session = user_sessions[user_id]
    page = session["page"]
    context_browser = session["context"]
    
    cookies_to_add = [
        {"name": "auth_token", "value": "09fe982487255e707f7a9b3d380ea429421adae3", "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281", "domain": ".x.com", "path": "/"},
        {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
        {"name": "guest_id", "value": "v1%3A178224957371538879", "domain": ".x.com", "path": "/"},
        {"name": "guest_id_ads", "value": "v1%3A178224957371538879", "domain": ".x.com", "path": "/"},
        {"name": "guest_id_marketing", "value": "v1%3A178224957371538879", "domain": ".x.com", "path": "/"},
        {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    ]
    
    try:
        await context_browser.clear_cookies()
        await context_browser.add_cookies(cookies_to_add)
        await update.message.reply_text(f"✅ Установлено {len(cookies_to_add)} кук")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка установки кук: {e}")
        return
    try:
        await goto_url(page, "https://x.com")
        session["current_url"] = "https://x.com"
        await page.wait_for_timeout(3000)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка открытия X.com: {e}")
        return
    try:
        profile_data = await page.evaluate("""
            () => {
                const data = { name: '', username: '', avatar: '', followers: 0, following: 0, tweets: 0, bio: '' };
                try {
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    if (nameEl) {
                        const spans = nameEl.querySelectorAll('span');
                        if (spans.length > 0) data.name = spans[0].textContent;
                        if (spans.length > 1) data.username = spans[1].textContent.replace('@', '');
                    }
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    if (bioEl) data.bio = bioEl.textContent;
                    const avatarEl = document.querySelector('img[src*="profile_images"]');
                    if (avatarEl) data.avatar = avatarEl.src;
                    const stats = document.querySelectorAll('[data-testid="UserStats"]');
                    if (stats.length > 0) {
                        const texts = stats[0].textContent.split('·');
                        if (texts.length > 0) {
                            const followers = texts[0].match(/\\d+/);
                            if (followers) data.followers = parseInt(followers[0]);
                        }
                        if (texts.length > 1) {
                            const following = texts[1].match(/\\d+/);
                            if (following) data.following = parseInt(following[0]);
                        }
                    }
                } catch(e) {}
                return data;
            }
        """)
        name = profile_data.get('name', 'Неизвестно')
        username = profile_data.get('username', 'Неизвестно')
        avatar = profile_data.get('avatar', '')
        followers = profile_data.get('followers', 0)
        following = profile_data.get('following', 0)
        tweets = profile_data.get('tweets', 0)
        bio = profile_data.get('bio', '')
        cookies = await page.context.cookies()
        save_cookies_to_file(user_id, cookies)
        text = (
            f"🐦 **X.com запущен!**\n\n"
            f"✅ Куки установлены и сохранены\n"
            f"👤 **Имя:** {name}\n"
            f"🔹 **@** {username}\n"
            f"📝 **Био:** {bio[:100] + '...' if len(bio) > 100 else bio or 'Не указана'}\n\n"
            f"📊 **Статистика:**\n"
            f"   📌 Подписчиков: {followers:,}\n"
            f"   📌 Подписок: {following:,}\n"
            f"   📌 Твитов: {tweets:,}\n\n"
            f"💾 Куки сохранены навсегда!"
        )
        if avatar:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.get(avatar) as resp:
                        if resp.status == 200:
                            avatar_data = await resp.read()
                            await update.message.reply_photo(
                                photo=BytesIO(avatar_data),
                                caption=text,
                                parse_mode="Markdown"
                            )
                            return
            except:
                pass
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"✅ X.com открыт!\n\nКуки установлены и сохранены.")
        print(f"Ошибка получения профиля: {e}")

# ============ КОМАНДА /XPROFILE ============
async def x_profile_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    session = user_sessions[user_id]
    page = session["page"]
    await update.message.reply_text("🔍 Получаю информацию о профиле X...")
    try:
        cookies = await page.context.cookies()
        has_session = any(c['name'] in ['auth_token', 'ct0', 'twid'] for c in cookies)
        if not has_session:
            await update.message.reply_text("❌ Нет активной сессии X. Сначала войди.")
            return
        if save_cookies_to_file(user_id, cookies):
            await update.message.reply_text("💾 Куки сохранены навсегда!")
        await page.goto("https://x.com", wait_until="load")
        await page.wait_for_timeout(2000)
        profile_data = await page.evaluate("""
            () => {
                const data = { name: '', username: '', avatar: '', followers: 0, following: 0, tweets: 0, bio: '' };
                try {
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    if (nameEl) {
                        const spans = nameEl.querySelectorAll('span');
                        if (spans.length > 0) data.name = spans[0].textContent;
                        if (spans.length > 1) data.username = spans[1].textContent.replace('@', '');
                    }
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    if (bioEl) data.bio = bioEl.textContent;
                    const avatarEl = document.querySelector('img[src*="profile_images"]');
                    if (avatarEl) data.avatar = avatarEl.src;
                    const stats = document.querySelectorAll('[data-testid="UserStats"]');
                    if (stats.length > 0) {
                        const texts = stats[0].textContent.split('·');
                        if (texts.length > 0) {
                            const followers = texts[0].match(/\\d+/);
                            if (followers) data.followers = parseInt(followers[0]);
                        }
                        if (texts.length > 1) {
                            const following = texts[1].match(/\\d+/);
                            if (following) data.following = parseInt(following[0]);
                        }
                    }
                } catch(e) {}
                return data;
            }
        """)
        name = profile_data.get('name', 'Неизвестно')
        username = profile_data.get('username', 'Неизвестно')
        avatar = profile_data.get('avatar', '')
        followers = profile_data.get('followers', 0)
        following = profile_data.get('following', 0)
        tweets = profile_data.get('tweets', 0)
        bio = profile_data.get('bio', '')
        text = (
            f"🐦 **Профиль X**\n\n"
            f"👤 **Имя:** {name}\n"
            f"🔹 **@** {username}\n"
            f"📝 **Био:** {bio[:100] + '...' if len(bio) > 100 else bio or 'Не указана'}\n\n"
            f"📊 **Статистика:**\n"
            f"   📌 Подписчиков: {followers:,}\n"
            f"   📌 Подписок: {following:,}\n"
            f"   📌 Твитов: {tweets:,}\n\n"
            f"💾 Куки сохранены навсегда!"
        )
        if avatar:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.get(avatar) as resp:
                        if resp.status == 200:
                            avatar_data = await resp.read()
                            await update.message.reply_photo(
                                photo=BytesIO(avatar_data),
                                caption=text,
                                parse_mode="Markdown"
                            )
                            return
            except:
                pass
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ КОМАНДА /TWITTERMENU ============
async def twitter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    
    session = user_sessions[user_id]
    page = session["page"]
    
    cookies = await page.context.cookies()
    has_session = any(c['name'] in ['auth_token', 'ct0', 'twid'] for c in cookies)
    
    if not has_session:
        await update.message.reply_text(
            "⚠️ **Ты не вошёл в X.com!**\n\n"
            "Используй /startxspeed или /setcookie",
            reply_markup=get_twitter_menu()
        )
        return
    
    await update.message.reply_text(
        "🐦 **TWITTER МЕНЮ**\n\n"
        "Выбери раздел:",
        reply_markup=get_twitter_menu()
    )

# ============ ОБРАБОТЧИК КНОПОК TWITTER ============
async def twitter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    # ============ ГЛАВНАЯ ЛЕНТА ============
    if data == "twitter_home":
        await query.edit_message_text("📡 Загружаю главную ленту...")
        try:
            await page.goto("https://x.com", wait_until="load")
            await page.wait_for_timeout(3000)
            
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(1000)
            
            posts = await get_posts_from_page(page, limit=10)
            
            if posts:
                await query.edit_message_text(
                    f"🏠 **Главная лента**\n\n📊 Найдено {len(posts)} постов",
                    reply_markup=get_twitter_menu()
                )
                for post in posts:
                    await send_post(query.message, post)
            else:
                await query.edit_message_text(
                    "❌ Посты не найдены",
                    reply_markup=get_twitter_menu()
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_twitter_menu())
    
    # ============ ТРЕНДЫ ============
    elif data == "twitter_trends":
        await query.edit_message_text("📈 Загружаю тренды...")
        try:
            try:
                await page.goto("https://x.com/explore/tabs/trending", wait_until="load", timeout=30000)
            except Exception as e:
                await query.edit_message_text("🔄 Перезапускаю браузер...")
                await close_user_browser(user_id)
                await get_user_browser(user_id)
                page = user_sessions[user_id]["page"]
                await page.goto("https://x.com/explore/tabs/trending", wait_until="load", timeout=30000)
            
            await page.wait_for_timeout(3000)
            
            trends = await page.evaluate("""
                () => {
                    const trends = [];
                    const items = document.querySelectorAll('[data-testid="trend"]');
                    items.forEach((item, i) => {
                        if (i >= 20) return;
                        const text = item.textContent || '';
                        if (text) trends.push(text.trim());
                    });
                    return trends;
                }
            """)
            
            if trends:
                text = "📈 **Тренды X.com**\n\n"
                for i, trend in enumerate(trends[:10], 1):
                    text += f"{i}. {trend[:60]}\n"
                await query.edit_message_text(text, reply_markup=get_twitter_menu())
            else:
                await query.edit_message_text(
                    "❌ Тренды не найдены",
                    reply_markup=get_twitter_menu()
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_twitter_menu())
    
    # ============ ПРОФИЛЬ ============
    elif data == "twitter_profile":
        await query.edit_message_text("👤 Загружаю профиль...")
        try:
            await page.goto("https://x.com", wait_until="load")
            await page.wait_for_timeout(2000)
            
            profile = await get_profile_info(page)
            
            if profile and profile.get('name'):
                text = (
                    f"👤 **{profile['name']}**\n"
                    f"🔹 @{profile['username']}\n\n"
                    f"📝 {profile['bio'][:100] if profile['bio'] else 'Био не указана'}\n\n"
                    f"📊 Подписчиков: {profile['followers']:,}\n"
                    f"📊 Подписок: {profile['following']:,}\n"
                    f"📊 Твитов: {profile['tweets']:,}"
                )
                await query.edit_message_text(text, reply_markup=get_twitter_menu())
            else:
                await query.edit_message_text(
                    "❌ Не удалось загрузить профиль",
                    reply_markup=get_twitter_menu()
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_twitter_menu())
    
    # ============ ЗАКЛАДКИ ============
    elif data == "twitter_bookmarks":
        await query.edit_message_text("📥 Загружаю закладки...")
        try:
            await page.goto("https://x.com/i/bookmarks", wait_until="load")
            await page.wait_for_timeout(3000)
            
            for _ in range(2):
                await page.evaluate("window.scrollBy(0, 400)")
                await page.wait_for_timeout(500)
            
            posts = await get_posts_from_page(page, limit=10)
            
            if posts:
                await query.edit_message_text(
                    f"📥 **Закладки**\n\n📊 Найдено {len(posts)} постов",
                    reply_markup=get_twitter_menu()
                )
                for post in posts:
                    await send_post(query.message, post)
            else:
                await query.edit_message_text(
                    "❌ Закладок нет",
                    reply_markup=get_twitter_menu()
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=get_twitter_menu())
    
    # ============ ЗАКРЫТЬ ============
    elif data == "twitter_close":
        await query.edit_message_text("❌ Меню закрыто", reply_markup=None)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def get_posts_from_page(page, limit=10):
    try:
        posts = await page.evaluate(f"""
            () => {{
                const posts = [];
                const articles = document.querySelectorAll('[data-testid="tweet"], article');
                
                articles.forEach((article, index) => {{
                    if (index >= {limit}) return;
                    
                    try {{
                        const nameEl = article.querySelector('[data-testid="User-Name"]');
                        let author = 'Неизвестно';
                        let username = '';
                        if (nameEl) {{
                            const spans = nameEl.querySelectorAll('span');
                            if (spans.length > 0) author = spans[0]?.textContent || 'Неизвестно';
                            if (spans.length > 1) username = spans[1]?.textContent?.replace('@', '') || '';
                        }}
                        
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.textContent : '';
                        
                        const timeEl = article.querySelector('time');
                        const time = timeEl ? timeEl.textContent : '';
                        
                        if (text) {{
                            posts.push({{
                                author: author,
                                username: username,
                                text: text,
                                time: time
                            }});
                        }}
                    }} catch(e) {{}}
                }});
                
                return posts;
            }}
        """)
        return posts
    except Exception as e:
        print(f"Ошибка сбора постов: {e}")
        return []

async def get_profile_info(page):
    try:
        profile = await page.evaluate("""
            () => {
                const data = { name: '', username: '', bio: '', followers: 0, following: 0, tweets: 0 };
                try {
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    if (nameEl) {
                        const spans = nameEl.querySelectorAll('span');
                        if (spans.length > 0) data.name = spans[0].textContent;
                        if (spans.length > 1) data.username = spans[1].textContent.replace('@', '');
                    }
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    if (bioEl) data.bio = bioEl.textContent;
                    const stats = document.querySelectorAll('[data-testid="UserStats"]');
                    if (stats.length > 0) {
                        const texts = stats[0].textContent.split('·');
                        if (texts.length > 0) {
                            const followers = texts[0].match(/\\d+/);
                            if (followers) data.followers = parseInt(followers[0]);
                        }
                        if (texts.length > 1) {
                            const following = texts[1].match(/\\d+/);
                            if (following) data.following = parseInt(following[0]);
                        }
                    }
                } catch(e) {}
                return data;
            }
        """)
        return profile
    except:
        return {}

async def send_post(message, post):
    text = (
        f"👤 **{post['author']}**\n"
        f"🔹 @{post['username']}\n"
        f"🕐 {post['time']}\n\n"
        f"📝 {post['text'][:300]}{'...' if len(post['text']) > 300 else ''}"
    )
    await message.reply_text(text, parse_mode="Markdown")
    await asyncio.sleep(0.3)

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
    bot_app.add_handler(CommandHandler("close", close_command))
    bot_app.add_handler(CommandHandler("go", go_command))
    bot_app.add_handler(CommandHandler("status", status_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("setcookie", set_cookies))
    bot_app.add_handler(CommandHandler("loadcookies", load_cookies))
    bot_app.add_handler(CommandHandler("loadsavedcookies", load_saved_cookies_command))
    bot_app.add_handler(CommandHandler("savecookies", save_cookies_command))
    bot_app.add_handler(CommandHandler("startxspeed", start_x_com))
    bot_app.add_handler(CommandHandler("xprofile", x_profile_info))
    bot_app.add_handler(CommandHandler("twittermenu", twitter_menu))
    bot_app.add_handler(CommandHandler("vision", vision_command))
    bot_app.add_handler(CommandHandler("vclick", vision_click_command))
    bot_app.add_handler(CommandHandler("vask", vision_ask_command))
    
    bot_app.add_handler(CallbackQueryHandler(twitter_callback, pattern="^twitter_"))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()