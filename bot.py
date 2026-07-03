# bot.py - X.com бот с Pydoll + Playwright
import os
import sys
import subprocess
import logging
import asyncio
import base64
from datetime import datetime
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
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
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
            # Используем execute_script вместо evaluate
            if hasattr(pydoll_tab, 'execute_script'):
                await pydoll_tab.execute_script('1')
            else:
                await pydoll_tab.evaluate('1')
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
        
        # Находим Chromium
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
        
        # Добавляем аргументы (рабочий вариант из диагностики)
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
        
        logger.info("🍪 Устанавливаю куки для X.com...")
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
                logger.debug(f"🍪 Установлена кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка установки куки {cookie['name']}: {e}")
        
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
    """Переход по URL с повторными попытками"""
    logger.info(f"🌐 Переход по URL: {url}")
    
    page = await get_browser()
    if page is None:
        raise Exception("Не удалось получить страницу")
    
    for attempt in range(3):
        try:
            if hasattr(page, 'go_to'):
                await page.go_to(url)
            elif hasattr(page, 'goto'):
                await page.goto(url, wait_until='domcontentloaded')
            else:
                raise Exception(f"Неизвестный тип страницы: {type(page)}")
            
            await asyncio.sleep(3)
            logger.info(f"✅ Переход выполнен: {url}")
            return
        except Exception as e:
            logger.error(f"❌ Попытка {attempt + 1} перехода failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
            else:
                raise

async def execute_js(script):
    """Выполнение JS с поддержкой обоих методов"""
    logger.debug(f"📜 Выполнение JS")
    
    page = await get_browser()
    if page is None:
        logger.error("❌ Страница не получена для выполнения JS")
        return None
    
    try:
        # Пробуем execute_script (новый метод в Pydoll 2.23.0)
        if hasattr(page, 'execute_script'):
            result = await page.execute_script(script)
            logger.debug(f"✅ JS выполнен через execute_script")
            return result
        # Пробуем evaluate (старый метод)
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

# ========== РАСШИРЕННАЯ ДИАГНОСТИЧЕСКАЯ КОМАНДА ==========
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расширенная диагностика Pydoll с множеством вариантов"""
    msg = await update.message.reply_text("🔍 Запуск расширенной диагностики Pydoll...\nЭто может занять 2-3 минуты.")
    
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
            '/usr/bin/google-chrome-stable',
            '/snap/bin/chromium',
            '/usr/lib/chromium-browser/chromium-browser'
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
            try:
                files = os.listdir('/usr/bin')
                chrome_files = [f for f in files if 'chrome' in f.lower() or 'chromium' in f.lower()]
                log_diag(f"Найдены похожие файлы: {chrome_files[:10]}")
            except:
                pass
            await msg.edit_text("❌ Chromium не найден! Невозможно продолжить.")
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(diagnostic_log))
            await update.message.reply_document(document=open(log_file, 'rb'), caption="📋 Лог диагностики")
            return
        
        log_diag(f"✅ Chromium найден: {found}")
        await msg.edit_text(f"✅ Chromium найден: {found}\n\n2️⃣ Проверяю импорт Pydoll...")
        
        # 2. Проверка импорта
        log_diag("=== ПРОВЕРКА ИМПОРТА ===")
        try:
            from pydoll.browser import Chrome
            from pydoll.browser.options import ChromiumOptions
            log_diag("✅ Pydoll импортирован успешно")
        except Exception as e:
            log_diag(f"❌ Ошибка импорта: {e}")
            await msg.edit_text(f"❌ Ошибка импорта: {e}")
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(diagnostic_log))
            await update.message.reply_document(document=open(log_file, 'rb'), caption="📋 Лог диагностики")
            return
        
        await msg.edit_text("✅ Pydoll импортирован\n\n3️⃣ Запуск всех вариантов...")
        
        # 3. Тестируем все варианты
        variants = [
            {"name": "Стандартный запуск", "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--headless=new"]},
            {"name": "Расширенные аргументы", "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--headless=new", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled", "--window-size=1280,720"]},
            {"name": "С user-data-dir", "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--headless=new", "--user-data-dir=/tmp/chromium-profile"]},
            {"name": "С remote-debugging-port", "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--headless=new", "--remote-debugging-port=9222"]},
            {"name": "Без headless", "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]},
            {"name": "Только --no-sandbox", "args": ["--no-sandbox"]},
            {"name": "Минимальный набор", "args": ["--no-sandbox", "--headless=new"]},
        ]
        
        working_variant = None
        variant_results = []
        
        for i, variant in enumerate(variants, 1):
            variant_name = variant["name"]
            log_diag(f"\n=== ВАРИАНТ {i}: {variant_name} ===")
            log_diag(f"Аргументы: {variant['args']}")
            await msg.edit_text(f"🔄 Вариант {i}/{len(variants)}: {variant_name}...")
            
            try:
                options = ChromiumOptions()
                options.binary_location = found
                for arg in variant["args"]:
                    options.add_argument(arg)
                
                browser = Chrome(options=options)
                tab = await browser.start()
                log_diag("✅ Браузер запущен!")
                
                # Переход на Google
                log_diag("🌐 Переход на google.com...")
                await tab.go_to('https://www.google.com')
                await asyncio.sleep(2)
                
                # Используем execute_script вместо evaluate
                title = await tab.execute_script('document.title')
                log_diag(f"📄 Заголовок: {title}")
                
                # Скриншот Google
                log_diag("📸 Скриншот Google...")
                screenshot_b64 = await tab.take_screenshot(as_base64=True)
                if screenshot_b64:
                    screenshot = base64.b64decode(screenshot_b64)
                    log_diag(f"✅ Скриншот Google: {len(screenshot)} байт")
                    await update.message.reply_photo(photo=screenshot, caption=f"📸 Вариант {i}: {variant_name} - Google")
                else:
                    log_diag("⚠️ Скриншот Google не удался")
                
                # Переход на X.com
                log_diag("🌐 Переход на x.com...")
                await tab.go_to('https://x.com')
                await asyncio.sleep(3)
                title_x = await tab.execute_script('document.title')
                log_diag(f"📄 Заголовок X.com: {title_x}")
                
                # Скриншот X.com
                log_diag("📸 Скриншот X.com...")
                screenshot_b64_x = await tab.take_screenshot(as_base64=True)
                if screenshot_b64_x:
                    screenshot_x = base64.b64decode(screenshot_b64_x)
                    log_diag(f"✅ Скриншот X.com: {len(screenshot_x)} байт")
                    await update.message.reply_photo(photo=screenshot_x, caption=f"📸 Вариант {i}: {variant_name} - X.com")
                else:
                    log_diag("⚠️ Скриншот X.com не удался")
                
                # Закрытие
                await browser.close()
                log_diag("✅ Браузер закрыт")
                
                variant_results.append(f"✅ Вариант {i} ({variant_name}) - РАБОТАЕТ!")
                if working_variant is None:
                    working_variant = variant
                    log_diag(f"🎯 РАБОЧИЙ ВАРИАНТ: {variant_name}")
                
            except Exception as e:
                log_diag(f"❌ Ошибка: {str(e)[:200]}")
                variant_results.append(f"❌ Вариант {i} ({variant_name}) - НЕ РАБОТАЕТ: {str(e)[:100]}")
                try:
                    await browser.close()
                except:
                    pass
        
        # 4. Итог
        await msg.edit_text("📊 Диагностика завершена! Формирую отчет...")
        log_diag("\n=== РЕЗУЛЬТАТЫ ===")
        for result in variant_results:
            log_diag(result)
        
        if working_variant:
            log_diag(f"\n🎯 РАБОЧИЙ ВАРИАНТ: {working_variant['name']}")
            log_diag(f"Аргументы: {working_variant['args']}")
        else:
            log_diag("\n❌ НЕ ОДИН ВАРИАНТ НЕ СРАБОТАЛ!")
        
        # Отправляем лог-файл
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        
        await update.message.reply_document(
            document=open(log_file, 'rb'), 
            caption=f"📋 Лог диагностики\n{'✅ Найден рабочий вариант!' if working_variant else '❌ Рабочий вариант не найден'}"
        )
        
        if working_variant:
            await msg.edit_text(
                f"✅ **Диагностика завершена!**\n\n"
                f"🎯 Найден рабочий вариант: **{working_variant['name']}**\n"
                f"Аргументы: `{' '.join(working_variant['args'])}`\n\n"
                f"📋 Полный лог отправлен файлом."
            )
        else:
            await msg.edit_text(
                f"❌ **Диагностика завершена!**\n\n"
                f"Ни один вариант не сработал.\n"
                f"📋 Полный лог отправлен файлом для анализа."
            )
            
    except Exception as e:
        log_diag(f"❌ Критическая ошибка: {e}")
        logger.error(f"Critical test error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Критическая ошибка: {str(e)[:200]}")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(diagnostic_log))
        await update.message.reply_document(document=open(log_file, 'rb'), caption="📋 Лог диагностики (с ошибкой)")

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🎮 Движок: {'Pydoll' if engine_mode == 'pydoll' else 'Playwright'}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
        f"📍 Путь: {CHROMIUM_PATH or 'не найден'}\n\n"
        f"📌 Команды:\n"
        f"/engine pydoll - Переключиться на Pydoll\n"
        f"/engine playwright - Переключиться на Playwright\n"
        f"/login - Авторизация в X.com\n"
        f"/screen - Скриншот\n"
        f"/status - Статус браузера\n"
        f"/close - Закрыть браузер\n"
        f"/test - Расширенная диагностика Pydoll",
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
            f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
            f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}"
        )
        return
    
    engine_type = context.args[0].lower()
    msg = await update.message.reply_text(f"⏳ Переключаю на {engine_type}...")
    
    if engine_type == "pydoll":
        if not CHROMIUM_INSTALLED:
            await msg.edit_text("📦 Chromium не найден. Устанавливаю...")
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
        await msg.edit_text("✅ **Переключено на Pydoll!**\nИспользуй /login для авторизации")
        
    elif engine_type == "playwright":
        if not PLAYWRIGHT_AVAILABLE:
            await msg.edit_text("📦 Playwright не установлен. Устанавливаю...")
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
        await msg.edit_text("✅ **Переключено на Playwright!**\nИспользуй /login для авторизации")
    else:
        await msg.edit_text(f"❌ Неизвестный движок: {engine_type}")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com через выбранный движок"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        logger.info("✅ Браузер получен, перехожу на X.com...")
        
        await goto_url('https://x.com')
        
        logger.info("⏳ Ожидание загрузки страницы...")
        await asyncio.sleep(5)
        
        try:
            title = await execute_js('document.title')
            logger.info(f"📄 Заголовок страницы: {title}")
        except Exception as e:
            logger.error(f"❌ Не удалось получить заголовок: {e}")
        
        auth_status = None
        for attempt in range(3):
            logger.info(f"🔄 Попытка проверки авторизации {attempt + 1}/3...")
            try:
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
                            isLoggedIn: !!(hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav),
                            url: window.location.href,
                            title: document.title || ''
                        };
                    }
                ''')
                
                if auth_status is not None:
                    logger.info(f"✅ Авторизация проверена")
                    break
                else:
                    logger.warning(f"⚠️ Попытка {attempt + 1} вернула None")
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"❌ Ошибка при попытке {attempt + 1}: {e}")
                await asyncio.sleep(2)
        
        if auth_status is None:
            logger.error("❌ Не удалось проверить авторизацию после 3 попыток")
            try:
                screenshot = await take_screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        photo=screenshot,
                        caption="📸 Диагностический скриншот страницы"
                    )
            except:
                pass
            await msg.edit_text("❌ Не удалось проверить авторизацию. Попробуйте позже.")
            return
        
        global login_status
        login_status['is_logged_in'] = auth_status.get('isLoggedIn', False)
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False) and auth_status.get('hasCt0', False)
        
        status_msg = f"✅ X.com ({engine_mode})\n\n"
        status_msg += f"📍 URL: {auth_status.get('url', 'неизвестно')}\n"
        status_msg += f"📄 Заголовок: {auth_status.get('title', 'неизвестно')}\n\n"
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
        
        logger.info("📸 Создание скриншота...")
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
            )
            logger.info("✅ Скриншот отправлен")
        else:
            logger.warning("⚠️ Не удалось сделать скриншот")
        
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
        status_msg += f"📍 Путь: {CHROMIUM_PATH or 'не найден'}\n\n"
        
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

# ========== ЗАПУСК ==========
def main():
    logger.info("🚀 Запуск бота...")
    logger.info(f"📊 Текущий движок: {engine_mode}")
    logger.info(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    logger.info(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    logger.info(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    logger.info(f"📍 Путь к Chromium: {CHROMIUM_PATH or 'не найден'}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("engine", engine))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("test", test))
    
    logger.info("✅ Бот запущен и готов к работе!")
    print("\n✅ Бот запущен!")
    print(f"🎮 Движок: {engine_mode}")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print(f"📍 Путь к Chromium: {CHROMIUM_PATH or 'не найден'}")
    print("\nКоманды:")
    print("  /start, /engine, /login, /screen, /status, /close, /test")
    print("\n📋 Подробные логи пишутся в bot.log")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()