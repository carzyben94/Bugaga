# bot.py - X.com бот с Pydoll + Playwright
import os
import sys
import subprocess
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Union
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

# ========== ПРОВЕРКА БИБЛИОТЕК ==========
PYDOLL_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
BROWSER_USE_AVAILABLE = False
AGNES_AVAILABLE = False

def check_libraries():
    """Проверка всех библиотек"""
    global PYDOLL_AVAILABLE, PLAYWRIGHT_AVAILABLE
    
    # Проверка Pydoll
    try:
        import pydoll
        PYDOLL_AVAILABLE = True
        print("✅ Pydoll загружен")
    except ImportError:
        PYDOLL_AVAILABLE = False
        print("⚠️ Pydoll не найден")
    
    # Проверка Playwright
    try:
        from playwright.async_api import async_playwright
        PLAYWRIGHT_AVAILABLE = True
        print("✅ Playwright загружен")
    except ImportError:
        PLAYWRIGHT_AVAILABLE = False
        print("⚠️ Playwright не найден")

check_libraries()

# ========== AGNES (БЕСПЛАТНАЯ LLM) ==========
agnes_llm = None

def init_agnes():
    """Инициализация Agnes через прямой API"""
    global AGNES_AVAILABLE, agnes_llm
    try:
        from langchain_openai import ChatOpenAI
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=os.environ.get("AGNES_API_KEY", ""),
        )
        
        # Проверяем, работает ли
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes загружена")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
        return False

init_agnes()

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
pydoll_browser = None
pydoll_tab = None
browser_lock = False
use_pydoll = False  # По умолчанию Playwright
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== PYDOLL БРАУЗЕР ==========
async def get_pydoll_browser():
    """Получает Pydoll браузер с человеческим поведением"""
    global pydoll_browser, pydoll_tab
    
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.evaluate('1')
            return pydoll_tab
        except:
            await close_pydoll_browser()
    
    try:
        from pydoll.browser import Chrome
        
        # Важные флаги для Railway/контейнеров
        pydoll_browser = await Chrome(
            headless=True,
            options=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1280,720',
                '--headless=new',
            ]
        ).start()
        
        pydoll_tab = await pydoll_browser.get_current_tab()
        
        # Устанавливаем куки
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
            except Exception as e:
                logger.warning(f"Pydoll cookie error {cookie['name']}: {e}")
        
        logger.info("✅ Pydoll браузер запущен")
        return pydoll_tab
    except Exception as e:
        logger.error(f"Pydoll ошибка: {e}")
        return None

async def close_pydoll_browser():
    global pydoll_browser, pydoll_tab
    if pydoll_browser:
        try:
            await pydoll_browser.stop()
        except:
            pass
        pydoll_browser = None
        pydoll_tab = None

