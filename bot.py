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
        
    async def get_random_photo_url(self, page) -> Optional[str]:
        """Получает случайное фото из случайного паблика с логированием"""
        self.total_attempts += 1
        logger.info(f"🔍 Попытка #{self.total_attempts} найти фото")
        
        # Выбираем все паблики и перемешиваем
        selected_pages = self.beauty_pages.copy()
        random.shuffle(selected_pages)
        logger.info(f"📋 Паблики для проверки: {', '.join(selected_pages)}")
        
        page_index = 0
        for username in selected_pages:
            page_index += 1
            logger.info(f"📄 [{page_index}/{len(selected_pages)}] Проверяю паблик @{username}")
            
            try:
                # Переходим на страницу паблика
                logger.info(f"  ⏳ Загрузка страницы @{username}...")
                page_load_start = datetime.now()
                
                try:
                    await page.goto(f"https://x.com/{username}", wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(3000)
                    load_time = (datetime.now() - page_load_start).total_seconds()
                    logger.info(f"  ✅ Страница @{username} загружена за {load_time:.2f}с")
                except Exception as e:
                    logger.error(f"  ❌ Ошибка загрузки страницы @{username}: {e}")
                    continue
                
                # Ждем загрузки твитов
                try:
                    logger.info(f"  ⏳ Ожидание твитов...")
                    await page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
                    logger.info(f"  ✅ Твиты найдены")
                except Exception as e:
                    logger.warning(f"  ⚠️ Твиты не загрузились на @{username}: {e}")
                    continue
                
                # Получаем все твиты с фото
                logger.info(f"  ⏳ Извлечение твитов с фото...")
                tweets_data = await page.evaluate('''
                    () => {
                        const tweets = [];
                        const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                        
                        tweetElements.forEach((tweet) => {
                            const images = tweet.querySelectorAll('img');
                            const imageUrls = [];
                            
                            images.forEach(img => {
                                const src = img.getAttribute('src');
                                if (src && src.includes('pbs.twimg.com/media/')) {
                                    if (!src.includes('profile_images') && !src.includes('emoji')) {
                                        imageUrls.push(src);
                                    }
                                }
                            });
                            
                            if (imageUrls.length > 0) {
                                const link = tweet.querySelector('a[href*="/status/"]');
                                const tweetUrl = link ? link.getAttribute('href') : '';
                                
                                tweets.push({
                                    id: tweet.getAttribute('data-tweet-id') || '',
                                    photo_urls: imageUrls,
                                    url: tweetUrl
                                });
                            }
                        });
                        
                        return tweets;
                    }
                ''')
                
                if not tweets_data:
                    logger.warning(f"  ⚠️ Нет фото в твитах @{username}")
                    continue
                
                logger.info(f"  ✅ Найдено {len(tweets_data)} твитов с фото в @{username}")
                
                # Перемешиваем твиты
                random.shuffle(tweets_data)
                
                # Проверяем твиты на дубли
                checked = 0
                for tweet in tweets_data:
                    checked += 1
                    
                    # Проверяем дубли
                    if tweet['id'] and tweet['id'] in self.sent_posts:
                        logger.info(f"  🔄 Твит {tweet['id']} уже отправлен (пропускаем)")
                        continue
                    
                    if tweet['photo_urls']:
                        photo_url = tweet['photo_urls'][0]
                        logger.info(f"  ✅ Найдено новое фото в твите {tweet['id']}")
                        logger.info(f"  🖼️ URL: {photo_url[:80]}...")
                        
                        # Добавляем в историю
                        if tweet['id']:
                            self.sent_posts.add(tweet['id'])
                            self.sent_history.append(tweet['id'])
                            self.successful_finds += 1
                            
                            # Ограничиваем историю
                            if len(self.sent_history) > 100:
                                old_id = self.sent_history.pop(0)
                                self.sent_posts.remove(old_id)
                                logger.info(f"  🗑️ Удален старый ID из истории: {old_id}")
                            
                            logger.info(f"  📊 Отправлено фото #{self.successful_finds}")
                            logger.info(f"  📊 В истории: {len(self.sent_posts)} уникальных ID")
                        
                        return photo_url
                
                logger.warning(f"  ⚠️ Все {checked} твитов в @{username} уже отправлены")
                
            except Exception as e:
                logger.error(f"  ❌ Ошибка при обработке @{username}: {e}", exc_info=True)
                continue
        
        logger.warning(f"❌ Фото не найдено ни в одном из {len(selected_pages)} пабликов")
        logger.warning(f"📊 Всего попыток: {self.total_attempts}, успешно: {self.successful_finds}")
        return None

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
        
        if browser_ok and browser_info.get('title'):
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
        status_msg += f"\n🧠 Browser-Use: {'✅' if BROWSER_USE_AVAILABLE else '❌'}"
        status_msg += f"\n🤖 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}"
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== /GETGIRL - КРАСИВЫЕ ДЕВУШКИ С ЛОГАМИ ==========

async def getgirl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет случайное фото из пабликов с красивыми девушками"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"🌸 /getgirl вызван пользователем @{user.username} (id: {user.id}) в чате {chat_id}")
    
    msg = await update.message.reply_text("🌸 Ищу красивую девушку...")
    start_time = datetime.now()
    
    try:
        # Шаг 1: Получение браузера
        logger.info(f"📱 Шаг 1: Получение браузера...")
        browser_start = datetime.now()
        
        try:
            browser = await get_browser()
            page = browser['page']
            logger.info(f"✅ Браузер получен за {(datetime.now() - browser_start).total_seconds():.2f}с")
        except Exception as e:
            logger.error(f"❌ Ошибка получения браузера: {e}", exc_info=True)
            await msg.edit_text("❌ Ошибка: не удалось запустить браузер")
            return
        
        # Шаг 2: Создание экземпляра BeautyBot
        logger.info(f"📱 Шаг 2: Инициализация BeautyBot...")
        beauty_bot = BeautyBot()
        logger.info(f"✅ BeautyBot инициализирован. Пабликов: {len(beauty_bot.beauty_pages)}")
        logger.info(f"📋 Список пабликов: {', '.join(beauty_bot.beauty_pages)}")
        
        # Шаг 3: Поиск фото
        logger.info(f"📱 Шаг 3: Поиск фото...")
        photo_start = datetime.now()
        
        try:
            photo_url = await beauty_bot.get_random_photo_url(page)
            search_time = (datetime.now() - photo_start).total_seconds()
            
            if photo_url:
                logger.info(f"✅ Фото найдено за {search_time:.2f}с")
                logger.info(f"🖼️ URL фото: {photo_url[:100]}...")
                
                # Шаг 4: Отправка фото
                logger.info(f"📱 Шаг 4: Отправка фото...")
                send_start = datetime.now()
                
                try:
                    await msg.delete()
                    await update.message.reply_photo(photo=photo_url)
                    send_time = (datetime.now() - send_start).total_seconds()
                    total_time = (datetime.now() - start_time).total_seconds()
                    
                    logger.info(f"✅ Фото отправлено за {send_time:.2f}с")
                    logger.info(f"✅ ВСЕГО: {total_time:.2f}с")
                    logger.info(f"✅ Статус: УСПЕШНО")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}", exc_info=True)
                    await msg.edit_text("❌ Ошибка отправки фото, попробуйте ещё раз")
                    
            else:
                logger.warning(f"⚠️ Фото не найдено. Время поиска: {search_time:.2f}с")
                logger.warning(f"⚠️ Причина: нет фото в пабликах или все фото уже отправлены")
                await msg.edit_text("😔 Не удалось найти фото, попробуйте позже")
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска фото: {e}", exc_info=True)
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в getgirl: {e}", exc_info=True)
        try:
            await msg.edit_text(f"❌ Критическая ошибка: {str(e)[:200]}")
        except:
            await update.message.reply_text(f"❌ Критическая ошибка: {str(e)[:200]}")
    
    finally:
        total_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"🏁 Завершение /getgirl. Общее время: {total_time:.2f}с")

