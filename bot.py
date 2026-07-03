# bot.py - X.com бот с Pydoll + Playwright (с эмуляцией и меню)
import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
import random
from datetime import datetime
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Pydantic для структурированных данных
try:
    from pydantic import BaseModel, Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    logging.warning("⚠️ Pydantic не установлен")

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

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЭМУЛЯЦИИ ==========
def random_delay(min_sec=0.5, max_sec=2.0):
    """Случайная задержка для имитации человека"""
    return random.uniform(min_sec, max_sec)

async def human_click(element):
    """Клик с эмуляцией человеческого поведения"""
    try:
        if hasattr(element, 'click'):
            await element.click(humanize=True)
        else:
            await element.click()
        await asyncio.sleep(random_delay(0.2, 0.8))
    except Exception as e:
        logger.warning(f"Human click error: {e}")
        await element.click()

async def human_type(element, text):
    """Ввод текста с эмуляцией человеческого поведения"""
    try:
        if hasattr(element, 'type_text'):
            await element.type_text(text, humanize=True)
        else:
            await element.fill(text)
        await asyncio.sleep(random_delay(0.1, 0.5))
    except Exception as e:
        logger.warning(f"Human type error: {e}")
        await element.fill(text)

async def human_goto(page, url):
    """Переход с эмуляцией человеческого поведения"""
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)

async def human_scroll(page, amount=300):
    """Прокрутка с эмуляцией человеческого поведения"""
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            # Fallback через JS
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
    except Exception as e:
        logger.warning(f"Human scroll error: {e}")
        await page.execute_script(f'window.scrollBy(0, {amount})')

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

