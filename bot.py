import os
import sys
import stat
import time
import logging
import base64
import re
import asyncio
import io
import json
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.helpers import escape_markdown
from promt import SYSTEM_PROMPT
from PIL import Image

# DSPy импорты для версии 3.3.0b1
import dspy
from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

agent_workspace = "/app/browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)

helpers_file = os.path.join(agent_workspace, "agent_helpers.py")
os.makedirs(agent_workspace, exist_ok=True)
if not os.path.exists(helpers_file):
    with open(helpers_file, "w") as f:
        f.write('"""Agent-editable browser helpers."""\n')
os.chmod(agent_workspace, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
os.chmod(helpers_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

os.environ["BH_DOMAIN_SKILLS"] = "1"
os.environ["BH_AGENT_WORKSPACE"] = "/app/browser-harness/agent-workspace"

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

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)
logging.getLogger("dspy").setLevel(logging.INFO)
logging.getLogger("litellm").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info(f"✅ agent_workspace: {agent_workspace}")
logger.info(f"✅ helpers_file: {helpers_file}")
logger.info(f"✅ screenshots_dir: {SCREENSHOTS_DIR}")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
)
from browser_harness.admin import ensure_daemon

# ============================================================
# DSPy ИНТЕГРАЦИЯ (DSPy 3.3.0b1)
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
                
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================================
# СИГНАТУРА
# ============================================================

