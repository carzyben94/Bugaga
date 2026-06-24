import os
import logging
import threading
import asyncio
import random
import re
import time
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

# ============ ЭМУЛЯЦИЯ ЧЕЛОВЕКА ============

def random_delay(min_sec=0.3, max_sec=1.5):
    """Случайная задержка как у человека"""
    return random.uniform(min_sec, max_sec)

async def human_sleep(min_sec=0.3, max_sec=1.5):
    """Сон с случайной задержкой"""
    await asyncio.sleep(random_delay(min_sec, max_sec))

async def human_move(page, x, y, steps=12):
    """Плавное движение мыши с кривой Безье"""
    try:
        current = await page.evaluate("""
            () => ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        
        # Добавляем случайное дрожание
        for i in range(steps):
            progress = (i + 1) / steps
            ease = 1 - (1 - progress) ** 3
            noise_x = random.randint(-3, 3)
            noise_y = random.randint(-3, 3)
            target_x = current["x"] + (x - current["x"]) * ease + noise_x
            target_y = current["y"] + (y - current["y"]) * ease + noise_y
            await page.mouse.move(target_x, target_y)
            await asyncio.sleep(random.uniform(0.02, 0.08))
        
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        return True
    except:
        return False

async def human_click(page, x, y, button="left"):
    """Реалистичный клик с задержками"""
    try:
        await human_move(page, x, y, steps=10)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.down(button=button)
        await asyncio.sleep(random.uniform(0.03, 0.12))
        await page.mouse.up(button=button)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return True
    except:
        return False

async def human_scroll(page, amount, steps=4):
    """Плавная прокрутка с ускорением"""
    try:
        for i in range(steps):
            progress = (i + 1) / steps
            eased = 1 - (1 - progress) ** 2
            scroll_amount = int(amount * eased * 0.6 + random.randint(-10, 10))
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.1, 0.4))
        return True
    except:
        return False

async def human_type(page, text, delay=40):
    """Ввод текста с задержками как у человека"""
    try:
        # Клик для фокуса
        await page.mouse.click(100, 100)
        await asyncio.sleep(0.2)
        
        for char in text:
            wait_time = delay + random.randint(-10, 25)
            if char.isupper() or char in '!@#$%^&*()_+':
                wait_time += random.randint(15, 40)
            await page.keyboard.type(char, delay=wait_time)
            
            # Иногда "ошибаемся" (реалистичность)
            if random.random() < 0.005 and len(text) > 3:
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))
                await page.keyboard.type(char, delay=wait_time)
        
        await asyncio.sleep(random.uniform(0.2, 0.6))
        return True
    except:
        return False

async def human_wait_for_page(page, min_wait=2, max_wait=5):
    """Ждём как человек — смотрим на страницу"""
    await asyncio.sleep(random.uniform(min_wait, max_wait))
    
    # Иногда делаем случайное движение мыши
    if random.random() < 0.3:
        viewport = page.viewport_size
        await page.mouse.move(
            random.randint(100, viewport['width'] - 100),
            random.randint(100, viewport['height'] - 100)
        )
        await asyncio.sleep(random.uniform(0.1, 0.3))

# ============ ПАРСИНГ С ЭМУЛЯЦИЕЙ ============
async def human_get_tweets(page, limit=3):
    """Собирает твиты с полной эмуляцией человека"""
    try:
        # Ждём как человек
        await human_wait_for_page(page, 1.5, 3)
        
        # Прокручиваем как человек
        for _ in range(random.randint(2, 4)):
            scroll_amount = random.randint(300, 700)
            await human_scroll(page, scroll_amount)
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Случайная пауза перед сбором
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # Собираем посты
        tweets = await page.evaluate(f"""
            () => {{
                const posts = [];
                const selectors = [
                    '[data-testid="tweet"]',
                    'article[data-testid="tweet"]',
                    'article',
                    '[role="article"]',
                    '[data-testid="cellInnerDiv"]',
                    'div[data-testid="tweet"]'
                ];
                
                let articles = [];
                for (const selector of selectors) {{
                    const found = document.querySelectorAll(selector);
                    if (found.length > 0) {{
                        articles = found;
                        break;
                    }}
                }}
                
                if (articles.length === 0) {{
                    articles = document.querySelectorAll('div[lang]');
                }}
                
                articles.forEach((article, index) => {{
                    if (index >= {limit}) return;
                    
                    try {{
                        // Имя
                        let name = 'Неизвестно';
                        const nameEls = article.querySelectorAll('[data-testid="User-Name"] span, [dir="ltr"] span');
                        for (const el of nameEls) {{
                            const text = el.textContent?.trim() || '';
                            if (text && text.length > 0 && !text.includes('·') && !text.startsWith('@')) {{
                                name = text;
                                break;
                            }}
                        }}
                        
                        // Username
                        let username = '';
                        const userEls = article.querySelectorAll('[data-testid="User-Name"] span:last-child, [dir="ltr"] span:last-child');
                        for (const el of userEls) {{
                            const text = el.textContent?.trim() || '';
                            if (text && text.startsWith('@')) {{
                                username = text.replace('@', '');
                                break;
                            }}
                        }}
                        
                        // Текст
                        let text = '';
                        const textEls = article.querySelectorAll('[data-testid="tweetText"], [data-testid="tweetText"] span, div[lang]');
                        for (const el of textEls) {{
                            const t = el.textContent?.trim() || '';
                            if (t && t.length > 0) {{
                                text = t;
                                break;
                            }}
                        }}
                        
                        // Время
                        let time = '';
                        const timeEl = article.querySelector('time');
                        if (timeEl) time = timeEl.textContent?.trim() || '';
                        
                        // Ссылка
                        let link = '';
                        const linkEl = article.querySelector('a[href*="/status/"]');
                        if (linkEl) link = linkEl.href || '';
                        
                        if (text || link) {{
                            posts.push({{
                                name: name || 'Неизвестно',
                                username: username || '',
                                text: text || '',
                                time: time || '',
                                link: link || ''
                            }});
                        }}
                    }} catch(e) {{
                        // Пропускаем
                    }}
                }});
                
                return posts;
            }}
        """)
        
        return tweets[:limit]
    except Exception as e:
        print(f"Ошибка сбора: {e}")
        return []

async def take_screenshot(page) -> bytes:
    try:
        return await page.screenshot(type="png")
    except:
        return b""

def escape_markdown(text):
    if not text:
        return ''
    return re.sub(r'([_*\[\]()~>#+=|{}.!-])', r'\\\1', text)

# ============ БРАУЗЕР (МАКСИМАЛЬНАЯ ЭМУЛЯЦИЯ) ============
async def get_browser():
    playwright = await async_playwright().start()
    
    # Случайные параметры как у реального пользователя
    viewport_width = random.choice([1366, 1440, 1536, 1600, 1920])
    viewport_height = random.choice([768, 900, 960, 1080])
    
    # Случайный User-Agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    # Случайный часовой пояс
    timezones = ["Europe/Moscow", "Europe/London", "America/New_York", "Asia/Tokyo", "Europe/Berlin"]
    
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
            '--disable-features=OutOfBlinkCors',
            '--disable-features=SharedArrayBuffer',
            '--disable-features=CrossOriginIsolation',
        ]
    )
    
    context = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height},
        user_agent=random.choice(user_agents),
        locale="ru-RU",
        timezone_id=random.choice(timezones),
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        color_scheme="light",
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
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-full-version": '"120.0.6099.109"',
            "sec-ch-ua-platform-version": '"10.0.0"',
            "sec-ch-ua-model": '""',
            "sec-ch-ua-bitness": '"64"',
            "DNT": "1",
        }
    )
    
    # Добавляем реалистичные куки
    await context.add_cookies([
        {"name": "_ga", "value": f"GA1.2.{random.randint(100000, 999999)}.{int(time.time())}", "domain": ".x.com", "path": "/"},
        {"name": "_gid", "value": f"GA1.2.{random.randint(100000, 999999)}.{int(time.time())}", "domain": ".x.com", "path": "/"},
        {"name": "personalization_id", "value": f"v1_{random.randint(1000000000, 9999999999)}", "domain": ".x.com", "path": "/"},
    ])
    
    await context.add_cookies(MY_COOKIES)
    
    page = await context.new_page()
    
    # ============ МАКСИМАЛЬНАЯ МАСКИРОВКА ============
    await page.add_init_script("""
        // Полное удаление webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete Object.getPrototypeOf(navigator).webdriver;
        
        // Полная эмуляция плагинов
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
        
        // Эмуляция mimeTypes
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => {
                const mimes = [
                    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                    { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' }
                ];
                mimes.length = 2;
                mimes.item = (i) => mimes[i] || null;
                mimes.namedItem = (type) => mimes.find(m => m.type === type) || null;
                return mimes;
            }
        });
        
        // Языки
        Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'language', { get: () => 'ru-RU' });
        
        // Платформа
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        
        // Железо
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        // Экран
        Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
        Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
        Object.defineProperty(screen, 'width', { get: () => 1920 });
        Object.defineProperty(screen, 'height', { get: () => 1080 });
        Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
        
        // Chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {
                return {
                    navigationType: 'Other',
                    wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false,
                    connectionInfo: 'http/1.1'
                };
            },
            csi: function() {
                return {
                    startE: 0,
                    onloadT: 0,
                    pageT: 0
                };
            },
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
        
        // WebGL
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter(parameter);
        };
        
        // Canvas
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png') {
                return originalToDataURL.apply(this, arguments);
            }
            return originalToDataURL.apply(this, arguments);
        };
        
        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Добавляем случайные шумы для fingerprint
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: ['4g', '4g', '3g', '3g', '2g'][Math.floor(Math.random() * 3)],
                rtt: Math.floor(Math.random() * 100) + 50,
                downlink: Math.floor(Math.random() * 10) + 1
            })
        });
        
        console.log('✅ Максимальная эмуляция включена');
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

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **МАКСИМАЛЬНАЯ ЭМУЛЯЦИЯ**\n\n"
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
    await update.message.reply_text("🌐 Открываю браузер с максимальной эмуляцией...")
    await get_user_browser(user_id)
    await update.message.reply_text("✅ Браузер готов! Полная эмуляция человека включена.")

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("🐦 Открываю X.com...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await human_wait_for_page(page, 2, 4)
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
    
    try:
        screenshot = await take_screenshot(page)
        if screenshot and len(screenshot) > 1000:
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 Скриншот")
        else:
            await update.message.reply_text("❌ Не удалось")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("📡 Собираю 3 твита (человеческий парсинг)...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await human_wait_for_page(page, 2, 4)
        
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