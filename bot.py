# bot.py - X.com бот с Pydoll + Playwright (расширенная версия)
import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
from datetime import datetime
from typing import Optional, List
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

# ========== PYDANTIC МОДЕЛИ ДЛЯ СТРУКТУРИРОВАННЫХ ДАННЫХ ==========
if PYDANTIC_AVAILABLE:
    class TweetModel(BaseModel):
        """Модель твита для структурированного извлечения"""
        text: str = Field(description="Текст твита")
        author: Optional[str] = Field(default=None, description="Автор твита")
        username: Optional[str] = Field(default=None, description="Username автора")
        time: Optional[str] = Field(default=None, description="Время публикации")
        likes: Optional[str] = Field(default=None, description="Количество лайков")
        retweets: Optional[str] = Field(default=None, description="Количество ретвитов")
        replies: Optional[str] = Field(default=None, description="Количество ответов")
        
    class UserProfileModel(BaseModel):
        """Модель профиля пользователя"""
        name: Optional[str] = Field(default=None, description="Имя пользователя")
        username: Optional[str] = Field(default=None, description="Username")
        bio: Optional[str] = Field(default=None, description="Биография")
        followers: Optional[str] = Field(default=None, description="Количество подписчиков")
        following: Optional[str] = Field(default=None, description="Количество подписок")
        location: Optional[str] = Field(default=None, description="Местоположение")
        joined: Optional[str] = Field(default=None, description="Дата регистрации")

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
# Для гибридной автоматизации храним сессию
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
        # Используем request из Pydoll
        if hasattr(tab, 'request'):
            if method.lower() == 'get':
                response = await tab.request.get(url, headers=headers)
            elif method.lower() == 'post':
                response = await tab.request.post(url, data=data, headers=headers)
            elif method.lower() == 'put':
                response = await tab.request.put(url, data=data, headers=headers)
            else:
                return {"error": f"Неподдерживаемый метод: {method}"}
            
            # Парсим ответ
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
            # Fallback через JS
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
        # Пробуем использовать extractor из Pydoll
        from pydoll.extractor import ExtractionModel, Field
        
        # Динамически создаем модель для извлечения твитов
        class TweetExtract(ExtractionModel):
            text: str = Field(selector='[data-testid="tweetText"]', description='Текст твита')
            author: str = Field(selector='[data-testid="User-Name"]', description='Автор')
        
        # Извлекаем данные
        if selector:
            tweets = await tab.extract_all(TweetExtract, scope=selector)
        else:
            tweets = await tab.extract_all(TweetExtract)
        
        return {
            "count": len(tweets),
            "data": [t.model_dump() for t in tweets]
        }
    except ImportError:
        # Fallback: ручной парсинг через JS
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
        # Ищем элемент с shadow root
        # Пример для X.com - ищем кнопку Grok
        host = await tab.find('[data-testid="GrokDrawer"]')
        if host:
            shadow_root = await host.get_shadow_root()
            if shadow_root:
                # Ищем элемент внутри shadow root
                inner_elem = await shadow_root.query('.some-class')
                if inner_elem:
                    text = await inner_elem.text
                    return {"found": True, "text": text}
        
        # Если не нашли конкретный shadow root, демонстрируем возможность
        return {
            "status": "Shadow DOM доступен",
            "message": "Используйте host.get_shadow_root() для доступа к закрытым shadow roots"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка Shadow DOM: {e}")
        return {"error": str(e)}

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    await update.message.reply_text(
        f"🤖 **X.com Бот - Расширенная версия**\n\n"
        f"🎮 Движок: {'Pydoll' if engine_mode == 'pydoll' else 'Playwright'}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}\n"
        f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        f"📌 **Основные команды:**\n"
        f"/login - Авторизация в X.com\n"
        f"/screen - Скриншот\n"
        f"/status - Статус браузера\n"
        f"/close - Закрыть браузер\n"
        f"/engine - Переключить движок\n\n"
        f"📌 **Расширенные команды (Pydoll):**\n"
        f"/api <url> - API-запрос с сессией браузера\n"
        f"/extract - Извлечь структурированные данные\n"
        f"/shadow - Работа с Shadow DOM\n"
        f"/install_pydantic - Установить Pydantic",
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
    """Авторизация в X.com - комбинированная проверка"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        await goto_url('https://x.com')
        await asyncio.sleep(5)
        
        # Комбинированная проверка авторизации
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
                    hasLoginLink: hasLoginLink,
                    hasSignupLink: hasSignupLink,
                    hasLoginButton: hasLoginButton,
                    hasNoLoginButtons: hasNoLoginButtons,
                    hasProfileLink: hasProfileLink,
                    hasSideNav: hasSideNav,
                    hasTweetBtn: hasTweetBtn,
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
        status_msg += f"🔍 Кнопка входа: {'❌ (отсутствует)' if auth_status.get('hasNoLoginButtons') else '✅ (присутствует)'}\n"
        status_msg += f"🔍 Элементы профиля: {'✅' if auth_status.get('hasUserElements') else '❌'}\n\n"
        
        if auth_status.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username') and auth_status.get('username') != 'неизвестно':
                status_msg += f"👤 @{auth_status['username']}\n"
            status_msg += "\n💡 Теперь доступны расширенные функции:\n"
            status_msg += "  /api <url> - API-запросы\n"
            status_msg += "  /extract - Извлечение данных\n"
            status_msg += "  /shadow - Shadow DOM"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
            if not auth_status.get('hasAuthToken'):
                status_msg += "⚠️ Кука auth_token отсутствует или истекла\n"
            status_msg += "\nИспользуйте /setcookies для обновления кук"
        
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
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

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
    
    print("\n✅ Бот запущен!")
    print(f"🎮 Движок: {engine_mode}")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}")
    print(f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды:")
    print("  Основные: /start, /login, /screen, /status, /engine, /close")
    print("  Расширенные: /api <url>, /extract, /shadow, /install_pydantic")
    print("  Куки: /setcookies, /cancel")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()