class BrowserTask(Signature):
    """Ты агент с доступом к браузеру.
    Используй инструменты для выполнения задач пользователя.
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ============================================================
# ВСЕ ИНСТРУМЕНТЫ BROWSER_HARNESS
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
        goto_url(url)
        wait_for_load()
        return f"✅ Перешел на {url}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_wait_for_load() -> str:
    """Дождаться загрузки страницы"""
    try:
        wait_for_load()
        return "✅ Страница загружена"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_js(expression: str) -> str:
    """Выполнить JavaScript на странице"""
    try:
        result = js(expression)
        if isinstance(result, dict):
            return str(result.get('result', result))
        return str(result) if result is not None else "✅ JavaScript выполнен (нет результата)"
    except Exception as e:
        return f"❌ Ошибка JavaScript: {e}"

def tool_http_get(url: str) -> str:
    """Выполнить HTTP GET запрос"""
    try:
        return http_get(url)
    except Exception as e:
        return f"❌ Ошибка HTTP: {e}"

def tool_capture_screenshot(filename: str = None) -> str:
    """Сделать скриншот страницы"""
    try:
        if not filename:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
        full_path = os.path.join(SCREENSHOTS_DIR, filename)
        capture_screenshot(path=full_path)
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
    """Получить информацию о странице (URL, Title)"""
    try:
        info = page_info()
        return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

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
# ДОПОЛНИТЕЛЬНЫЕ УДОБНЫЕ ИНСТРУМЕНТЫ
# ============================================================

def tool_get_text() -> str:
    """Получить весь текст на странице"""
    try:
        result = js('() => document.body.innerText')
        if isinstance(result, dict):
            text = result.get('result', str(result))
        else:
            text = str(result)
        if text and len(text) > 10:
            return text[:5000]
        return "❌ Текст не найден или страница пуста"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_get_links() -> str:
    """Получить все ссылки на странице"""
    try:
        result = js('() => Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
        if isinstance(result, list) and result:
            links = [str(item) for item in result if item]
            return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
        return "❌ Ссылок не найдено"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_get_buttons() -> str:
    """Получить все кнопки на странице"""
    try:
        result = js('() => Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())')
        if isinstance(result, list) and result:
            buttons = [str(item).strip() for item in result if item and str(item).strip()]
            return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
        return "❌ Кнопок не найдено"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_get_headings() -> str:
    """Получить все заголовки на странице (h1-h6)"""
    try:
        result = js('() => Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t.trim())')
        if isinstance(result, list) and result:
            headings = [str(item).strip() for item in result if item and str(item).strip()]
            return f"Заголовки:\n" + "\n".join(headings)
        return "❌ Заголовков не найдено"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_get_accessibility_text() -> str:
    """Получить доступный текст страницы через Accessibility Tree"""
    try:
        result = js('''
            () => {
                const elements = document.querySelectorAll('[role], [aria-label], [aria-labelledby], h1, h2, h3, h4, h5, h6, p, a, button, input, label');
                const texts = [];
                elements.forEach(el => {
                    let text = '';
                    if (el.hasAttribute('aria-label')) {
                        text = el.getAttribute('aria-label');
                    } else if (el.hasAttribute('aria-labelledby')) {
                        const labelEl = document.getElementById(el.getAttribute('aria-labelledby'));
                        if (labelEl) text = labelEl.innerText || labelEl.textContent;
                    } else if (['A','BUTTON','H1','H2','H3','H4','H5','H6','P','LABEL'].includes(el.tagName)) {
                        text = el.innerText || el.textContent;
                    } else if (el.tagName === 'INPUT' && el.hasAttribute('placeholder')) {
                        text = el.getAttribute('placeholder');
                    }
                    if (text && text.trim()) {
                        texts.push({
                            tag: el.tagName,
                            role: el.getAttribute('role') || 'none',
                            text: text.trim()
                        });
                    }
                });
                return JSON.stringify(texts.slice(0, 50));
            }
        ''')
        if isinstance(result, dict):
            return result.get('result', str(result))
        if result and result != '[]':
            return f"Доступный текст:\n{result}"
        return "❌ Доступный текст не найден"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ============================================================
# ПОИСК НОВОСТЕЙ
# ============================================================

def tool_search_news(query: str) -> str:
    """Поиск новостей по запросу через Google News RSS"""
    try:
        import feedparser
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        if feed.entries:
            results = []
            for entry in feed.entries[:5]:
                results.append(f"• {entry.title}\n  {entry.link}")
            return f"Новости о {query}:\n\n" + "\n\n".join(results)
        return "❌ Новости не найдены"
    except Exception as e:
        return f"❌ Ошибка поиска новостей: {e}"

# ============================================================
# ВСЕ ИНСТРУМЕНТЫ
# ============================================================

tools = [
    Tool(tool_new_tab),
    Tool(tool_goto_url),
    Tool(tool_wait_for_load),
    Tool(tool_js),
    Tool(tool_http_get),
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
    Tool(tool_get_text),
    Tool(tool_get_links),
    Tool(tool_get_buttons),
    Tool(tool_get_headings),
    Tool(tool_get_accessibility_text),
    Tool(tool_search_news),
]

# ============================================================
# СОЗДАЕМ REACTV2 АГЕНТА
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
        
        # Fallback: пробуем без Tool
        try:
            tools_fallback = [
                tool_new_tab,
                tool_goto_url,
                tool_wait_for_load,
                tool_js,
                tool_http_get,
                tool_capture_screenshot,
                tool_fill_input,
                tool_click_at_xy,
                tool_type_text,
                tool_press_key,
                tool_scroll,
                tool_page_info,
                tool_list_tabs,
                tool_current_tab,
                tool_switch_tab,
                tool_close_tab,
                tool_get_text,
                tool_get_links,
                tool_get_buttons,
                tool_get_headings,
                tool_get_accessibility_text,
                tool_search_news,
            ]
            
            agent = ReActV2(
                signature=BrowserTask,
                tools=tools_fallback,
                max_iters=10,
            )
            logger.info("✅ ReActV2 агент создан (без Tool)")
            return agent
        except Exception as e2:
            logger.error(f"❌ Fallback тоже не работает: {e2}")
            
            # Второй fallback: ChainOfThought
            try:
                from dspy import ChainOfThought
                
                class SimpleAgent(Module):
                    def __init__(self):
                        super().__init__()
                        self.generate = ChainOfThought(BrowserTask)
                    
                    def forward(self, question):
                        return self.generate(question=question)
                
                logger.info("⚠️ Использую ChainOfThought как fallback")
                return SimpleAgent()
            except Exception as e3:
                logger.error(f"❌ ChainOfThought fallback не работает: {e3}")
                return None

# ============================================================
# ИНИЦИАЛИЗАЦИЯ DSPy
# ============================================================

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

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
    import websockets
    
    async def set_cookies_async():
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Network.setCookies", "params": {"cookies": COOKIES}}))
                response = json.loads(await ws.recv())
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def set_cookies_global():
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    logger.warning("⚠️ websockets не установлен")
    COOKIES = []
    def set_cookies_global():
        return False

# ============================================================
# НАСТРОЙКА РАЗМЕРА ОКНА
# ============================================================

async def set_viewport_async():
    try:
        import httpx
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
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# НАСТРОЙКА БРАУЗЕРА
# ============================================================

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
try:
    ensure_daemon()
    logger.info("✅ Браузер готов")
except Exception as e:
    logger.error(f"❌ Ошибка запуска браузера: {e}")
    sys.exit(1)

set_cookies_global()
set_viewport_global()

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан")
        return False

    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = f"browser-harness/agent-workspace/domain-skills/{host}/{filename}"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        else:
            sha = None
    except Exception:
        sha = None

    data = {
        "message": f"Добавлен/обновлён навык {filename} для {host}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Навык отправлен в GitHub: {file_path}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в GitHub: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке в GitHub: {e}")
        return False

def push_helpers_to_github():
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан")
        return False
    
    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = "browser-harness/agent-workspace/agent_helpers.py"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        sha = resp.json().get("sha", None) if resp.status_code == 200 else None
    except:
        sha = None
    
    helpers_path = os.path.join(agent_workspace, "agent_helpers.py")
    if not os.path.exists(helpers_path):
        logger.warning("⚠️ agent_helpers.py не найден")
        return False
    
    with open(helpers_path, "r", encoding='utf-8') as f:
        content = f.read()
    
    data = {
        "message": "Обновлён agent_helpers.py",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    
    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ agent_helpers.py отправлен в GitHub")
            return True
        else:
            logger.error(f"❌ Ошибка отправки helpers: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке helpers: {e}")
        return False

# ============================================================
# ФОТОШОП
# ============================================================

AGNES_IMAGE_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"

def get_image_size(image_data):
    try:
        img = Image.open(io.BytesIO(image_data))
        width, height = img.size
        return width, height
    except Exception as e:
        logger.error(f"Ошибка при определении размера: {e}")
        return None, None

def replace_background(image_data, new_background_prompt: str):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    
    if not image_data:
        return None, "Нет данных изображения"
    
    if not new_background_prompt or len(new_background_prompt.strip()) < 2:
        return None, "Слишком короткое описание фона"
    
    try:
        width, height = get_image_size(image_data)
        MAX_SIZE = 1024
        MIN_SIZE = 256
        
        if width and height:
            if width > MAX_SIZE or height > MAX_SIZE:
                ratio = min(MAX_SIZE / width, MAX_SIZE / height)
                width = int(width * ratio)
                height = int(height * ratio)
            if width < MIN_SIZE or height < MIN_SIZE:
                ratio = max(MIN_SIZE / width, MIN_SIZE / height)
                width = int(width * ratio)
                height = int(height * ratio)
            size = f"{width}x{height}"
        else:
            size = "1024x1024"
        
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85, optimize=True)
            image_data = buffer.getvalue()
        except Exception as e:
            logger.warning(f"Не удалось оптимизировать изображение: {e}")
        
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        
        enhanced_prompt = f"""
        Replace the background with: {new_background_prompt}.
        Keep the main subject exactly as is.
        Maintain the original lighting and shadows.
        Make the background look natural and realistic.
        Do not alter the main subject.
        """
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-image-2.0-flash",
            "prompt": enhanced_prompt.strip(),
            "size": size,
            "extra_body": {
                "image": [data_uri],
                "response_format": "url"
            }
        }
        
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                AGNES_IMAGE_API_URL,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
        
        if 'data' in result and len(result['data']) > 0:
            if 'url' in result['data'][0]:
                return result['data'][0]['url'], None
            elif 'b64_json' in result['data'][0]:
                return result['data'][0]['b64_json'], None
        
        return None, "Неожиданный формат ответа от API"
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None, f"Внутренняя ошибка: {str(e)[:100]}"

# ============================================================
# LLM
# ============================================================

async def ask_agnes_dspy(messages):
    if not browser_agent:
        return await ask_agnes_fallback(messages)
    
    try:
        # Извлекаем вопрос пользователя
        user_question = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_question = msg.get("content", "")
        
        if not user_question:
            return "❌ Нет вопроса для обработки"
        
        logger.info(f"🧠 DSPy обрабатывает: {user_question}")
        
        # Вызываем агента
        result = browser_agent(question=user_question)
        
        # Извлекаем ответ
        answer = getattr(result, 'answer', str(result))
        
        if not answer or answer.strip() == "":
            return await ask_agnes_fallback(messages)
        
        return answer
            
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return await ask_agnes_fallback(messages)

async def ask_agnes_fallback(messages):
    logger.info("=" * 60)
    logger.info("📤 ОТПРАВКА В AGNES AI (FALLBACK):")
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        logger.info(f"  [{role}]: {content[:500]}..." if len(content) > 500 else f"  [{role}]: {content}")
    logger.info("=" * 60)
    
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "agnes-2.0-flash",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post("https://apihub.agnes-ai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"❌ Ошибка Agnes AI: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузер:\n"
        "/ask <запрос> — задать задачу агенту\n"
        "/image — последний скриншот\n"
        "/images — все скриншоты\n"
        "/skills — список навыков\n"
        "/log — скачать логи\n\n"
        "🎨 Фотошоп:\n"
        "/bg <описание> — заменить фон\n"
        "/clear — очистить кэш\n\n"
        "🧠 DSPy:\n"
        "/dspy <запрос> — использовать DSPy"
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log', caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills(update, context):
    try:
        skills_dir = os.path.join(agent_workspace, "domain-skills")
        if not os.path.exists(skills_dir):
            await update.message.reply_text("📭 Папка с навыками не найдена")
            return
        
        skills_list = []
        for domain in os.listdir(skills_dir):
            domain_path = os.path.join(skills_dir, domain)
            if os.path.isdir(domain_path):
                for f in os.listdir(domain_path):
                    if f.endswith(".md") or f.endswith(".txt"):
                        skills_list.append(f"{domain}/{f}")
        
        if skills_list:
            msg = "🧠 **Доступные навыки:**\n\n"
            for skill in skills_list[:20]:
                msg += f"• `{skill}`\n"
            if len(skills_list) > 20:
                msg += f"\n... и ещё {len(skills_list) - 20}"
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text("🧠 Навыков пока нет. Агент создаст их по мере работы.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def image(update, context):
    try:
        screenshot_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
        if not screenshot_files:
            await update.message.reply_text("📭 Скриншотов не найдено")
            return
        screenshot_files.sort(key=lambda x: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, x)), reverse=True)
        latest = screenshot_files[0]
        file_path = os.path.join(SCREENSHOTS_DIR, latest)
        with open(file_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption=f"📸 {latest}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def images(update, context):
    try:
        screenshot_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
        if not screenshot_files:
            await update.message.reply_text("📭 Скриншотов не найдено")
            return
        screenshot_files.sort(key=lambda x: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, x)), reverse=True)
        sent_count = 0
        for s_file in screenshot_files[:10]:
            file_path = os.path.join(SCREENSHOTS_DIR, s_file)
            with open(file_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📸 {s_file}")
            sent_count += 1
            await asyncio.sleep(0.5)
        if len(screenshot_files) > 10:
            await update.message.reply_text(f"📸 Показано 10 из {len(screenshot_files)} скриншотов")
        else:
            await update.message.reply_text(f"✅ Отправлено {sent_count} скриншотов")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def ask(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /ask сделай скриншот google.com")
        return

    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} запросил: {user_query}")
    
    status_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        if browser_agent:
            # Используем агента
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ]
            response = await ask_agnes_dspy(messages)
            
            if response and response.strip():
                response_escaped = escape_markdown(response[:4000], version=2)
                await status_msg.edit_text(f"✅ Результат:\n{response_escaped}", parse_mode='MarkdownV2')
            else:
                await status_msg.edit_text("❌ Агент вернул пустой ответ")
        else:
            # Fallback
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ]
            response = await ask_agnes_fallback(messages)
            response_escaped = escape_markdown(response[:4000], version=2)
            await status_msg.edit_text(f"💬 Ответ:\n{response_escaped}", parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"❌ Ошибка в /ask для {username}: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update, context):
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован. Проверьте AGNES_API_KEY")
        return
    
    if not context.args:
        await update.message.reply_text("Пример: /dspy открыть google.com и сделать скриншот")
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} DSPy запрос: {query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        # Вызываем агента
        result = browser_agent(question=query)
        answer = getattr(result, 'answer', str(result))
        
        if answer and answer.strip():
            answer_escaped = escape_markdown(answer[:4000], version=2)
            await status_msg.edit_text(f"✅ Результат:\n{answer_escaped}", parse_mode='MarkdownV2')
        else:
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def clear_command(update, context):
    if 'last_image' in context.user_data:
        del context.user_data['last_image']
        await update.message.reply_text("🧹 Кэш очищен!")
    else:
        await update.message.reply_text("📭 Кэш пуст")

async def handle_photo(update, context):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        
        width, height = get_image_size(photo_bytes)
        size_info = f" ({width}x{height})" if width and height else ""
        
        await update.message.reply_text(
            f"📸 Фото сохранено{size_info}!\n"
            f"✏️ Используй /bg <описание> для замены фона"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def bg_command(update, context):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен. Нет AGNES_API_KEY")
        return

    if 'last_image' not in context.user_data:
        await update.message.reply_text("📸 Сначала загрузите картинку!")
        return

    if not context.args:
        await update.message.reply_text("✏️ Напишите описание нового фона. Пример: /bg beach")
        return

    prompt = ' '.join(context.args)
    waiting_msg = await update.message.reply_text(f"🎨 Заменяю фон: {prompt}\n⏳ Ожидайте...")

    try:
        image_data = context.user_data['last_image']
        loop = asyncio.get_event_loop()
        result_url, error = await loop.run_in_executor(
            None, replace_background, image_data, prompt
        )

        try:
            await waiting_msg.delete()
        except:
            pass

        if error:
            await update.message.reply_text(f"❌ Ошибка: {error}")
            return

        if result_url:
            try:
                if result_url.startswith('data:image'):
                    img_data = base64.b64decode(result_url.split(',')[1])
                    await update.message.reply_photo(
                        img_data,
                        caption=f"🖼️ Готово! Фон заменён на: {prompt}"
                    )
                else:
                    response = httpx.get(result_url, timeout=30)
                    if response.status_code == 200:
                        await update.message.reply_photo(
                            response.content,
                            caption=f"🖼️ Готово! Фон заменён на: {prompt}"
                        )
                    else:
                        await update.message.reply_text(f"❌ Ошибка загрузки: {response.status_code}")
            except Exception as e:
                logger.error(f"Ошибка скачивания: {e}")
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        else:
            await update.message.reply_text("❌ Не удалось заменить фон")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("skills", skills))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(CommandHandler("images", images))
    
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    app.add_handler(CommandHandler("bg", bg_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен (ReActV2)' if browser_agent else '❌ Отключен'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()