# ========== PLAYWRIGHT БРАУЗЕР ==========
async def get_playwright_browser():
    """Получает Playwright браузер"""
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
        from playwright.async_api import async_playwright
        
        p = await async_playwright().start()
        
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,720',
                '--headless=new',
            ]
        )
        
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
            window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} } };
        """)
        
        for cookie in COOKIES:
            try:
                await context.add_cookies([{
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': '.x.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False
                }])
            except Exception as e:
                logger.warning(f"Cookie error {cookie['name']}: {e}")
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page,
            'started_at': datetime.now()
        }
        
        logger.info("✅ Playwright браузер запущен")
        return browser_data
    finally:
        browser_lock = False

async def close_playwright_browser():
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

# ========== УНИВЕРСАЛЬНЫЙ БРАУЗЕР С FALLBACK ==========
async def get_browser():
    """Универсальное получение браузера с автоматическим fallback"""
    global use_pydoll
    
    if use_pydoll and PYDOLL_AVAILABLE:
        try:
            # Пробуем Pydoll
            browser = await get_pydoll_browser()
            if browser:
                logger.info("✅ Использую Pydoll")
                return browser
        except Exception as e:
            logger.error(f"❌ Pydoll failed: {e}, falling back to Playwright")
            use_pydoll = False
            await close_pydoll_browser()
    
    # Fallback на Playwright
    logger.info("🔄 Использую Playwright")
    browser_data = await get_playwright_browser()
    return browser_data['page'] if browser_data else None

async def close_browser():
    """Универсальное закрытие браузера"""
    if use_pydoll:
        await close_pydoll_browser()
    else:
        await close_playwright_browser()

async def get_page():
    """Универсальное получение страницы"""
    return await get_browser()

async def take_screenshot():
    """Универсальный скриншот"""
    if use_pydoll and PYDOLL_AVAILABLE:
        try:
            page = await get_pydoll_browser()
            if page:
                return await page.screenshot()
        except:
            pass
    
    # Fallback на Playwright
    browser = await get_playwright_browser()
    if browser:
        page = browser['page']
        return await page.screenshot(type='jpeg', quality=80)
    return None

async def goto_url(url):
    """Универсальный переход по URL"""
    if use_pydoll and PYDOLL_AVAILABLE:
        try:
            page = await get_pydoll_browser()
            if page:
                await page.go_to(url)
                return
        except:
            pass
    
    # Fallback на Playwright
    browser = await get_playwright_browser()
    if browser:
        page = browser['page']
        await page.goto(url, wait_until='domcontentloaded')

async def evaluate_js(script):
    """Универсальное выполнение JS"""
    if use_pydoll and PYDOLL_AVAILABLE:
        try:
            page = await get_pydoll_browser()
            if page:
                return await page.evaluate(script)
        except:
            pass
    
    # Fallback на Playwright
    browser = await get_playwright_browser()
    if browser:
        page = browser['page']
        return await page.evaluate(script)
    return None

async def wait_for_selector(selector, timeout=15000):
    """Универсальное ожидание элемента"""
    if use_pydoll and PYDOLL_AVAILABLE:
        try:
            page = await get_pydoll_browser()
            if page:
                await page.wait_for_element(selector, timeout=timeout/1000)
                return
        except:
            pass
    
    # Fallback на Playwright
    browser = await get_playwright_browser()
    if browser:
        page = browser['page']
        await page.wait_for_selector(selector, timeout=timeout)

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🎮 Движок: {'Pydoll' if use_pydoll else 'Playwright'}\n"
        f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n\n"
        f"📌 Команды:\n"
        f"/login - Авторизация в X.com\n"
        f"/screen - Скриншот\n"
        f"/status - Статус браузера\n"
        f"/engine - Переключить движок\n"
        f"/close - Закрыть браузер\n"
        f"/tweets <username> - Твиты пользователя\n"
        f"/search <запрос> - Поиск твитов\n"
        f"/browse <задача> - AI задача в браузере\n"
        f"/agnes - Статус Agnes",
        parse_mode='Markdown'
    )

async def engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение между движками браузера"""
    global use_pydoll
    
    if not context.args:
        current = "Pydoll" if use_pydoll else "Playwright"
        status = ""
        if use_pydoll and not PYDOLL_AVAILABLE:
            status = " (⚠️ Pydoll не установлен!)"
        
        await update.message.reply_text(
            f"🔧 Текущий движок: **{current}**{status}\n\n"
            f"Доступные движки:\n"
            f"  /engine playwright - Playwright (стабильный)\n"
            f"  /engine pydoll - Pydoll (человеческое поведение)\n\n"
            f"ℹ️ Pydoll лучше для обхода антибот-систем"
        )
        return
    
    engine_type = context.args[0].lower()
    
    if engine_type == "pydoll":
        if not PYDOLL_AVAILABLE:
            await update.message.reply_text(
                "❌ Pydoll не установлен!\n\n"
                "Установите вручную: pip install pydoll-python\n"
                "Или перезапустите бота"
            )
            return
        
        await close_browser()
        use_pydoll = True
        await update.message.reply_text(
            "✅ Переключено на **Pydoll**\n"
            "Теперь браузер будет с человеческим поведением!"
        )
        
    elif engine_type == "playwright":
        await close_browser()
        use_pydoll = False
        await update.message.reply_text(
            "✅ Переключено на **Playwright**"
        )
    else:
        await update.message.reply_text(
            f"❌ Неизвестный движок: {engine_type}\n"
            f"Доступно: playwright, pydoll"
        )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        await goto_url('https://x.com')
        await asyncio.sleep(3)
        
        # Проверка авторизации
        auth_status = await evaluate_js('''
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
        elif auth_status['hasLoginForm']:
            status_msg += "❌ НЕ АВТОРИЗОВАН (форма входа)\n"
        else:
            status_msg += "⚠️ НЕ ОПРЕДЕЛЕНО\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if auth_status['isLoggedIn'] else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Скриншот X.com\n🎮 Движок: {'Pydoll' if use_pydoll else 'Playwright'}"
            )
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        status_msg = "📊 **СТАТУС БОТА**\n\n"
        
        # Движки
        status_msg += f"🎮 Текущий движок: **{'Pydoll' if use_pydoll else 'Playwright'}**\n"
        status_msg += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        status_msg += f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        status_msg += f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n\n"
        
        # Статус браузера
        try:
            if use_pydoll and PYDOLL_AVAILABLE:
                page = await get_pydoll_browser()
                if page:
                    status_msg += "🌐 Браузер: ✅ Запущен (Pydoll)\n"
                    try:
                        url = await page.evaluate('window.location.href')
                        status_msg += f"🔗 URL: {url[:50]}\n"
                    except:
                        pass
            else:
                browser = await get_playwright_browser()
                if browser:
                    status_msg += "🌐 Браузер: ✅ Запущен (Playwright)\n"
                    page = browser['page']
                    url = page.url
                    status_msg += f"🔗 URL: {url[:50]}\n"
        except:
            status_msg += "🌐 Браузер: ❌ Не запущен\n"
        
        # Авторизация
        status_msg += "\n🔐 **АВТОРИЗАЦИЯ:**\n"
        if login_status['is_logged_in']:
            status_msg += f"✅ Авторизован\n"
            if login_status['username']:
                status_msg += f"👤 @{login_status['username']}\n"
        else:
            status_msg += "❌ Не авторизован\n"
        
        status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await msg.edit_text(status_msg, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг твитов пользователя"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /tweets <username> [count]\n"
            "Пример: /tweets elonmusk 10"
        )
        return
    
    username = context.args[0].replace('@', '').strip()
    count = int(context.args[1]) if len(context.args) > 1 else 10
    msg = await update.message.reply_text(f"📊 Парсю твиты @{username}...")
    
    try:
        await goto_url(f"https://x.com/{username}")
        await asyncio.sleep(3)
        
        await wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        tweets_data = await evaluate_js(f'''
            () => {{
                const tweets = [];
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                const count = {count};
                
                tweetElements.forEach((tweet, index) => {{
                    if (index >= count) return;
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const timeEl = tweet.querySelector('time');
                    const isPinned = !!tweet.querySelector('[data-testid="pinIcon"]');
                    
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/\\s{{2,}}/g, ' ');
                    text = text.trim();
                    
                    tweets.push({{
                        text: text,
                        time: timeEl ? timeEl.getAttribute('datetime') : '',
                        is_pinned: isPinned
                    }});
                }});
                
                return tweets;
            }}
        ''')
        
        if not tweets_data:
            await msg.edit_text(f"❌ Твиты @{username} не найдены!")
            return
        
        report = f"📊 **ТВИТЫ @{username}**\n"
        report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        report += f"📌 Всего: {len(tweets_data)}\n\n"
        
        for i, tweet in enumerate(tweets_data, 1):
            if tweet['is_pinned']:
                report += f"📌 **{i}. ЗАКРЕПЛЕН**\n"
            else:
                report += f"**{i}.** "
            
            text = tweet['text'][:250]
            if len(tweet['text']) > 250:
                text += "..."
            report += f"{text}\n"
            
            if tweet['time']:
                time_str = tweet['time'][:16].replace('T', ' ')
                report += f"\n🕐 {time_str}"
            
            report += "\n\n"
        
        if len(report) > 4000:
            filename = f"tweets_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 {len(tweets_data)} твитов @{username}"
            )
        else:
            await msg.edit_text(report, parse_mode='Markdown')
        
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Твиты @{username}"
            )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in tweets: {e}", exc_info=True)

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск твитов"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /search <запрос>\n"
            "Пример: /search биткоин"
        )
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query"
        await goto_url(search_url)
        await asyncio.sleep(3)
        
        await wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        tweets_data = await evaluate_js('''
            () => {
                const tweets = [];
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                
                tweetElements.forEach((tweet, index) => {
                    if (index >= 10) return;
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const timeEl = tweet.querySelector('time');
                    
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/\\s{2,}/g, ' ');
                    text = text.trim();
                    
                    tweets.push({
                        text: text,
                        time: timeEl ? timeEl.getAttribute('datetime') : ''
                    });
                });
                
                return tweets;
            }
        ''')
        
        if not tweets_data:
            await msg.edit_text(f"❌ По запросу '{query}' ничего не найдено!")
            return
        
        report = f"🔍 **РЕЗУЛЬТАТЫ ПО ЗАПРОСУ**\n"
        report += f"📌 `{query}`\n"
        report += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        report += f"📊 Найдено: {len(tweets_data)}\n\n"
        
        for i, tweet in enumerate(tweets_data, 1):
            report += f"**{i}.** "
            
            text = tweet['text'][:280]
            if len(tweet['text']) > 280:
                text += "..."
            
            if text.strip():
                report += f"{text}\n"
            
            if tweet['time']:
                time_str = tweet['time'][:16].replace('T', ' ')
                report += f"\n🕐 {time_str}"
            
            report += "\n\n"
        
        if len(report) > 4000:
            filename = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Результаты поиска: {query}"
            )
        else:
            await msg.edit_text(report, parse_mode='Markdown')
        
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"🔍 Поиск: {query}"
            )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in search: {e}", exc_info=True)

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере через AI"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /browse <задача>\n"
            "Пример: /browse Найди последние новости про ИИ"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    if not AGNES_AVAILABLE:
        await msg.edit_text(
            "❌ Agnes не доступна. Установи AGNES_API_KEY в переменные окружения.\n"
            "Ключ можно получить на https://agnes-ai.com/"
        )
        return
    
    try:
        from browser_use import Agent
        
        # Создаем агента с Agnes
        agent = Agent(
            task=task,
            llm=agnes_llm,
            use_vision=False,
        )
        
        await msg.edit_text(f"🧠 Agnes думает над задачей: {task[:100]}...")
        
        result = await agent.run()
        
        response = f"✅ **Задача выполнена!**\n\n"
        response += f"📋 **Запрос:** {task}\n\n"
        
        if result:
            response += f"📝 **Результат:**\n{str(result)[:1500]}"
        else:
            response += "⚠️ Результат не получен"
        
        if len(response) > 4000:
            filename = f"browse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Задача: {task}\n\n{result}")
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Результат: {task[:50]}"
            )
        else:
            await msg.edit_text(response, parse_mode='Markdown')
        
    except ImportError as e:
        await msg.edit_text(f"❌ Ошибка импорта: {str(e)[:200]}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in browse: {e}", exc_info=True)

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса Agnes"""
    if AGNES_AVAILABLE:
        await update.message.reply_text(
            "✅ **Agnes готова к работе!**\n\n"
            f"Модель: agnes-2.0-flash\n"
            f"Провайдер: Agnes AI (https://agnes-ai.com/)\n\n"
            "Используй /browse <задача> для выполнения задач."
        )
    else:
        await update.message.reply_text(
            "❌ **Agnes не доступна**\n\n"
            "Для настройки:\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь в переменные окружения: AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("engine", engine))
    app.add_handler(CommandHandler("close", close))
    
    # X.com команды
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("search", search))
    
    # AI команды
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("agnes", agnes))
    
    print("✅ Бот запущен!")
    print(f"🎮 Движок: {'Pydoll' if use_pydoll else 'Playwright'}")
    print(f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print("\nКоманды:")
    print("  /start, /login, /screen, /status, /engine, /close")
    print("  /tweets, /search, /browse, /agnes")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()