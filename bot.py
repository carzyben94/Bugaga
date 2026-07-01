# bot.py - X.com бот с анализом структуры
import os
import sys
import subprocess
import logging
import asyncio
import json
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

# Папка для логов
LOG_DIR = "x_analysis_logs"
os.makedirs(LOG_DIR, exist_ok=True)

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

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **X.com Bot**\n\n"
        "📌 **Основные команды:**\n"
        "/login — авторизация в X.com\n"
        "/screen — скриншот\n"
        "/status — статус браузера\n"
        "/close — закрыть браузер\n\n"
        "📊 **Анализ структуры:**\n"
        "/inspect — полный анализ X.com\n"
        "/logs — список логов\n"
        "/viewlog <номер> — просмотр лога\n\n"
        "🔍 **Парсинг:**\n"
        "/parsetweets — спарсить твиты\n"
        "/parseprofile <username> — спарсить профиль",
        parse_mode='Markdown'
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

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== АНАЛИЗ СТРУКТУРЫ X.COM С ЛОГАМИ ==========

async def inspect_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный анализ структуры X.com с сохранением логов"""
    msg = await update.message.reply_text("🔍 Начинаю полный анализ X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'url': '',
            'title': '',
            'testids': {},
            'selectors': {},
            'elements': {},
            'cookies': []
        }
        
        # 1. Переходим на главную
        await msg.edit_text("🌐 Загружаю X.com...")
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(5000)
        
        log_data['url'] = page.url
        log_data['title'] = await page.title()
        
        # 2. Собираем ВСЕ data-testid
        await msg.edit_text("🔍 Собираю data-testid элементы...")
        
        testids_data = await page.evaluate('''
            () => {
                const elements = document.querySelectorAll('[data-testid]');
                const result = {};
                const allSelectors = {};
                
                elements.forEach(el => {
                    const id = el.getAttribute('data-testid');
                    if (!result[id]) {
                        result[id] = {
                            count: 0,
                            tags: new Set(),
                            classes: new Set(),
                            text_samples: [],
                            parent_tags: new Set(),
                            visible: 0
                        };
                    }
                    
                    result[id].count++;
                    result[id].tags.add(el.tagName);
                    if (el.className) result[id].classes.add(el.className);
                    if (el.innerText && el.innerText.trim()) {
                        result[id].text_samples.push(el.innerText.trim().substring(0, 100));
                    }
                    if (el.parentElement) {
                        result[id].parent_tags.add(el.parentElement.tagName);
                    }
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result[id].visible++;
                    }
                    
                    if (id.includes('tweet') || id.includes('profile') || 
                        id.includes('button') || id.includes('input')) {
                        const selector = `[data-testid="${id}"]`;
                        if (!allSelectors[id]) {
                            allSelectors[id] = [];
                        }
                        let uniqueSelector = selector;
                        if (el.id) {
                            uniqueSelector = `#${el.id}`;
                        } else if (el.className) {
                            const classes = el.className.split(' ').filter(c => c).join('.');
                            if (classes) {
                                uniqueSelector = `${el.tagName.toLowerCase()}.${classes}`;
                            }
                        }
                        allSelectors[id].push({
                            selector: uniqueSelector,
                            tag: el.tagName,
                            text: el.innerText ? el.innerText.substring(0, 50) : ''
                        });
                    }
                });
                
                Object.keys(result).forEach(key => {
                    result[key].tags = Array.from(result[key].tags);
                    result[key].classes = Array.from(result[key].classes);
                    result[key].parent_tags = Array.from(result[key].parent_tags);
                    result[key].text_samples = result[key].text_samples.slice(0, 3);
                });
                
                return { testids: result, selectors: allSelectors };
            }
        ''')
        
        log_data['testids'] = testids_data['testids']
        log_data['selectors'] = testids_data['selectors']
        
        # 3. Собираем куки
        cookies = await browser['context'].cookies()
        log_data['cookies'] = [
            {'name': c['name'], 'domain': c['domain'], 'secure': c.get('secure', False)}
            for c in cookies
        ]
        
        # 4. Дополнительный анализ структуры
        await msg.edit_text("📊 Анализирую структуру страницы...")
        
        structure = await page.evaluate('''
            () => {
                const result = {
                    main_sections: [],
                    interactive_elements: {
                        buttons: [],
                        inputs: [],
                        links: []
                    },
                    navigation: [],
                    tweets: []
                };
                
                document.querySelectorAll('[role="main"], [role="navigation"], [role="complementary"]').forEach(el => {
                    const role = el.getAttribute('role');
                    const testid = el.getAttribute('data-testid') || 'unknown';
                    const children = el.querySelectorAll('*').length;
                    result.main_sections.push({ role, testid, children });
                });
                
                document.querySelectorAll('button').forEach(btn => {
                    const testid = btn.getAttribute('data-testid') || 'no-testid';
                    const text = btn.innerText ? btn.innerText.substring(0, 50) : '';
                    result.interactive_elements.buttons.push({ testid, text });
                });
                
                document.querySelectorAll('input').forEach(inp => {
                    const testid = inp.getAttribute('data-testid') || 'no-testid';
                    const placeholder = inp.getAttribute('placeholder') || '';
                    result.interactive_elements.inputs.push({ testid, placeholder });
                });
                
                document.querySelectorAll('a[href]').forEach(link => {
                    const href = link.getAttribute('href');
                    const testid = link.getAttribute('data-testid') || 'no-testid';
                    if (href && !href.startsWith('javascript:')) {
                        result.interactive_elements.links.push({ href: href.substring(0, 100), testid });
                    }
                });
                
                document.querySelectorAll('[data-testid*="AppTabBar"], [data-testid*="SideNav"]').forEach(el => {
                    const testid = el.getAttribute('data-testid');
                    const text = el.innerText ? el.innerText.substring(0, 30) : '';
                    result.navigation.push({ testid, text });
                });
                
                document.querySelectorAll('[data-testid="tweet"]').forEach((tweet, i) => {
                    if (i < 3) {
                        const text = tweet.querySelector('[data-testid="tweetText"]');
                        const author = tweet.querySelector('[data-testid="User-Name"]');
                        result.tweets.push({
                            author: author ? author.innerText : 'unknown',
                            text: text ? text.innerText.substring(0, 100) : '',
                            has_media: !!tweet.querySelector('[data-testid="tweetPhoto"]')
                        });
                    }
                });
                
                return result;
            }
        ''')
        
        log_data['structure'] = structure
        
        # 5. Скриншоты
        await msg.edit_text("📸 Делаю скриншоты...")
        
        screenshots = {}
        full_screenshot = await page.screenshot(type='jpeg', quality=80)
        screenshots['full'] = full_screenshot
        
        try:
            tweet_area = await page.locator('[data-testid="primaryColumn"]').first
            if tweet_area:
                tweet_screenshot = await tweet_area.screenshot(type='jpeg', quality=80)
                screenshots['tweets'] = tweet_screenshot
        except:
            pass
        
        # 6. Сохраняем логи
        await msg.edit_text("💾 Сохраняю логи...")
        
        json_file = os.path.join(LOG_DIR, f"x_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        report_file = os.path.join(LOG_DIR, f"x_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"X.COM STRUCTURE ANALYSIS\n")
            f.write(f"Time: {log_data['timestamp']}\n")
            f.write(f"URL: {log_data['url']}\n")
            f.write(f"Title: {log_data['title']}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("📋 DATA-TESTID ЭЛЕМЕНТЫ:\n")
            f.write("-" * 40 + "\n")
            for testid, data in sorted(log_data['testids'].items()):
                f.write(f"\n{testid}:\n")
                f.write(f"  Count: {data['count']}\n")
                f.write(f"  Tags: {', '.join(data['tags'])}\n")
                f.write(f"  Visible: {data['visible']}/{data['count']}\n")
                if data['text_samples']:
                    f.write(f"  Text samples: {data['text_samples'][0][:50]}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("🔍 ВАЖНЫЕ СЕЛЕКТОРЫ:\n")
            f.write("-" * 40 + "\n")
            for testid, selectors in log_data['selectors'].items():
                f.write(f"\n{testid}:\n")
                for sel in selectors[:3]:
                    f.write(f"  {sel['selector']}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("🏗️ СТРУКТУРА СТРАНИЦЫ:\n")
            f.write("-" * 40 + "\n")
            
            if 'structure' in log_data:
                struct = log_data['structure']
                f.write("\nОсновные секции:\n")
                for section in struct.get('main_sections', []):
                    f.write(f"  {section['role']}: {section['testid']} ({section['children']} элементов)\n")
                
                f.write("\nНавигация:\n")
                for nav in struct.get('navigation', []):
                    f.write(f"  {nav['testid']}: {nav['text']}\n")
                
                f.write("\nИнтерактивные элементы:\n")
                f.write(f"  Кнопок: {len(struct.get('interactive_elements', {}).get('buttons', []))}\n")
                f.write(f"  Полей ввода: {len(struct.get('interactive_elements', {}).get('inputs', []))}\n")
                f.write(f"  Ссылок: {len(struct.get('interactive_elements', {}).get('links', []))}\n")
                
                f.write("\nПримеры твитов:\n")
                for tweet in struct.get('tweets', []):
                    f.write(f"  {tweet['author']}: {tweet['text'][:50]}...\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("🍪 КУКИ:\n")
            f.write("-" * 40 + "\n")
            for cookie in log_data['cookies']:
                f.write(f"  {cookie['name']}: {cookie['domain']} (secure: {cookie['secure']})\n")
        
        # 7. Отправляем результаты
        await msg.edit_text("📤 Отправляю результаты...")
        
        with open(json_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                caption=f"📊 JSON лог анализа X.com\n{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
        
        with open(report_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                caption="📄 Текстовый отчет по структуре X.com"
            )
        
        if screenshots.get('full'):
            await update.message.reply_photo(
                photo=screenshots['full'],
                caption="📸 Полный скриншот страницы"
            )
        
        if screenshots.get('tweets'):
            await update.message.reply_photo(
                photo=screenshots['tweets'],
                caption="📸 Область с твитами"
            )
        
        summary = f"""✅ **Анализ X.com завершен!**

