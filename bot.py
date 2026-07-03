# bot.py - X.com бот с Pydoll + Playwright (полная версия)
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

# ========== ДИАГНОСТИЧЕСКАЯ КОМАНДА ==========
async def diagnos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная диагностика со всеми вариантами решения"""
    msg = await update.message.reply_text(
        "🔬 **ДИАГНОСТИКА ВСЕХ КОМАНД**\n\n"
        "⏳ Проверка с множеством вариантов...\n"
        "Это займет 3-5 минут."
    )
    
    log_file = f"diagnos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    diagnostic_log = []
    
    def log_diag(text, level="INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {text}"
        diagnostic_log.append(log_entry)
        logger.info(log_entry)
    
    def log_section(title):
        log_diag(f"\n{'='*70}")
        log_diag(f"📌 {title}")
        log_diag(f"{'='*70}")
    
    def log_error(command, error):
        log_diag(f"❌ ОШИБКА: {str(error)[:300]}", "ERROR")
        logger.error(f"Error in {command}: {error}", exc_info=True)
    
    def log_solution(command, solution):
        log_diag(f"💡 РЕШЕНИЕ для {command}: {solution}", "SOLUTION")
    
    results = {}
    solutions = {}
    
    try:
        # ============================================================
        # 1. ПРОВЕРКА БРАУЗЕРА
        # ============================================================
        log_section("1️⃣ ПРОВЕРКА БРАУЗЕРА")
        await msg.edit_text("🔬 1/7: Проверка браузера...")
        
        page = await get_browser()
        if page is None:
            log_diag("❌ Браузер не запущен", "ERROR")
            log_solution("Браузер", "Используйте /login для запуска браузера")
            await msg.edit_text("❌ Браузер не запущен. Используйте /login")
            return
        log_diag("✅ Браузер запущен")
        
        # Проверка авторизации
        if not login_status['is_logged_in']:
            log_diag("⚠️ Пользователь не авторизован", "WARNING")
            log_solution("Авторизация", "Используйте /login или обновите куки через /setcookies")
        
        # ============================================================
        # 2. SHADOW DOM - ВСЕ ВАРИАНТЫ
        # ============================================================
        log_section("2️⃣ SHADOW DOM - ВСЕ ВАРИАНТЫ")
        await msg.edit_text("🔬 2/7: Проверка Shadow DOM (3 варианта)...")
        
        shadow_results = []
        
        # Вариант 1: Поиск через JS
        try:
            log_diag("🔍 Вариант 1: Поиск элементов с shadowRoot через JS")
            js_shadow = """
                () => {
                    const elements = [];
                    document.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) {
                            elements.push({
                                tag: el.tagName,
                                id: el.id || '',
                                class: el.className || ''
                            });
                        }
                    });
                    return elements;
                }
            """
            shadow_elements = await page.execute_script(js_shadow)
            if shadow_elements and len(shadow_elements) > 0:
                log_diag(f"  ✅ Найдено {len(shadow_elements)} элементов с Shadow DOM")
                for el in shadow_elements[:3]:
                    log_diag(f"    📦 {el.get('tag', '')} id={el.get('id', '')}")
                shadow_results.append("Вариант 1: ✅ РАБОТАЕТ")
            else:
                log_diag("  ⚠️ Вариант 1: Элементы не найдены")
                shadow_results.append("Вариант 1: ⚠️ Не найдены")
        except Exception as e:
            log_error("Shadow DOM Вариант 1", e)
            shadow_results.append(f"Вариант 1: ❌ {str(e)[:30]}")
        
        # Вариант 2: Поиск конкретных элементов
        try:
            log_diag("🔍 Вариант 2: Поиск конкретных элементов")
            selectors = [
                ('GrokDrawer', '[data-testid="GrokDrawer"]'),
                ('GrokDrawerHeader', '[data-testid="GrokDrawerHeader"]'),
                ('chat-drawer-root', '[data-testid="chat-drawer-root"]'),
            ]
            found = False
            for name, selector in selectors:
                try:
                    host = await page.find(selector, timeout=2000)
                    if host and hasattr(host, 'get_shadow_root'):
                        shadow = await host.get_shadow_root()
                        if shadow:
                            log_diag(f"  ✅ {name}: Shadow DOM найден")
                            found = True
                except Exception as e:
                    log_diag(f"  ❌ {name}: {str(e)[:30]}")
            if found:
                shadow_results.append("Вариант 2: ✅ РАБОТАЕТ")
            else:
                shadow_results.append("Вариант 2: ⚠️ Не найдены")
        except Exception as e:
            log_error("Shadow DOM Вариант 2", e)
            shadow_results.append(f"Вариант 2: ❌ {str(e)[:30]}")
        
        # Вариант 3: Рекурсивный поиск
        try:
            log_diag("🔍 Вариант 3: Рекурсивный поиск shadowRoot")
            js_recursive = """
                () => {
                    function findShadowRoots(el) {
                        let results = [];
                        if (el.shadowRoot) {
                            results.push({
                                tag: el.tagName,
                                id: el.id || '',
                                class: el.className || ''
                            });
                        }
                        el.childNodes.forEach(child => {
                            if (child.nodeType === 1) {
                                results = results.concat(findShadowRoots(child));
                            }
                        });
                        return results;
                    }
                    return findShadowRoots(document.body);
                }
            """
            recursive_results = await page.execute_script(js_recursive)
            if recursive_results and len(recursive_results) > 0:
                log_diag(f"  ✅ Найдено {len(recursive_results)} элементов")
                shadow_results.append("Вариант 3: ✅ РАБОТАЕТ")
            else:
                shadow_results.append("Вариант 3: ⚠️ Не найдены")
        except Exception as e:
            log_error("Shadow DOM Вариант 3", e)
            shadow_results.append(f"Вариант 3: ❌ {str(e)[:30]}")
        
        # Итог по Shadow DOM
        if any("РАБОТАЕТ" in r for r in shadow_results):
            results["shadow"] = "✅ Работает"
            solutions["shadow"] = "Используйте работающий вариант из диагностики"
        else:
            results["shadow"] = "⚠️ Не найден"
            solutions["shadow"] = "Проверьте, что вы на странице X.com"
        
        # ============================================================
        # 3. API ЗАПРОС - ВСЕ ВАРИАНТЫ
        # ============================================================
        log_section("3️⃣ API ЗАПРОС - ВСЕ ВАРИАНТЫ")
        await msg.edit_text("🔬 3/7: Проверка API (3 варианта)...")
        
        api_results = []
        
        # Вариант 1: Fetch с credentials
        try:
            log_diag("🌐 Вариант 1: Fetch с credentials")
            test_url = "https://x.com/i/api/1.1/onboarding/task.json"
            js_fetch = f"""
                (async () => {{
                    try {{
                        const response = await fetch('{test_url}', {{
                            method: 'GET',
                            credentials: 'include',
                            headers: {{ 'Accept': 'application/json' }}
                        }});
                        const data = await response.json();
                        return {{
                            status: response.status,
                            ok: response.ok,
                            data: data
                        }};
                    }} catch (e) {{
                        return {{ error: e.message }};
                    }}
                }})()
            """
            result = await page.execute_script(js_fetch)
            if result and result.get('ok'):
                log_diag(f"  ✅ Успешно (статус: {result.get('status')})")
                api_results.append("Вариант 1: ✅ РАБОТАЕТ")
            else:
                status = result.get('status', 'unknown') if result else 'unknown'
                log_diag(f"  ⚠️ Статус: {status}")
                api_results.append(f"Вариант 1: ⚠️ Статус {status}")
        except Exception as e:
            log_error("API Вариант 1", e)
            api_results.append(f"Вариант 1: ❌ {str(e)[:30]}")
        
        # Вариант 2: XMLHttpRequest
        try:
            log_diag("🌐 Вариант 2: XMLHttpRequest")
            js_xhr = """
                (async () => {
                    return new Promise((resolve) => {
                        const xhr = new XMLHttpRequest();
                        xhr.open('GET', 'https://x.com/i/api/1.1/onboarding/task.json', true);
                        xhr.withCredentials = true;
                        xhr.setRequestHeader('Accept', 'application/json');
                        xhr.onload = function() {
                            resolve({
                                status: xhr.status,
                                ok: xhr.status >= 200 && xhr.status < 300,
                                data: JSON.parse(xhr.responseText)
                            });
                        };
                        xhr.onerror = function() {
                            resolve({ error: 'Network error' });
                        };
                        xhr.send();
                    });
                })()
            """
            xhr_result = await page.execute_script(js_xhr)
            if xhr_result and xhr_result.get('ok'):
                log_diag(f"  ✅ Успешно (статус: {xhr_result.get('status')})")
                api_results.append("Вариант 2: ✅ РАБОТАЕТ")
            else:
                log_diag(f"  ⚠️ Статус: {xhr_result.get('status', 'unknown')}")
                api_results.append(f"Вариант 2: ⚠️ Статус {xhr_result.get('status', 'unknown')}")
        except Exception as e:
            log_error("API Вариант 2", e)
            api_results.append(f"Вариант 2: ❌ {str(e)[:30]}")
        
        # Вариант 3: Прямой запрос через Pydoll
        try:
            log_diag("🌐 Вариант 3: Через Pydoll request")
            if hasattr(page, 'request'):
                response = await page.request.get('https://x.com/i/api/1.1/onboarding/task.json')
                if response and response.status == 200:
                    log_diag(f"  ✅ Успешно (статус: {response.status})")
                    api_results.append("Вариант 3: ✅ РАБОТАЕТ")
                else:
                    log_diag(f"  ⚠️ Статус: {response.status if response else 'unknown'}")
                    api_results.append(f"Вариант 3: ⚠️ Статус {response.status if response else 'unknown'}")
            else:
                log_diag("  ⚠️ Метод request не доступен")
                api_results.append("Вариант 3: ⚠️ Недоступен")
        except Exception as e:
            log_error("API Вариант 3", e)
            api_results.append(f"Вариант 3: ❌ {str(e)[:30]}")
        
        # Итог по API
        if any("РАБОТАЕТ" in r for r in api_results):
            results["api"] = "✅ Работает"
            solutions["api"] = "Используйте работающий вариант"
        else:
            results["api"] = "⚠️ Не работает"
            solutions["api"] = "Проверьте авторизацию и куки"
        
        # ============================================================
        # 4. EXTRACT - ВСЕ ВАРИАНТЫ
        # ============================================================
        log_section("4️⃣ EXTRACT - ВСЕ ВАРИАНТЫ")
        await msg.edit_text("🔬 4/7: Проверка Extract (3 варианта)...")
        
        extract_results = []
        
        # Вариант 1: Через Pydantic (если установлен)
        if PYDANTIC_AVAILABLE:
            try:
                log_diag("📊 Вариант 1: Через Pydantic")
                from pydoll.extractor import ExtractionModel, Field
                
                class TweetExtract(ExtractionModel):
                    text: str = Field(selector='[data-testid="tweetText"]')
                    author: str = Field(selector='[data-testid="User-Name"]')
                
                tweets = await page.extract_all(TweetExtract, scope='[data-testid="tweet"]')
                if tweets and len(tweets) > 0:
                    log_diag(f"  ✅ Извлечено {len(tweets)} элементов")
                    extract_results.append("Вариант 1: ✅ РАБОТАЕТ")
                else:
                    log_diag("  ⚠️ Данные не извлечены")
                    extract_results.append("Вариант 1: ⚠️ Нет данных")
            except Exception as e:
                log_error("Extract Вариант 1", e)
                extract_results.append(f"Вариант 1: ❌ {str(e)[:30]}")
        else:
            log_diag("⚠️ Pydantic не установлен")
            extract_results.append("Вариант 1: ⚠️ Pydantic не установлен")
        
        # Вариант 2: Через JS
        try:
            log_diag("📊 Вариант 2: Через JS")
            js_extract = """
                () => {
                    const tweets = [];
                    document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                        const textEl = el.querySelector('[data-testid="tweetText"]');
                        const userEl = el.querySelector('[data-testid="User-Name"]');
                        tweets.push({
                            text: textEl ? textEl.textContent : '',
                            author: userEl ? userEl.textContent : ''
                        });
                    });
                    return tweets.slice(0, 5);
                }
            """
            extracted = await page.execute_script(js_extract)
            if extracted and len(extracted) > 0:
                log_diag(f"  ✅ Извлечено {len(extracted)} элементов")
                extract_results.append("Вариант 2: ✅ РАБОТАЕТ")
            else:
                log_diag("  ⚠️ Данные не извлечены")
                extract_results.append("Вариант 2: ⚠️ Нет данных")
        except Exception as e:
            log_error("Extract Вариант 2", e)
            extract_results.append(f"Вариант 2: ❌ {str(e)[:30]}")
        
        # Вариант 3: Через querySelectorAll
        try:
            log_diag("📊 Вариант 3: Через querySelectorAll")
            js_query = """
                () => {
                    const tweets = [];
                    const elements = document.querySelectorAll('[data-testid="tweet"]');
                    elements.forEach((el, i) => {
                        if (i >= 3) return;
                        const text = el.querySelector('[data-testid="tweetText"]');
                        tweets.push(text ? text.textContent : '');
                    });
                    return tweets;
                }
            """
            query_results = await page.execute_script(js_query)
            if query_results and len(query_results) > 0:
                log_diag(f"  ✅ Найдено {len(query_results)} элементов")
                extract_results.append("Вариант 3: ✅ РАБОТАЕТ")
            else:
                log_diag("  ⚠️ Данные не найдены")
                extract_results.append("Вариант 3: ⚠️ Нет данных")
        except Exception as e:
            log_error("Extract Вариант 3", e)
            extract_results.append(f"Вариант 3: ❌ {str(e)[:30]}")
        
        # Итог по Extract
        if any("РАБОТАЕТ" in r for r in extract_results):
            results["extract"] = "✅ Работает"
            solutions["extract"] = "Используйте работающий вариант"
        else:
            results["extract"] = "⚠️ Не работает"
            solutions["extract"] = "Убедитесь, что на странице есть твиты"
        
        # ============================================================
        # 5. ПОИСК - ВСЕ ВАРИАНТЫ
        # ============================================================
        log_section("5️⃣ ПОИСК - ВСЕ ВАРИАНТЫ")
        await msg.edit_text("🔬 5/7: Проверка Поиска (3 варианта)...")
        
        search_results_combined = []
        
        test_queries = ["python", "ai", "news"]
        for query in test_queries[:2]:
            try:
                log_diag(f"🔍 Вариант с запросом: '{query}'")
                search_url = f"https://x.com/search?q={query}&src=typed_query"
                await page.go_to(search_url)
                await asyncio.sleep(2)
                
                js_search = """
                    () => {
                        const tweets = [];
                        document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                            const text = el.querySelector('[data-testid="tweetText"]');
                            if (text) tweets.push(text.textContent);
                        });
                        return tweets.slice(0, 3);
                    }
                """
                results = await page.execute_script(js_search)
                if results and len(results) > 0:
                    log_diag(f"  ✅ Найдено {len(results)} твитов")
                    search_results_combined.append(f"'{query}': ✅ {len(results)} результатов")
                else:
                    log_diag(f"  ⚠️ По запросу '{query}' ничего не найдено")
                    search_results_combined.append(f"'{query}': ⚠️ Нет результатов")
            except Exception as e:
                log_error(f"Поиск '{query}'", e)
                search_results_combined.append(f"'{query}': ❌ {str(e)[:30]}")
        
        # Итог по Поиску
        if any("✅" in r for r in search_results_combined):
            results["search"] = "✅ Работает"
            solutions["search"] = "Поиск работает. Используйте /search <запрос>"
        else:
            results["search"] = "⚠️ Не работает"
            solutions["search"] = "Проверьте соединение или попробуйте другой запрос"
        
        # ============================================================
        # 6. ТВИТЫ - ВСЕ ВАРИАНТЫ
        # ============================================================
        log_section("6️⃣ ТВИТЫ - ВСЕ ВАРИАНТЫ")
        await msg.edit_text("🔬 6/7: Проверка Твитов (3 варианта)...")
        
        tweets_results = []
        
        test_users = ["elonmusk", "x", "tech"]
        for username in test_users[:2]:
            try:
                log_diag(f"📊 Парсинг твитов: @{username}")
                await page.go_to(f"https://x.com/{username}")
                await asyncio.sleep(2)
                
                js_tweets = """
                    () => {
                        const tweets = [];
                        document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                            const text = el.querySelector('[data-testid="tweetText"]');
                            if (text) tweets.push(text.textContent);
                        });
                        return tweets.slice(0, 3);
                    }
                """
                tweets_data = await page.execute_script(js_tweets)
                if tweets_data and len(tweets_data) > 0:
                    log_diag(f"  ✅ Найдено {len(tweets_data)} твитов")
                    tweets_results.append(f"@{username}: ✅ {len(tweets_data)} твитов")
                else:
                    log_diag(f"  ⚠️ Твиты от @{username} не найдены")
                    tweets_results.append(f"@{username}: ⚠️ Нет твитов")
            except Exception as e:
                log_error(f"Твиты @{username}", e)
                tweets_results.append(f"@{username}: ❌ {str(e)[:30]}")
        
        # Итог по Твитам
        if any("✅" in r for r in tweets_results):
            results["tweets"] = "✅ Работает"
            solutions["tweets"] = "Парсинг работает. Используйте /tweets <username>"
        else:
            results["tweets"] = "⚠️ Не работает"
            solutions["tweets"] = "Проверьте, что пользователь существует"
        
        # ============================================================
        # 7. ВСЕ РЕШЕНИЯ
        # ============================================================
        log_section("7️⃣ ВСЕ РЕШЕНИЯ")
        await msg.edit_text("🔬 7/7: Сбор решений...")
        
        log_diag("\n📋 **ВСЕ ВАРИАНТЫ РЕШЕНИЙ:**")
        for cmd, solution in solutions.items():
            log_diag(f"  💡 {cmd.upper()}: {solution}")
        
        # ============================================================
        # 8. ИТОГИ
        # ============================================================
        log_section("8️⃣ ИТОГИ ДИАГНОСТИКИ")
        
        log_diag("\n📊 РЕЗУЛЬТАТЫ:")
        for cmd, status in results.items():
            log_diag(f"  {cmd.upper()}: {status}")
        
        # Подсчет успехов
        success_count = sum(1 for s in results.values() if "✅" in str(s))
        total = len(results)
        
        log_diag(f"\n✅ Успешно: {success_count}/{total}")
        
        if success_count == total:
            log_diag("🎉 ВСЕ КОМАНДЫ РАБОТАЮТ!")
        elif success_count >= total // 2:
            log_diag("⚠️ НЕКОТОРЫЕ КОМАНДЫ НЕ РАБОТАЮТ")
        else:
            log_diag("❌ БОЛЬШИНСТВО КОМАНД НЕ РАБОТАЮТ")
        
        # ============================================================
        # 9. ОТПРАВКА РЕЗУЛЬТАТОВ
        # ============================================================
        
        # Сохраняем лог
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        
        # Формируем отчет
        report = "🔬 **ДИАГНОСТИКА ЗАВЕРШЕНА**\n\n"
        report += f"📊 **Результаты:**\n"
        for cmd, status in results.items():
            emoji = "✅" if "✅" in str(status) else ("⚠️" if "⚠️" in str(status) else "❌")
            report += f"  {emoji} {cmd.upper()}: {status}\n"
        
        report += f"\n✅ Успешно: {success_count}/{total}\n\n"
        
        # Добавляем решения
        report += "📋 **РЕШЕНИЯ:**\n"
        for cmd, solution in solutions.items():
            report += f"  💡 {cmd.upper()}: {solution}\n"
        
        if success_count == total:
            report += "\n🎉 **ВСЕ КОМАНДЫ РАБОТАЮТ!**"
        elif success_count >= total // 2:
            report += "\n\n⚠️ **НЕКОТОРЫЕ КОМАНДЫ НЕ РАБОТАЮТ**"
            report += "\n📋 Проверьте лог-файл для деталей"
        else:
            report += "\n\n❌ **БОЛЬШИНСТВО КОМАНД НЕ РАБОТАЮТ**"
            report += "\n📋 Проверьте лог-файл для деталей"
        
        await msg.edit_text(report)
        
        # Отправляем лог-файл
        await update.message.reply_document(
            document=open(log_file, 'rb'),
            caption=f"📋 Лог диагностики\n{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        # Если есть ошибки - показываем их отдельно
        errors = [f"{cmd}: {status}" for cmd, status in results.items() if "❌" in str(status)]
        if errors:
            error_msg = "⚠️ **Обнаружены ошибки:**\n\n" + "\n".join(errors)
            await update.message.reply_text(error_msg)
        
    except Exception as e:
        log_diag(f"❌ Критическая ошибка: {e}", "ERROR")
        logger.error(f"Critical error: {e}", exc_info=True)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        
        await msg.edit_text(f"❌ Ошибка диагностики: {str(e)[:200]}")
        await update.message.reply_document(
            document=open(log_file, 'rb'),
            caption="📋 Лог ошибки"
        )

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое меню с кнопками"""
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
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
        [
            InlineKeyboardButton("🔬 Диагностика", callback_data="diagnos"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
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
    elif callback_data == "diagnos":
        await diagnos(update, context)

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

async def engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение между движками браузера через команду"""
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
    """Авторизация в X.com с эмуляцией"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(random_delay(2.0, 4.0))
        
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
        await goto_url(f"https://x.com/{username}")
        await asyncio.sleep(random_delay(2.0, 3.5))
        
        await human_scroll(await get_browser(), 500)
        await asyncio.sleep(random_delay(1.0, 2.0))
        
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
        
        await goto_url(search_url)
        await asyncio.sleep(random_delay(2.0, 3.5))
        
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
    """API-запрос с сессией браузера"""
    logger.info(f"📩 Команда /api от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        await update.message.reply_text(
            "ℹ️ **API запрос с сессией браузера**\n\n"
            "Использование: `/api <url>`\n"
            "Пример: `/api https://x.com/i/api/1.1/onboarding/task.json`\n\n"
            "⚠️ Запрос использует сессию браузера с вашими куками."
        )
        return
    
    url = context.args[0]
    msg = await update.message.reply_text(f"🌐 Выполняю API запрос: {url[:80]}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Браузер не запущен. Используйте /login")
            return
        
        if not login_status['is_logged_in']:
            await msg.edit_text("❌ Вы не авторизованы. Используйте /login")
            return
        
        js_code = f"""
            (async () => {{
                try {{
                    const response = await fetch('{url}', {{
                        method: 'GET',
                        credentials: 'include',
                        headers: {{
                            'Accept': 'application/json',
                        }}
                    }});
                    
                    const data = await response.json();
                    return {{
                        status: response.status,
                        ok: response.ok,
                        data: data
                    }};
                }} catch (e) {{
                    return {{
                        error: e.message,
                        status: 0
                    }};
                }}
            }})()
        """
        
        result = await page.execute_script(js_code)
        
        if result.get('error'):
            await msg.edit_text(f"❌ Ошибка: {result['error']}")
            return
        
        status = result.get('status', 0)
        data = result.get('data', {})
        
        response_text = f"✅ **API запрос выполнен!**\n\n"
        response_text += f"📊 Статус: {status}\n"
        response_text += f"📊 Успешно: {'✅' if result.get('ok') else '❌'}\n\n"
        
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
                json.dump(data, f, indent=2, ensure_ascii=False)
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
        # Используем JS вариант (более надежный)
        js_extract = """
            () => {
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const textEl = el.querySelector('[data-testid="tweetText"]');
                    const userEl = el.querySelector('[data-testid="User-Name"]');
                    tweets.push({
                        text: textEl ? textEl.textContent : '',
                        author: userEl ? userEl.textContent : ''
                    });
                });
                return tweets.slice(0, 10);
            }
        """
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        extracted = await page.execute_script(js_extract)
        
        if not extracted or len(extracted) == 0:
            await msg.edit_text("⚠️ Нет данных для извлечения")
            return
        
        count = len(extracted)
        response_text = f"✅ **Извлечено {count} элементов**\n\n"
        
        for i, item in enumerate(extracted[:5], 1):
            text = item.get('text', '')[:100] if isinstance(item, dict) else str(item)[:100]
            author = item.get('author', 'Неизвестно') if isinstance(item, dict) else 'Неизвестно'
            response_text += f"**{i}.** {author}: {text}...\n\n"
        
        if count > 5:
            response_text += f"... и еще {count - 5} элементов\n\n"
        
        if extracted and len(extracted) > 0:
            filename = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(extracted, f, indent=2, ensure_ascii=False)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Извлеченные данные ({count} элементов)"
            )
        
        await msg.edit_text(response_text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Работа с Shadow DOM"""
    logger.info(f"📩 Команда /shadow от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Исследую Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Браузер не запущен. Используйте /login")
            return
        
        # Ищем элементы с shadowRoot через JS
        js_shadow = """
            () => {
                const elements = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        elements.push({
                            tag: el.tagName,
                            id: el.id || '',
                            class: el.className || ''
                        });
                    }
                });
                return elements;
            }
        """
        shadow_elements = await page.execute_script(js_shadow)
        
        log_diag = "🛡️ **Shadow DOM**\n\n"
        
        if shadow_elements and len(shadow_elements) > 0:
            log_diag += f"✅ Найдено {len(shadow_elements)} элементов с Shadow DOM:\n\n"
            for el in shadow_elements[:5]:
                log_diag += f"• **{el.get('tag', '')}**"
                if el.get('id'):
                    log_diag += f" id=\"{el.get('id')}\""
                if el.get('class'):
                    log_diag += f" class=\"{el.get('class')}\""
                log_diag += "\n"
            
            log_diag += "\n💡 Как использовать:\n"
            log_diag += "```python\n"
            log_diag += "host = await tab.find('#shadow-host')\n"
            log_diag += "shadow_root = await host.get_shadow_root()\n"
            log_diag += "inner = await shadow_root.query('.inner-class')\n"
            log_diag += "```"
        else:
            log_diag += "⚠️ Shadow DOM элементы не найдены.\n\n"
            log_diag += "📌 **Что такое Shadow DOM?**\n"
            log_diag += "Это изолированная часть DOM, скрытая от основного документа.\n\n"
            log_diag += "📌 **Как найти:**\n"
            log_diag += "1. Откройте DevTools (F12)\n"
            log_diag += "2. Включите 'Show user agent shadow DOM'\n"
            log_diag += "3. Ищите элементы с #shadow-root\n\n"
            log_diag += "📌 **Пример кода:**\n"
            log_diag += "```python\n"
            log_diag += "host = await tab.find('#shadow-host')\n"
            log_diag += "shadow_root = await host.get_shadow_root()\n"
            log_diag += "inner = await shadow_root.query('.inner-class')\n"
            log_diag += "```"
        
        await msg.edit_text(log_diag, parse_mode='Markdown')
        
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
    
    # Диагностика
    app.add_handler(CommandHandler("diagnos", diagnos))
    
    # Управление куками
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(login|screen|status|engine|tweets_menu|search_menu|api_menu|extract|shadow|close|setcookies|diagnos)$"))
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
    print("  Диагностика: /diagnos")
    print("  Куки: /setcookies, /cancel")
    print("\n💡 Нажмите /start для открытия меню с кнопками!")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()