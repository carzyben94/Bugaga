# bot.py - X.com бот с Agnes (бесплатная LLM)
import os
import sys
import subprocess
import logging
import asyncio
import re
import random
from datetime import datetime
from typing import Optional, List, Dict, Set
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

# ========== BROWSER-USE ==========
BROWSER_USE_AVAILABLE = False

def check_browser_use():
    """Проверяет, установлен ли browser-use"""
    global BROWSER_USE_AVAILABLE
    try:
        from browser_use import Agent
        BROWSER_USE_AVAILABLE = True
        return True
    except ImportError:
        BROWSER_USE_AVAILABLE = False
        return False

def install_browser_use():
    """Устанавливает browser-use через pip"""
    global BROWSER_USE_AVAILABLE
    try:
        if check_browser_use():
            return True
        
        print("⏳ Устанавливаю browser-use...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'browser-use'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ browser-use установлен!")
            check_browser_use()
            return True
        else:
            print(f"❌ Ошибка установки: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

# Проверяем при запуске
check_browser_use()

# ========== AGNES (БЕСПЛАТНАЯ LLM) ==========
AGNES_AVAILABLE = False
agnes_llm = None

def init_agnes():
    """Инициализация Agnes через прямой API"""
    global AGNES_AVAILABLE, agnes_llm
    try:
        # Проверяем наличие langchain-openai
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            print("⏳ Устанавливаю langchain-openai...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', 'langchain-openai'
            ], capture_output=True, text=True)
            from langchain_openai import ChatOpenAI
        
        # Agnes API напрямую
        # Регистрируйся на https://agnes-ai.com/ и получи API ключ
        # Бесплатные модели: agnes-2.0-flash
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",  # Бесплатная модель
            temperature=0.7,
            api_key=os.environ.get("AGNES_API_KEY", ""),
        )
        
        # Проверяем, работает ли
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            print("✅ Agnes (LLM) загружена через прямой API")
            return True
        else:
            print("⚠️ Agnes не отвечает")
            return False
            
    except Exception as e:
        print(f"⚠️ Ошибка Agnes: {e}")
        return False

# Инициализируем при запуске
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

# ========== УНИВЕРСАЛЬНЫЕ ФУНКЦИИ ДЛЯ ВСЕХ КОМАНД ==========

async def safe_goto(page, url: str, timeout: int = 30000, retries: int = 3) -> bool:
    """
    Безопасная загрузка страницы с повторными попытками
    Используется для ВСЕХ команд
    """
    logger.info(f"🌐 Загрузка: {url[:80]}...")
    
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            await page.wait_for_timeout(2000)
            logger.info(f"✅ Страница загружена (попытка {attempt+1})")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Попытка {attempt+1}/{retries} не удалась: {str(e)[:100]}")
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"⏳ Ожидание {wait_time}с перед следующей попыткой...")
                await page.wait_for_timeout(wait_time * 1000)
            else:
                logger.error(f"❌ Не удалось загрузить страницу после {retries} попыток")
                return False
    return False

async def wait_for_content(page, selector: str = 'article', timeout: int = 10000, retries: int = 2) -> bool:
    """
    Универсальная функция ожидания контента
    """
    for attempt in range(retries):
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            logger.info(f"✅ Контент найден: {selector}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Ожидание контента, попытка {attempt+1}: {str(e)[:50]}")
            if attempt < retries - 1:
                await page.wait_for_timeout(3000)
    return False

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

# ========== КЛАСС BEAUTYBOT ==========

