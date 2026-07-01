# bot.py - X.com бот
import os
import sys
import subprocess
import logging
import asyncio
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# ========== ПРОВЕРКА PHANTOMWRIGHT ==========
try:
    from phantomwright_driver.async_api import async_playwright
    PHANTOMWRIGHT_AVAILABLE = True
    print("✅ Phantomwright загружен")
except ImportError:
    PHANTOMWRIGHT_AVAILABLE = False
    print("⚠️ Phantomwright не найден, использую Playwright")
    from playwright.async_api import async_playwright

# ========== КУКИ X.COM ==========
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "gt", "value": "2071329406237220892", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": ".I7b6GGmlN4fNcwOMuw9lT0dsT0ARfcIVwJt0bKVn1A-1782678389.549309-1.0.1.1-ZyWyQlXJpxNQRq6_2VYG2dr8Gz2iv_dZ2DrW2mnM.xR8yrtzsdhU310hzPoDkIQZYC6QGWKef5dCUOQQKZdp5_AmnVQS5zZ1p67ydtzPrydFxyV6zl740zd69v0Xs3JC", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"}
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
browser_lock = False
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== УСТАНОВКА БРАУЗЕРА ==========
def get_chromium_path() -> Optional[str]:
    base_dir = PLAYWRIGHT_DIR
    if not os.path.exists(base_dir):
        return None
    for item in os.listdir(base_dir):
        if item.startswith("chromium-") and "headless" not in item:
            chrome_path = os.path.join(base_dir, item, "chrome-linux", "chrome")
            if os.path.exists(chrome_path):
                return chrome_path
    return None

def install_browser():
    if get_chromium_path():
        print("✅ Браузер уже установлен")
        return True
    
    print("⏳ Устанавливаю браузер...")
    
    if PHANTOMWRIGHT_AVAILABLE:
        try:
            subprocess.run([sys.executable, "-m", "phantomwright_driver", "install", "chromium"], check=True)
            print("✅ Браузер установлен через Phantomwright")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка Phantomwright: {e}")
    
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
        print("✅ Браузер установлен через Playwright")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки: {e}")
        return False