# ========== ТВИТЫ ПОЛЬЗОВАТЕЛЯ ==========

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
        browser = await get_browser()
        page = browser['page']
        
        await page.goto(f"https://x.com/{username}", wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        await page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        tweets_data = await page.evaluate(f'''
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
                    text = text.replace(/http?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/ftp?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/www\\.[^\\s]*/g, '');
                    text = text.replace(/[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}\\S*/g, '');
                    text = text.replace(/\\b[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}\\b/g, '');
                    text = text.replace(/[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+/g, '');
                    text = text.replace(/[a-zA-Z0-9]+\\.[a-zA-Z]{{2,}}\\b/g, '');
                    text = text.replace(/\\n\\s*\\n/g, '\\n');
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
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Твиты @{username}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in tweets: {e}", exc_info=True)

# ========== ПОИСК ТВИТОВ ==========

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
        browser = await get_browser()
        page = browser['page']
        
        search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query"
        await page.goto(search_url, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        await page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
        
        tweets_data = await page.evaluate('''
            () => {
                const tweets = [];
                const tweetElements = document.querySelectorAll('[data-testid="tweet"]');
                
                tweetElements.forEach((tweet, index) => {
                    if (index >= 10) return;
                    
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const timeEl = tweet.querySelector('time');
                    
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/http?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/ftp?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/www\\.[^\\s]*/g, '');
                    text = text.replace(/[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\\S*/g, '');
                    text = text.replace(/\\b[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\\b/g, '');
                    text = text.replace(/[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+/g, '');
                    text = text.replace(/[a-zA-Z0-9]+\\.[a-zA-Z]{2,}\\b/g, '');
                    text = text.replace(/\\n\\s*\\n/g, '\\n');
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
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"🔍 Поиск: {query}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Error in search: {e}", exc_info=True)

# ========== BROWSER-USE ==========

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере через AI"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /browse <задача>\n"
            "Пример: /browse Найди последние новости про ИИ\n"
            "Пример: /browse Перейди на x.com"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🌐 Выполняю: {task[:100]}...")
    
    # Проверяем, установлен ли browser-use
    if not BROWSER_USE_AVAILABLE:
        await msg.edit_text("⏳ Browser-Use не найден. Устанавливаю...")
        if not install_browser_use():
            await msg.edit_text("❌ Не удалось установить browser-use.")
            return
        await msg.edit_text("✅ Browser-Use установлен! Выполняю задачу...")
    
    # Проверяем Agnes
    if not AGNES_AVAILABLE:
        await msg.edit_text("⏳ Инициализирую Agnes...")
        init_agnes()
        if not AGNES_AVAILABLE:
            await msg.edit_text(
                "❌ Agnes не доступна. Установи AGNES_API_KEY в переменные окружения.\n"
                "Ключ можно получить на https://agnes-ai.com/"
            )
            return
        await msg.edit_text("✅ Agnes готова! Выполняю задачу...")
    
    try:
        from browser_use import Agent
        
        # Создаем агента с Agnes (без явного Browser)
        agent = Agent(
            task=task,
            llm=agnes_llm,
            use_vision=False,
        )
        
        await msg.edit_text(f"🧠 Agnes думает над задачей: {task[:100]}...")
        
        # Выполняем задачу
        result = await agent.run()
        
        response = f"✅ **Задача выполнена!**\n\n"
        response += f"📋 **Запрос:** {task}\n\n"
        
        if result:
            response += f"📝 **Результат:**\n{result[:1500]}"
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
    global AGNES_AVAILABLE, agnes_llm
    
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
            "Возможные причины:\n"
            "1. Не установлен AGNES_API_KEY в переменные окружения\n"
            "2. Проблемы с подключением к API\n"
            "3. Не установлены зависимости (langchain-openai)\n\n"
            "Для настройки:\n"
            "1. Получи ключ на https://agnes-ai.com/\n"
            "2. Добавь в переменные окружения: AGNES_API_KEY=твой_ключ\n"
            "3. Перезапусти бота"
        )

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    # XBOT
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("search", search))
    
    # Browser-Use + Agnes
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("agnes", agnes))
    
    # КРАСИВЫЕ ДЕВУШКИ
    app.add_handler(CommandHandler("getgirl", getgirl))
    
    print("✅ Бот запущен!")
    print(f"🧠 Browser-Use: {'✅ Доступен' if BROWSER_USE_AVAILABLE else '❌ Не установлен'}")
    print(f"🤖 Agnes: {'✅ Доступна' if AGNES_AVAILABLE else '❌ Не доступна'}")
    print("🌸 /getgirl - случайное фото из пабликов с красивыми девушками")
    print("Команды:")
    print("  /start, /login, /screen, /status, /close")
    print("  /tweets, /search, /browse, /agnes, /getgirl")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()