#!/usr/bin/env python3
"""
Telegram Bot с Agnes AI агентом для управления браузером через Pydoll
Версия: 5.0 - Финальная, с учётом всех рекомендаций

Рекомендации Pydoll:
- Использование @retry с конкретными исключениями
- humanize=True для реалистичного поведения
- Правильная обработка ошибок
- PageObject паттерн
- Обход Cloudflare
"""

import asyncio
import logging
import os
import base64
import json
import traceback
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ============================================================
# ИМПОРТЫ PYDOLL (по документации)
# ============================================================
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key

# Правильные импорты исключений
from pydoll.exceptions import (
    ElementNotFound,
    WaitElementTimeout,
    ElementNotVisible,
    ElementNotInteractable,
    NetworkError,
    PageLoadTimeout,
    ConnectionFailed,
    ClickIntercepted,
    PydollException
)

# Декоратор retry (с правильным использованием)
try:
    from pydoll.decorators import retry
    RETRY_AVAILABLE = True
except ImportError:
    RETRY_AVAILABLE = False
    # Заглушка с правильным поведением
    def retry(max_retries=3, exceptions=None, on_retry=None, delay=1.0, exponential_backoff=False):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

# Скролл
try:
    from pydoll.constants import ScrollPosition
    SCROLL_AVAILABLE = True
except ImportError:
    SCROLL_AVAILABLE = False

# Сетевые протоколы
try:
    from pydoll.protocol.fetch.events import FetchEvent, RequestPausedEvent
    from pydoll.protocol.network.types import ErrorReason
    from pydoll.protocol.network.events import NetworkEvent
    NETWORK_AVAILABLE = True
except ImportError:
    NETWORK_AVAILABLE = False

# ============================================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

LOG_DIR = Path("logs")
MEMORY_DIR = Path("memory")
TEMPLATES_DIR = Path("templates")
LOG_DIR.mkdir(exist_ok=True)
MEMORY_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Логгеры
error_logger = logging.getLogger('error_logger')
error_handler = logging.FileHandler(LOG_DIR / 'errors.log')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

debug_logger = logging.getLogger('debug_logger')
debug_handler = logging.FileHandler(LOG_DIR / 'debug.log')
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
debug_logger.addHandler(debug_handler)

audit_logger = logging.getLogger('audit_logger')
audit_handler = logging.FileHandler(LOG_DIR / 'audit.log')
audit_handler.setLevel(logging.INFO)
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
audit_logger.addHandler(audit_handler)

# ============================================================
# 2. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    raise ValueError("AGNES_API_KEY не установлен!")

CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "").split(",") if id]
PERSISTENT_SESSION = os.environ.get("PERSISTENT_SESSION", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER", "")
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============================================================
# 3. ТРЕКЕР ОШИБОК
# ============================================================

class ErrorTracker:
    def __init__(self, max_errors: int = 100):
        self.errors = []
        self.max_errors = max_errors

    def add_error(self, error: Exception, context: Dict[str, Any] = None):
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context or {}
        }
        self.errors.append(error_info)
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)
        self._save_to_file(error_info)
        return error_info

    def _save_to_file(self, error_info: Dict):
        filename = LOG_DIR / f"error_{datetime.now().strftime('%Y%m%d')}.json"
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                json.dump(error_info, f, ensure_ascii=False)
                f.write('\n')
        except:
            pass

    def get_recent(self, limit: int = 10):
        return self.errors[-limit:]

    def clear(self):
        self.errors.clear()

error_tracker = ErrorTracker()

