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

MY_COOKIES = [
    {"name": "auth_token", "value": "09fe982487255e707f7a9b3d380ea429421adae3", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

user_sessions = {}

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

# ============ ЭМУЛЯЦИЯ КУРСОРА ============
async def human_move(page, x, y, steps=10):
    """Плавное движение мыши как у человека"""
    try:
        # Получаем текущую позицию
        current = await page.evaluate("""
            () => ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        
        for i in range(steps):
            progress = (i + 1) / steps
            # Кривая Безье для плавности
            ease = 1 - (1 - progress) ** 3
            target_x = current["x"] + (x - current["x"]) * ease + random.randint(-3, 3)
            target_y = current["y"] + (y - current["y"]) * ease + random.randint(-3, 3)
            await page.mouse.move(target_x, target_y)
            await asyncio.sleep(random.uniform(0.02, 0.06))
        
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        return True
    except:
        return False

async def human_click(page, x, y, button="left"):
    """Клик с задержкой как у человека"""
    try:
        await human_move(page, x, y, steps=8)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.down(button=button)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up(button=button)
        await asyncio.sleep(random.uniform(0.1, 0.2))
        return True
    except:
        return False

async def human_scroll(page, amount, steps=3):
    """Плавная прокрутка"""
    try:
        for i in range(steps):
            scroll_amount = amount // steps + random.randint(-20, 20)
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.1, 0.3))
        return True
    except:
        return False

# ============ ЭМУЛЯЦИЯ КЛАВИАТУРЫ ============
async def human_type(page, text, delay=50):
    """Ввод текста с случайными задержками между символами"""
    try:
        # Клик на поле ввода (фокус)
        await page.mouse.click(100, 100)
        await asyncio.sleep(0.2)
        
        for char in text:
            # Случайная задержка между символами
            wait_time = delay + random.randint(-15, 30)
            if char.isupper() or char in '!@#$%^&*()_+':
                wait_time += random.randint(20, 50)
            await page.keyboard.type(char, delay=wait_time)
            
            # Иногда "ошибаемся" и исправляем (реалистичность)
            if random.random() < 0.01 and len(text) > 3:
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))
                await page.keyboard.type(char, delay=wait_time)
        
        await asyncio.sleep(random.uniform(0.2, 0.5))
        return True
    except:
        return False

async def human_press_key(page, key):
    """Нажатие клавиши с задержкой"""
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.keyboard.press(key)
        await asyncio.sleep(random.uniform(0.1, 0.2))
        return True
    except:
        return False

# ============ ЭМУЛЯЦИЯ ПАРСИНГА (ЧЕЛОВЕЧНЫЙ) ============
async def human_get_tweets(page, limit=3):
    """Собирает твиты с имитацией человеческого поведения"""
    try:
        # Ждём как человек
        await asyncio.sleep(random.uniform(1, 2))
        
        # Прокручиваем как человек
        for _ in range(random.randint(1, 3)):
            scroll_amount = random.randint(300, 700)
            await human_scroll(page, scroll_amount)
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Собираем посты
        tweets = await page.evaluate(f"""
            () => {{
                const posts = [];
                const articles = document.querySelectorAll('[data-testid="tweet"], article');
                
                articles.forEach((article, index) => {{
                    if (index >= {limit}) return;
                    
                    try {{
                        const nameEl = article.querySelector('[data-testid="User-Name"]');
                        let name = 'Неизвестно', username = '';
                        if (nameEl) {{
                            const spans = nameEl.querySelectorAll('span');
                            if (spans.length > 0) name = spans[0]?.textContent || 'Неизвестно';
                            if (spans.length > 1) username = spans[1]?.textContent?.replace('@', '') || '';
                        }}
                        
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.textContent : '';
                        
                        const timeEl = article.querySelector('time');
                        const time = timeEl ? timeEl.textContent : '';
                        
                        const linkEl = article.querySelector('a[href*="/status/"]');
                        let link = '';
                        if (linkEl) {{
                            const href = linkEl.getAttribute('href');
                            if (href) link = 'https://x.com' + href;
                        }}
                        
                        if (text || link) {{
                            posts.push({{
                                name: name,
                                username: username,
                                text: text,
                                time: time,
                                link: link
                            }});
                        }}
                    }} catch(e) {{}}
                }});
                
                return posts;
            }}
        """)
        
        return tweets
    except:
        return []

# ============ БРАУЗЕР ============
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
            '--disable-web-security',
        ]
    )
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    
    await context.add_cookies(MY_COOKIES)
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete Object.getPrototypeOf(navigator).webdriver;
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
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
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: { isInstalled: false } };
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
        console.log('✅ Полная эмуляция включена');
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
    return re.sub(r'([_*\[\]()~>#+=|{}.!-])', r'\\\1', text)

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **ЭМУЛЯЦИЯ ЧЕЛОВЕКА**\n\n"
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
    await update.message.reply_text("✅ Браузер готов!")

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("🐦 Открываю X.com...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))
        
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
    
    await update.message.reply_text("📡 Собираю 3 твита (человеческий парсинг)...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))
        
        # Человеческий парсинг
        tweets = await human_get_tweets(page, limit=3)
        
        if tweets and len(tweets) > 0:
            for i, tweet in enumerate(tweets, 1):
                msg = (
                    f"📌 **Твит {i}**\n\n"
                    f"👤 **{escape_markdown(tweet['name'])}**\n"
                    f"🔹 @{escape_markdown(tweet['username'])}\n"
                    f"🕐 {escape_markdown(tweet['time'])}\n\n"
                    f"📝 {escape_markdown(tweet['text'][:500])}{'...' if len(tweet['text']) > 500 else ''}\n\n"
                    f"🔗 {escape_markdown(tweet['link'])}"
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
    
    if "x.com" in url and has_cookie:
        login_status = "✅ Вошли"
    elif "x.com" in url and not has_cookie:
        login_status = "❌ Не вошли"
    else:
        login_status = "⚠️ Не на X.com"
    
    text = (
        f"🌐 URL: {url[:80]}\n"
        f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
        f"📱 X.com: {login_status}"
    )
    
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