class BeautyBot:
    def __init__(self):
        # ВАШИ ПАБЛИКИ С КРАСИВЫМИ ДЕВУШКАМИ
        self.beauty_pages = [
            "bikinisnbabes",
            "EuGirlsDom",
            "wxrldofbeauty"
        ]
        
        # Защита от дублей
        self.sent_posts = set()
        self.sent_history = []
        self.total_attempts = 0
        self.successful_finds = 0
        self.max_history = 50
        
    def reset_history(self):
        """Сбрасывает историю отправленных постов"""
        self.sent_posts.clear()
        self.sent_history.clear()
        logger.info(f"🔄 История сброшена!")
    
    def fix_photo_url(self, url: str) -> str:
        """Исправляет URL фото для Telegram"""
        if not url:
            return url
        
        url = url.split('?')[0]
        url = url.split('&')[0]
        
        if 'pbs.twimg.com/media/' in url:
            if not url.endswith('.jpg') and not url.endswith('.png') and not url.endswith('.jpeg'):
                url = url + '.jpg'
            url = url + '?format=jpg&name=large'
        
        return url
        
    async def get_random_photo_url(self, page) -> Optional[str]:
        """Получает случайное фото из случайного паблика"""
        self.total_attempts += 1
        logger.info(f"🔍 Попытка #{self.total_attempts} найти фото")
        logger.info(f"📊 В истории: {len(self.sent_posts)} уникальных ID")
        
        if len(self.sent_posts) >= self.max_history:
            logger.info(f"⚠️ Достигнут лимит истории, сбрасываю...")
            self.reset_history()
        
        selected_pages = self.beauty_pages.copy()
        random.shuffle(selected_pages)
        logger.info(f"📋 Паблики для проверки: {', '.join(selected_pages)}")
        
        for username in selected_pages:
            logger.info(f"📄 Проверяю паблик @{username}")
            
            try:
                # Используем safe_goto
                if not await safe_goto(page, f"https://x.com/{username}"):
                    continue
                
                # Используем wait_for_content
                if not await wait_for_content(page, 'article'):
                    continue
                
                tweets_data = await page.evaluate('''
                    () => {
                        const tweets = [];
                        const selectors = ['[data-testid="tweet"]', 'article'];
                        let tweetElements = [];
                        
                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            if (elements.length > 0) {
                                tweetElements = elements;
                                break;
                            }
                        }
                        
                        tweetElements.forEach((tweet) => {
                            const images = tweet.querySelectorAll('img');
                            const imageUrls = [];
                            
                            images.forEach(img => {
                                const src = img.getAttribute('src');
                                if (src && !src.includes('profile_images') && 
                                    !src.includes('emoji') && !src.includes('default_profile')) {
                                    imageUrls.push(src);
                                }
                            });
                            
                            if (imageUrls.length > 0) {
                                let tweetId = tweet.getAttribute('data-tweet-id') || '';
                                if (!tweetId) {
                                    const link = tweet.querySelector('a[href*="/status/"]');
                                    if (link) {
                                        const href = link.getAttribute('href');
                                        const match = href.match(/\\/status\\/(\\d+)/);
                                        if (match) tweetId = match[1];
                                    }
                                }
                                
                                tweets.push({
                                    id: tweetId,
                                    photo_urls: imageUrls
                                });
                            }
                        });
                        
                        return tweets;
                    }
                ''')
                
                if not tweets_data:
                    logger.warning(f"  ⚠️ Нет фото в @{username}")
                    continue
                
                logger.info(f"  ✅ Найдено {len(tweets_data)} твитов с фото")
                random.shuffle(tweets_data)
                
                for tweet in tweets_data:
                    if tweet['id'] and tweet['id'] in self.sent_posts:
                        continue
                    
                    if tweet['photo_urls']:
                        raw_url = tweet['photo_urls'][0]
                        photo_url = self.fix_photo_url(raw_url)
                        
                        if tweet['id']:
                            self.sent_posts.add(tweet['id'])
                            self.sent_history.append(tweet['id'])
                            self.successful_finds += 1
                            
                            if len(self.sent_history) > self.max_history:
                                old_id = self.sent_history.pop(0)
                                self.sent_posts.remove(old_id)
                            
                            logger.info(f"  📊 Отправлено фото #{self.successful_finds}")
                        
                        return photo_url
                
            except Exception as e:
                logger.error(f"  ❌ Ошибка @{username}: {e}")
                continue
        
        self.reset_history()
        return await self.get_random_photo_url(page)

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Меню\n"
        f"/login Авторизация в X.com\n"
        f"/screen Скриншот\n"
        f"/status Статус браузера\n"
        f"/close Закрыть браузер\n"
        f"Бот\n"
        f"/tweets <username>\n"
        f"/search <запрос>\n"
        f"/getgirl"
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
        
        # Используем safe_goto
        if not await safe_goto(page, 'https://x.com'):
            await msg.edit_text("❌ Не удалось загрузить X.com")
            return
        
        # Используем wait_for_content
        if not await wait_for_content(page, '[data-testid="primaryColumn"]', timeout=15000):
            await page.wait_for_timeout(3000)
        
        auth_status = await page.evaluate('''
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
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
        
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
        
        status_msg += "\n🔐 АВТОРИЗАЦИЯ:\n"
        
        if browser_ok and browser_info.get('auth'):
            auth = browser_info['auth']
            
            status_msg += f"🍪 auth_token: {'✅' if auth.get('hasAuthToken') else '❌'}\n"
            status_msg += f"🍪 ct0: {'✅' if auth.get('hasCt0') else '❌'}\n"
            
            if auth.get('isLoggedIn'):
                status_msg += "\n✅ ВЫ АВТОРИЗОВАНЫ\n"
                if auth.get('username'):
                    status_msg += f"👤 @{auth['username']}\n"
            elif auth.get('hasLoginForm'):
                status_msg += "\n❌ НЕ АВТОРИЗОВАН (форма входа)\n"
            else:
                status_msg += "\n⚠️ НЕ ОПРЕДЕЛЕНО\n"
        else:
            status_msg += "❌ Нет данных (выполните /login)\n"
        
        status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== /TWEETS ==========

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /tweets <username>")
        return
    
    username = context.args[0].replace('@', '').strip()
    msg = await update.message.reply_text(f"📊 Парсю твиты @{username}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Используем safe_goto
        if not await safe_goto(page, f"https://x.com/{username}"):
            await msg.edit_text(f"❌ Не удалось загрузить страницу @{username}")
            return
        
        # Используем wait_for_content
        if not await wait_for_content(page, '[data-testid="tweet"]'):
            await msg.edit_text("❌ Твиты не найдены")
            return
        
        tweets_data = await page.evaluate('''
            () => {
                const tweets = [];
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                
                tweetElements.forEach((tweet, index) => {
                    if (index >= 5) return;
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.trim();
                    
                    if (text) {
                        tweets.push({text: text});
                    }
                });
                
                return tweets;
            }
        ''')
        
        if not tweets_data:
            await msg.edit_text(f"❌ Твиты @{username} не найдены!")
            return
        
        report = f"📊 ТВИТЫ @{username}\n\n"
        for i, tweet in enumerate(tweets_data, 1):
            report += f"{i}. {tweet['text'][:200]}\n\n"
        
        await msg.edit_text(report[:4000])
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== /SEARCH ==========

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /search <запрос>")
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query"
        
        # Используем safe_goto
        if not await safe_goto(page, search_url):
            await msg.edit_text("❌ Не удалось загрузить страницу поиска")
            return
        
        # Используем wait_for_content
        if not await wait_for_content(page, '[data-testid="tweet"]'):
            await msg.edit_text("❌ Ничего не найдено")
            return
        
        tweets_data = await page.evaluate('''
            () => {
                const tweets = [];
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                
                tweetElements.forEach((tweet, index) => {
                    if (index >= 5) return;
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.trim();
                    
                    if (text) {
                        tweets.push({text: text});
                    }
                });
                
                return tweets;
            }
        ''')
        
        if not tweets_data:
            await msg.edit_text(f"❌ По запросу '{query}' ничего не найдено!")
            return
        
        report = f"🔍 РЕЗУЛЬТАТЫ\nЗапрос: {query}\n\n"
        for i, tweet in enumerate(tweets_data, 1):
            report += f"{i}. {tweet['text'][:200]}\n\n"
        
        await msg.edit_text(report[:4000])
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== /GETGIRL ==========

async def getgirl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет случайное фото из пабликов с красивыми девушками"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"🌸 /getgirl вызван пользователем @{user.username}")
    
    msg = await update.message.reply_text("🌸 Ищу красивую девушку...")
    start_time = datetime.now()
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        beauty_bot = BeautyBot()
        
        # Поиск фото с повторными попытками
        photo_url = None
        for attempt in range(3):
            logger.info(f"Попытка {attempt+1}/3")
            try:
                photo_url = await beauty_bot.get_random_photo_url(page)
                if photo_url:
                    break
            except Exception as e:
                logger.error(f"Ошибка в попытке {attempt+1}: {e}")
                await page.wait_for_timeout(2000)
        
        if photo_url:
            try:
                await msg.delete()
                await update.message.reply_photo(photo=photo_url)
                total_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ Фото отправлено! Время: {total_time:.2f}с")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки фото: {e}")
                await msg.edit_text("❌ Ошибка отправки фото")
        else:
            logger.warning("⚠️ Фото не найдено")
            await msg.edit_text("😔 Не удалось найти фото, попробуйте позже")
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== BROWSER-USE ==========

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /browse <задача>")
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    if not BROWSER_USE_AVAILABLE:
        await msg.edit_text("⏳ Устанавливаю browser-use...")
        if not install_browser_use():
            await msg.edit_text("❌ Не удалось установить browser-use")
            return
    
    if not AGNES_AVAILABLE:
        await msg.edit_text("⏳ Инициализирую Agnes...")
        init_agnes()
        if not AGNES_AVAILABLE:
            await msg.edit_text("❌ Agnes не доступна")
            return
    
    try:
        from browser_use import Agent
        
        agent = Agent(
            task=task,
            llm=agnes_llm,
            use_vision=False,
        )
        
        await msg.edit_text(f"🧠 Agnes выполняет: {task[:100]}...")
        result = await agent.run()
        
        response = f"✅ Задача выполнена!\n\n{result[:1500] if result else 'Результат не получен'}"
        await msg.edit_text(response)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if AGNES_AVAILABLE:
        await update.message.reply_text("✅ Agnes готова к работе!")
    else:
        await update.message.reply_text("❌ Agnes не доступна")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("getgirl", getgirl))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("agnes", agnes))
    
    print("✅ Бот запущен!")
    print("Команды: /start, /login, /screen, /status, /close, /tweets, /search, /getgirl, /browse, /agnes")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()