def log_error(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            context = {
                "function": func.__name__,
                "args": str(args)[:200],
                "kwargs": str(kwargs)[:200]
            }
            if args and hasattr(args[0], 'effective_user'):
                context['user_id'] = args[0].effective_user.id
            error_tracker.add_error(e, context)
            error_logger.error(f"Ошибка в {func.__name__}: {e}\n{traceback.format_exc()}")
            raise
    return wrapper

# ============================================================
# 4. СИСТЕМА САМООБУЧЕНИЯ
# ============================================================

class LearningMemory:
    """Система самообучения агента"""
    
    def __init__(self):
        self.memory_file = MEMORY_DIR / "agent_memory.json"
        self.templates_file = TEMPLATES_DIR / "templates.json"
        self.memory = self._load_memory()
        self.templates = self._load_templates()
    
    def _load_memory(self) -> Dict:
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "sites": {},
            "patterns": {},
            "selectors": {},
            "learned_at": datetime.now().isoformat()
        }
    
    def _load_templates(self) -> Dict:
        if self.templates_file.exists():
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "templates": [],
            "stats": {"total": 0, "successful": 0, "failed": 0}
        }
    
    def save_memory(self):
        self.memory["learned_at"] = datetime.now().isoformat()
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)
    
    def save_templates(self):
        with open(self.templates_file, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
    
    def learn_site_structure(self, url: str, analysis: Dict):
        domain = self._extract_domain(url)
        if domain not in self.memory["sites"]:
            self.memory["sites"][domain] = {
                "first_seen": datetime.now().isoformat(),
                "visits": 0,
                "analysis": None,
                "selectors": {}
            }
        
        site = self.memory["sites"][domain]
        site["visits"] += 1
        site["analysis"] = analysis
        
        if analysis.get("search_inputs"):
            site["selectors"]["search"] = analysis["search_inputs"][0]
        if analysis.get("buttons"):
            site["selectors"]["buttons"] = analysis["buttons"][:5]
        
        self.save_memory()
        logger.info(f"🧠 Агент запомнил структуру {domain}")
    
    def get_learned_selector(self, url: str, element_type: str) -> Optional[Dict]:
        domain = self._extract_domain(url)
        if domain in self.memory["sites"]:
            site = self.memory["sites"][domain]
            if element_type in site.get("selectors", {}):
                return site["selectors"][element_type]
        return None
    
    def _extract_domain(self, url: str) -> str:
        match = re.search(r'https?://([^/]+)', url)
        if match:
            return match.group(1).replace('www.', '')
        return url

learning_memory = LearningMemory()

# ============================================================
# 5. УПРАВЛЕНИЕ КОНТЕКСТАМИ БРАУЗЕРА
# ============================================================

@dataclass
class BrowserSession:
    browser: Optional[Chrome] = None
    context_id: Optional[str] = None
    tab: Optional[Any] = None
    is_active: bool = False
    current_url: str = ""
    page_title: str = ""
    last_action: str = ""
    last_action_time: datetime = field(default_factory=datetime.now)
    context_variables: Dict[str, Any] = field(default_factory=dict)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, BrowserSession] = {}
        self._browser: Optional[Chrome] = None
        self._lock = asyncio.Lock()

    async def _get_or_create_browser(self) -> Chrome:
        if self._browser is None:
            options = ChromiumOptions()
            options.binary_location = CHROME_PATH
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--headless=new')
            options.start_timeout = 30

            if PERSISTENT_SESSION:
                options.add_argument("--user-data-dir=/data/browser-profile")
                logger.info("💾 Используется Persistent Session")

            if PROXY_SERVER:
                proxy_parts = PROXY_SERVER.split('://')
                proxy_type = proxy_parts[0] if len(proxy_parts) > 1 else 'http'
                proxy_host = proxy_parts[1] if len(proxy_parts) > 1 else PROXY_SERVER
                if PROXY_USER and PROXY_PASS:
                    options.add_argument(f"--proxy-server={proxy_type}://{PROXY_USER}:{PROXY_PASS}@{proxy_host}")
                else:
                    options.add_argument(f"--proxy-server={proxy_type}://{proxy_host}")
                logger.info(f"🌐 Используется прокси: {proxy_type}://{proxy_host}")

            self._browser = Chrome(options=options)
            await self._browser.start()
            logger.info("🌐 Браузер успешно запущен")

        return self._browser

    async def get_session(self, user_id: int) -> BrowserSession:
        async with self._lock:
            if user_id not in self.sessions:
                session = BrowserSession()
                self.sessions[user_id] = session
                logger.info(f"🆕 Создана новая сессия для пользователя {user_id}")

            session = self.sessions[user_id]

            if not session.context_id:
                browser = await self._get_or_create_browser()
                try:
                    session.context_id = await browser.create_browser_context()
                except AttributeError:
                    session.context_id = "default"
                    logger.warning("⚠️ create_browser_context не поддерживается")

                session.tab = await browser.new_tab()
                session.is_active = True
                session.last_action_time = datetime.now()
                logger.info(f"🔒 Контекст {session.context_id} для пользователя {user_id}")

            if session.tab:
                try:
                    session.current_url = await session.tab.current_url
                    session.page_title = await session.tab.title
                except Exception as e:
                    logger.warning(f"⚠️ Вкладка пользователя {user_id} умерла: {e}")
                    browser = await self._get_or_create_browser()
                    session.tab = await browser.new_tab()

            return session

    async def close_session(self, user_id: int):
        async with self._lock:
            if user_id in self.sessions:
                session = self.sessions[user_id]
                if session.tab:
                    try:
                        await session.tab.close()
                    except:
                        pass
                if session.context_id and session.context_id != "default":
                    try:
                        await session.browser.close_browser_context(session.context_id)
                    except:
                        pass
                del self.sessions[user_id]
                logger.info(f"❌ Сессия пользователя {user_id} закрыта")

    async def cleanup_inactive(self, max_age_seconds: int = 1800):
        now = datetime.now()
        to_remove = []
        for user_id, session in self.sessions.items():
            age = (now - session.last_action_time).total_seconds()
            if age > max_age_seconds:
                to_remove.append(user_id)
        for user_id in to_remove:
            await self.close_session(user_id)
            logger.info(f"🧹 Сессия {user_id} очищена (неактивна)")

    async def close_all(self):
        for user_id in list(self.sessions.keys()):
            await self.close_session(user_id)
        if self._browser:
            try:
                await self._browser.stop()
            except:
                pass
            self._browser = None

