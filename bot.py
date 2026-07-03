# bot.py - X.com бот с Pydoll + Playwright (автоустановка)
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
BROWSER_USE_AVAILABLE = False
AGNES_AVAILABLE = False
CHROMIUM_INSTALLED = False

def check_chromium():
    """Проверяет, установлен ли Chromium в системе"""
    global CHROMIUM_INSTALLED
    logger.info("🔍 Проверяю наличие Chromium в системе...")
    
    try:
        result = subprocess.run(['chromium', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            CHROMIUM_INSTALLED = True
            version = result.stdout.strip()
            logger.info(f"✅ Chromium установлен: {version}")
            return True
    except Exception as e:
        logger.debug(f"Команда chromium --version не найдена: {e}")
    
    # Проверяем альтернативные пути
    chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
    for path in chromium_paths:
        if os.path.exists(path):
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден по пути: {path}")
            return True
    
    CHROMIUM_INSTALLED = False
    logger.warning("⚠️ Chromium не найден в системе")
    return False

def check_libraries():
    """Проверка всех библиотек"""
    global PYDOLL_AVAILABLE, PLAYWRIGHT_AVAILABLE
    logger.info("🔍 Проверяю установленные библиотеки...")
    
    # Проверка Pydoll
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
    
    # Проверка Playwright
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
    
    # Проверка Chromium
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
        
        logger.debug(f"STDOUT: {result.stdout[:500]}")
        if result.stderr:
            logger.debug(f"STDERR: {result.stderr[:500]}")
        
        if result.returncode == 0:
            logger.info("✅ Pydoll установлен успешно!")
            try:
                import pydoll
                PYDOLL_AVAILABLE = True
                logger.info(f"✅ Pydoll импортирован успешно (версия: {getattr(pydoll, '__version__', 'unknown')})")
                return True
            except ImportError as e:
                PYDOLL_AVAILABLE = False
                logger.error(f"❌ Не удалось импортировать Pydoll после установки: {e}")
                return False
        else:
            logger.error(f"❌ Ошибка установки Pydoll (код {result.returncode}): {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Исключение при установке Pydoll: {e}", exc_info=True)
        return False

def install_chromium():
    """Устанавливает Chromium в системе"""
    global CHROMIUM_INSTALLED
    logger.info("📦 Начинаю установку Chromium...")
    
    try:
        result = subprocess.run(['which', 'apt-get'], capture_output=True, text=True)
        logger.debug(f"apt-get path: {result.stdout}")
        
        if result.returncode == 0:
            logger.info("⏳ Установка через apt-get...")
            subprocess.run(['apt-get', 'update'], check=True, capture_output=True)
            logger.info("✅ Список пакетов обновлен")
            
            packages = [
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
            ]
            
            result = subprocess.run([
                'apt-get', 'install', '-y'
            ] + packages, capture_output=True, text=True)
            
            if result.returncode == 0:
                CHROMIUM_INSTALLED = True
                logger.info("✅ Chromium установлен через apt!")
                return True
            else:
                logger.error(f"❌ Ошибка установки Chromium: {result.stderr}")
                return False
        else:
            logger.warning("⚠️ apt-get не найден, пропускаю установку Chromium")
            return False
            
    except Exception as e:
        logger.error(f"❌ Исключение при установке Chromium: {e}", exc_info=True)
        return False

def install_playwright_browser():
    """Устанавливает браузер для Playwright"""
    logger.info("📦 Устанавливаю Playwright браузер...")
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'playwright', 'install', 'chromium'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Playwright браузер установлен!")
            return True
        else:
            logger.error(f"⚠️ Ошибка установки Playwright: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"⚠️ Исключение при установке Playwright: {e}", exc_info=True)
        return False

# ========== AGNES (БЕСПЛАТНАЯ LLM) ==========
agnes_llm = None

def init_agnes():
    """Инициализация Agnes через прямой API"""
    global AGNES_AVAILABLE, agnes_llm
    logger.info("🔍 Инициализация Agnes...")
    
    try:
        try:
            from langchain_openai import ChatOpenAI
            logger.info("✅ langchain-openai загружен")
        except ImportError:
            logger.info("⏳ Устанавливаю langchain-openai...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', 'langchain-openai'
            ], capture_output=True, text=True)
            from langchain_openai import ChatOpenAI
            logger.info("✅ langchain-openai установлен")
        
        api_key = os.environ.get("AGNES_API_KEY", "")
        if not api_key:
            logger.warning("⚠️ AGNES_API_KEY не задан в переменных окружения")
        
        llm = ChatOpenAI(
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            temperature=0.7,
            api_key=api_key,
        )
        
        logger.info("⏳ Проверка подключения к Agnes API...")
        test_response = llm.invoke("Test")
        if test_response:
            agnes_llm = llm
            AGNES_AVAILABLE = True
            logger.info(f"✅ Agnes загружена и работает!")
            return True
        else:
            logger.warning("⚠️ Agnes не отвечает (пустой ответ)")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Agnes: {e}", exc_info=True)
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

logger.info(f"🍪 Загружено {len(COOKIES)} кук для X.com")

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
pydoll_browser = None
pydoll_page = None
browser_lock = False
engine_mode = "pydoll"  # По умолчанию Pydoll
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

logger.info(f"🎮 Начальный движок: {engine_mode}")

# ========== PYDOLL БРАУЗЕР (ДЛЯ ВЕРСИИ 2.23.0) ==========
async def get_pydoll_browser():
    """Получает Pydoll браузер с человеческим поведением (для версии 2.23.0)"""
    global pydoll_browser, pydoll_page
    logger.info("🚀 Запрос на получение Pydoll браузера")
    
    if pydoll_browser and pydoll_page:
        logger.info("🔄 Проверка существующего браузера...")
        try:
            await pydoll_page.evaluate('1')
            logger.info("✅ Существующий браузер работает")
            return pydoll_page
        except Exception as e:
            logger.warning(f"⚠️ Существующий браузер не отвечает: {e}, пересоздаю...")
            await close_pydoll_browser()
    
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        logger.info("✅ Модули Pydoll импортированы")
        
        logger.info("🚀 Запускаю Pydoll браузер с ChromiumOptions...")
        
        options = ChromiumOptions()
        
        # Добавляем аргументы для Railway/контейнеров
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,720",
            "--headless=new",
        ]
        for arg in args:
            options.add_argument(arg)
            logger.debug(f"📌 Добавлен аргумент: {arg}")
        
        # Если Chromium установлен, указываем путь
        if CHROMIUM_INSTALLED:
            chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
            for path in chromium_paths:
                if os.path.exists(path):
                    options.binary_location = path
                    logger.info(f"📍 Использую Chromium по пути: {path}")
                    break
        
        # Запускаем браузер
        logger.info("⏳ Запуск браузера (может занять 10-30 секунд)...")
        pydoll_browser = await Chrome(options=options).start()
        logger.info("✅ Браузер запущен успешно!")
        
        # Получаем страницу (вкладку) - для версии 2.23.0
        pydoll_page = None
        logger.info("🔍 Пытаюсь получить страницу...")
        
        # Способ 1: через pages (основной способ в 2.23.0)
        if hasattr(pydoll_browser, 'pages'):
            logger.debug("📍 Проверяю атрибут pages")
            try:
                if isinstance(pydoll_browser.pages, list) and len(pydoll_browser.pages) > 0:
                    pydoll_page = pydoll_browser.pages[0]
                    logger.info("✅ Страница получена через pages[0]")
                elif hasattr(pydoll_browser.pages, '__aiter__'):
                    async for page in pydoll_browser.pages:
                        pydoll_page = page
                        logger.info("✅ Страница получена через async pages")
                        break
            except Exception as e:
                logger.error(f"⚠️ Ошибка при получении pages: {e}")
        else:
            logger.debug("📍 Атрибут pages отсутствует")
        
        # Способ 2: через tabs
        if not pydoll_page and hasattr(pydoll_browser, 'tabs'):
            logger.debug("📍 Проверяю атрибут tabs")
            try:
                if isinstance(pydoll_browser.tabs, list) and len(pydoll_browser.tabs) > 0:
                    pydoll_page = pydoll_browser.tabs[0]
                    logger.info("✅ Страница получена через tabs[0]")
            except Exception as e:
                logger.error(f"⚠️ Ошибка при получении tabs: {e}")
        
        # Способ 3: через current_page
        if not pydoll_page and hasattr(pydoll_browser, 'current_page'):
            logger.debug("📍 Проверяю атрибут current_page")
            try:
                if callable(pydoll_browser.current_page):
                    pydoll_page = await pydoll_browser.current_page()
                else:
                    pydoll_page = pydoll_browser.current_page
                if pydoll_page:
                    logger.info("✅ Страница получена через current_page")
            except Exception as e:
                logger.error(f"⚠️ Ошибка при получении current_page: {e}")
        
        # Способ 4: через new_page (создаем новую)
        if not pydoll_page and hasattr(pydoll_browser, 'new_page'):
            logger.debug("📍 Пытаюсь создать новую страницу через new_page")
            try:
                if callable(pydoll_browser.new_page):
                    pydoll_page = await pydoll_browser.new_page()
                else:
                    pydoll_page = pydoll_browser.new_page
                if pydoll_page:
                    logger.info("✅ Страница создана через new_page")
            except Exception as e:
                logger.error(f"⚠️ Ошибка при создании new_page: {e}")
        
        # Способ 5: через get_page
        if not pydoll_page and hasattr(pydoll_browser, 'get_page'):
            logger.debug("📍 Проверяю метод get_page")
            try:
                if callable(pydoll_browser.get_page):
                    pydoll_page = await pydoll_browser.get_page()
                else:
                    pydoll_page = pydoll_browser.get_page
                if pydoll_page:
                    logger.info("✅ Страница получена через get_page")
            except Exception as e:
                logger.error(f"⚠️ Ошибка при вызове get_page: {e}")
        
        # Если ничего не сработало
        if not pydoll_page:
            logger.error("❌ Не удалось получить страницу браузера!")
            attrs = dir(pydoll_browser)
            logger.debug(f"📋 Доступные атрибуты браузера: {attrs}")
            raise Exception("Не удалось получить страницу браузера")
        
        # Устанавливаем куки
        logger.info("🍪 Устанавливаю куки для X.com...")
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await pydoll_page.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
                cookies_set += 1
                logger.debug(f"🍪 Установлена кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка установки куки {cookie['name']}: {e}")
        
        logger.info(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        logger.info("✅ Pydoll браузер полностью готов!")
        return pydoll_page
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта Pydoll: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Pydoll ошибка: {e}", exc_info=True)
        return None

async def close_pydoll_browser():
    """Закрывает Pydoll браузер"""
    global pydoll_browser, pydoll_page
    logger.info("📌 Закрываю Pydoll браузер...")
    
    if pydoll_browser:
        try:
            await pydoll_browser.stop()
            logger.info("✅ Pydoll браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии Pydoll: {e}")
        pydoll_browser = None
        pydoll_page = None
    else:
        logger.info("📌 Браузер уже закрыт")

# ========== PLAYWRIGHT БРАУЗЕР ==========
async def get_playwright_browser():
    """Получает Playwright браузер"""
    global browser_data, browser_lock
    logger.info("🚀 Запрос на получение Playwright браузера")
    
    if browser_data:
        logger.info("🔄 Проверка существующего браузера...")
        try:
            await browser_data['page'].evaluate('1')
            logger.info("✅ Существующий браузер работает")
            return browser_data
        except Exception as e:
            logger.warning(f"⚠️ Существующий браузер не отвечает: {e}, пересоздаю...")
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    while browser_lock:
        logger.debug("⏳ Ожидание освобождения блокировки...")
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        from playwright.async_api import async_playwright
        
        logger.info("🚀 Запускаю Playwright браузер...")
        
        p = await async_playwright().start()
        logger.debug("✅ Playwright запущен")
        
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
        logger.info("✅ Chromium запущен")
        
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
        logger.info("✅ Создана новая страница")
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} } };
        """)
        logger.debug("✅ Добавлен init-скрипт")
        
        logger.info("🍪 Устанавливаю куки...")
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
                logger.debug(f"🍪 Установлена кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Cookie error {cookie['name']}: {e}")
        
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
            logger.info("✅ Playwright браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии Playwright: {e}")
        browser_data = None
        login_status = {
            'is_logged_in': False,
            'username': None,
            'last_check': None,
            'cookies_valid': False
        }
    else:
        logger.info("📌 Браузер уже закрыт")

# ========== УНИВЕРСАЛЬНЫЙ БРАУЗЕР ==========
async def get_browser():
    """Получает браузер согласно выбранному движку"""
    global engine_mode
    logger.info(f"🎮 Получение браузера для движка: {engine_mode}")
    
    if engine_mode == "pydoll":
        if not PYDOLL_AVAILABLE:
            error_msg = "Pydoll не установлен! Используйте /engine pydoll для установки"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
        return await get_pydoll_browser()
    elif engine_mode == "playwright":
        if not PLAYWRIGHT_AVAILABLE:
            error_msg = "Playwright не установлен!"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
        browser_data = await get_playwright_browser()
        return browser_data['page'] if browser_data else None
    else:
        error_msg = f"Неизвестный движок: {engine_mode}"
        logger.error(f"❌ {error_msg}")
        raise Exception(error_msg)

async def close_browser():
    """Закрывает браузер согласно выбранному движку"""
    global engine_mode
    logger.info(f"📌 Закрытие браузера для движка: {engine_mode}")
    
    if engine_mode == "pydoll":
        await close_pydoll_browser()
    elif engine_mode == "playwright":
        await close_playwright_browser()

async def take_screenshot():
    """Делает скриншот согласно выбранному движку"""
    logger.info(f"📸 Создание скриншота (движок: {engine_mode})")
    
    try:
        if engine_mode == "pydoll":
            page = await get_pydoll_browser()
            if page:
                screenshot = await page.screenshot()
                logger.info(f"✅ Скриншот создан (размер: {len(screenshot)} байт)")
                return screenshot
        else:
            browser = await get_playwright_browser()
            if browser:
                page = browser['page']
                screenshot = await page.screenshot(type='jpeg', quality=80)
                logger.info(f"✅ Скриншот создан (размер: {len(screenshot)} байт)")
                return screenshot
        logger.warning("⚠️ Не удалось создать скриншот - страница не найдена")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}", exc_info=True)
        return None

async def goto_url(url):
    """Переход по URL согласно выбранному движку"""
    logger.info(f"🌐 Переход по URL: {url} (движок: {engine_mode})")
    
    try:
        if engine_mode == "pydoll":
            page = await get_pydoll_browser()
            if page:
                await page.go_to(url)
                logger.info(f"✅ Переход выполнен: {url}")
                return
        else:
            browser = await get_playwright_browser()
            if browser:
                page = browser['page']
                await page.goto(url, wait_until='domcontentloaded')
                logger.info(f"✅ Переход выполнен: {url}")
                return
        raise Exception("Не удалось перейти по URL")
    except Exception as e:
        logger.error(f"❌ Ошибка при переходе: {e}", exc_info=True)
        raise

async def evaluate_js(script):
    """Выполнение JS согласно выбранному движку"""
    logger.debug(f"📜 Выполнение JS (движок: {engine_mode})")
    
    try:
        if engine_mode == "pydoll":
            page = await get_pydoll_browser()
            if page:
                result = await page.evaluate(script)
                logger.debug(f"✅ JS выполнен")
                return result
        else:
            browser = await get_playwright_browser()
            if browser:
                page = browser['page']
                result = await page.evaluate(script)
                logger.debug(f"✅ JS выполнен")
                return result
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении JS: {e}", exc_info=True)
        return None

async def wait_for_selector(selector, timeout=15000):
    """Ожидание элемента согласно выбранному движку"""
    logger.info(f"⏳ Ожидание элемента: {selector} (таймаут: {timeout}ms)")
    
    try:
        if engine_mode == "pydoll":
            page = await get_pydoll_browser()
            if page:
                await page.wait_for_element(selector, timeout=timeout/1000)
                logger.info(f"✅ Элемент найден: {selector}")
                return
        else:
            browser = await get_playwright_browser()
            if browser:
                page = browser['page']
                await page.wait_for_selector(selector, timeout=timeout)
                logger.info(f"✅ Элемент найден: {selector}")
                return
        raise Exception(f"Элемент {selector} не найден")
    except Exception as e:
        logger.error(f"❌ Ошибка при ожидании элемента: {e}", exc_info=True)
        raise

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🎮 Движок: {'Pydoll' if engine_mode == 'pydoll' else 'Playwright'}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n\n"
        f"📌 Команды:\n"
        f"/engine - Переключить движок (автоустановка)\n"
        f"/login - Авторизация в X.com\n"
        f"/screen - Скриншот\n"
        f"/status - Статус браузера\n"
        f"/close - Закрыть браузер\n"
        f"/tweets <username> - Твиты пользователя\n"
        f"/search <запрос> - Поиск твитов\n"
        f"/browse <задача> - AI задача в браузере\n"
        f"/agnes - Статус Agnes",
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ Ответ на /start отправлен")

async def engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение между движками браузера с автоустановкой"""
    global engine_mode, PYDOLL_AVAILABLE, PLAYWRIGHT_AVAILABLE, CHROMIUM_INSTALLED
    logger.info(f"📩 Команда /engine от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        current = "Pydoll" if engine_mode == "pydoll" else "Playwright"
        status = ""
        if engine_mode == "pydoll" and not PYDOLL_AVAILABLE:
            status = " (⚠️ Pydoll не установлен!)"
        elif engine_mode == "playwright" and not PLAYWRIGHT_AVAILABLE:
            status = " (⚠️ Playwright не установлен!)"
        
        await update.message.reply_text(
            f"🔧 Текущий движок: **{current}**{status}\n\n"
            f"Доступные движки:\n"
            f"  /engine playwright - Playwright (стабильный)\n"
            f"  /engine pydoll - Pydoll (человеческое поведение)\n\n"
            f"ℹ️ Pydoll лучше для обхода антибот-систем\n"
            f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
            f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
            f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}"
        )
        return
    
    engine_type = context.args[0].lower()
    msg = await update.message.reply_text(f"⏳ Переключаю на {engine_type}...")
    logger.info(f"🔄 Переключение на движок: {engine_type}")
    
    if engine_type == "pydoll":
        if not CHROMIUM_INSTALLED:
            logger.info("📦 Chromium не найден, начинаю установку...")
            await msg.edit_text("📦 Chromium не найден. Устанавливаю...")
            if install_chromium():
                CHROMIUM_INSTALLED = True
                logger.info("✅ Chromium установлен")
                await msg.edit_text("✅ Chromium установлен!")
            else:
                logger.warning("⚠️ Не удалось установить Chromium автоматически")
                await msg.edit_text("⚠️ Не удалось установить Chromium автоматически. Продолжаю...")
        
        if not PYDOLL_AVAILABLE:
            logger.info("📦 Pydoll не найден, начинаю установку...")
            await msg.edit_text("📦 Устанавливаю Pydoll...")
            if install_pydoll():
                PYDOLL_AVAILABLE = True
                logger.info("✅ Pydoll установлен")
                await msg.edit_text("✅ Pydoll установлен!")
            else:
                logger.error("❌ Не удалось установить Pydoll")
                await msg.edit_text("❌ Не удалось установить Pydoll")
                return
        
        await close_browser()
        engine_mode = "pydoll"
        logger.info(f"✅ Переключено на Pydoll")
        
        await msg.edit_text(
            "✅ **Переключено на Pydoll!**\n"
            "Теперь браузер будет с человеческим поведением!\n\n"
            "Используй /login для авторизации"
        )
        
    elif engine_type == "playwright":
        if not PLAYWRIGHT_AVAILABLE:
            logger.info("📦 Playwright не найден, начинаю установку...")
            await msg.edit_text("📦 Устанавливаю Playwright...")
            try:
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install', 'playwright'
                ], check=True, capture_output=True)
                PLAYWRIGHT_AVAILABLE = True
                logger.info("✅ Playwright установлен")
                await msg.edit_text("✅ Playwright установлен!")
            except Exception as e:
                logger.error(f"❌ Не удалось установить Playwright: {e}")
                await msg.edit_text(f"❌ Не удалось установить Playwright: {e}")
                return
        
        await msg.edit_text("📦 Устанавливаю браузер для Playwright...")
        if install_playwright_browser():
            logger.info("✅ Браузер для Playwright установлен")
            await msg.edit_text("✅ Браузер для Playwright установлен!")
        else:
            logger.warning("⚠️ Не удалось установить браузер")
            await msg.edit_text("⚠️ Не удалось установить браузер, но попробуем...")
        
        await close_browser()
        engine_mode = "playwright"
        logger.info(f"✅ Переключено на Playwright")
        
        await msg.edit_text(
            "✅ **Переключено на Playwright!**\n\n"
            "Используй /login для авторизации"
        )
    else:
        logger.warning(f"⚠️ Неизвестный движок: {engine_type}")
        await msg.edit_text(
            f"❌ Неизвестный движок: {engine_type}\n"
            f"Доступно: playwright, pydoll"
        )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com через выбранный движок"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        logger.info(f"🔍 Получение браузера для {engine_mode}")
        page = await get_browser()
        if not page:
            logger.error(f"❌ Не удалось запустить {engine_mode} браузер")
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        logger.info("🌐 Переход на X.com...")
        await goto_url('https://x.com')
        await asyncio.sleep(3)
        
        logger.info("🔍 Проверка авторизации...")
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
        
        logger.info(f"📊 Статус авторизации: isLoggedIn={auth_status['isLoggedIn']}, username={auth_status.get('username')}")
        
        global login_status
        login_status['is_logged_in'] = auth_status['isLoggedIn']
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status['hasAuthToken'] and auth_status['hasCt0']
        
        status_msg = f"✅ X.com ({engine_mode})\n\n"
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
        
        try:
            logger.info("📸 Создание скриншота...")
            screenshot = await take_screenshot()
            if screenshot:
                await update.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 X.com - {'✅ Авторизован' if auth_status['isLoggedIn'] else '❌ Не авторизован'}"
                )
                logger.info("✅ Скриншот отправлен")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании скриншота: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот текущей страницы"""
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
            logger.info("✅ Скриншот отправлен")
        else:
            logger.warning("⚠️ Не удалось сделать скриншот")
            await msg.edit_text("❌ Не удалось сделать скриншот")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в screen: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус бота"""
    logger.info(f"📩 Команда /status от {update.effective_user.username}")
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        status_msg = "📊 **СТАТУС БОТА**\n\n"
        
        status_msg += f"🎮 Текущий движок: **{engine_mode}**\n"
        status_msg += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        status_msg += f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        status_msg += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
        status_msg += f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}\n\n"
        
        try:
            if engine_mode == "pydoll":
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
        except Exception as e:
            status_msg += f"🌐 Браузер: ❌ Не запущен\n"
        
        status_msg += "\n🔐 **АВТОРИЗАЦИЯ:**\n"
        if login_status['is_logged_in']:
            status_msg += f"✅ Авторизован\n"
            if login_status['username']:
                status_msg += f"👤 @{login_status['username']}\n"
        else:
            status_msg += "❌ Не авторизован\n"
        
        status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await msg.edit_text(status_msg, parse_mode='Markdown')
        logger.info("✅ Статус отправлен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в status: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    logger.info(f"📩 Команда /close от {update.effective_user.username}")
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")
    logger.info("✅ Браузер закрыт по команде")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг твитов пользователя"""
    logger.info(f"📩 Команда /tweets от {update.effective_user.username} с аргументами: {context.args}")
    
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
        
        logger.info(f"✅ Твиты @{username} спарсены, найдено: {len(tweets_data)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в tweets: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск твитов"""
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
        
        logger.info(f"✅ Поиск '{query}' выполнен, найдено: {len(tweets_data)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в search: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить задачу в браузере через AI"""
    logger.info(f"📩 Команда /browse от {update.effective_user.username} с аргументами: {context.args}")
    
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
        
        agent = Agent(
            task=task,
            llm=agnes_llm,
            use_vision=False,
        )
        
        await msg.edit_text(f"🧠 Agnes думает над задачей: {task[:100]}...")
        logger.info(f"🧠 Запуск агента с задачей: {task}")
        
        result = await agent.run()
        logger.info(f"✅ Агент завершил работу")
        
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
        logger.error(f"❌ Ошибка импорта browser_use: {e}")
        await msg.edit_text(f"❌ Ошибка импорта: {str(e)[:200]}")
    except Exception as e:
        logger.error(f"❌ Ошибка в browse: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса Agnes"""
    logger.info(f"📩 Команда /agnes от {update.effective_user.username}")
    
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
    logger.info("🚀 Запуск бота...")
    logger.info(f"📊 Текущий движок: {engine_mode}")
    logger.info(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    logger.info(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    logger.info(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    logger.info(f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("engine", engine))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("agnes", agnes))
    
    logger.info("✅ Бот запущен и готов к работе!")
    print("\n✅ Бот запущен!")
    print(f"🎮 Движок: {engine_mode}")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print(f"🧠 Agnes: {'✅' if AGNES_AVAILABLE else '❌'}")
    print("\nКоманды:")
    print("  /start, /login, /screen, /status, /engine, /close")
    print("  /tweets, /search, /browse, /agnes")
    print("\n📋 Подробные логи пишутся в bot.log")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()