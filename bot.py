import os
import logging
import threading
import asyncio
import random
import re
from io import BytesIO
import requests
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# ============ КУКИ ============
MY_COOKIES = [
    {"name": "auth_token", "value": "09fe982487255e707f7a9b3d380ea429421adae3", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

user_sessions = {}

# ============ FLASK ============
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ ПОЛНАЯ ЭМУЛЯЦИЯ БРАУЗЕРА ============
async def get_browser():
    playwright = await async_playwright().start()
    
    viewport_width = random.choice([1366, 1440, 1536, 1600, 1920])
    viewport_height = random.choice([768, 900, 960, 1080])
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--disable-gpu',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-features=BlockInsecurePrivateNetworkRequests',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-site-isolation-trials',
            '--disable-software-rasterizer',
        ]
    )
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    context = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height},
        user_agent=random.choice(user_agents),
        locale="ru-RU",
        timezone_id="Europe/Moscow",
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
        {"name": "_ga", "value": f"GA1.2.{random.randint(100000, 999999)}.{random.randint(1000000000, 9999999999)}", "domain": ".x.com", "path": "/"},
        {"name": "_gid", "value": f"GA1.2.{random.randint(100000, 999999)}.{random.randint(1000000000, 9999999999)}", "domain": ".x.com", "path": "/"},
        {"name": "_gat", "value": "1", "domain": ".x.com", "path": "/"},
    ])
    
    await context.add_cookies(MY_COOKIES)
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete Object.getPrototypeOf(navigator).webdriver;
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.length = 3;
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                return plugins;
            }
        });
        
        Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
        Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
        Object.defineProperty(screen, 'width', { get: () => 1920 });
        Object.defineProperty(screen, 'height', { get: () => 1080 });
        
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
        
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter(parameter);
        };
        
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png') {
                return originalToDataURL.apply(this, arguments);
            }
            return originalToDataURL.apply(this, arguments);
        };
        
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        console.log('✅ Полная эмуляция браузера включена');
    """)
    
    return page, browser, context

async def get_user_browser(user_id: int):
    if user_id not in user_sessions:
        page, browser, context = await get_browser()
        user_sessions[user_id] = {"page": page, "browser": browser, "context": context}
        await page.goto("about:blank")
    return user_sessions[user_id]

async def close_user_browser(user_id: int):
    if user_id in user_sessions:
        await user_sessions[user_id]["browser"].close()
        del user_sessions[user_id]

async def take_screenshot(page) -> bytes:
    try:
        return await page.screenshot(type="png")
    except:
        return b""

def escape_markdown(text):
    if not text:
        return ''
    escape_chars = r'[_*\[\]()~>#+=|{}.!-]'
    return re.sub(r'([%s])' % escape_chars, r'\\\1', text)

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **КОМАНДЫ**\n\n"
        "/browser — Открыть браузер\n"
        "/x — Открыть X.com\n"
        "/screenshot — Скриншот\n"
        "/tweets — 3 твита\n"
        "/status — Статус\n"
        "/close — Закрыть",
        parse_mode="Markdown"
    )

async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер с полной эмуляцией...")
    await get_user_browser(user_id)
    await update.message.reply_text("✅ Браузер готов! Эмуляция включена.")

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("🐦 Открываю X.com...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(3)
        
        screenshot = await take_screenshot(page)
        if screenshot and len(screenshot) > 1000:
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="✅ X.com открыт!")
        else:
            await update.message.reply_text("✅ X.com открыт!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("📸 Делаю скриншот...")
    page = user_sessions[user_id]["page"]
    screenshot = await take_screenshot(page)
    
    if screenshot and len(screenshot) > 1000:
        await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 Скриншот")
    else:
        await update.message.reply_text("❌ Не удалось")

async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("📡 Собираю 3 твита...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(4)
        
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1)
        
        tweets = await page.evaluate("""
            () => {
                const posts = [];
                const articles = document.querySelectorAll('[data-testid="tweet"], article');
                articles.forEach((article, index) => {
                    if (index >= 3) return;
                    try {
                        const nameEl = article.querySelector('[data-testid="User-Name"]');
                        let name = 'Неизвестно', username = '';
                        if (nameEl) {
                            const spans = nameEl.querySelectorAll('span');
                            if (spans.length > 0) name = spans[0]?.textContent || 'Неизвестно';
                            if (spans.length > 1) username = spans[1]?.textContent?.replace('@', '') || '';
                        }
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.textContent : '';
                        const timeEl = article.querySelector('time');
                        const time = timeEl ? timeEl.textContent : '';
                        const linkEl = article.querySelector('a[href*="/status/"]');
                        let link = '';
                        if (linkEl) {
                            const href = linkEl.getAttribute('href');
                            if (href) link = 'https://x.com' + href;
                        }
                        if (text || link) {
                            posts.push({ name, username, text, time, link });
                        }
                    } catch(e) {}
                });
                return posts;
            }
        """)
        
        if tweets and len(tweets) > 0:
            for i, tweet in enumerate(tweets, 1):
                name = escape_markdown(tweet['name'])
                username = escape_markdown(tweet['username'])
                text = escape_markdown(tweet['text'][:500])
                time = escape_markdown(tweet['time'])
                link = escape_markdown(tweet['link'])
                
                msg = (
                    f"📌 **Твит {i}**\n\n"
                    f"👤 **{name}**\n"
                    f"🔹 @{username}\n"
                    f"🕐 {time}\n\n"
                    f"📝 {text}{'...' if len(tweet['text']) > 500 else ''}\n\n"
                    f"🔗 {link}"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ Готово!")
        else:
            await update.message.reply_text("❌ Посты не найдены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Браузер не открыт")
        return
    
    page = user_sessions[user_id]["page"]
    url = page.url
    cookies = await page.context.cookies()
    has_cookie = any(c['name'] == 'auth_token' for c in cookies)
    
    text = f"📊 **Статус**\n\n🌐 URL: {url[:60]}\n🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
    if "x.com" in url:
        text += f"📱 X.com - {'✅ Вошли' if has_cookie else '❌ Не вошли'}"
    await update.message.reply_text(text)

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    await update.message.reply_text("❌ Закрыто")

# ============ ЗАПУСК ============
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("browser", browser_command))
    bot_app.add_handler(CommandHandler("x", x_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("tweets", tweets_command))
    bot_app.add_handler(CommandHandler("status", status_command))
    bot_app.add_handler(CommandHandler("close", close_command))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()