def install_pydantic():
    """Устанавливает Pydantic через pip"""
    global PYDANTIC_AVAILABLE
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', 'pydantic'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            from pydantic import BaseModel, Field
            PYDANTIC_AVAILABLE = True
            logger.info("✅ Pydantic установлен!")
            return True
        else:
            logger.error(f"❌ Ошибка установки Pydantic: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
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
current_session = None

logger.info(f"🎮 Начальный движок: {engine_mode}")

# ========== PYDOLL БРАУЗЕР ==========
async def get_pydoll_browser():
    """Получает Pydoll браузер и возвращает Tab (вкладку)"""
    global pydoll_browser, pydoll_tab, CHROMIUM_PATH, current_session
    logger.info("🚀 Запрос на получение Pydoll браузера")
    
    if pydoll_browser and pydoll_tab:
        logger.info("🔄 Проверка существующего браузера...")
        try:
            await pydoll_tab.execute_script('1')
            logger.info("✅ Существующий браузер работает")
            current_session = pydoll_tab
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
        
        # Проверяем куки
        try:
            check_cookies = await pydoll_tab.execute_script('document.cookie')
            logger.info(f"📋 Куки в браузере: {check_cookies[:500]}...")
            if 'auth_token' in check_cookies:
                logger.info("✅ auth_token найден в куках!")
            else:
                logger.warning("⚠️ auth_token НЕ найден в куках!")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки кук: {e}")
        
        current_session = pydoll_tab
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
    global pydoll_browser, pydoll_tab, current_session
    logger.info("📌 Закрываю Pydoll браузер...")
    
    if pydoll_browser:
        try:
            await pydoll_browser.close()
            logger.info("✅ Pydoll браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии Pydoll: {e}")
        pydoll_browser = None
        pydoll_tab = None
        current_session = None

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
    """Переход по URL с эмуляцией"""
    logger.info(f"🌐 Переход по URL: {url}")
    
    page = await get_browser()
    if page is None:
        raise Exception("Не удалось получить страницу")
    
    await human_goto(page, url)
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

# ========== НОВЫЕ ФУНКЦИИ Pydoll ==========

async def api_request(method='get', url='', data=None, headers=None):
    """Гибридная автоматизация: API-запрос с сессией браузера"""
    global current_session
    logger.info(f"🌐 API запрос: {method.upper()} {url}")
    
    if engine_mode != "pydoll":
        return {"error": "API запросы доступны только в режиме Pydoll"}
    
    tab = await get_pydoll_browser()
    if tab is None:
        return {"error": "Браузер не запущен"}
    
    try:
        if hasattr(tab, 'request'):
            if method.lower() == 'get':
                response = await tab.request.get(url, headers=headers)
            elif method.lower() == 'post':
                response = await tab.request.post(url, data=data, headers=headers)
            elif method.lower() == 'put':
                response = await tab.request.put(url, data=data, headers=headers)
            else:
                return {"error": f"Неподдерживаемый метод: {method}"}
            
            try:
                response_data = response.json()
            except:
                response_data = {"text": response.text}
            
            return {
                "status": response.status,
                "data": response_data,
                "headers": dict(response.headers)
            }
        else:
            js_code = f"""
                const resp = await fetch('{url}', {{
                    method: '{method.upper()}',
                    headers: {json.dumps(headers or {})},
                    body: {json.dumps(data) if data else 'undefined'}
                }});
                return {{
                    status: resp.status,
                    data: await resp.json()
                }};
            """
            result = await tab.execute_script(js_code)
            return result
    except Exception as e:
        logger.error(f"❌ Ошибка API запроса: {e}")
        return {"error": str(e)}

async def extract_structured_data(selector=None):
    """Извлечение структурированных данных с помощью Pydantic"""
    global PYDANTIC_AVAILABLE
    logger.info(f"📊 Извлечение структурированных данных")
    
    if not PYDANTIC_AVAILABLE:
        return {"error": "Pydantic не установлен. Используйте /install_pydantic"}
    
    if engine_mode != "pydoll":
        return {"error": "Структурированное извлечение доступно только в режиме Pydoll"}
    
    tab = await get_pydoll_browser()
    if tab is None:
        return {"error": "Браузер не запущен"}
    
    try:
        from pydoll.extractor import ExtractionModel, Field
        
        class TweetExtract(ExtractionModel):
            text: str = Field(selector='[data-testid="tweetText"]', description='Текст твита')
            author: str = Field(selector='[data-testid="User-Name"]', description='Автор')
        
        if selector:
            tweets = await tab.extract_all(TweetExtract, scope=selector)
        else:
            tweets = await tab.extract_all(TweetExtract)
        
        return {
            "count": len(tweets),
            "data": [t.model_dump() for t in tweets]
        }
    except ImportError:
        js_code = """
            () => {
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(tweet => {
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const userEl = tweet.querySelector('[data-testid="User-Name"]');
                    tweets.push({
                        text: textEl ? textEl.textContent : '',
                        author: userEl ? userEl.textContent : ''
                    });
                });
                return tweets.slice(0, 10);
            }
        """
        result = await tab.execute_script(js_code)
        return {
            "count": len(result) if result else 0,
            "data": result
        }
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения данных: {e}")
        return {"error": str(e)}

async def shadow_dom_example():
    """Демонстрация работы с Shadow DOM"""
    logger.info("🛡️ Работа с Shadow DOM")
    
    if engine_mode != "pydoll":
        return {"error": "Shadow DOM доступен только в режиме Pydoll"}
    
    tab = await get_pydoll_browser()
    if tab is None:
        return {"error": "Браузер не запущен"}
    
    try:
        host = await tab.find('[data-testid="GrokDrawer"]')
        if host:
            shadow_root = await host.get_shadow_root()
            if shadow_root:
                inner_elem = await shadow_root.query('.some-class')
                if inner_elem:
                    text = await inner_elem.text
                    return {"found": True, "text": text}
        
        return {
            "status": "Shadow DOM доступен",
            "message": "Используйте host.get_shadow_root() для доступа к закрытым shadow roots"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка Shadow DOM: {e}")
        return {"error": str(e)}

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое меню с кнопками"""
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    # Создаем клавиатуру с кнопками
    keyboard = [
        [
            InlineKeyboardButton("🔐 Авторизация", callback_data="login"),
            InlineKeyboardButton("📸 Скриншот", callback_data="screen"),
        ],
        [
            InlineKeyboardButton("📊 Статус", callback_data="status"),
            InlineKeyboardButton("🔧 Движок", callback_data="engine"),
        ],
        [
            InlineKeyboardButton("📝 Твиты", callback_data="tweets_menu"),
            InlineKeyboardButton("🔍 Поиск", callback_data="search_menu"),
        ],
        [
            InlineKeyboardButton("🌐 API Запрос", callback_data="api_menu"),
            InlineKeyboardButton("📊 Extract", callback_data="extract"),
        ],
        [
            InlineKeyboardButton("🛡️ Shadow DOM", callback_data="shadow"),
            InlineKeyboardButton("❌ Закрыть", callback_data="close"),
        ],
        [
            InlineKeyboardButton("🍪 Обновить куки", callback_data="setcookies"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Определяем статус
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот - Главное меню**\n\n"
        f"🎮 Движок: {'Pydoll' if engine_mode == 'pydoll' else 'Playwright'}\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"📌 **Нажмите кнопку для выполнения команды:**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    # Имитация команд
    if callback_data == "login":
        await login(update, context)
    elif callback_data == "screen":
        await screen(update, context)
    elif callback_data == "status":
        await status(update, context)
    elif callback_data == "engine":
        await engine_menu(update, context)
    elif callback_data == "tweets_menu":
        await query.edit_message_text(
            "📝 **Введите username для парсинга твитов:**\n\n"
            "Пример: `/tweets elonmusk 5`\n\n"
            "Или просто введите команду в чате."
        )
    elif callback_data == "search_menu":
        await query.edit_message_text(
            "🔍 **Введите запрос для поиска:**\n\n"
            "Пример: `/search биткоин`\n\n"
            "Или просто введите команду в чате."
        )
    elif callback_data == "api_menu":
        await query.edit_message_text(
            "🌐 **Введите URL для API запроса:**\n\n"
            "Пример: `/api https://x.com/api/graphql/...`\n\n"
            "Запрос использует сессию браузера с вашими куками."
        )
    elif callback_data == "extract":
        await extract(update, context)
    elif callback_data == "shadow":
        await shadow(update, context)
    elif callback_data == "close":
        await close(update, context)
    elif callback_data == "setcookies":
        await setcookies(update, context)

async def engine_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора движка"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("🎮 Pydoll", callback_data="engine_pydoll"),
            InlineKeyboardButton("🎭 Playwright", callback_data="engine_playwright"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔧 **Выбор движка браузера**\n\n"
        f"Текущий: **{engine_mode}**\n\n"
        f"Pydoll - человеческое поведение, обход антибот\n"
        f"Playwright - стабильный, проверенный",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def engine_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение движка через кнопки"""
    global engine_mode
    query = update.callback_query
    await query.answer()
    
    engine_type = query.data.replace("engine_", "")
    
    if engine_type == "pydoll":
        if not PYDOLL_AVAILABLE:
            await query.edit_message_text("❌ Pydoll не установлен. Используйте /engine pydoll для установки.")
            return
        engine_mode = "pydoll"
        await query.edit_message_text("✅ Переключено на Pydoll!\n\nИспользуйте /login для авторизации.")
    elif engine_type == "playwright":
        if not PLAYWRIGHT_AVAILABLE:
            await query.edit_message_text("❌ Playwright не установлен.")
            return
        engine_mode = "playwright"
        await query.edit_message_text("✅ Переключено на Playwright!\n\nИспользуйте /login для авторизации.")
    
    await close_browser()

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com с эмуляцией"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    
    # Проверяем, откуда пришел вызов
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        # Эмуляция перехода
        await human_goto(page, 'https://x.com')
        
        # Эмуляция ожидания
        await asyncio.sleep(random_delay(2.0, 4.0))
        
        # Проверка авторизации
        auth_status = await execute_js('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const hasSignupLink = !!document.querySelector('a[href="/signup"]');
                const hasLoginButton = !!document.querySelector('[data-testid="loginButton"]');
                
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                if (!username) {
                    const accountBtn = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                    if (accountBtn) {
                        const text = accountBtn.textContent || '';
                        const match = text.match(/@([a-zA-Z0-9_]+)/);
                        if (match) username = match[1];
                    }
                }
                
                const hasNoLoginButtons = !hasLoginLink && !hasSignupLink && !hasLoginButton;
                const hasUserElements = hasProfileLink || hasSideNav || hasTweetBtn;
                const isLoggedIn = hasAuthToken || (hasNoLoginButtons && hasUserElements);
                
                return {
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    hasNoLoginButtons: hasNoLoginButtons,
                    hasUserElements: hasUserElements,
                    username: username || 'неизвестно',
                    isLoggedIn: isLoggedIn
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
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False)
        
        status_msg = f"✅ X.com ({engine_mode})\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status.get('hasCt0') else '❌'}\n\n"
        
        if auth_status.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username') and auth_status.get('username') != 'неизвестно':
                status_msg += f"👤 @{auth_status['username']}\n"
            status_msg += "\n💡 Теперь доступны расширенные функции:"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
            status_msg += "\nИспользуйте /setcookies для обновления кук"
        
        await msg.edit_text(status_msg)
        
        screenshot = await take_screenshot()
        if screenshot:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
                )
            else:
                await update.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
                )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг твитов пользователя с эмуляцией"""
    logger.info(f"📩 Команда /tweets от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /tweets <username> [count]\n"
            "Пример: /tweets elonmusk 5"
        )
        return
    
    username = context.args[0].replace('@', '').strip()
    count = int(context.args[1]) if len(context.args) > 1 else 10
    msg = await update.message.reply_text(f"📊 Парсю твиты @{username}...")
    
    try:
        # Эмуляция перехода с задержкой
        await goto_url(f"https://x.com/{username}")
        await asyncio.sleep(random_delay(2.0, 3.5))
        
        # Эмуляция прокрутки для загрузки твитов
        await human_scroll(await get_browser(), 500)
        await asyncio.sleep(random_delay(1.0, 2.0))
        
        # Парсим твиты
        tweets_data = await execute_js(f'''
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
        
        # Эмуляция скриншота
        await asyncio.sleep(random_delay(0.5, 1.0))
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Твиты @{username}"
            )
        
        logger.info(f"✅ Твиты @{username} спарсены, найдено: {len(tweets_data)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в tweets: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск твитов с эмуляцией"""
    logger.info(f"📩 Команда /search от {update.effective_user.username} с аргументами: {context.args}")
    
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
        
        # Эмуляция перехода
        await goto_url(search_url)
        await asyncio.sleep(random_delay(2.0, 3.5))
        
        # Эмуляция прокрутки
        await human_scroll(await get_browser(), 400)
        await asyncio.sleep(random_delay(1.0, 2.0))
        
        tweets_data = await execute_js('''
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
        
        await asyncio.sleep(random_delay(0.5, 1.0))
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"🔍 Поиск: {query}"
            )
        
        logger.info(f"✅ Поиск '{query}' выполнен, найдено: {len(tweets_data)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в search: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API-запрос с сессией браузера (гибридная автоматизация)"""
    logger.info(f"📩 Команда /api от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        await update.message.reply_text(
            "ℹ️ **API запрос с сессией браузера**\n\n"
            "Использование: `/api <url>`\n"
            "Пример: `/api https://x.com/api/graphql/...`\n\n"
            "Запрос автоматически использует куки и заголовки от авторизованной сессии."
        )
        return
    
    url = context.args[0]
    msg = await update.message.reply_text(f"🌐 Выполняю API запрос: {url[:80]}...")
    
    try:
        result = await api_request('get', url)
        
        if result.get('error'):
            await msg.edit_text(f"❌ Ошибка: {result['error']}")
            return
        
        response_text = f"✅ **API запрос выполнен!**\n\n"
        response_text += f"📊 Статус: {result.get('status')}\n\n"
        
        data = result.get('data')
        if data:
            if isinstance(data, dict):
                data_str = json.dumps(data, indent=2, ensure_ascii=False)[:1500]
            else:
                data_str = str(data)[:1500]
            response_text += f"📝 **Данные:**\n```json\n{data_str}\n```"
        else:
            response_text += "⚠️ Данные не получены"
        
        if len(response_text) > 4000:
            filename = f"api_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 API ответ: {url[:50]}"
            )
            await msg.delete()
        else:
            await msg.edit_text(response_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"❌ Ошибка API: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Извлечение структурированных данных"""
    logger.info(f"📩 Команда /extract от {update.effective_user.username}")
    
    if not PYDANTIC_AVAILABLE:
        await update.message.reply_text(
            "❌ Pydantic не установлен.\n\n"
            "Используйте `/install_pydantic` для установки."
        )
        return
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📊 Извлекаю структурированные данные...")
    else:
        msg = await update.message.reply_text("📊 Извлекаю структурированные данные...")
    
    try:
        result = await extract_structured_data()
        
        if result.get('error'):
            await msg.edit_text(f"❌ Ошибка: {result['error']}")
            return
        
        count = result.get('count', 0)
        data = result.get('data', [])
        
        response_text = f"✅ **Извлечено {count} элементов**\n\n"
        
        for i, item in enumerate(data[:5], 1):
            if isinstance(item, dict):
                text = item.get('text', '')[:100]
                author = item.get('author', 'Неизвестно')
                response_text += f"**{i}.** {author}: {text}...\n\n"
        
        if count > 5:
            response_text += f"... и еще {count - 5} элементов\n\n"
        
        if data and len(data) > 0:
            filename = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Извлеченные данные ({count} элементов)"
            )
        
        await msg.edit_text(response_text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Демонстрация работы с Shadow DOM"""
    logger.info(f"📩 Команда /shadow от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Исследую Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    try:
        result = await shadow_dom_example()
        
        if result.get('error'):
            await msg.edit_text(f"❌ Ошибка: {result['error']}")
            return
        
        response_text = f"✅ **Shadow DOM**\n\n"
        response_text += f"📊 Результат: {json.dumps(result, indent=2, ensure_ascii=False)[:1000]}"
        
        await msg.edit_text(response_text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка Shadow DOM: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def install_pydantic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка Pydantic"""
    global PYDANTIC_AVAILABLE
    logger.info(f"📩 Команда /install_pydantic от {update.effective_user.username}")
    
    msg = await update.message.reply_text("⏳ Устанавливаю Pydantic...")
    
    if install_pydantic():
        await msg.edit_text("✅ Pydantic установлен успешно!\n\nТеперь доступны структурированные данные через /extract")
    else:
        await msg.edit_text("❌ Не удалось установить Pydantic")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот"""
    logger.info(f"📩 Команда /screen от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Делаю скриншот...")
    else:
        msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        # Эмуляция задержки перед скриншотом
        await asyncio.sleep(random_delay(0.5, 1.5))
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 Скриншот X.com\n🎮 Движок: {engine_mode}"
                )
            else:
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
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Проверяю статус...")
    else:
        msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        status_msg = "📊 **СТАТУС БОТА**\n\n"
        status_msg += f"🎮 Движок: **{engine_mode}**\n"
        status_msg += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        status_msg += f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        status_msg += f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}\n"
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
            if login_status['username'] and login_status['username'] != 'неизвестно':
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
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== КОМАНДА ДЛЯ ОБНОВЛЕНИЯ КУК ==========
async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление кук через Telegram"""
    global COOKIES
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(
            "🍪 **Обновление кук X.com**\n\n"
            "Отправьте куки в JSON формате:\n"
            "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\",\"path\":\"/\"}]`\n\n"
            "Или отправьте /cancel для отмены"
        )
    else:
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

# ========== ЗАПУСК ==========
def main():
    logger.info("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("engine", engine))
    app.add_handler(CommandHandler("close", close))
    
    # Расширенные команды Pydoll
    app.add_handler(CommandHandler("api", api))
    app.add_handler(CommandHandler("extract", extract))
    app.add_handler(CommandHandler("shadow", shadow))
    app.add_handler(CommandHandler("install_pydantic", install_pydantic))
    
    # Управление куками
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(login|screen|status|engine|tweets_menu|search_menu|api_menu|extract|shadow|close|setcookies)$"))
    app.add_handler(CallbackQueryHandler(engine_switch, pattern="^engine_(pydoll|playwright)$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    
    print("\n✅ Бот запущен!")
    print(f"🎮 Движок: {engine_mode}")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    print(f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды:")
    print("  Основные: /start, /login, /tweets, /search, /screen, /status, /engine, /close")
    print("  Расширенные: /api <url>, /extract, /shadow, /install_pydantic")
    print("  Куки: /setcookies, /cancel")
    print("\n💡 Нажмите /start для открытия меню с кнопками!")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()