install_browser()

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    global browser_data, browser_lock
    
    if browser_data:
        try:
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        
        chromium_path = get_chromium_path()
        if not chromium_path:
            install_browser()
            chromium_path = get_chromium_path()
        
        launch_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,720',
                '--headless=new',
            ]
        }
        if chromium_path:
            launch_args['executable_path'] = chromium_path
        
        browser = await p.chromium.launch(**launch_args)
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
            }
        )
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} }, app: { isInstalled: false } };
            Object.defineProperty(document, 'hidden', { get: () => false });
            Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        """)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page,
            'started_at': datetime.now()
        }
        
        logger.info("✅ Браузер запущен")
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data, login_status
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None
        login_status = {
            'is_logged_in': False,
            'username': None,
            'last_check': None,
            'cookies_valid': False
        }

# ========== ДЕКОРАТОР ДЛЯ ПРОВЕРКИ АВТОРИЗАЦИИ ==========
def require_auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not login_status.get('is_logged_in', False):
            await update.message.reply_text(
                "❌ Вы не авторизованы в X.com!\n\n"
                "Сначала выполните команду:\n"
                "/login — авторизация в X.com\n\n"
                "После успешного входа повторите команду."
            )
            return
        
        if not browser_data:
            await update.message.reply_text(
                "⚠️ Браузер не активен.\n"
                "Выполните /login заново."
            )
            return
        
        try:
            page = browser_data['page']
            await page.evaluate('1')
        except Exception:
            await update.message.reply_text(
                "⚠️ Сессия истекла.\n"
                "Выполните /login заново."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 X.com Бот\n\n"
        "🔐 Авторизация:\n"
        "/login — войти в X.com\n\n"
        "📰 Лента:\n"
        "/feed — показать посты\n"
        "/post N — пост по номеру\n"
        "/top — самый популярный\n"
        "/stats N — статистика поста\n\n"
        "📈 Тренды:\n"
        "/trends — актуальные темы\n\n"
        "👤 Профиль:\n"
        "/me — мой профиль\n\n"
        "🛠️ Система:\n"
        "/status — статус бота\n"
        "/screen — скриншот\n"
        "/close — закрыть браузер"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await browser['context'].clear_cookies()
        await page.goto('about:blank')
        await page.wait_for_timeout(2000)
        
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([{
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': '.x.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False
                }])
            except Exception as e:
                logger.warning(f"Cookie error {cookie['name']}: {e}")
        
        await msg.edit_text("🔄 Загружаю X.com...")
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=30000)
        
        try:
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
        except:
            await page.wait_for_timeout(5000)
        
        await page.wait_for_timeout(3000)
        
        auth_status = await page.evaluate('''
            () => {
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]');
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasHomeLink = !!document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasLoginForm = !!document.querySelector('[data-testid="loginForm"]');
                const hasPrimaryColumn = !!document.querySelector('[data-testid="primaryColumn"]');
                
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                return {
                    hasTweetBtn,
                    hasProfileLink,
                    hasHomeLink,
                    hasSideNav,
                    hasLoginForm,
                    hasPrimaryColumn,
                    hasAuthToken: !!cookies.auth_token,
                    hasCt0: !!cookies.ct0,
                    username: username,
                    isLoggedIn: hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav
                };
            }
        ''')
        
        global login_status
        login_status['is_logged_in'] = auth_status['isLoggedIn']
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status['hasAuthToken'] and auth_status['hasCt0']
        
        status_msg = f"✅ X.com\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status['hasAuthToken'] else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status['hasCt0'] else '❌'}\n\n"
        
        if auth_status['isLoggedIn']:
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username'):
                status_msg += f"👤 @{auth_status['username']}\n"
            if auth_status['hasTweetBtn']:
                status_msg += "   • Кнопка Tweet: ✅\n"
            if auth_status['hasProfileLink']:
                status_msg += "   • Профиль: ✅\n"
            if auth_status['hasHomeLink']:
                status_msg += "   • Домой: ✅\n"
        elif auth_status['hasLoginForm']:
            status_msg += "❌ НЕ АВТОРИЗОВАН (форма входа)\n"
        else:
            status_msg += "⚠️ НЕ ОПРЕДЕЛЕНО\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 X.com - {'✅ Авторизован' if auth_status['isLoggedIn'] else '❌ Не авторизован'}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю ленту...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        posts = await page.evaluate('''
            () => {
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                const result = [];
                
                for (const tweet of tweets.slice(0, 5)) {
                    const nameEl = tweet.querySelector('[data-testid="User-Name"]');
                    const name = nameEl ? nameEl.textContent.trim() : 'Неизвестный';
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const text = textEl ? textEl.textContent.trim().slice(0, 150) : '';
                    
                    const likeBtn = tweet.querySelector('[data-testid="like"]');
                    let likes = '0';
                    if (likeBtn) {
                        const label = likeBtn.getAttribute('aria-label') || '';
                        const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                        likes = match ? match[1] : '0';
                    }
                    
                    const retweetBtn = tweet.querySelector('[data-testid="retweet"]');
                    let retweets = '0';
                    if (retweetBtn) {
                        const label = retweetBtn.getAttribute('aria-label') || '';
                        const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                        retweets = match ? match[1] : '0';
                    }
                    
                    const replyBtn = tweet.querySelector('[data-testid="reply"]');
                    let replies = '0';
                    if (replyBtn) {
                        const label = replyBtn.getAttribute('aria-label') || '';
                        const match = label.match(/(\\d+)/);
                        replies = match ? match[1] : '0';
                    }
                    
                    const timeEl = tweet.querySelector('time');
                    const time = timeEl ? timeEl.textContent.trim() : '';
                    
                    if (text || name) {
                        result.push({
                            name: name,
                            text: text || '[Медиа]',
                            likes: likes,
                            retweets: retweets,
                            replies: replies,
                            time: time
                        });
                    }
                }
                
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("📭 В ленте нет постов или не удалось загрузить.")
            return
        
        response = "📰 Лента\n\n"
        for i, post in enumerate(posts, 1):
            response += f"{i}. @{post['name']}"
            if post['time']:
                response += f" · {post['time']}"
            response += "\n"
            response += f"📝 {post['text']}\n"
            response += f"❤️ {post['likes']} | 🔄 {post['retweets']} | 💬 {post['replies']}\n"
            response += "────────────────────\n"
        
        response += f"\n📊 Всего постов: {len(posts)}"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Feed error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📌 Использование: /post [номер]")
        return
    
    try:
        num = int(context.args[0]) - 1
        if num < 0:
            await update.message.reply_text("❌ Номер должен быть больше 0")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число: /post 3")
        return
    
    msg = await update.message.reply_text(f"⏳ Загружаю пост #{num+1}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        post_data = await page.evaluate(f'''
            () => {{
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                const tweet = tweets[{num}];
                if (!tweet) return null;
                
                const nameEl = tweet.querySelector('[data-testid="User-Name"]');
                const name = nameEl ? nameEl.textContent.trim() : 'Неизвестный';
                
                const textEl = tweet.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent.trim() : '[Медиа]';
                
                const likeBtn = tweet.querySelector('[data-testid="like"]');
                let likes = '0';
                if (likeBtn) {{
                    const label = likeBtn.getAttribute('aria-label') || '';
                    const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                    likes = match ? match[1] : '0';
                }}
                
                const retweetBtn = tweet.querySelector('[data-testid="retweet"]');
                let retweets = '0';
                if (retweetBtn) {{
                    const label = retweetBtn.getAttribute('aria-label') || '';
                    const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                    retweets = match ? match[1] : '0';
                }}
                
                const replyBtn = tweet.querySelector('[data-testid="reply"]');
                let replies = '0';
                if (replyBtn) {{
                    const label = replyBtn.getAttribute('aria-label') || '';
                    const match = label.match(/(\\d+)/);
                    replies = match ? match[1] : '0';
                }}
                
                const timeEl = tweet.querySelector('time');
                const time = timeEl ? timeEl.textContent.trim() : '';
                
                const hasPhoto = !!tweet.querySelector('[data-testid="tweetPhoto"] img');
                
                return {{
                    name, text, likes, retweets, replies, time, hasPhoto
                }};
            }}
        ''')
        
        if not post_data:
            await msg.edit_text(f"❌ Пост #{num+1} не найден")
            return
        
        response = f"📄 Пост #{num+1}\n\n"
        response += f"👤 @{post_data['name']}"
        if post_data['time']:
            response += f" · {post_data['time']}"
        response += "\n\n"
        response += f"📝 {post_data['text']}\n\n"
        response += f"❤️ {post_data['likes']} | 🔄 {post_data['retweets']} | 💬 {post_data['replies']}"
        if post_data['hasPhoto']:
            response += " | 🖼️ Есть фото"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Post error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю тренды...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com/explore', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        trends_data = await page.evaluate('''
            () => {
                const trends = document.querySelectorAll('[data-testid="trend"]');
                const result = [];
                
                for (const trend of trends.slice(0, 10)) {
                    const textEl = trend.querySelector('[data-testid="trend"] div:last-child > div:last-child');
                    const text = textEl ? textEl.textContent.trim() : '';
                    
                    const categoryEl = trend.querySelector('[data-testid="trend"] div:first-child');
                    const category = categoryEl ? categoryEl.textContent.trim() : '';
                    
                    const descEl = trend.querySelector('[data-testid="trend"] div:nth-child(3)');
                    const desc = descEl ? descEl.textContent.trim() : '';
                    
                    if (text) {
                        result.push({ text, category, desc });
                    }
                }
                
                return result;
            }
        ''')
        
        if not trends_data:
            await msg.edit_text("📭 Тренды не найдены")
            return
        
        response = "📈 Актуальные тренды\n\n"
        
        for i, trend in enumerate(trends_data[:7], 1):
            response += f"{i}. {trend['text']}\n"
            if trend['category']:
                response += f"   📌 {trend['category']}\n"
            if trend['desc']:
                response += f"   📝 {trend['desc']}\n"
            response += "\n"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Trends error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю профиль...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        profile_data = await page.evaluate('''
            () => {
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                let username = null;
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                const nameEl = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"] .css-146c3p1');
                let name = null;
                if (nameEl) {
                    const span = nameEl.querySelector('span');
                    if (span) name = span.textContent.trim();
                }
                
                return { username, name };
            }
        ''')
        
        response = "👤 Мой профиль\n\n"
        response += f"📛 Имя: {profile_data.get('name') or login_status.get('username', 'Неизвестно')}\n"
        response += f"🔗 Username: @{profile_data.get('username') or login_status.get('username') or 'неизвестно'}\n"
        response += f"\n📊 Статус: ✅ Авторизован"
        response += f"\n🍪 Куки: ✅ OK"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Me error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📌 Использование: /stats [номер]")
        return
    
    try:
        num = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ Введите число: /stats 3")
        return
    
    msg = await update.message.reply_text(f"⏳ Загружаю статистику поста #{num+1}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        stats_data = await page.evaluate(f'''
            () => {{
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                const tweet = tweets[{num}];
                if (!tweet) return null;
                
                const nameEl = tweet.querySelector('[data-testid="User-Name"]');
                const name = nameEl ? nameEl.textContent.trim() : 'Неизвестный';
                
                const textEl = tweet.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent.trim().slice(0, 100) : '';
                
                const likeBtn = tweet.querySelector('[data-testid="like"]');
                let likes = '0';
                if (likeBtn) {{
                    const label = likeBtn.getAttribute('aria-label') || '';
                    const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                    likes = match ? match[1] : '0';
                }}
                
                const retweetBtn = tweet.querySelector('[data-testid="retweet"]');
                let retweets = '0';
                if (retweetBtn) {{
                    const label = retweetBtn.getAttribute('aria-label') || '';
                    const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                    retweets = match ? match[1] : '0';
                }}
                
                const replyBtn = tweet.querySelector('[data-testid="reply"]');
                let replies = '0';
                if (replyBtn) {{
                    const label = replyBtn.getAttribute('aria-label') || '';
                    const match = label.match(/(\\d+)/);
                    replies = match ? match[1] : '0';
                }}
                
                const timeEl = tweet.querySelector('time');
                const time = timeEl ? timeEl.textContent.trim() : '';
                
                let views = 'Нет данных';
                const viewEl = tweet.querySelector('a[aria-label*="просмотр"]');
                if (viewEl) {{
                    const label = viewEl.getAttribute('aria-label') || '';
                    const match = label.match(/([\\d.]+\\s*тыс\.?|\\d+)/);
                    views = match ? match[1] : 'Нет данных';
                }}
                
                return {{ name, text, likes, retweets, replies, time, views }};
            }}
        ''')
        
        if not stats_data:
            await msg.edit_text(f"❌ Пост #{num+1} не найден")
            return
        
        response = f"📊 Статистика поста #{num+1}\n\n"
        response += f"👤 @{stats_data['name']}"
        if stats_data['time']:
            response += f" · {stats_data['time']}"
        response += "\n\n"
        response += f"📝 {stats_data['text']}...\n\n" if len(stats_data['text']) > 50 else f"📝 {stats_data['text']}\n\n"
        response += f"💬 Ответы: {stats_data['replies']}\n"
        response += f"🔄 Репосты: {stats_data['retweets']}\n"
        response += f"❤️ Лайки: {stats_data['likes']}\n"
        response += f"👁️ Просмотры: {stats_data['views']}"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

@require_auth
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Ищу самый популярный пост...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        top_post = await page.evaluate('''
            () => {
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                let best = null;
                let maxLikes = -1;
                
                for (const tweet of tweets) {
                    const likeBtn = tweet.querySelector('[data-testid="like"]');
                    let likes = 0;
                    if (likeBtn) {
                        const label = likeBtn.getAttribute('aria-label') || '';
                        const match = label.match(/(\\d+)/);
                        if (match) likes = parseInt(match[1]);
                    }
                    
                    if (likes > maxLikes) {
                        maxLikes = likes;
                        
                        const nameEl = tweet.querySelector('[data-testid="User-Name"]');
                        const name = nameEl ? nameEl.textContent.trim() : 'Неизвестный';
                        
                        const textEl = tweet.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.textContent.trim() : '[Медиа]';
                        
                        const retweetBtn = tweet.querySelector('[data-testid="retweet"]');
                        let retweets = '0';
                        if (retweetBtn) {
                            const label = retweetBtn.getAttribute('aria-label') || '';
                            const match = label.match(/(\\d+)/);
                            retweets = match ? match[1] : '0';
                        }
                        
                        const replyBtn = tweet.querySelector('[data-testid="reply"]');
                        let replies = '0';
                        if (replyBtn) {
                            const label = replyBtn.getAttribute('aria-label') || '';
                            const match = label.match(/(\\d+)/);
                            replies = match ? match[1] : '0';
                        }
                        
                        const timeEl = tweet.querySelector('time');
                        const time = timeEl ? timeEl.textContent.trim() : '';
                        
                        best = { name, text, likes, retweets, replies, time };
                    }
                }
                
                return best;
            }
        ''')
        
        if not top_post:
            await msg.edit_text("❌ Не удалось найти популярный пост")
            return
        
        response = "🏆 Самый популярный пост\n\n"
        response += f"👤 @{top_post['name']}"
        if top_post['time']:
            response += f" · {top_post['time']}"
        response += "\n\n"
        response += f"📝 {top_post['text']}\n\n"
        response += f"❤️ {top_post['likes']} лайков\n"
        response += f"🔄 {top_post['retweets']} репостов\n"
        response += f"💬 {top_post['replies']} ответов"
        
        await msg.edit_text(response)
        
    except Exception as e:
        logger.error(f"Top error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        browser_ok = False
        browser_info = {}
        
        if browser_data:
            try:
                page = browser_data['page']
                await page.evaluate('1')
                browser_ok = True
                
                url = page.url
                title = await page.title()
                started_at = browser_data.get('started_at')
                uptime = (datetime.now() - started_at).total_seconds() if started_at else 0
                
                auth_check = await page.evaluate('''
                    () => {
                        const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]');
                        const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                        const hasHomeLink = !!document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                        const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                        const hasLoginForm = !!document.querySelector('[data-testid="loginForm"]');
                        
                        const cookies = document.cookie.split(';').reduce((acc, c) => {
                            const [key, val] = c.trim().split('=');
                            acc[key] = val;
                            return acc;
                        }, {});
                        
                        let username = null;
                        const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                        if (profileLink) {
                            const href = profileLink.getAttribute('href');
                            if (href) {
                                const match = href.match(/^\\/([^\\/]+)/);
                                if (match) username = match[1];
                            }
                        }
                        
                        return {
                            hasTweetBtn,
                            hasProfileLink,
                            hasHomeLink,
                            hasSideNav,
                            hasLoginForm,
                            hasAuthToken: !!cookies.auth_token,
                            hasCt0: !!cookies.ct0,
                            username: username,
                            isLoggedIn: hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav
                        };
                    }
                ''')
                
                browser_info = {
                    'url': url,
                    'title': title[:60] if title else 'Нет',
                    'uptime': uptime,
                    'auth': auth_check
                }
                
                login_status['is_logged_in'] = auth_check['isLoggedIn']
                login_status['username'] = auth_check.get('username')
                login_status['last_check'] = datetime.now()
                login_status['cookies_valid'] = auth_check['hasAuthToken'] and auth_check['hasCt0']
                
            except Exception as e:
                browser_ok = False
                browser_info['error'] = str(e)[:50]
        else:
            browser_info = {'error': 'Браузер не запущен'}
        
        status_msg = "📊 СТАТУС БОТА\n\n"
        
        if browser_ok:
            status_msg += "🌐 Браузер: ✅ Запущен\n"
            if browser_info.get('uptime'):
                hours = int(browser_info['uptime'] // 3600)
                minutes = int((browser_info['uptime'] % 3600) // 60)
                status_msg += f"⏱️ Аптайм: {hours}ч {minutes}м\n"
        else:
            status_msg += "🌐 Браузер: ❌ Не запущен\n"
        
        if browser_ok and browser_info.get('url'):
            status_msg += f"🔗 URL: {browser_info['url'][:60]}\n"
            status_msg += f"📌 Заголовок: {browser_info.get('title', 'Нет')}\n"
        
        status_msg += "\n🔐 АВТОРИЗАЦИЯ:\n"
        
        if browser_ok and browser_info.get('auth'):
            auth = browser_info['auth']
            
            status_msg += f"🍪 auth_token: {'✅' if auth.get('hasAuthToken') else '❌'}\n"
            status_msg += f"🍪 ct0: {'✅' if auth.get('hasCt0') else '❌'}\n"
            
            if auth.get('isLoggedIn'):
                status_msg += "\n✅ ВЫ АВТОРИЗОВАНЫ\n"
                if auth.get('username'):
                    status_msg += f"👤 @{auth['username']}\n"
                if auth.get('hasTweetBtn'):
                    status_msg += "   • Кнопка Tweet: ✅\n"
                if auth.get('hasProfileLink'):
                    status_msg += "   • Профиль: ✅\n"
                if auth.get('hasHomeLink'):
                    status_msg += "   • Домой: ✅\n"
            elif auth.get('hasLoginForm'):
                status_msg += "\n❌ НЕ АВТОРИЗОВАН (форма входа)\n"
            else:
                status_msg += "\n⚠️ НЕ ОПРЕДЕЛЕНО\n"
        else:
            status_msg += "❌ Нет данных (выполните /login)\n"
        
        status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        status_msg += f"📦 Драйвер: {'Phantomwright' if PHANTOMWRIGHT_AVAILABLE else 'Playwright'}\n"
        status_msg += f"🍪 Куки загружены: {len(COOKIES)} шт."
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.delete()
        
        url = page.url
        title = await page.title()
        
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 {title[:40] if title else 'X.com'}\n🔗 {url[:50]}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("feed", feed))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("me", me))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("close", close))
    
    print("🐦 X.com Bot запущен!")
    print("📌 Команды:")
    print("   🔐 /login — авторизация")
    print("   📰 /feed — лента")
    print("   📄 /post N — пост по номеру")
    print("   📈 /trends — тренды")
    print("   👤 /me — мой профиль")
    print("   📊 /stats N — статистика поста")
    print("   🏆 /top — лучший пост")
    print("   📸 /screen — скриншот")
    print("   📊 /status — статус")
    print("   ❌ /close — закрыть браузер")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()