📊 **Статистика:**
• data-testid элементов: {len(log_data['testids'])}
• Уникальных селекторов: {len(log_data['selectors'])}
• Кук: {len(log_data['cookies'])}
• Кнопок: {len(log_data.get('structure', {}).get('interactive_elements', {}).get('buttons', []))}
• Твитов на странице: {len(log_data.get('structure', {}).get('tweets', []))}

📁 **Файлы сохранены:**
• JSON: `{os.path.basename(json_file)}`
• Отчет: `{os.path.basename(report_file)}`

💡 Используйте эти данные для создания команд парсинга!
"""
        
        await update.message.reply_text(summary, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in inspect_x: {e}", exc_info=True)

# ========== КОМАНДЫ ДЛЯ РАБОТЫ С ЛОГАМИ ==========

async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список последних логов"""
    try:
        log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.json')], reverse=True)
        
        if not log_files:
            await update.message.reply_text("❌ Логов нет. Сначала выполните /inspect")
            return
        
        msg = "📁 **Последние логи анализа:**\n\n"
        for i, file in enumerate(log_files[:10], 1):
            file_path = os.path.join(LOG_DIR, file)
            size = os.path.getsize(file_path) / 1024
            modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            msg += f"{i}. `{file}`\n   📦 {size:.1f} KB | 🕐 {modified.strftime('%d.%m %H:%M')}\n\n"
        
        msg += "💡 Для просмотра содержимого используйте /viewlog <номер>"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def view_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр содержимого конкретного лога"""
    try:
        if not context.args:
            await update.message.reply_text("ℹ️ Использование: /viewlog <номер лога>\nНапример: /viewlog 1")
            return
        
        log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.json')], reverse=True)
        index = int(context.args[0]) - 1
        
        if index < 0 or index >= len(log_files):
            await update.message.reply_text(f"❌ Лог с номером {context.args[0]} не найден. Всего логов: {len(log_files)}")
            return
        
        log_file = log_files[index]
        file_path = os.path.join(LOG_DIR, log_file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        report = f"📄 **Лог: {log_file}**\n\n"
        report += f"🕐 {data.get('timestamp', 'N/A')}\n"
        report += f"🔗 {data.get('url', 'N/A')}\n\n"
        
        report += f"**📊 Статистика:**\n"
        report += f"• data-testid: {len(data.get('testids', {}))}\n"
        report += f"• Селекторов: {len(data.get('selectors', {}))}\n"
        report += f"• Кук: {len(data.get('cookies', []))}\n"
        
        if 'structure' in data:
            struct = data['structure']
            report += f"• Кнопок: {len(struct.get('interactive_elements', {}).get('buttons', []))}\n"
            report += f"• Полей ввода: {len(struct.get('interactive_elements', {}).get('inputs', []))}\n"
            report += f"• Ссылок: {len(struct.get('interactive_elements', {}).get('links', []))}\n"
            report += f"• Твитов: {len(struct.get('tweets', []))}\n"
        
        report += f"\n**🔑 Ключевые элементы:**\n"
        important = ['tweet', 'profile', 'button', 'input', 'search', 'compose']
        for testid in sorted(data.get('testids', {}).keys()):
            if any(keyword in testid.lower() for keyword in important):
                count = data['testids'][testid]['count']
                report += f"• `{testid}` ({count})\n"
        
        if len(report) > 4000:
            txt_file = file_path.replace('.json', '_view.txt')
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(report)
            await update.message.reply_document(
                document=open(txt_file, 'rb'),
                caption=f"📄 Содержимое {log_file}"
            )
        else:
            await update.message.reply_text(report, parse_mode='Markdown')
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== КОМАНДЫ ПАРСИНГА ==========

async def parse_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг твитов с главной страницы"""
    msg = await update.message.reply_text("📊 Парсю твиты...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Проверяем, на X ли мы
        if 'x.com' not in page.url:
            await page.goto('https://x.com', wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
        
        await page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        tweets = await page.evaluate('''
            () => {
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                const result = [];
                
                tweetElements.forEach((tweet, index) => {
                    if (index >= 10) return;
                    
                    const authorEl = tweet.querySelector('[data-testid="User-Name"]');
                    const author = authorEl ? authorEl.innerText : 'Unknown';
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const text = textEl ? textEl.innerText : '';
                    
                    const timeEl = tweet.querySelector('time');
                    const time = timeEl ? timeEl.getAttribute('datetime') : '';
                    
                    const replyEl = tweet.querySelector('[data-testid="reply"]');
                    const replies = replyEl ? replyEl.innerText : '0';
                    
                    const retweetEl = tweet.querySelector('[data-testid="retweet"]');
                    const retweets = retweetEl ? retweetEl.innerText : '0';
                    
                    const likeEl = tweet.querySelector('[data-testid="like"]');
                    const likes = likeEl ? likeEl.innerText : '0';
                    
                    const linkEl = tweet.querySelector('a[href*="/status/"]');
                    const link = linkEl ? linkEl.getAttribute('href') : '';
                    
                    const hasMedia = !!tweet.querySelector('[data-testid="tweetPhoto"]');
                    
                    result.push({
                        author,
                        text,
                        time,
                        stats: { replies, retweets, likes },
                        link: link ? `https://x.com${link}` : '',
                        has_media: hasMedia
                    });
                });
                
                return result;
            }
        ''')
        
        if not tweets:
            await msg.edit_text("❌ Твиты не найдены. Возможно, нужно авторизоваться (/login)")
            return
        
        report = f"📊 **НАЙДЕНО ТВИТОВ:** {len(tweets)}\n\n"
        for i, tweet in enumerate(tweets, 1):
            report += f"**{i}. {tweet['author']}**\n"
            report += f"📝 {tweet['text'][:200]}\n"
            if tweet['time']:
                report += f"🕐 {tweet['time']}\n"
            report += f"💬 {tweet['stats']['replies']} | 🔄 {tweet['stats']['retweets']} | ❤️ {tweet['stats']['likes']}\n"
            if tweet['has_media']:
                report += f"🖼️ Есть медиа\n"
            if tweet['link']:
                report += f"🔗 {tweet['link']}\n"
            report += "\n"
        
        await msg.edit_text(report[:4000], parse_mode='Markdown')
        
        # Делаем скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Скриншот страницы с твитами"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in parse_tweets: {e}", exc_info=True)

async def parse_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг профиля пользователя"""
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /parseprofile <username>\nНапример: /parseprofile elonmusk")
        return
    
    username = context.args[0].replace('@', '')
    msg = await update.message.reply_text(f"👤 Парсю профиль @{username}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Переходим на профиль
        profile_url = f"https://x.com/{username}"
        await page.goto(profile_url, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        # Ждем загрузки профиля
        await page.wait_for_selector('[data-testid="UserName"]', timeout=10000)
        
        profile_data = await page.evaluate('''
            () => {
                const result = {
                    username: '',
                    display_name: '',
                    bio: '',
                    location: '',
                    join_date: '',
                    following: '',
                    followers: '',
                    tweets_count: '',
                    is_verified: false,
                    is_private: false,
                    avatar_url: '',
                    website: '',
                    tweets: []
                };
                
                // Имя
                const nameEl = document.querySelector('[data-testid="UserName"]');
                if (nameEl) {
                    const text = nameEl.innerText;
                    const parts = text.split('\\n');
                    if (parts.length >= 2) {
                        result.display_name = parts[0];
                        result.username = parts[1].replace('@', '');
                    }
                }
                
                // Био
                const bioEl = document.querySelector('[data-testid="UserDescription"]');
                if (bioEl) {
                    result.bio = bioEl.innerText;
                }
                
                // Статистика
                const followingEl = document.querySelector('[data-testid="followingCount"]');
                if (followingEl) {
                    result.following = followingEl.innerText;
                }
                
                const followersEl = document.querySelector('[data-testid="followersCount"]');
                if (followersEl) {
                    result.followers = followersEl.innerText;
                }
                
                // Проверка верификации
                const verifiedEl = document.querySelector('[data-testid="icon-verified"]');
                result.is_verified = !!verifiedEl;
                
                // Аватар
                const avatarEl = document.querySelector('[data-testid="UserAvatar"] img');
                if (avatarEl) {
                    result.avatar_url = avatarEl.getAttribute('src');
                }
                
                // Сайт
                const websiteEl = document.querySelector('[data-testid="UserProfileHeader_Items"] a[href*="http"]');
                if (websiteEl) {
                    result.website = websiteEl.getAttribute('href');
                }
                
                // Последние твиты
                document.querySelectorAll('[data-testid="tweet"]').forEach((tweet, i) => {
                    if (i < 5) {
                        const textEl = tweet.querySelector('[data-testid="tweetText"]');
                        const timeEl = tweet.querySelector('time');
                        const likesEl = tweet.querySelector('[data-testid="like"]');
                        const retweetEl = tweet.querySelector('[data-testid="retweet"]');
                        
                        result.tweets.push({
                            text: textEl ? textEl.innerText : '',
                            time: timeEl ? timeEl.getAttribute('datetime') : '',
                            likes: likesEl ? likesEl.innerText : '0',
                            retweets: retweetEl ? retweetEl.innerText : '0'
                        });
                    }
                });
                
                return result;
            }
        ''')
        
        # Формируем отчет
        report = f"👤 **ПРОФИЛЬ @{profile_data.get('username', username)}**\n\n"
        report += f"📛 **Имя:** {profile_data.get('display_name', 'Не указано')}\n"
        
        if profile_data.get('is_verified'):
            report += f"🔵 **Верифицирован** ✅\n"
        
        if profile_data.get('bio'):
            report += f"\n📝 **Био:**\n{profile_data['bio']}\n"
        
        report += f"\n📊 **Статистика:**\n"
        report += f"• Подписчики: {profile_data.get('followers', 'N/A')}\n"
        report += f"• Подписки: {profile_data.get('following', 'N/A')}\n"
        
        if profile_data.get('website'):
            report += f"\n🌐 **Сайт:** {profile_data['website']}\n"
        
        if profile_data.get('avatar_url'):
            report += f"\n🖼️ **Аватар:** {profile_data['avatar_url'][:100]}...\n"
        
        if profile_data.get('tweets'):
            report += f"\n📝 **Последние твиты:**\n"
            for i, tweet in enumerate(profile_data['tweets'][:3], 1):
                report += f"\n{i}. {tweet['text'][:150]}\n"
                report += f"   ❤️ {tweet['likes']} | 🔄 {tweet['retweets']} | 🕐 {tweet['time'][:10]}\n"
        
        await msg.edit_text(report[:4000], parse_mode='Markdown')
        
        # Скриншот профиля
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Профиль @{username}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in parse_profile: {e}", exc_info=True)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    # Анализ структуры
    app.add_handler(CommandHandler("inspect", inspect_x))
    app.add_handler(CommandHandler("logs", show_logs))
    app.add_handler(CommandHandler("viewlog", view_log))
    
    # Парсинг
    app.add_handler(CommandHandler("parsetweets", parse_tweets))
    app.add_handler(CommandHandler("parseprofile", parse_profile))
    
    print("🐦 X.com Bot запущен!")
    print("📌 Доступные команды:")
    print("   /start - показать справку")
    print("   /login - авторизация в X.com")
    print("   /screen - скриншот")
    print("   /status - статус браузера")
    print("   /close - закрыть браузер")
    print("   /inspect - полный анализ структуры X.com")
    print("   /logs - список логов")
    print("   /viewlog <номер> - просмотр лога")
    print("   /parsetweets - спарсить твиты")
    print("   /parseprofile <username> - спарсить профиль")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()