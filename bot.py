import os
import sys
import time
import logging
import asyncio
import json
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# ============================================================
# НАСТРОЙКА
# ============================================================

LOGS_DIR = '/app/logs'
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("dspy").setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ============================================================
# ПУТИ
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js,
    list_tabs, current_tab, close_tab, switch_tab, fill_input
)
from browser_harness.admin import ensure_daemon

# ============================================================
# ДОПОЛНИТЕЛЬНЫЕ ИМПОРТЫ ДЛЯ CDP
# ============================================================

import websockets
import threading
from functools import wraps

# ============================================================
# ГЛОБАЛЬНЫЕ НАСТРОЙКИ ТАЙМАУТОВ
# ============================================================

CDP_TIMEOUT = 30.0  # 30 секунд для CDP операций
X_TIMEOUT = 60.0    # 60 секунд для X/Twitter
DEFAULT_RETRIES = 3

# ============================================================
# ОБЕРТКИ С ТАЙМАУТАМИ
# ============================================================

def with_timeout(timeout=CDP_TIMEOUT, retries=DEFAULT_RETRIES):
    """Декоратор для добавления таймаута и повторных попыток"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(retries):
                try:
                    # Запускаем в отдельном потоке с таймаутом
                    result = None
                    error = None
                    
                    def target():
                        nonlocal result, error
                        try:
                            result = func(*args, **kwargs)
                        except Exception as e:
                            error = e
                    
                    thread = threading.Thread(target=target)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=timeout)
                    
                    if thread.is_alive():
                        raise TimeoutError(f"Операция превысила таймаут {timeout}с (попытка {attempt+1}/{retries})")
                    
                    if error:
                        raise error
                    
                    return result
                    
                except TimeoutError as e:
                    last_error = e
                    logger.warning(f"⏱️ {func.__name__} таймаут, попытка {attempt+1}/{retries}")
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)  # Экспоненциальная задержка
                    continue
                except Exception as e:
                    last_error = e
                    logger.warning(f"⚠️ {func.__name__} ошибка: {e}, попытка {attempt+1}/{retries}")
                    if attempt < retries - 1:
                        time.sleep(1)
                    continue
            
            raise last_error or RuntimeError(f"Все {retries} попыток провалились")
        return wrapper
    return decorator

# ============================================================
# ПЕРЕОПРЕДЕЛЕННЫЕ ФУНКЦИИ С ТАЙМАУТАМИ
# ============================================================

@with_timeout(timeout=CDP_TIMEOUT)
def safe_page_info():
    """Безопасная версия page_info с таймаутом"""
    try:
        return page_info()
    except Exception as e:
        logger.error(f"❌ page_info ошибка: {e}")
        raise

@with_timeout(timeout=X_TIMEOUT)
def safe_page_info_x():
    """Специальная версия page_info для X с большим таймаутом"""
    try:
        # Получаем список страниц
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            raise RuntimeError("Нет активных вкладок")
        
        ws_url = pages[0]["webSocketDebuggerUrl"]
        
        # Используем asyncio для прямого CDP вызова
        async def get_info():
            # Убираем timeout из connect() - старая версия websockets
            async with websockets.connect(ws_url) as ws:
                # Отправляем запрос на выполнение JS
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": "JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY,pw:document.documentElement.scrollWidth,ph:document.documentElement.scrollHeight})",
                        "timeout": 30000,  # 30 секунд в мс
                        "returnByValue": True
                    }
                }))
                
                # Таймаут только на получение ответа
                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=35.0))
                
                if "error" in response:
                    raise RuntimeError(f"CDP ошибка: {response['error']}")
                
                result = response.get("result", {})
                if "exceptionDetails" in result:
                    raise RuntimeError(f"JS ошибка: {result['exceptionDetails']}")
                
                # Парсим результат
                value = result.get("result", {}).get("value", "{}")
                info = json.loads(value)
                
                return info
        
        # Запускаем асинхронную функцию с общим таймаутом
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            info = loop.run_until_complete(
                asyncio.wait_for(get_info(), timeout=X_TIMEOUT)
            )
        finally:
            loop.close()
        
        return info
        
    except asyncio.TimeoutError:
        raise TimeoutError(f"X/Twitter страница не отвечает после {X_TIMEOUT} секунд")
    except Exception as e:
        logger.error(f"❌ safe_page_info_x ошибка: {e}")
        raise

@with_timeout(timeout=CDP_TIMEOUT)
def safe_goto_url(url):
    """Безопасная версия goto_url с таймаутом"""
    try:
        goto_url(url)
        
        # Специальная обработка для X/Twitter
        if "x.com" in url or "twitter.com" in url:
            logger.info("🐦 Обнаружен X/Twitter, даем время на загрузку...")
            time.sleep(5)  # Дополнительное ожидание для React
            try:
                wait_for_load(timeout=60.0)
            except:
                logger.warning("⚠️ wait_for_load таймаут, но продолжаем")
        else:
            wait_for_load()
        
        return True
    except Exception as e:
        logger.error(f"❌ safe_goto_url ошибка: {e}")
        raise

@with_timeout(timeout=CDP_TIMEOUT)
def safe_capture_screenshot(filename=None):
    """Безопасная версия capture_screenshot с таймаутом"""
    try:
        if not filename:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
        full_path = os.path.join(SCREENSHOTS_DIR, filename)
        capture_screenshot(path=full_path)
        return filename
    except Exception as e:
        logger.error(f"❌ safe_capture_screenshot ошибка: {e}")
        raise

@with_timeout(timeout=CDP_TIMEOUT)
def safe_js(expression):
    """Безопасная версия js с таймаутом"""
    try:
        result = js(expression)
        if isinstance(result, dict):
            return str(result.get('result', result))
        return str(result) if result is not None else "✅ JavaScript выполнен"
    except Exception as e:
        logger.error(f"❌ safe_js ошибка: {e}")
        raise

# ============================================================
# DSPy АДАПТЕР ДЛЯ AGNES AI
# ============================================================

class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI"""
    
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        
        super().__init__(
            model=model, 
            model_type="chat",
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
            cache=False
        )
        
        self.provider = "agnes-ai"
        self.forward_contract = "legacy"
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            logger.error("❌ AGNES_API_KEY не задан")
            return ["Ошибка: API ключ не задан"]
        
        params = {**self.kwargs, **kwargs}
        
        if messages:
            api_messages = messages
        else:
            api_messages = [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", 0.3),
            "max_tokens": params.get("max_tokens", 2000)
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    result = data["choices"][0]["message"]["content"]
                    return [result]
                return ["Ошибка: пустой ответ от API"]
                
        except httpx.TimeoutException:
            return ["Ошибка: таймаут API (60 сек)"]
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================================
# СИГНАТУРА С УЛУЧШЕННЫМ ПРОМПТОМ
# ============================================================

class BrowserTask(Signature):
    """Ты — AI-агент, который управляет реальным браузером через Browser Harness.

    У тебя есть полный доступ к браузеру через CDP (Chrome DevTools Protocol).
    Ты можешь выполнять любые действия: навигация, клики, ввод текста, скроллинг,
    заполнение форм, работа с вкладками, скриншоты и выполнение JavaScript.

    ВАЖНЫЕ ПРИНЦИПЫ РАБОТЫ:
    1. Браузер ПЕРСИСТЕНТЕН — состояние (куки, сессии, вкладки) сохраняется
       между вызовами. Ты можешь авторизоваться один раз и продолжать работу.
    2. Используй СЕМАНТИЧЕСКИЕ ССЫЛКИ (e1, e2, e3...) вместо CSS-селекторов —
       они стабильнее и не ломаются при изменении верстки.
    3. Не пиши произвольный JavaScript без необходимости — используй
       предоставленные инструменты.
    4. После каждого действия проверяй результат через page_info() или
       capture_screenshot(), чтобы убедиться, что действие выполнено.
    5. Для сложных сайтов (Amazon, LinkedIn, GitHub) используй готовые
       доменные скиллы из agent-workspace/domain-skills/.

    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    - new_tab(), close_tab(), switch_tab(), list_tabs() — управление вкладками
    - goto_url(), wait_for_load() — навигация
    - click_at_xy(), type_text(), press_key() — взаимодействие с интерфейсом
    - fill_input(selector, text) — заполнение форм (используй семантические refs)
    - scroll(dx, dy) — прокрутка страницы
    - js(expression) — выполнение JavaScript (используй ТОЛЬКО когда нужно)
    - capture_screenshot() — создание скриншота
    - page_info() — получение информации о текущей странице

    РЕКОМЕНДАЦИИ:
    - Начинай с page_info(), чтобы понять текущее состояние
    - Используй capture_screenshot() для визуальной проверки
    - Для многошаговых задач разбивай на логические этапы
    - Если что-то пошло не так, сделай скриншот и проанализируй ситуацию

    ПРОТОКОЛ ВЫПОЛНЕНИЯ ЗАДАЧ:
    1. Сначала получи информацию о текущей странице (page_info())
    2. Выполни необходимые действия (навигация, клики, ввод)
    3. После каждого действия проверяй результат
    4. В случае ошибки сделай скриншот и попробуй альтернативный подход
    5. Верни подробный отчет с результатами

    ФОРМАТ ОТВЕТА:
    - ✅ Действие выполнено: [что сделано]
    - 📸 Скриншот: [имя файла]
    - ℹ️ Результат: [что получилось]
    - ❌ Ошибка: [если была]
    """
    question = InputField(desc="Задача пользователя для выполнения в браузере")
    answer = OutputField(desc="Подробный отчет о выполнении задачи с результатами")

# ============================================================
# ИНСТРУМЕНТЫ (С БЕЗОПАСНЫМИ ОБЕРТКАМИ)
# ============================================================

def tool_new_tab() -> str:
    """Открыть новую вкладку"""
    try:
        new_tab()
        return "✅ Новая вкладка открыта"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_goto_url(url: str) -> str:
    """Перейти на URL и дождаться загрузки"""
    try:
        safe_goto_url(url)
        return f"✅ Перешел на {url}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_wait_for_load() -> str:
    """Дождаться загрузки страницы"""
    try:
        wait_for_load(timeout=60.0)
        return "✅ Страница загружена"
    except Exception as e:
        logger.warning(f"⚠️ wait_for_load() failed: {e}")
        time.sleep(5)  # Даем время на прогрузку
        return "✅ Ожидание завершено (таймаут)"

def tool_js(expression: str) -> str:
    """Выполнить JavaScript на странице"""
    try:
        return safe_js(expression)
    except Exception as e:
        return f"❌ Ошибка JavaScript: {e}"

def tool_capture_screenshot(filename: str = None) -> str:
    """Сделать скриншот страницы"""
    try:
        filename = safe_capture_screenshot(filename)
        return f"✅ Скриншот сохранен: {filename}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_fill_input(selector: str, text: str) -> str:
    """Заполнить поле ввода по CSS селектору"""
    try:
        fill_input(selector, text)
        return f"✅ Заполнено: {selector} -> {text}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_click_at_xy(x: int, y: int) -> str:
    """Кликнуть по координатам"""
    try:
        click_at_xy(x, y)
        return f"✅ Клик по ({x}, {y})"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_type_text(text: str) -> str:
    """Ввести текст"""
    try:
        type_text(text)
        return f"✅ Введено: {text}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_press_key(key: str) -> str:
    """Нажать клавишу"""
    try:
        press_key(key)
        return f"✅ Нажата клавиша: {key}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_scroll(dx: int, dy: int) -> str:
    """Прокрутить страницу"""
    try:
        scroll(dx, dy)
        return f"✅ Прокрутка на ({dx}, {dy})"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_page_info() -> str:
    """Получить информацию о странице (с автоматическим определением X)"""
    try:
        # Проверяем, не X ли это
        try:
            current_info = safe_page_info()
            url = current_info.get('url', '')
            
            # Если это X/Twitter - используем специальную функцию
            if "x.com" in url or "twitter.com" in url:
                logger.info("🐦 Используем специальный парсер для X")
                info = safe_page_info_x()
            else:
                info = current_info
                
        except Exception as e:
            logger.warning(f"⚠️ Первичная page_info() не удалась: {e}")
            # Пробуем X-версию как fallback
            info = safe_page_info_x()
        
        return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')[:100]}"
        
    except TimeoutError as e:
        return f"❌ Таймаут при получении информации (30 сек): {e}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def tool_list_tabs() -> str:
    """Список всех открытых вкладок"""
    try:
        tabs = list_tabs()
        return f"Вкладки: {tabs}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_current_tab() -> str:
    """ID текущей вкладки"""
    try:
        tab = current_tab()
        return f"Текущая вкладка: {tab}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_switch_tab(tab_id: int) -> str:
    """Переключиться на вкладку по ID"""
    try:
        switch_tab(tab_id)
        return f"✅ Переключился на вкладку {tab_id}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_close_tab() -> str:
    """Закрыть текущую вкладку"""
    try:
        close_tab()
        return "✅ Вкладка закрыта"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ============================================================
# ВСЕ ИНСТРУМЕНТЫ
# ============================================================

tools = [
    Tool(tool_new_tab),
    Tool(tool_goto_url),
    Tool(tool_wait_for_load),
    Tool(tool_js),
    Tool(tool_capture_screenshot),
    Tool(tool_fill_input),
    Tool(tool_click_at_xy),
    Tool(tool_type_text),
    Tool(tool_press_key),
    Tool(tool_scroll),
    Tool(tool_page_info),
    Tool(tool_list_tabs),
    Tool(tool_current_tab),
    Tool(tool_switch_tab),
    Tool(tool_close_tab),
]

# ============================================================
# СОЗДАНИЕ АГЕНТА
# ============================================================

def create_browser_agent():
    """Создать ReActV2 агента"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания ReActV2 агента: {e}")
        return None

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

browser_agent = None

if AGNES_API_KEY:
    try:
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        browser_agent = create_browser_agent()
        if browser_agent:
            logger.info("✅ BrowserAgent инициализирован")
        else:
            logger.warning("⚠️ Не удалось создать агента")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации DSPy: {e}")
        browser_agent = None
else:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")

# ============================================================
# КУКИ
# ============================================================

try:
    from cookies import COOKIES
    
    async def set_cookies_async():
        """Установить куки через WebSocket"""
        try:
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            
            ws_url = pages[0]["webSocketDebuggerUrl"]
            
            async with websockets.connect(ws_url) as ws:
                # Устанавливаем куки
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Network.setCookies",
                    "params": {"cookies": COOKIES}
                }))
                
                response = json.loads(await ws.recv())
                
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                
                logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False
    
    def set_cookies_global():
        """Обертка для синхронного вызова"""
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    logger.warning("⚠️ websockets или cookies.py не найдены")
    COOKIES = []
    
    def set_cookies_global():
        logger.warning("⚠️ Куки не установлены (нет websockets)")
        return False

# ============================================================
# РАЗМЕР ОКНА
# ============================================================

async def set_viewport_async():
    """Установить размер окна через WebSocket"""
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            logger.warning("⚠️ Нет активных вкладок для установки размера")
            return False
        
        ws_url = pages[0]["webSocketDebuggerUrl"]
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": 1280,
                    "height": 720,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                    "screenWidth": 1280,
                    "screenHeight": 720,
                    "positionX": 0,
                    "positionY": 0
                }
            }))
            
            response = json.loads(await ws.recv())
            
            if "error" in response:
                logger.warning(f"⚠️ CDP ошибка: {response['error']}")
                return False
            
            logger.info("✅ Размер окна установлен: 1280x720")
            return True
            
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

def set_viewport_global():
    """Обертка для синхронного вызова"""
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# ЗАПУСК БРАУЗЕРА
# ============================================================

os.environ["BU_CDP_URL"] = "http://localhost:9222"

try:
    ensure_daemon()
    logger.info("✅ Браузер готов")
except Exception as e:
    logger.error(f"❌ Ошибка запуска браузера: {e}")
    sys.exit(1)

# Устанавливаем куки
if COOKIES:
    set_cookies_global()
else:
    logger.info("ℹ️ Куки не установлены (нет cookies.py)")

# Устанавливаем размер окна
set_viewport_global()

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🧠 *DSPy Браузерный агент*\n\n"
        "/dspy <запрос> — выполнить задачу через агента\n"
        "/tab — показать все открытые вкладки\n"
        "/switch <id> — переключиться на вкладку по ID\n"
        "/close — закрыть текущую вкладку\n"
        "/newtab — открыть новую вкладку\n"
        "/log — скачать логи\n\n"
        "*Примеры:*\n"
        "/dspy открыть google\\.com и сделать скриншот\n"
        "/dspy найти новости о Трампе на BBC\n"
        "/dspy перейти на сайт и показать заголовки",
        parse_mode='MarkdownV2'
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        
        with open(log_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename='bot.log',
                caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_command(update, context):
    """Показать все открытые вкладки с улучшенной обработкой ошибок"""
    try:
        tabs = list_tabs()
        current = current_tab()
        
        if not tabs:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return
        
        result = "📑 *Открытые вкладки:*\n\n"
        failed_tabs = []
        
        for tab in tabs:
            try:
                switch_tab(tab)
                
                # Пробуем получить информацию с таймаутом
                try:
                    # Быстрая проверка с таймаутом 5 секунд
                    info = None
                    
                    def get_info():
                        nonlocal info
                        try:
                            # Проверяем URL для определения X
                            current_info = page_info()
                            url = current_info.get('url', '')
                            
                            if "x.com" in url or "twitter.com" in url:
                                info = safe_page_info_x()
                            else:
                                info = current_info
                        except Exception as e:
                            raise e
                    
                    thread = threading.Thread(target=get_info)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=8.0)  # 8 секунд на получение информации
                    
                    if thread.is_alive():
                        title = "⏳ Загрузка..."
                        url = "⏳ Таймаут (страница медленно грузится)"
                    elif info is None:
                        title = "❌ Не удалось получить информацию"
                        url = "❌ Ошибка"
                    else:
                        title = info.get('title', 'Без названия')[:50]
                        url = info.get('url', 'unknown')[:60]
                        
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить инфо для вкладки {tab}: {e}")
                    title = "⚠️ Ошибка получения"
                    url = f"❌ {str(e)[:50]}"
                
                # Экранируем для Markdown
                title_escaped = escape_markdown(title, version=2)
                url_escaped = escape_markdown(url, version=2)
                
                if tab == current:
                    result += f"👉 *ТЕКУЩАЯ* \\(ID: `{tab}`\\)\n"
                else:
                    result += f"ID: `{tab}`\n"
                result += f"   📄 {title_escaped}\n"
                result += f"   🔗 {url_escaped}\n\n"
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка обработки вкладки {tab}: {e}")
                failed_tabs.append(str(tab))
                result += f"ID: `{tab}`\n"
                result += f"   ❌ Недоступно: {str(e)[:50]}\n\n"
        
        # Возвращаемся на текущую вкладку
        try:
            switch_tab(current)
        except:
            pass
        
        # Добавляем информацию о проблемных вкладках
        if failed_tabs:
            result += f"\n⚠️ Проблемные вкладки: {', '.join(failed_tabs)}\n"
            result += "Рекомендуется закрыть их через /close"
        
        if len(result) > 4000:
            result = result[:4000] + "\n\n\\.\\.\\. \\(обрезано\\)"
        
        await update.message.reply_text(
            result,
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /tab: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def switch_command(update, context):
    """Переключиться на вкладку по ID"""
    if not context.args:
        await update.message.reply_text(
            "📝 *Использование:*\n"
            "/switch <id_вкладки>\n\n"
            "Сначала используйте /tab чтобы увидеть ID вкладок",
            parse_mode='MarkdownV2'
        )
        return
    
    try:
        tab_id = int(context.args[0])
        switch_tab(tab_id)
        
        # Получаем информацию о новой вкладке с таймаутом
        try:
            info = safe_page_info()
            title = escape_markdown(info.get('title', 'Без названия'), version=2)
            url = escape_markdown(info.get('url', 'unknown')[:100], version=2)
            
            await update.message.reply_text(
                f"✅ Переключился на вкладку `{tab_id}`\n"
                f"📄 {title}\n"
                f"🔗 {url}",
                parse_mode='MarkdownV2'
            )
        except:
            await update.message.reply_text(
                f"✅ Переключился на вкладку `{tab_id}`\n"
                f"⚠️ Но не удалось получить информацию о странице",
                parse_mode='MarkdownV2'
            )
        
    except ValueError:
        await update.message.reply_text("❌ ID вкладки должен быть числом")
    except Exception as e:
        logger.error(f"❌ Ошибка в /switch: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def close_command(update, context):
    """Закрыть текущую вкладку"""
    try:
        current = current_tab()
        close_tab()
        await update.message.reply_text(
            f"✅ Вкладка `{current}` закрыта",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /close: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def newtab_command(update, context):
    """Открыть новую вкладку"""
    try:
        new_tab()
        wait_for_load(timeout=30.0)
        current = current_tab()
        await update.message.reply_text(
            f"✅ Новая вкладка открыта\n"
            f"ID: `{current}`",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /newtab: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update, context):
    """Обработчик команды /dspy"""
    if not browser_agent:
        await update.message.reply_text(
            "❌ DSPy не инициализирован.\n"
            "Проверьте AGNES_API_KEY"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 *Пример использования:*\n"
            "/dspy открыть google\\.com и сделать скриншот",
            parse_mode='MarkdownV2'
        )
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} запросил: {query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        # Вызываем агента
        result = browser_agent(question=query)
        
        # Обработка ответа
        if isinstance(result, list):
            answer = result[0] if result else "Пустой ответ"
        elif hasattr(result, 'answer'):
            answer = result.answer
        else:
            answer = str(result)
        
        if answer and answer.strip():
            answer_escaped = escape_markdown(answer[:4000], version=2)
            await status_msg.edit_text(
                f"✅ *Результат:*\n{answer_escaped}",
                parse_mode='MarkdownV2'
            )
        else:
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("tab", tab_command))
    app.add_handler(CommandHandler("switch", switch_command))
    app.add_handler(CommandHandler("close", close_command))
    app.add_handler(CommandHandler("newtab", newtab_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен (ReActV2)' if browser_agent else '❌ Отключен'}")
    logger.info(f"🍪 Куки: {'✅ Установлены' if COOKIES else '❌ Не установлены'}")
    logger.info(f"📁 Логи: {LOGS_DIR}")
    logger.info(f"📸 Скриншоты: {SCREENSHOTS_DIR}")
    logger.info("📋 Доступные команды: /start, /log, /dspy, /tab, /switch, /close, /newtab")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()