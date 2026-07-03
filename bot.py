# bot.py - X.com бот с Pydoll + Playwright
import os
import sys
import subprocess
import logging
import asyncio
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Отключаем слишком шумные логгеры
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ПРОВЕРКА БИБЛИОТЕК ==========
PYDOLL_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
CHROMIUM_INSTALLED = False
CHROMIUM_PATH = None

def check_chromium():
    """Проверяет, установлен ли Chromium в системе и находит путь"""
    global CHROMIUM_INSTALLED, CHROMIUM_PATH
    logger.info("🔍 Проверяю наличие Chromium в системе...")
    
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    
    for path in chromium_paths:
        if os.path.exists(path):
            CHROMIUM_PATH = path
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден по пути: {path}")
            return True
    
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            CHROMIUM_PATH = result.stdout.strip()
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден через which: {CHROMIUM_PATH}")
            return True
    except:
        pass
    
    CHROMIUM_INSTALLED = False
    logger.warning("⚠️ Chromium не найден в системе")
    return False

def check_libraries():
    """Проверка всех библиотек"""
    global PYDOLL_AVAILABLE, PLAYWRIGHT_AVAILABLE
    logger.info("🔍 Проверяю установленные библиотеки...")
    
    try:
        import pydoll
        PYDOLL_AVAILABLE = True
        version = getattr(pydoll, '__version__', 'неизвестна')
        logger.info(f"✅ Pydoll загружен (версия: {version})")
    except ImportError as e:
        PYDOLL_AVAILABLE = False
        logger.warning(f"⚠️ Pydoll не найден: {e}")
    except Exception as e:
        PYDOLL_AVAILABLE = False
        logger.error(f"❌ Ошибка при загрузке Pydoll: {e}")
    
    try:
        from playwright.async_api import async_playwright
        PLAYWRIGHT_AVAILABLE = True
        logger.info("✅ Playwright загружен")
    except ImportError as e:
        PLAYWRIGHT_AVAILABLE = False
        logger.warning(f"⚠️ Playwright не найден: {e}")
    except Exception as e:
        PLAYWRIGHT_AVAILABLE = False
        logger.error(f"❌ Ошибка при загрузке Playwright: {e}")
    
    check_chromium()
    logger.info(f"📊 Итог: Pydoll={PYDOLL_AVAILABLE}, Playwright={PLAYWRIGHT_AVAILABLE}, Chromium={CHROMIUM_INSTALLED}")

check_libraries()

# ========== ФУНКЦИИ УСТАНОВКИ ==========
def install_pydoll():
    """Устанавливает Pydoll через pip"""
    global PYDOLL_AVAILABLE
    logger.info("📦 Начинаю установку Pydoll...")
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'pydoll-python', '--upgrade'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Pydoll установлен успешно!")
            try:
                import pydoll
                PYDOLL_AVAILABLE = True
                logger.info("✅ Pydoll импортирован успешно")
                return True
            except ImportError as e:
                PYDOLL_AVAILABLE = False
                logger.error(f"❌ Не удалось импортировать Pydoll: {e}")
                return False
        else:
            logger.error(f"❌ Ошибка установки Pydoll: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Исключение при установке Pydoll: {e}", exc_info=True)
        return False

def install_chromium():
    """Устанавливает Chromium в системе"""
    global CHROMIUM_INSTALLED, CHROMIUM_PATH
    logger.info("📦 Начинаю установку Chromium...")
    
    try:
        result = subprocess.run(['which', 'apt-get'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("⏳ Установка через apt-get...")
            subprocess.run(['apt-get', 'update'], check=True, capture_output=True)
            subprocess.run([
                'apt-get', 'install', '-y',
                'chromium',
                'chromium-driver',
                'fonts-liberation',
                'libasound2',
                'libatk-bridge2.0-0',
                'libatk1.0-0',
                'libcups2',
                'libdbus-1-3',
                'libgbm1',
                'libgtk-3-0',
                'libnspr4',
                'libnss3',
                'libx11-xcb1',
                'libxcomposite1',
                'libxdamage1',
                'libxrandr2',
                'xdg-utils'
            ], check=True, capture_output=True)
            
            check_chromium()
            if CHROMIUM_INSTALLED:
                logger.info(f"✅ Chromium установлен через apt! Путь: {CHROMIUM_PATH}")
                return True
            else:
                logger.error("❌ Chromium не найден после установки")
                return False
        else:
            logger.warning("⚠️ apt-get не найден, пропускаю установку Chromium")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка установки Chromium: {e}", exc_info=True)
        return False

# ========== КУКИ X.COM ==========
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "nTs3wcXdCJEOwWzrJyjIg_huVdfck44vXhCJEXi.WuM-1783057691.7981694-1.0.1.1-pPPuXat31U4x5zNib67xLk9EFfH73h1ZdJPU8GvpXVu3pQ6TVu_rRHHpSZZMRRlzToQCMmjHQmaxoa_A4lwaYonLGPxEPsBIDig2wlei1L210t._g0yt.3n7XxfTQzrP", "domain": ".x.com", "path": "/"}
]