session_manager = SessionManager()

# ============================================================
# 6. AGNES AI КЛИЕНТ
# ============================================================

agnes_client = None

def init_agnes():
    global agnes_client
    from openai import OpenAI
    agnes_client = OpenAI(
        api_key=AGNES_API_KEY,
        base_url="https://apihub.agnes-ai.com/v1",
    )
    logger.info("✅ Agnes AI клиент инициализирован")
    return agnes_client

# ============================================================
# 7. ИНСТРУМЕНТЫ (с использованием @retry)
# ============================================================

TOOLS = [
    # Навигация
    {
        "type": "function",
        "function": {
            "name": "go_to_url",
            "description": "Переходит на URL и анализирует страницу",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "go_back",
            "description": "Возвращает на предыдущую страницу",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_page",
            "description": "Обновляет текущую страницу",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    # Поиск элементов
    {
        "type": "function",
        "function": {
            "name": "find_element",
            "description": "Находит элемент по атрибутам (id, class_name, name, tag_name, text)",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "tag_name": {"type": "string"},
                    "text": {"type": "string"},
                    "timeout": {"type": "integer", "default": 10}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_element_smart",
            "description": "Умный поиск элемента по тексту (placeholder, aria-label, title)",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "element_type": {"type": "string", "enum": ["input", "button", "link"]}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_element_from_memory",
            "description": "Ищет элемент используя память агента",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_type": {"type": "string", "enum": ["search", "login", "submit"]}
                },
                "required": ["element_type"]
            }
        }
    },
    # Взаимодействие (с humanize)
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу (с humanize=True)",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Вводит текст с humanize=True (реалистичный ввод)",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_into_search_smart",
            "description": "Находит поле поиска и вводит текст (с humanize)",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Нажимает клавишу",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        }
    },
    # Скриншоты
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Делает скриншот (только видимая область)",
            "parameters": {
                "type": "object",
                "properties": {"full_page": {"type": "boolean", "default": False}}
            }
        }
    },
    # Данные
    {
        "type": "function",
        "function": {
            "name": "get_page_title",
            "description": "Получает заголовок страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_url",
            "description": "Получает текущий URL",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": "Выполняет JavaScript",
            "parameters": {
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"]
            }
        }
    },
    # GitHub
    {
        "type": "function",
        "function": {
            "name": "analyze_github_repo",
            "description": "Анализирует GitHub репозиторий",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string"},
                    "depth": {"type": "string", "enum": ["quick", "deep"], "default": "quick"}
                },
                "required": ["repo_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_github",
            "description": "Ищет на GitHub по ключевым словам",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    # Обход Cloudflare
    {
        "type": "function",
        "function": {
            "name": "bypass_cloudflare",
            "description": "Обходит Cloudflare капчу на указанном URL",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    # Память
    {
        "type": "function",
        "function": {
            "name": "get_memory_stats",
            "description": "Показывает статистику памяти агента",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# ============================================================
# 8. ИСПОЛНЕНИЕ ИНСТРУМЕНТОВ (с @retry)
# ============================================================

@retry(
    max_retries=3,
    exceptions=[ElementNotFound, WaitElementTimeout, NetworkError],
    delay=1.0,
    exponential_backoff=True
)
async def safe_find_element(tab, **kwargs):
    """Безопасный поиск элемента с retry"""
    return await tab.find(**kwargs)

@retry(
    max_retries=2,
    exceptions=[ElementNotFound, ClickIntercepted],
    delay=0.5
)
async def safe_click_element(tab, selector: str):
    """Безопасный клик с retry"""
    element = await tab.query(selector)
    await element.click(humanize=True)  # ← humanize=True
    return element

@retry(
    max_retries=2,
    exceptions=[ElementNotFound, ElementNotInteractable],
    delay=0.5
)
async def safe_type_text(tab, selector: str, text: str):
    """Безопасный ввод текста с retry и humanize"""
    element = await tab.query(selector)
    await element.clear()
    await element.type_text(text, humanize=True)  # ← humanize=True
    return element

@log_error
async def execute_tool(tool_name: str, arguments: Dict, user_id: int) -> Dict:
    """Выполняет инструмент с использованием retry и humanize"""
    session = await session_manager.get_session(user_id)
    tab = session.tab

    if not tab:
        return {"success": False, "error": "⚠️ Браузер не открыт"}

    try:
        # ============================================================
        # НАВИГАЦИЯ
        # ============================================================
        if tool_name == "go_to_url":
            url = arguments.get("url", "")
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Обход Cloudflare если нужно
            if "cloudflare" in url or "captcha" in url:
                async with tab.expect_and_bypass_cloudflare_captcha():
                    await tab.go_to(url)
            else:
                await tab.go_to(url)
            
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.last_action = "go_to_url"
            session.last_action_time = datetime.now()
            
            # Авто-анализ
            try:
                analysis_result = await execute_tool("analyze_page_structure", {}, user_id)
                if analysis_result.get("success"):
                    learning_memory.learn_site_structure(url, analysis_result.get("analysis", {}))
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проанализировать: {e}")
            
            return {"success": True, "url": session.current_url, "title": session.page_title}

        elif tool_name == "go_back":
            await tab.go_back()
            return {"success": True, "message": "↩️ Назад"}

        elif tool_name == "refresh_page":
            await tab.refresh()
            return {"success": True, "message": "🔄 Обновлено"}

        # ============================================================
        # АНАЛИЗ
        # ============================================================
        elif tool_name == "analyze_page_structure":
            script = """
            (function() {
                const result = {
                    inputs: [],
                    buttons: [],
                    search_inputs: []
                };
                
                document.querySelectorAll('input, textarea').forEach(el => {
                    const data = {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        id: el.id || null,
                        name: el.name || null,
                        placeholder: el.placeholder || null,
                        aria_label: el.getAttribute('aria-label') || null
                    };
                    result.inputs.push(data);
                    
                    if (el.type === 'search' || 
                        (el.placeholder && /search|поиск|find/i.test(el.placeholder)) ||
                        (el.name && /search|q|s|query|find/i.test(el.name))) {
                        result.search_inputs.push(data);
                    }
                });
                
                document.querySelectorAll('button, input[type="submit"]').forEach(el => {
                    result.buttons.push({
                        text: (el.innerText || el.value || '').trim(),
                        id: el.id || null,
                        class: el.className || null
                    });
                });
                
                return result;
            })()
            """
            
            analysis = await tab.execute_script(script)
            session.context_variables['page_analysis'] = analysis
            learning_memory.learn_site_structure(session.current_url, analysis)
            
            summary = f"📊 Найдено: {len(analysis.get('inputs', []))} полей, {len(analysis.get('buttons', []))} кнопок"
            return {"success": True, "analysis": analysis, "summary": summary}

        # ============================================================
        # ПОИСК (с retry)
        # ============================================================
        elif tool_name == "find_element":
            find_args = {}
            for attr in ['id', 'class_name', 'name', 'tag_name', 'text']:
                if attr in arguments:
                    find_args[attr] = arguments[attr]
            
            timeout = arguments.get("timeout", 10)
            
            try:
                element = await safe_find_element(tab, timeout=timeout, **find_args)
                text = await element.text
                return {"success": True, "found": True, "text": text[:200] if text else ""}
            except ElementNotFound:
                return {"success": False, "error": "Элемент не найден"}

        elif tool_name == "find_element_smart":
            text = arguments["text"]
            element_type = arguments.get("element_type", "")
            
            script = f"""
            (function() {{
                const hint = '{text}';
                const type = '{element_type}';
                
                let elements = document.querySelectorAll(
                    '[placeholder*="{text}"], [aria-label*="{text}"], [title*="{text}"]'
                );
                
                if (elements.length === 0) {{
                    const all = document.querySelectorAll('*');
                    for (let el of all) {{
                        if (el.innerText && el.innerText.includes(hint)) {{
                            elements = [el];
                            break;
                        }}
                    }}
                }}
                
                if (type) {{
                    elements = Array.from(elements).filter(el => el.tagName.toLowerCase() === type);
                }}
                
                return elements.length > 0 ? elements[0].outerHTML : null;
            }})()
            """
            
            result = await tab.execute_script(script)
            if result:
                return {"success": True, "found": True}
            return {"success": False, "error": f"Не найдено: {text}"}

        elif tool_name == "find_element_from_memory":
            element_type = arguments["element_type"]
            selector_info = learning_memory.get_learned_selector(session.current_url, element_type)
            if not selector_info:
                return {"success": False, "error": f"Нет селектора для {element_type}"}
            
            try:
                if selector_info.get('id'):
                    element = await tab.query(f"#{selector_info['id']}")
                elif selector_info.get('name'):
                    element = await tab.query(f"[name='{selector_info['name']}']")
                else:
                    return {"success": False, "error": "Неизвестный селектор"}
                return {"success": True, "found": True}
            except:
                return {"success": False, "error": "Элемент не найден"}

        # ============================================================
        # ВЗАИМОДЕЙСТВИЕ (с humanize)
        # ============================================================
        elif tool_name == "click_element":
            try:
                await safe_click_element(tab, arguments["selector"])
                return {"success": True, "message": f"🖱️ Кликнут: {arguments['selector']}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif tool_name == "type_text":
            try:
                await safe_type_text(tab, arguments["selector"], arguments["text"])
                return {"success": True, "message": f"⌨️ Введён текст"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif tool_name == "type_into_search_smart":
            text = arguments["text"]
            
            # Пробуем из памяти
            remembered = learning_memory.get_learned_selector(session.current_url, "search")
            if remembered:
                try:
                    if remembered.get('id'):
                        selector = f"#{remembered['id']}"
                    elif remembered.get('name'):
                        selector = f"[name='{remembered['name']}']"
                    else:
                        selector = None
                    
                    if selector:
                        await safe_type_text(tab, selector, text)
                        await tab.keyboard.press(Key.ENTER)
                        return {"success": True, "message": f"🔍 Поиск: {text}", "found_by": "memory"}
                except:
                    pass
            
            # Fallback: перебор селекторов
            selectors = [
                'input[type="search"]',
                'input[name="q"]',
                'input[name="search_query"]',
                'input[name="search"]',
                'input[placeholder*="search" i]',
                'input[placeholder*="поиск" i]',
            ]
            
            for selector in selectors:
                try:
                    await safe_type_text(tab, selector, text)
                    await tab.keyboard.press(Key.ENTER)
                    return {"success": True, "message": f"🔍 Поиск: {text}", "found_by": "fallback"}
                except:
                    continue
            
            return {"success": False, "error": "Не найдено поле поиска"}

        elif tool_name == "press_key":
            key_map = {
                "Enter": Key.ENTER, "Tab": Key.TAB, "Escape": Key.ESCAPE,
                "ArrowUp": Key.ARROWUP, "ArrowDown": Key.ARROWDOWN,
                "ArrowLeft": Key.ARROWLEFT, "ArrowRight": Key.ARROWRIGHT,
            }
            key = key_map.get(arguments["key"], arguments["key"])
            await tab.keyboard.press(key)
            return {"success": True, "message": f"⌨️ Нажата: {arguments['key']}"}

        # ============================================================
        # СКРИНШОТЫ
        # ============================================================
        elif tool_name == "take_screenshot":
            try:
                screenshot = await tab.take_screenshot(
                    beyond_viewport=arguments.get("full_page", False),  # ← False по умолчанию
                    as_base64=True
                )
                return {"success": True, "screenshot": screenshot}
            except Exception as e:
                logger.warning(f"Screenshot failed: {e}")
                screenshot = await tab.take_screenshot(
                    beyond_viewport=False,
                    as_base64=True
                )
                return {"success": True, "screenshot": screenshot}

        # ============================================================
        # ДАННЫЕ
        # ============================================================
        elif tool_name == "get_page_title":
            title = await tab.title
            return {"success": True, "title": title}

        elif tool_name == "get_current_url":
            url = await tab.current_url
            return {"success": True, "url": url}

        elif tool_name == "execute_javascript":
            result = await tab.execute_script(arguments["script"])
            return {"success": True, "result": str(result)[:500]}

        # ============================================================
        # GITHUB
        # ============================================================
        elif tool_name == "analyze_github_repo":
            repo_url = arguments["repo_url"]
            match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
            if not match:
                return {"success": False, "error": "Неверный URL"}
            
            owner, repo = match.group(1), match.group(2).replace('.git', '')
            readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
            
            try:
                readme = await tab.execute_script(f"""
                    return fetch('{readme_url}')
                        .then(r => r.text())
                        .catch(e => 'README не найден')
                """)
                
                api_url = f"https://api.github.com/repos/{owner}/{repo}"
                headers = f"Authorization: token {GITHUB_TOKEN}" if GITHUB_TOKEN else ""
                
                repo_info = await tab.execute_script(f"""
                    return fetch('{api_url}', {{
                        headers: {{ 'Authorization': '{GITHUB_TOKEN}' }}
                    }})
                    .then(r => r.json())
                    .catch(e => ({{ error: e.message }}))
                """)
                
                result = {
                    "repo": f"{owner}/{repo}",
                    "description": repo_info.get("description", "Нет описания"),
                    "stars": repo_info.get("stargazers_count", 0),
                    "forks": repo_info.get("forks_count", 0),
                    "language": repo_info.get("language", "Неизвестно"),
                    "readme": readme[:1000] if readme else "Нет README"
                }
                
                return {
                    "success": True,
                    "data": result,
                    "summary": f"📦 {owner}/{repo}\n⭐ {result['stars']} звёзд\n📝 {result['description'][:100]}"
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif tool_name == "search_github":
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            search_url = f"https://api.github.com/search/repositories?q={query}&per_page={limit}"
            
            try:
                result = await tab.execute_script(f"""
                    return fetch('{search_url}')
                        .then(r => r.json())
                        .catch(e => ({{ error: e.message }}))
                """)
                
                if result.get("error"):
                    return {"success": False, "error": result["error"]}
                
                items = result.get("items", [])
                return {
                    "success": True,
                    "count": len(items),
                    "results": [{"name": item.get("full_name"), "stars": item.get("stargazers_count", 0)} for item in items]
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ============================================================
        # ОБХОД CLOUDFLARE
        # ============================================================
        elif tool_name == "bypass_cloudflare":
            url = arguments.get("url", "")
            try:
                async with tab.expect_and_bypass_cloudflare_captcha():
                    await tab.go_to(url)
                return {"success": True, "message": "✅ Cloudflare обойдён"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ============================================================
        # ПАМЯТЬ
        # ============================================================
        elif tool_name == "get_memory_stats":
            memory = learning_memory.memory
            return {
                "success": True,
                "stats": {
                    "sites_learned": len(memory.get("sites", {})),
                    "selectors_learned": sum(len(site.get("selectors", {})) for site in memory.get("sites", {}).values())
                }
            }

        else:
            return {"success": False, "error": f"❌ Неизвестный инструмент: {tool_name}"}

    except Exception as e:
        error_tracker.add_error(e, {"tool": tool_name, "user_id": user_id})
        return {"success": False, "error": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 9. ОБРАБОТКА ЧЕРЕЗ AGNES AI
# ============================================================

@log_error
async def process_with_agnes(user_message: str, user_id: int) -> Dict:
    """Обрабатывает запрос через Agnes AI"""
    global agnes_client

    if agnes_client is None:
        init_agnes()

    try:
        session = await session_manager.get_session(user_id)
        domain = learning_memory._extract_domain(session.current_url) if session.current_url else ""
        site_memory = learning_memory.memory.get("sites", {}).get(domain, {})

        system_prompt = f"""
Ты — AI агент, управляющий браузером через Pydoll.

**Состояние:**
- URL: {session.current_url or 'нет'}
- Браузер: {'открыт' if session.is_active else 'закрыт'}

**Память о сайте {domain}:**
{json.dumps(site_memory.get('selectors', {}), indent=2, ensure_ascii=False) if site_memory else 'Нет данных'}

**Правила:**
1. Используй type_into_search_smart для поиска — он сам найдёт поле
2. Используй click_element с humanize=True
3. Для сложных сайтов используй analyze_page_structure
4. Всегда проверяй память через find_element_from_memory
5. Для обхода Cloudflare используй bypass_cloudflare
6. При ошибках используй retry автоматически

**Доступные инструменты:**
- go_to_url, go_back, refresh_page — навигация
- find_element, find_element_smart, find_element_from_memory — поиск
- click_element, type_text, type_into_search_smart — взаимодействие
- take_screenshot — скриншот
- analyze_page_structure — анализ
- bypass_cloudflare — обход капчи
- analyze_github_repo, search_github — GitHub
- get_memory_stats — статистика памяти
"""

        response = agnes_client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            tools=TOOLS,
            tool_choice="auto"
        )

        message = response.choices[0].message

        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                logger.info(f"🔧 Вызов: {tool_name}")

                result = await execute_tool(tool_name, arguments, user_id)

                if tool_name == "take_screenshot" and result.get("success") and result.get("screenshot"):
                    return {"type": "screenshot", "data": result["screenshot"]}

                if not result.get("success"):
                    return {"type": "text", "content": f"❌ {result.get('error', 'Ошибка')}"}

            return {"type": "text", "content": "✅ Готово!"}
        else:
            return {"type": "text", "content": message.content or "✅ Готово!"}

    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id})
        return {"type": "text", "content": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 10. КОМАНДЫ ТЕЛЕГРАМ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с AI агентом**\n\n"
        "Управляю браузером через естественный язык!\n"
        "**С самообучением и человеческим поведением!**\n\n"
        "📌 **Примеры:**\n"
        "• `Открой браузер`\n"
        "• `Перейди на youtube.com`\n"
        "• `Найди видео про Джастина Бибера`\n"
        "• `Сделай скриншот`\n"
        "• `Проанализируй GitHub репозиторий`\n\n"
        "🔧 **Команды:**\n"
        "/open — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/status — Статус\n"
        "/memory — Память агента\n"
        "/debug — Отладка",
        parse_mode='Markdown'
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер...")
    try:
        session = await session_manager.get_session(user_id)
        await session.tab.current_url
        await update.message.reply_text("✅ Браузер открыт!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("❌ Закрываю браузер...")
    try:
        await session_manager.close_session(user_id)
        await update.message.reply_text("✅ Браузер закрыт!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)
    
    memory_stats = await execute_tool("get_memory_stats", {}, user_id)
    stats = memory_stats.get("stats", {}) if memory_stats.get("success") else {}

    message = (
        f"📊 **Статус**\n\n"
        f"🌐 Браузер: {'✅ Активен' if session.is_active else '❌ Не активен'}\n"
        f"🔗 URL: `{session.current_url or 'нет'}`\n"
        f"🧠 Сайтов изучено: {stats.get('sites_learned', 0)}\n"
        f"📋 Селекторов: {stats.get('selectors_learned', 0)}"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory_stats = await execute_tool("get_memory_stats", {}, update.effective_user.id)
    stats = memory_stats.get("stats", {}) if memory_stats.get("success") else {}
    
    sites = learning_memory.memory.get("sites", {})
    message = f"🧠 **Память агента**\n\n"
    message += f"📊 Сайтов изучено: {stats.get('sites_learned', 0)}\n"
    message += f"📋 Селекторов: {stats.get('selectors_learned', 0)}\n\n"
    message += "🌐 **Изученные сайты:**\n"
    
    for domain, info in list(sites.items())[:10]:
        message += f"  - {domain} (посещён {info.get('visits', 0)} раз)\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка отключена
    session = await session_manager.get_session(update.effective_user.id)
    memory_stats = await execute_tool("get_memory_stats", {}, update.effective_user.id)

    message = (
        f"🔍 **Отладка**\n\n"
        f"**Сессии:** {len(session_manager.sessions)}\n"
        f"**Браузер:** {'✅' if session_manager._browser else '❌'}\n"
        f"**Вкладка:** {'✅' if session.tab else '❌'}\n"
        f"**Ошибок:** {len(error_tracker.errors)}\n"
        f"**Память:** {memory_stats.get('stats', {}).get('sites_learned', 0)} сайтов\n"
        f"**Логи:** `{LOG_DIR.absolute()}`"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    if user_message.startswith('/'):
        return

    await update.message.reply_text("🤔 Думаю...")

    try:
        result = await process_with_agnes(user_message, user_id)

        if result["type"] == "screenshot":
            try:
                screenshot_bytes = base64.b64decode(result["data"])
                
                # Сжимаем если слишком большое
                if len(screenshot_bytes) > 10 * 1024 * 1024:
                    try:
                        from PIL import Image
                        import io
                        image = Image.open(io.BytesIO(screenshot_bytes))
                        if image.width > 1280:
                            ratio = 1280 / image.width
                            new_size = (1280, int(image.height * ratio))
                            image = image.resize(new_size, Image.Resampling.LANCZOS)
                            buffer = io.BytesIO()
                            image.save(buffer, format='PNG', optimize=True)
                            screenshot_bytes = buffer.getvalue()
                    except:
                        pass
                
                await update.message.reply_photo(
                    screenshot_bytes,
                    caption="📸 Скриншот"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        else:
            await update.message.reply_text(result["content"])

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    error_tracker.add_error(error, {
        "user_id": update.effective_user.id if update else None
    })
    error_logger.error(f"Ошибка: {error}\n{traceback.format_exc()}")

# ============================================================
# 11. ФОНОВЫЕ ЗАДАЧИ
# ============================================================

async def cleanup_task():
    while True:
        await asyncio.sleep(300)
        try:
            await session_manager.cleanup_inactive(max_age_seconds=1800)
        except Exception as e:
            logger.error(f"Ошибка в cleanup_task: {e}")

async def health_check_task():
    while True:
        await asyncio.sleep(60)
        try:
            if session_manager._browser:
                await session_manager._browser.active_page
        except:
            logger.warning("⚠️ Браузер умер, пересоздаём")
            session_manager._browser = None

# ============================================================
# 12. ЗАПУСК
# ============================================================

async def main():
    try:
        init_agnes()

        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open", open_command))
        application.add_handler(CommandHandler("close", close_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("memory", memory_command))
        application.add_handler(CommandHandler("debug", debug_command))

        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        asyncio.create_task(cleanup_task())
        asyncio.create_task(health_check_task())

        logger.info("=" * 60)
        logger.info("🚀 Бот v5.0 запущен!")
        logger.info(f"📁 Логи: {LOG_DIR.absolute()}")
        logger.info(f"🧠 Память: {MEMORY_DIR.absolute()}")
        logger.info("=" * 60)

        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        try:
            if 'application' in locals():
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            await session_manager.close_all()
        except:
            pass
        logger.info("✅ Бот завершил работу")

if __name__ == "__main__":
    asyncio.run(main())