logger.info(f"🍪 Загружено {len(COOKIES)} кук для X.com")

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
pydoll_browser = None
pydoll_tab = None
browser_lock = False
engine_mode = "pydoll"
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

logger.info(f"🎮 Начальный движок: {engine_mode}")

# ========== PYDOLL БРАУЗЕР ==========
async def get_pydoll_browser():
    """Получает Pydoll браузер и возвращает Tab (вкладку)"""
    global pydoll_browser, pydoll_tab, CHROMIUM_PATH
    logger.info("🚀 Запрос на получение Pydoll браузера")
    
    if pydoll_browser and pydoll_tab:
        logger.info("🔄 Проверка существующего браузера...")
        try:
            await pydoll_tab.execute_script('1')
            logger.info("✅ Существующий браузер работает")
            return pydoll_tab
        except Exception as e:
            logger.warning(f"⚠️ Существующий браузер не отвечает: {e}")
            await close_pydoll_browser()
    
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        logger.info("✅ Модули Pydoll импортированы")
        
        logger.info("🚀 Создаю Pydoll браузер с настройками...")
        
        options = ChromiumOptions()
        
        chromium_paths = [
            '/usr/bin/chromium', 
            '/usr/bin/chromium-browser', 
            '/usr/bin/google-chrome', 
            '/usr/bin/google-chrome-stable'
        ]
        found_path = None
        for path in chromium_paths:
            if os.path.exists(path):
                found_path = path
                break
        
        if found_path:
            options.binary_location = found_path
            logger.info(f"📍 Использую Chromium по пути: {found_path}")
            CHROMIUM_PATH = found_path
        else:
            logger.error("❌ Chromium не найден в системе!")
            raise Exception("Chromium не найден в системе")
        
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--headless=new",
        ]
        for arg in args:
            options.add_argument(arg)
            logger.debug(f"📌 Добавлен аргумент: {arg}")
        
        logger.info("⏳ Создание экземпляра браузера...")
        pydoll_browser = Chrome(options=options)
        logger.info("✅ Экземпляр браузера создан")
        
        logger.info("⏳ Запуск браузера и получение вкладки...")
        pydoll_tab = await pydoll_browser.start()
        logger.info("✅ Браузер запущен, вкладка получена!")
        
        # Устанавливаем куки
        logger.info(f"🍪 Устанавливаю {len(COOKIES)} кук для X.com...")
        
        # Сначала переходим на X.com
        logger.info("🌐 Переход на X.com для установки кук...")
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(3)
        
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain', '.x.com'),
                    path=cookie.get('path', '/')
                )
                cookies_set += 1
                logger.debug(f"🍪 Установлена кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка установки куки {cookie['name']}: {e}")
                try:
                    js_cookie = f"document.cookie='{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '.x.com')}; path={cookie.get('path', '/')}'"
                    await pydoll_tab.execute_script(js_cookie)
                    cookies_set += 1
                    logger.debug(f"🍪 Установлена кука через JS: {cookie['name']}")
                except Exception as e2:
                    logger.warning(f"⚠️ Не удалось установить куку {cookie['name']}: {e2}")
        
        logger.info(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        
        logger.info("✅ Pydoll браузер полностью готов!")
        return pydoll_tab
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта Pydoll: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Pydoll ошибка: {e}", exc_info=True)
        return None

async def close_pydoll_browser():
    """Закрывает Pydoll браузер"""
    global pydoll_browser, pydoll_tab
    logger.info("📌 Закрываю Pydoll браузер...")
    
    if pydoll_browser:
        try:
            await pydoll_browser.close()
            logger.info("✅ Pydoll браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии Pydoll: {e}")
        pydoll_browser = None
        pydoll_tab = None

# ========== PLAYWRIGHT БРАУЗЕР ==========
async def get_playwright_browser():
    """Получает Playwright браузер"""
    global browser_data, browser_lock
    logger.info("🚀 Запрос на получение Playwright браузера")
    
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
        
        logger.info("🚀 Запускаю Playwright браузер...")
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
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 720},
        )
        page = await context.new_page()
        
        for cookie in COOKIES:
            try:
                await context.add_cookies([{
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': '.x.com',
                    'path': '/',
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
        
        logger.info("✅ Playwright браузер готов!")
        return browser_data
    finally:
        browser_lock = False

async def close_playwright_browser():
    global browser_data, login_status
    logger.info("📌 Закрываю Playwright браузер...")
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

# ========== УНИВЕРСАЛЬНЫЕ ФУНКЦИИ ==========
async def get_browser():
    """Получает браузер и возвращает страницу/вкладку"""
    global engine_mode
    logger.info(f"🎮 Получение браузера для движка: {engine_mode}")
    
    if engine_mode == "pydoll":
        if not PYDOLL_AVAILABLE:
            logger.error("❌ Pydoll не установлен")
            return None
        result = await get_pydoll_browser()
        if result is None:
            logger.error("❌ Не удалось получить Pydoll браузер")
            return None
        logger.info("✅ Pydoll браузер получен")
        return result
    else:
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("❌ Playwright не установлен")
            return None
        browser_data = await get_playwright_browser()
        if browser_data is None:
            logger.error("❌ Не удалось получить Playwright браузер")
            return None
        logger.info("✅ Playwright браузер получен")
        return browser_data['page']

async def close_browser():
    """Закрывает браузер согласно выбранному движку"""
    global engine_mode
    logger.info(f"📌 Закрытие браузера для движка: {engine_mode}")
    
    if engine_mode == "pydoll":
        await close_pydoll_browser()
    else:
        await close_playwright_browser()

async def goto_url(url):
    """Переход по URL"""
    logger.info(f"🌐 Переход по URL: {url}")
    
    page = await get_browser()
    if page is None:
        raise Exception("Не удалось получить страницу")
    
    if hasattr(page, 'go_to'):
        await page.go_to(url)
    elif hasattr(page, 'goto'):
        await page.goto(url, wait_until='domcontentloaded')
    else:
        raise Exception(f"Неизвестный тип страницы: {type(page)}")
    
    await asyncio.sleep(3)
    logger.info(f"✅ Переход выполнен: {url}")

async def execute_js(script):
    """Выполнение JS"""
    logger.debug(f"📜 Выполнение JS")
    
    page = await get_browser()
    if page is None:
        logger.error("❌ Страница не получена для выполнения JS")
        return None
    
    try:
        if hasattr(page, 'execute_script'):
            result = await page.execute_script(script)
            logger.debug(f"✅ JS выполнен через execute_script")
            return result
        elif hasattr(page, 'evaluate'):
            result = await page.evaluate(script)
            logger.debug(f"✅ JS выполнен через evaluate")
            return result
        else:
            logger.error(f"❌ Нет метода execute_script или evaluate у {type(page)}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении JS: {e}")
        return None

async def take_screenshot():
    """Скриншот - возвращает bytes или None"""
    logger.info("📸 Создание скриншота")
    
    page = await get_browser()
    if page is None:
        logger.error("❌ Страница не получена для скриншота")
        return None
    
    if hasattr(page, 'take_screenshot'):
        try:
            screenshot_base64 = await page.take_screenshot(as_base64=True)
            if screenshot_base64:
                return base64.b64decode(screenshot_base64)
        except Exception as e:
            logger.error(f"Ошибка take_screenshot(as_base64=True): {e}")
            try:
                temp_file = '/tmp/screenshot.png'
                await page.take_screenshot(path=temp_file)
                if os.path.exists(temp_file):
                    with open(temp_file, 'rb') as f:
                        return f.read()
            except Exception as e2:
                logger.error(f"Ошибка сохранения скриншота: {e2}")
                return None
    elif hasattr(page, 'screenshot'):
        return await page.screenshot()
    else:
        logger.error(f"Неизвестный тип страницы: {type(page)}")
        return None

# ========== ДИАГНОСТИЧЕСКАЯ КОМАНДА ==========
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диагностика Pydoll с проверкой кук"""
    msg = await update.message.reply_text("🔍 Запуск диагностики Pydoll...")
    
    log_file = f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    diagnostic_log = []
    
    def log_diag(text):
        diagnostic_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        logger.info(text)
    
    try:
        # 1. Проверка Chromium
        await msg.edit_text("1️⃣ Проверяю Chromium...")
        log_diag("=== ПРОВЕРКА CHROMIUM ===")
        
        chromium_paths = [
            '/usr/bin/chromium', 
            '/usr/bin/chromium-browser', 
            '/usr/bin/google-chrome', 
            '/usr/bin/google-chrome-stable'
        ]
        found = None
        for path in chromium_paths:
            exists = os.path.exists(path)
            log_diag(f"  Проверка {path}: {'✅' if exists else '❌'}")
            if exists:
                found = path
                break
        
        if not found:
            log_diag("❌ Chromium НЕ НАЙДЕН!")
            await msg.edit_text("❌ Chromium не найден!")
            return
        
        log_diag(f"✅ Chromium найден: {found}")
        await msg.edit_text(f"✅ Chromium найден\n\n2️⃣ Проверяю Pydoll...")
        
        # 2. Проверка импорта
        try:
            from pydoll.browser import Chrome
            from pydoll.browser.options import ChromiumOptions
            log_diag("✅ Pydoll импортирован")
        except Exception as e:
            log_diag(f"❌ Ошибка импорта: {e}")
            await msg.edit_text(f"❌ Ошибка: {e}")
            return
        
        # 3. Запуск браузера
        await msg.edit_text("3️⃣ Запускаю браузер...")
        log_diag("=== ЗАПУСК БРАУЗЕРА ===")
        
        try:
            options = ChromiumOptions()
            options.binary_location = found
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--headless=new")
            
            browser = Chrome(options=options)
            tab = await browser.start()
            log_diag("✅ Браузер запущен!")
            
            # 4. Переход на X.com
            await msg.edit_text("4️⃣ Перехожу на X.com...")
            log_diag("🌐 Переход на X.com...")
            await tab.go_to('https://x.com')
            await asyncio.sleep(3)
            log_diag("✅ Переход выполнен")
            
            # 5. Проверка кук - ИСПРАВЛЕНО
            await msg.edit_text("5️⃣ Проверяю куки...")
            log_diag("=== ПРОВЕРКА КУК ===")
            
            try:
                cookies_js = await tab.execute_script('document.cookie')
                log_diag(f"📋 Куки из браузера: {cookies_js[:500] if cookies_js else 'пусто'}...")
                
                # Разбираем куки правильно
                cookie_list = []
                if cookies_js:
                    for cookie in cookies_js.split(';'):
                        cookie = cookie.strip()
                        if '=' in cookie:
                            # Разделяем только по первому '='
                            parts = cookie.split('=', 1)
                            if len(parts) == 2:
                                name = parts[0].strip()
                                value = parts[1].strip()
                                if len(value) > 30:
                                    value = value[:30] + '...'
                                cookie_list.append({'name': name, 'value': value})
                
                log_diag(f"📦 Всего кук: {len(cookie_list)}")
                
                # Проверяем важные куки
                important = ['auth_token', 'ct0', 'twid']
                found_cookies = []
                for c in cookie_list:
                    if c['name'] in important:
                        found_cookies.append(c)
                        log_diag(f"✅ Найдена кука: {c['name']} = {c['value']}")
                
                if found_cookies:
                    log_diag(f"✅ Найдены важные куки: {', '.join([c['name'] for c in found_cookies])}")
                else:
                    log_diag("❌ Важные куки НЕ НАЙДЕНЫ!")
                    
            except Exception as e:
                log_diag(f"❌ Ошибка при получении кук: {e}")
            
            # 6. Проверка авторизации
            await msg.edit_text("6️⃣ Проверяю авторизацию...")
            log_diag("=== ПРОВЕРКА АВТОРИЗАЦИИ ===")
            
            auth_check = await tab.execute_script('''
                () => {
                    const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]');
                    const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                    const hasHomeLink = !!document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                    const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                    const hasLoginForm = !!document.querySelector('[data-testid="loginForm"]');
                    
                    return {
                        hasTweetBtn: hasTweetBtn || false,
                        hasProfileLink: hasProfileLink || false,
                        hasHomeLink: hasHomeLink || false,
                        hasSideNav: hasSideNav || false,
                        hasLoginForm: hasLoginForm || false,
                        isLoggedIn: !!(hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav)
                    };
                }
            ''')
            
            log_diag(f"📊 Результат проверки авторизации: {auth_check}")
            
            if auth_check and auth_check.get('isLoggedIn'):
                log_diag("✅ ВЫ АВТОРИЗОВАНЫ!")
                await msg.edit_text("✅ **Диагностика завершена!**\n\n✅ ВЫ АВТОРИЗОВАНЫ!\nPydoll работает корректно.")
            else:
                log_diag("❌ НЕ АВТОРИЗОВАН")
                await msg.edit_text("✅ **Диагностика завершена!**\n\n❌ НЕ АВТОРИЗОВАН\nКуки не работают или истекли.\n\nИспользуйте /setcookies для обновления кук.")
            
            # 7. Скриншот для диагностики
            log_diag("📸 Делаю скриншот...")
            screenshot_b64 = await tab.take_screenshot(as_base64=True)
            if screenshot_b64:
                screenshot = base64.b64decode(screenshot_b64)
                await update.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 Диагностический скриншот X.com\n{'✅ Авторизован' if auth_check and auth_check.get('isLoggedIn') else '❌ Не авторизован'}"
                )
                log_diag("✅ Скриншот отправлен")
            
            # Закрываем браузер
            await browser.close()
            log_diag("✅ Браузер закрыт")
            
        except Exception as e:
            log_diag(f"❌ Ошибка: {e}")
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        
        # Отправляем лог
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        await update.message.reply_document(
            document=open(log_file, 'rb'), 
            caption="📋 Лог диагностики"
        )
            
    except Exception as e:
        logger.error(f"Critical test error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Критическая ошибка: {str(e)[:200]}")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        await update.message.reply_document(document=open(log_file, 'rb'), caption="📋 Лог диагностики")

# ========== КОМАНДА ДЛЯ ОБНОВЛЕНИЯ КУК ==========
async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление кук через Telegram"""
    global COOKIES
    await update.message.reply_text(
        "🍪 **Обновление кук X.com**\n\n"
        "Отправьте куки в JSON формате:\n"
        "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\",\"path\":\"/\"}]`\n\n"
        "Или отправьте /cancel для отмены"
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенных кук"""
    global COOKIES
    
    if not context.user_data.get('waiting_for_cookies'):
        return
    
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        context.user_data['waiting_for_cookies'] = False
        await update.message.reply_text("❌ Отменено")
        return
    
    try:
        import json
        data = json.loads(text)
        new_cookies = []
        
        if isinstance(data, list):
            for cookie in data:
                if 'name' in cookie and 'value' in cookie:
                    new_cookies.append({
                        "name": cookie['name'],
                        "value": cookie['value'],
                        "domain": cookie.get('domain', '.x.com'),
                        "path": cookie.get('path', '/')
                    })
        elif isinstance(data, dict):
            for name, value in data.items():
                if value:
                    new_cookies.append({
                        "name": name,
                        "value": value,
                        "domain": ".x.com",
                        "path": "/"
                    })
        
        if new_cookies:
            COOKIES = new_cookies
            context.user_data['waiting_for_cookies'] = False
            await close_browser()
            await update.message.reply_text(
                f"✅ **Куки обновлены!**\n\n"
                f"📦 Всего: {len(COOKIES)} кук\n"
                f"🍪 Включены: {', '.join([c['name'] for c in COOKIES])}\n\n"
                f"Используйте /login для авторизации"
            )
        else:
            await update.message.reply_text("❌ Не удалось распознать куки")
            
    except json.JSONDecodeError as e:
        await update.message.reply_text(f"❌ Ошибка JSON: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🎮 Движок: {'Pydoll' if engine_mode == 'pydoll' else 'Playwright'}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        f"📌 Команды:\n"
        f"/engine - Переключить движок\n"
        f"/login - Авторизация в X.com\n"
        f"/screen - Скриншот\n"
        f"/status - Статус браузера\n"
        f"/close - Закрыть браузер\n"
        f"/test - Диагностика Pydoll\n"
        f"/setcookies - Обновить куки",
        parse_mode='Markdown'
    )

async def engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение между движками браузера"""
    global engine_mode, PYDOLL_AVAILABLE, PLAYWRIGHT_AVAILABLE, CHROMIUM_INSTALLED
    logger.info(f"📩 Команда /engine от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        current = "Pydoll" if engine_mode == "pydoll" else "Playwright"
        await update.message.reply_text(
            f"🔧 Текущий движок: **{current}**\n\n"
            f"Использование: /engine <pydoll|playwright>\n"
            f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
            f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}"
        )
        return
    
    engine_type = context.args[0].lower()
    msg = await update.message.reply_text(f"⏳ Переключаю на {engine_type}...")
    
    if engine_type == "pydoll":
        if not CHROMIUM_INSTALLED:
            await msg.edit_text("📦 Устанавливаю Chromium...")
            if install_chromium():
                CHROMIUM_INSTALLED = True
                await msg.edit_text("✅ Chromium установлен!")
            else:
                await msg.edit_text("⚠️ Не удалось установить Chromium")
        
        if not PYDOLL_AVAILABLE:
            await msg.edit_text("📦 Устанавливаю Pydoll...")
            if install_pydoll():
                PYDOLL_AVAILABLE = True
                await msg.edit_text("✅ Pydoll установлен!")
            else:
                await msg.edit_text("❌ Не удалось установить Pydoll")
                return
        
        await close_browser()
        engine_mode = "pydoll"
        await msg.edit_text("✅ **Переключено на Pydoll!**")
        
    elif engine_type == "playwright":
        if not PLAYWRIGHT_AVAILABLE:
            await msg.edit_text("📦 Устанавливаю Playwright...")
            try:
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install', 'playwright'
                ], check=True, capture_output=True)
                PLAYWRIGHT_AVAILABLE = True
                await msg.edit_text("✅ Playwright установлен!")
            except Exception as e:
                await msg.edit_text(f"❌ Ошибка: {e}")
                return
        
        await close_browser()
        engine_mode = "playwright"
        await msg.edit_text("✅ **Переключено на Playwright!**")
    else:
        await msg.edit_text(f"❌ Неизвестный движок: {engine_type}")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        await goto_url('https://x.com')
        await asyncio.sleep(3)
        
        auth_status = await execute_js('''
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
                    hasTweetBtn: hasTweetBtn || false,
                    hasProfileLink: hasProfileLink || false,
                    hasHomeLink: hasHomeLink || false,
                    hasSideNav: hasSideNav || false,
                    hasLoginForm: hasLoginForm || false,
                    hasAuthToken: !!cookies.auth_token,
                    hasCt0: !!cookies.ct0,
                    username: username,
                    isLoggedIn: !!(hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav)
                };
            }
        ''')
        
        if auth_status is None:
            await msg.edit_text("❌ Не удалось проверить авторизацию")
            return
        
        global login_status
        login_status['is_logged_in'] = auth_status.get('isLoggedIn', False)
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False) and auth_status.get('hasCt0', False)
        
        status_msg = f"✅ X.com ({engine_mode})\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status.get('hasCt0') else '❌'}\n\n"
        
        if auth_status.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username'):
                status_msg += f"👤 @{auth_status['username']}\n"
        elif auth_status.get('hasLoginForm'):
            status_msg += "❌ НЕ АВТОРИЗОВАН (форма входа)\n"
        else:
            status_msg += "⚠️ НЕ ОПРЕДЕЛЕНО\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот"""
    logger.info(f"📩 Команда /screen от {update.effective_user.username}")
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Скриншот X.com\n🎮 Движок: {engine_mode}"
            )
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в screen: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус"""
    logger.info(f"📩 Команда /status от {update.effective_user.username}")
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        status_msg = "📊 **СТАТУС БОТА**\n\n"
        status_msg += f"🎮 Движок: **{engine_mode}**\n"
        status_msg += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        status_msg += f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        status_msg += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        
        if engine_mode == "pydoll":
            page = await get_pydoll_browser()
            if page:
                status_msg += "🌐 Браузер: ✅ Запущен (Pydoll)\n"
                try:
                    url = await execute_js('window.location.href')
                    status_msg += f"🔗 URL: {url[:50]}\n"
                except:
                    pass
            else:
                status_msg += "🌐 Браузер: ❌ Не запущен\n"
        else:
            browser = await get_playwright_browser()
            if browser:
                status_msg += "🌐 Браузер: ✅ Запущен (Playwright)\n"
                page = browser['page']
                url = page.url
                status_msg += f"🔗 URL: {url[:50]}\n"
            else:
                status_msg += "🌐 Браузер: ❌ Не запущен\n"
        
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
        logger.error(f"❌ Ошибка в status: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    logger.info(f"📩 Команда /close от {update.effective_user.username}")
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    logger.info("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("engine", engine))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n✅ Бот запущен!")
    print(f"🎮 Движок: {engine_mode}")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды: /start, /engine, /login, /screen, /status, /close, /test, /setcookies")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()