#!/usr/bin/env python3
"""
Telegram Bot с Agnes AI агентом для управления браузером через Pydoll
Версия: 4.0 - С самообучением и анализом GitHub
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
# ИМПОРТЫ PYDOLL ПО ДОКУМЕНТАЦИИ
# ============================================================
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key

# Исключения
try:
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
except ImportError:
    class PydollException(Exception): pass
    class ElementNotFound(Exception): pass
    class WaitElementTimeout(Exception): pass
    class ElementNotVisible(Exception): pass
    class ElementNotInteractable(Exception): pass
    class NetworkError(Exception): pass
    class PageLoadTimeout(Exception): pass
    class ConnectionFailed(Exception): pass
    class ClickIntercepted(Exception): pass

# Скролл
try:
    from pydoll.constants import ScrollPosition
    SCROLL_AVAILABLE = True
except ImportError:
    SCROLL_AVAILABLE = False

# Декораторы
try:
    from pydoll.decorators import retry
    RETRY_AVAILABLE = True
except ImportError:
    RETRY_AVAILABLE = False
    def retry(max_retries=3, exceptions=None, on_retry=None, delay=1.0, exponential_backoff=False):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # Для доступа к GitHub API

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
# 4. СИСТЕМА САМООБУЧЕНИЯ (ПАМЯТЬ И ШАБЛОНЫ)
# ============================================================

class LearningMemory:
    """Система самообучения агента"""
    
    def __init__(self):
        self.memory_file = MEMORY_DIR / "agent_memory.json"
        self.templates_file = TEMPLATES_DIR / "templates.json"
        self.memory = self._load_memory()
        self.templates = self._load_templates()
    
    def _load_memory(self) -> Dict:
        """Загружает память агента"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "sites": {},           # Знания о конкретных сайтах
            "patterns": {},        # Успешные паттерны действий
            "selectors": {},       # Сохранённые селекторы для сайтов
            "learned_at": datetime.now().isoformat()
        }
    
    def _load_templates(self) -> Dict:
        """Загружает шаблоны действий"""
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
        """Сохраняет память"""
        self.memory["learned_at"] = datetime.now().isoformat()
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)
    
    def save_templates(self):
        """Сохраняет шаблоны"""
        with open(self.templates_file, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
    
    def learn_site_structure(self, url: str, analysis: Dict):
        """Запоминает структуру сайта"""
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
        
        # Сохраняем важные селекторы
        if analysis.get("search_inputs"):
            site["selectors"]["search"] = analysis["search_inputs"][0]
        if analysis.get("buttons"):
            site["selectors"]["buttons"] = analysis["buttons"][:5]
        
        self.save_memory()
        logger.info(f"🧠 Агент запомнил структуру {domain}")
    
    def learn_successful_pattern(self, action_sequence: List[Dict], site: str, result: str):
        """Запоминает успешную последовательность действий"""
        pattern = {
            "site": site,
            "actions": action_sequence,
            "result": result,
            "created_at": datetime.now().isoformat(),
            "uses": 1,
            "success_rate": 1.0
        }
        
        # Проверяем, есть ли похожий паттерн
        for existing in self.templates["templates"]:
            if existing["site"] == site and existing["actions"] == action_sequence[:2]:
                existing["uses"] += 1
                existing["success_rate"] = (existing["success_rate"] * existing["uses"] + 1) / (existing["uses"] + 1)
                self.save_templates()
                return
        
        self.templates["templates"].append(pattern)
        self.templates["stats"]["total"] += 1
        self.templates["stats"]["successful"] += 1
        self.save_templates()
        logger.info(f"🧠 Агент запомнил новый паттерн для {site}")
    
    def get_learned_selector(self, url: str, element_type: str) -> Optional[Dict]:
        """Возвращает сохранённый селектор для сайта"""
        domain = self._extract_domain(url)
        if domain in self.memory["sites"]:
            site = self.memory["sites"][domain]
            if element_type in site.get("selectors", {}):
                return site["selectors"][element_type]
        return None
    
    def get_template_for_site(self, site: str) -> Optional[List[Dict]]:
        """Возвращает сохранённый шаблон для сайта"""
        for template in self.templates["templates"]:
            if template["site"] in site:
                return template["actions"]
        return None
    
    def _extract_domain(self, url: str) -> str:
        """Извлекает домен из URL"""
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
    action_history: List[Dict] = field(default_factory=list)  # Для самообучения

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
# 7. ИНСТРУМЕНТЫ ДЛЯ AGNES AI (С САМООБУЧЕНИЕМ И GITHUB)
# ============================================================

TOOLS = [
    # --- НАВИГАЦИЯ ---
    {
        "type": "function",
        "function": {
            "name": "go_to_url",
            "description": "Переходит на указанный URL и автоматически анализирует страницу",
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
    
    # --- АНАЛИЗ СТРАНИЦЫ ---
    {
        "type": "function",
        "function": {
            "name": "analyze_page_structure",
            "description": "Глубоко анализирует структуру страницы: все input, button, link, form с их атрибутами",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_learned_selectors",
            "description": "Возвращает сохранённые селекторы для текущего сайта из памяти агента",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- УМНЫЙ ПОИСК ЭЛЕМЕНТОВ ---
    {
        "type": "function",
        "function": {
            "name": "find_element",
            "description": "Находит элемент по HTML атрибутам (id, class_name, name, tag_name, text, placeholder, aria_label)",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "tag_name": {"type": "string"},
                    "text": {"type": "string"},
                    "placeholder": {"type": "string"},
                    "aria_label": {"type": "string"},
                    "timeout": {"type": "integer", "default": 10}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_element_by_css",
            "description": "Находит элемент по CSS селектору",
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
            "name": "find_element_smart",
            "description": "Умный поиск элемента по тексту (placeholder, aria-label, title, label)",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для поиска"},
                    "element_type": {"type": "string", "enum": ["input", "button", "link", "div", "span"]}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_element_from_memory",
            "description": "Ищет элемент используя сохранённую память о сайте",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_type": {"type": "string", "enum": ["search", "login", "submit", "email", "password"]}
                },
                "required": ["element_type"]
            }
        }
    },
    
    # --- ВЗАИМОДЕЙСТВИЕ ---
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу",
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
            "description": "Вводит текст в элемент",
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
            "description": "Автоматически находит поле поиска и вводит текст (с использованием памяти)",
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
            "name": "clear_field",
            "description": "Очищает поле ввода",
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
            "name": "press_key",
            "description": "Нажимает клавишу",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        }
    },
    
    # --- СКРИНШОТЫ ---
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Делает скриншот страницы",
            "parameters": {
                "type": "object",
                "properties": {"full_page": {"type": "boolean", "default": True}}
            }
        }
    },
    
    # --- СКРОЛЛ ---
    {
        "type": "function",
        "function": {
            "name": "scroll_to_bottom",
            "description": "Прокручивает страницу вниз",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_to_top",
            "description": "Прокручивает страницу вверх",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- ДАННЫЕ ---
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
            "name": "get_page_source",
            "description": "Получает HTML код страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- JAVASCRIPT ---
    {
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": "Выполняет JavaScript код на странице",
            "parameters": {
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_data_with_js",
            "description": "Извлекает данные со страницы используя JavaScript",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS селектор для данных"},
                    "attribute": {"type": "string", "description": "Атрибут для извлечения (text, html, value и т.д.)"}
                },
                "required": ["selector"]
            }
        }
    },
    
    # --- HTTP ---
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Выполняет HTTP GET запрос",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    
    # --- COOKIES ---
    {
        "type": "function",
        "function": {
            "name": "get_cookies",
            "description": "Получает все cookies текущей страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_cookie",
            "description": "Устанавливает cookie",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "domain": {"type": "string"}
                },
                "required": ["name", "value"]
            }
        }
    },
    
    # --- GITHUB АНАЛИЗ ---
    {
        "type": "function",
        "function": {
            "name": "analyze_github_repo",
            "description": "Анализирует GitHub репозиторий: читает README, структуру, находит примеры кода",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "URL репозитория (например, https://github.com/user/repo)"},
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
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "limit": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    
    # --- ПАМЯТЬ И ОБУЧЕНИЕ ---
    {
        "type": "function",
        "function": {
            "name": "save_learned_pattern",
            "description": "Сохраняет успешную последовательность действий для будущего использования",
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "description": "Список выполненных действий"},
                    "description": {"type": "string", "description": "Описание что было сделано"}
                },
                "required": ["actions"]
            }
        }
    },
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
# 8. ИСПОЛНЕНИЕ ИНСТРУМЕНТОВ (С САМООБУЧЕНИЕМ)
# ============================================================

@log_error
async def execute_tool(tool_name: str, arguments: Dict, user_id: int) -> Dict:
    """Выполняет инструмент с самообучением"""
    session = await session_manager.get_session(user_id)
    tab = session.tab

    if not tab:
        return {"success": False, "error": "⚠️ Браузер не открыт. Используйте /open"}

    try:
        # ============================================================
        # НАВИГАЦИЯ
        # ============================================================
        if tool_name == "go_to_url":
            url = arguments.get("url", "")
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await tab.go_to(url)
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.last_action = "go_to_url"
            session.last_action_time = datetime.now()
            
            # АВТО-АНАЛИЗ И ЗАПОМИНАНИЕ
            try:
                analysis_result = await execute_tool("analyze_page_structure", {}, user_id)
                if analysis_result.get("success"):
                    learning_memory.learn_site_structure(url, analysis_result.get("analysis", {}))
                    logger.info(f"🧠 Страница {url} проанализирована и запомнена")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проанализировать: {e}")
            
            return {"success": True, "url": session.current_url, "title": session.page_title}

        elif tool_name == "go_back":
            await tab.go_back()
            session.last_action = "go_back"
            session.last_action_time = datetime.now()
            return {"success": True, "message": "↩️ Назад"}

        elif tool_name == "refresh_page":
            await tab.refresh()
            session.last_action = "refresh_page"
            session.last_action_time = datetime.now()
            return {"success": True, "message": "🔄 Обновлено"}

        # ============================================================
        # АНАЛИЗ СТРАНИЦЫ
        # ============================================================
        elif tool_name == "analyze_page_structure":
            script = """
            (function() {
                const result = {
                    url: window.location.href,
                    title: document.title,
                    inputs: [],
                    buttons: [],
                    links: [],
                    forms: [],
                    search_inputs: [],
                    main_content: null
                };
                
                document.querySelectorAll('input, textarea').forEach(el => {
                    const data = {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        id: el.id || null,
                        name: el.name || null,
                        class: el.className || null,
                        placeholder: el.placeholder || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        title: el.title || null,
                        visible: el.offsetParent !== null
                    };
                    result.inputs.push(data);
                    
                    if (el.type === 'search' || 
                        (el.placeholder && /search|поиск|find|найти/i.test(el.placeholder)) ||
                        (el.name && /search|q|s|query|find/i.test(el.name))) {
                        result.search_inputs.push(data);
                    }
                });
                
                document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]').forEach(el => {
                    result.buttons.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        class: el.className || null,
                        text: (el.innerText || el.value || '').trim(),
                        type: el.type || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        visible: el.offsetParent !== null
                    });
                });
                
                document.querySelectorAll('a[href]').forEach(el => {
                    result.links.push({
                        href: el.href,
                        text: (el.innerText || '').trim(),
                        id: el.id || null,
                        class: el.className || null,
                        visible: el.offsetParent !== null
                    });
                });
                
                document.querySelectorAll('form').forEach(el => {
                    const inputs = [];
                    el.querySelectorAll('input, textarea, select').forEach(input => {
                        inputs.push({
                            name: input.name || null,
                            type: input.type || null,
                            placeholder: input.placeholder || null
                        });
                    });
                    result.forms.push({
                        id: el.id || null,
                        class: el.className || null,
                        action: el.action || null,
                        method: el.method || 'get',
                        inputs: inputs
                    });
                });
                
                const main = document.querySelector('main, [role="main"], #main, .main, article');
                if (main) {
                    result.main_content = {
                        tag: main.tagName.toLowerCase(),
                        id: main.id || null,
                        class: main.className || null,
                        text_preview: main.innerText.slice(0, 200)
                    };
                }
                
                return result;
            })()
            """
            
            analysis = await tab.execute_script(script)
            session.context_variables['page_analysis'] = analysis
            session.context_variables['page_analyzed_at'] = datetime.now().isoformat()
            
            # Запоминаем структуру
            learning_memory.learn_site_structure(session.current_url, analysis)
            
            # Формируем отчёт
            summary = f"""
📊 **Анализ страницы:**
- URL: {analysis.get('url', 'неизвестен')}
- Заголовок: {analysis.get('title', 'нет')}
- Полей ввода: {len(analysis.get('inputs', []))}
- Кнопок: {len(analysis.get('buttons', []))}
- Ссылок: {len(analysis.get('links', []))}
- Форм: {len(analysis.get('forms', []))}
- Поля поиска: {len(analysis.get('search_inputs', []))}
            """
            
            if analysis.get('search_inputs'):
                summary += "\n🔍 **Поля поиска:**\n"
                for inp in analysis['search_inputs'][:3]:
                    summary += f"  - {inp.get('tag')} name='{inp.get('name')}' placeholder='{inp.get('placeholder')}'\n"
            
            return {"success": True, "analysis": analysis, "summary": summary}

        elif tool_name == "get_learned_selectors":
            url = session.current_url
            domain = learning_memory._extract_domain(url)
            memory = learning_memory.memory
            
            if domain in memory.get("sites", {}):
                return {"success": True, "selectors": memory["sites"][domain].get("selectors", {})}
            return {"success": False, "error": "Нет сохранённых селекторов для этого сайта"}

        # ============================================================
        # УМНЫЙ ПОИСК
        # ============================================================
        elif tool_name == "find_element":
            find_args = {}
            for attr in ['id', 'class_name', 'name', 'tag_name', 'text', 'placeholder', 'aria_label']:
                if attr in arguments:
                    find_args[attr] = arguments[attr]
            
            timeout = arguments.get("timeout", 10)
            
            try:
                element = await tab.find(timeout=timeout, **find_args)
                text = await element.text
                return {"success": True, "found": True, "text": text[:200] if text else ""}
            except ElementNotFound:
                return {"success": False, "error": "Элемент не найден"}
            except WaitElementTimeout:
                return {"success": False, "error": f"Таймаут {timeout}с"}

        elif tool_name == "find_element_by_css":
            try:
                element = await tab.query(arguments["selector"])
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
                    '[placeholder*="{text}"], [aria-label*="{text}"], [title*="{text}"], [name*="{text}"]'
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
                return {"success": True, "found": True, "html": result[:300]}
            return {"success": False, "error": f"Не найдено: {text}"}

        elif tool_name == "find_element_from_memory":
            element_type = arguments["element_type"]
            url = session.current_url
            
            selector_info = learning_memory.get_learned_selector(url, element_type)
            if not selector_info:
                return {"success": False, "error": f"Нет сохранённого селектора для {element_type} на этом сайте"}
            
            try:
                if selector_info.get('id'):
                    element = await tab.query(f"#{selector_info['id']}")
                elif selector_info.get('name'):
                    element = await tab.query(f"[name='{selector_info['name']}']")
                else:
                    return {"success": False, "error": "Неизвестный селектор"}
                
                return {"success": True, "found": True, "element": selector_info}
            except:
                return {"success": False, "error": "Элемент не найден по сохранённому селектору"}

        # ============================================================
        # ВЗАИМОДЕЙСТВИЕ
        # ============================================================
        elif tool_name == "click_element":
            try:
                element = await tab.query(arguments["selector"])
                await element.click()
                session.last_action = "click_element"
                session.last_action_time = datetime.now()
                return {"success": True, "message": f"🖱️ Кликнут: {arguments['selector']}"}
            except ElementNotFound:
                return {"success": False, "error": "Элемент не найден"}

        elif tool_name == "type_text":
            try:
                element = await tab.query(arguments["selector"])
                await element.clear()
                await element.type_text(arguments["text"])
                session.last_action = "type_text"
                session.last_action_time = datetime.now()
                return {"success": True, "message": f"⌨️ Введён текст"}
            except ElementNotFound:
                return {"success": False, "error": "Элемент не найден"}

        elif tool_name == "type_into_search_smart":
            text = arguments["text"]
            url = session.current_url
            
            # 1. Проверяем память
            remembered = learning_memory.get_learned_selector(url, "search")
            if remembered:
                try:
                    if remembered.get('id'):
                        selector = f"#{remembered['id']}"
                    elif remembered.get('name'):
                        selector = f"[name='{remembered['name']}']"
                    else:
                        selector = None
                    
                    if selector:
                        element = await tab.query(selector)
                        await element.clear()
                        await element.type_text(text)
                        await tab.keyboard.press(Key.ENTER)
                        return {"success": True, "message": f"🔍 Поиск: {text}", "found_by": "memory"}
                except:
                    pass
            
            # 2. Fallback: перебор селекторов
            selectors = [
                'input[type="search"]',
                'input[name="q"]',
                'input[name="search_query"]',
                'input[name="search"]',
                'input#search',
                'input[placeholder*="search" i]',
                'input[placeholder*="поиск" i]',
                'textarea[placeholder*="search" i]',
                'textarea[placeholder*="поиск" i]',
                '[role="search"] input',
                '.search input',
                '#search input',
                'form[role="search"] input',
                'form[action*="search"] input'
            ]
            
            for selector in selectors:
                try:
                    element = await tab.query(selector)
                    if element:
                        await element.clear()
                        await element.type_text(text)
                        await tab.keyboard.press(Key.ENTER)
                        # Запоминаем успешный селектор
                        return {"success": True, "message": f"🔍 Поиск: {text}", "found_by": "fallback"}
                except ElementNotFound:
                    continue
            
            return {"success": False, "error": "Не найдено поле поиска"}

        elif tool_name == "clear_field":
            try:
                element = await tab.query(arguments["selector"])
                await element.clear()
                return {"success": True, "message": "🧹 Поле очищено"}
            except ElementNotFound:
                return {"success": False, "error": "Элемент не найден"}

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
                    beyond_viewport=arguments.get("full_page", True),
                    as_base64=True
                )
                session.last_action = "take_screenshot"
                session.last_action_time = datetime.now()
                return {"success": True, "screenshot": screenshot}
            except Exception as e:
                logger.warning(f"Full page screenshot failed: {e}, trying without")
                screenshot = await tab.take_screenshot(as_base64=True)
                return {"success": True, "screenshot": screenshot}

        # ============================================================
        # СКРОЛЛ
        # ============================================================
        elif tool_name == "scroll_to_bottom":
            await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            return {"success": True, "message": "📜 Вниз"}

        elif tool_name == "scroll_to_top":
            await tab.execute_script("window.scrollTo(0, 0)")
            return {"success": True, "message": "📜 Вверх"}

        # ============================================================
        # ДАННЫЕ
        # ============================================================
        elif tool_name == "get_page_title":
            title = await tab.title
            return {"success": True, "title": title}

        elif tool_name == "get_current_url":
            url = await tab.current_url
            return {"success": True, "url": url}

        elif tool_name == "get_page_source":
            source = await tab.page_source
            return {"success": True, "source": source[:2000] + "..." if len(source) > 2000 else source}

        # ============================================================
        # JAVASCRIPT
        # ============================================================
        elif tool_name == "execute_javascript":
            result = await tab.execute_script(arguments["script"])
            return {"success": True, "result": str(result)[:500]}

        elif tool_name == "extract_data_with_js":
            selector = arguments["selector"]
            attribute = arguments.get("attribute", "text")
            
            script = f"""
            (function() {{
                const elements = document.querySelectorAll('{selector}');
                return Array.from(elements).map(el => {{
                    if ('{attribute}' === 'text') return el.innerText.trim();
                    if ('{attribute}' === 'html') return el.innerHTML;
                    if ('{attribute}' === 'value') return el.value;
                    return el.getAttribute('{attribute}');
                }});
            }})()
            """
            
            result = await tab.execute_script(script)
            return {"success": True, "data": result, "count": len(result) if isinstance(result, list) else 0}

        # ============================================================
        # HTTP
        # ============================================================
        elif tool_name == "http_get":
            try:
                response = await tab.request.get(arguments["url"])
                return {"success": True, "data": response.text[:500]}
            except:
                result = await tab.execute_script(f"""
                    return fetch('{arguments["url"]}')
                        .then(r => r.text())
                        .catch(e => 'Error: ' + e.message)
                """)
                return {"success": True, "data": str(result)[:500]}

        # ============================================================
        # COOKIES
        # ============================================================
        elif tool_name == "get_cookies":
            try:
                cookies = await tab.execute_script("return document.cookie")
                return {"success": True, "cookies": cookies}
            except:
                return {"success": True, "cookies": "Не удалось получить"}

        elif tool_name == "set_cookie":
            await tab.execute_script(f"""
                document.cookie = "{arguments['name']}={arguments['value']}; domain={arguments.get('domain', '')}; path=/";
            """)
            return {"success": True, "message": f"🍪 Cookie установлен: {arguments['name']}"}

        # ============================================================
        # GITHUB АНАЛИЗ
        # ============================================================
        elif tool_name == "analyze_github_repo":
            repo_url = arguments["repo_url"]
            depth = arguments.get("depth", "quick")
            
            # Извлекаем имя репозитория
            match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
            if not match:
                return {"success": False, "error": "Неверный URL GitHub репозитория"}
            
            owner, repo = match.group(1), match.group(2)
            repo = repo.replace('.git', '')
            
            # Формируем API URL
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
            
            try:
                # Читаем README
                readme_result = await tab.execute_script(f"""
                    return fetch('{readme_url}')
                        .then(r => r.text())
                        .catch(e => 'README не найден')
                """)
                
                # Получаем информацию о репозитории через GitHub API (если есть токен)
                headers = ""
                if GITHUB_TOKEN:
                    headers = f"Authorization: token {GITHUB_TOKEN}"
                
                repo_info = await tab.execute_script(f"""
                    return fetch('{api_url}', {{
                        headers: {{ 'Authorization': '{GITHUB_TOKEN}' }}
                    }})
                    .then(r => r.json())
                    .catch(e => ({{ error: e.message }}))
                """)
                
                # Собираем результаты
                result = {
                    "repo": f"{owner}/{repo}",
                    "description": repo_info.get("description", "Нет описания"),
                    "stars": repo_info.get("stargazers_count", 0),
                    "forks": repo_info.get("forks_count", 0),
                    "language": repo_info.get("language", "Неизвестно"),
                    "readme": readme_result[:2000] if readme_result and len(readme_result) > 2000 else readme_result,
                    "topics": repo_info.get("topics", [])
                }
                
                # Сохраняем в память
                session.context_variables['last_github_analysis'] = result
                
                return {
                    "success": True,
                    "data": result,
                    "summary": f"📦 Репозиторий {owner}/{repo}\n⭐ {result['stars']} звёзд\n📝 {result['description'][:100] if result['description'] else 'Нет описания'}\n🔤 Язык: {result['language']}"
                }
            except Exception as e:
                return {"success": False, "error": f"Ошибка анализа: {str(e)}"}

        elif tool_name == "search_github":
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            
            # Используем GitHub Search API
            search_url = f"https://api.github.com/search/repositories?q={query}&per_page={limit}"
            
            try:
                headers = {}
                if GITHUB_TOKEN:
                    headers["Authorization"] = f"token {GITHUB_TOKEN}"
                
                result = await tab.execute_script(f"""
                    return fetch('{search_url}', {{
                        headers: {json.dumps(headers)}
                    }})
                    .then(r => r.json())
                    .catch(e => ({{ error: e.message }}))
                """)
                
                if result.get("error"):
                    return {"success": False, "error": result["error"]}
                
                items = result.get("items", [])
                return {
                    "success": True,
                    "count": len(items),
                    "results": [{
                        "name": item.get("full_name"),
                        "description": item.get("description", ""),
                        "stars": item.get("stargazers_count", 0),
                        "url": item.get("html_url")
                    } for item in items[:limit]]
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ============================================================
        # ПАМЯТЬ И ОБУЧЕНИЕ
        # ============================================================
        elif tool_name == "save_learned_pattern":
            actions = arguments.get("actions", [])
            description = arguments.get("description", "")
            
            if not actions:
                return {"success": False, "error": "Нет действий для сохранения"}
            
            url = session.current_url
            domain = learning_memory._extract_domain(url)
            
            # Сохраняем шаблон
            learning_memory.learn_successful_pattern(actions, domain, description)
            
            return {
                "success": True, 
                "message": f"🧠 Паттерн сохранён для {domain}",
                "actions_count": len(actions)
            }

        elif tool_name == "get_memory_stats":
            memory = learning_memory.memory
            templates = learning_memory.templates
            
            return {
                "success": True,
                "stats": {
                    "sites_learned": len(memory.get("sites", {})),
                    "templates_saved": len(templates.get("templates", [])),
                    "selectors_learned": sum(len(site.get("selectors", {})) for site in memory.get("sites", {}).values()),
                    "templates_success": templates.get("stats", {}).get("successful", 0)
                }
            }

        else:
            return {"success": False, "error": f"❌ Неизвестный инструмент: {tool_name}"}

    except Exception as e:
        error_tracker.add_error(e, {"tool": tool_name, "user_id": user_id})
        return {"success": False, "error": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 9. ОБРАБОТКА ЧЕРЕЗ AGNES AI С САМООБУЧЕНИЕМ
# ============================================================

@log_error
async def process_with_agnes(user_message: str, user_id: int) -> Dict:
    """Обрабатывает запрос через Agnes AI с использованием памяти"""
    global agnes_client

    if agnes_client is None:
        init_agnes()

    try:
        session = await session_manager.get_session(user_id)
        
        # Получаем память для текущего сайта
        domain = learning_memory._extract_domain(session.current_url) if session.current_url else ""
        site_memory = learning_memory.memory.get("sites", {}).get(domain, {})
        templates = learning_memory.get_template_for_site(domain)
        
        # Формируем системный промпт с памятью
        memory_context = ""
        if site_memory:
            selectors = site_memory.get("selectors", {})
            if selectors:
                memory_context += f"\n🧠 **Сохранённые селекторы для {domain}:**\n"
                for key, value in selectors.items():
                    memory_context += f"  - {key}: {value}\n"
        
        if templates:
            memory_context += f"\n📋 **Сохранённые шаблоны для {domain}:** {len(templates)} действий\n"
        
        system_prompt = f"""
Ты — AI агент, управляющий браузером через Pydoll.

**Состояние браузера:**
- Браузер: {'открыт' if session.is_active else 'закрыт'}
- URL: {session.current_url or 'нет'}
- Заголовок: {session.page_title or 'нет'}

{memory_context}

**Правила:**
1. Если браузер закрыт — сначала открой его
2. Используй инструменты для действий
3. Для скриншотов используй take_screenshot
4. Используй сохранённые селекторы из памяти (find_element_from_memory)
5. Для поиска на новом сайте используй analyze_page_structure
6. Сохраняй успешные паттерны через save_learned_pattern
7. После перехода на сайт, страница анализируется автоматически

**Доступные инструменты:**
- go_to_url, go_back, refresh_page — навигация
- analyze_page_structure — анализ страницы
- find_element, find_element_by_css — поиск элементов
- find_element_smart — умный поиск по тексту
- find_element_from_memory — поиск из памяти
- click_element, type_text, clear_field — взаимодействие
- type_into_search_smart — поиск с авто-определением
- take_screenshot — скриншот
- scroll_to_bottom, scroll_to_top — прокрутка
- get_page_title, get_current_url, get_page_source — данные
- execute_javascript — JS код
- extract_data_with_js — извлечение данных
- http_get — HTTP запросы
- get_cookies, set_cookie — управление куками
- analyze_github_repo — анализ GitHub репозиториев
- search_github — поиск на GitHub
- save_learned_pattern — сохранение паттернов
- get_memory_stats — статистика памяти

**Рекомендации:**
- Для YouTube используй type_into_search_smart
- Для Google используй type_into_search_smart или find_element(name="q")
- Для GitHub используй analyze_github_repo или search_github
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
        results = []
        action_sequence = []

        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                logger.info(f"🔧 Вызов: {tool_name} с аргументами: {arguments}")
                
                # Запоминаем действие
                action_sequence.append({"tool": tool_name, "args": arguments})

                result = await execute_tool(tool_name, arguments, user_id)
                results.append({"tool": tool_name, "result": result})

                if tool_name == "take_screenshot" and result.get("success") and result.get("screenshot"):
                    return {
                        "type": "screenshot",
                        "data": result["screenshot"],
                        "message": "📸 Скриншот готов"
                    }

            # Сохраняем успешный паттерн
            if results and all(r["result"].get("success") for r in results):
                await execute_tool(
                    "save_learned_pattern",
                    {"actions": action_sequence, "description": user_message[:100]},
                    user_id
                )

            # Формируем ответ
            if message.content:
                content = message.content
            else:
                content = "\n".join([
                    r["result"].get("message", r["result"].get("error", "✅ Готово"))
                    for r in results
                    if r["result"].get("success", False)
                ])

            errors = [r["result"].get("error", "") for r in results if not r["result"].get("success", False)]
            if errors:
                content += "\n\n⚠️ Ошибки:\n" + "\n".join(errors)

            return {"type": "text", "content": content}
        else:
            return {"type": "text", "content": message.content or "✅ Готово!"}

    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id, "action": "process_with_agnes"})
        return {"type": "text", "content": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 10. КОМАНДЫ ТЕЛЕГРАМ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    user_id = update.effective_user.id
    audit_logger.info(f"User {user_id} запустил бота")

    await update.message.reply_text(
        "🤖 **Бот с AI агентом на Agnes AI**\n\n"
        "Управляю браузером через естественный язык!\n"
        "**Обладает самообучением и памятью!**\n\n"
        "📌 **Примеры:**\n"
        "• `Открой браузер`\n"
        "• `Перейди на google.com`\n"
        "• `Найди кнопку Войти и кликни`\n"
        "• `Сделай скриншот`\n"
        "• `Проанализируй GitHub репозиторий https://github.com/user/repo`\n"
        "• `Найди на GitHub библиотеку для парсинга`\n\n"
        "🔧 **Команды:**\n"
        "/open — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/status — Статус сессии\n"
        "/memory — Статистика памяти\n"
        "/debug — Детальная отладка\n"
        "/errors — Показать ошибки\n\n"
        "💡 Просто напиши, что нужно сделать!",
        parse_mode='Markdown'
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает браузер"""
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер...")

    try:
        session = await session_manager.get_session(user_id)
        session.last_action = "open_browser"
        session.last_action_time = datetime.now()
        await session.tab.current_url
        await update.message.reply_text("✅ Браузер успешно открыт!")
    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id, "action": "open_command"})
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    user_id = update.effective_user.id
    await update.message.reply_text("❌ Закрываю браузер...")

    try:
        await session_manager.close_session(user_id)
        await update.message.reply_text("✅ Браузер закрыт!")
    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id, "action": "close_command"})
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус сессии"""
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)
    
    # Статистика памяти
    memory_stats = await execute_tool("get_memory_stats", {}, user_id)
    memory_info = memory_stats.get("stats", {}) if memory_stats.get("success") else {}

    status = "🟢 Активен" if session.is_active else "🔴 Не активен"

    message = (
        f"📊 **Статус сессии**\n\n"
        f"🆔 Пользователь: `{user_id}`\n"
        f"🌐 Браузер: {status}\n"
        f"🔒 Контекст: `{session.context_id or 'нет'}`\n"
        f"🔗 URL: `{session.current_url or 'нет'}`\n"
        f"📄 Заголовок: `{session.page_title or 'нет'}`\n"
        f"⚡ Последнее действие: {session.last_action or 'нет'}\n"
        f"⏰ Обновлено: {session.last_action_time.strftime('%H:%M:%S')}\n\n"
        f"🧠 **Память агента:**\n"
        f"  - Сайтов изучено: {memory_info.get('sites_learned', 0)}\n"
        f"  - Шаблонов сохранено: {memory_info.get('templates_saved', 0)}\n"
        f"  - Селекторов запомнено: {memory_info.get('selectors_learned', 0)}"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает память агента"""
    user_id = update.effective_user.id
    
    memory_stats = await execute_tool("get_memory_stats", {}, user_id)
    if not memory_stats.get("success"):
        await update.message.reply_text("❌ Не удалось получить статистику памяти")
        return
    
    stats = memory_stats.get("stats", {})
    
    memory = learning_memory.memory
    sites = memory.get("sites", {})
    
    message = (
        f"🧠 **Память агента**\n\n"
        f"📊 **Статистика:**\n"
        f"  - Изученных сайтов: {stats.get('sites_learned', 0)}\n"
        f"  - Сохранённых шаблонов: {stats.get('templates_saved', 0)}\n"
        f"  - Запомненных селекторов: {stats.get('selectors_learned', 0)}\n"
        f"  - Успешных шаблонов: {stats.get('templates_success', 0)}\n\n"
        f"🌐 **Изученные сайты:**\n"
    )
    
    for domain, info in list(sites.items())[:10]:
        visits = info.get("visits", 0)
        selectors_count = len(info.get("selectors", {}))
        message += f"  - {domain} (посещён {visits} раз, запомнено {selectors_count} селекторов)\n"
    
    if len(sites) > 10:
        message += f"  ... и ещё {len(sites) - 10} сайтов\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние ошибки (только для админов)"""
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде")
        return

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)

    errors = error_tracker.get_recent(limit)

    if not errors:
        await update.message.reply_text("✅ Ошибок нет")
        return

    message = f"📊 **Последние {len(errors)} ошибок:**\n\n"
    for i, error in enumerate(errors, 1):
        message += f"**{i}. {error['error_type']}**\n"
        message += f"⏰ {error['timestamp']}\n"
        message += f"💬 {error['error_message'][:100]}\n"
        if error.get('context', {}).get('function'):
            message += f"📁 Функция: {error['context']['function']}\n"
        message += "---\n"

    if len(message) > 4000:
        message = message[:4000] + "\n... (обрезано)"

    await update.message.reply_text(message, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная отладка (только для админов)"""
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде")
        return

    session = await session_manager.get_session(user_id)
    memory_stats = await execute_tool("get_memory_stats", {}, user_id)

    message = (
        f"🔍 **Отладка**\n\n"
        f"**Сессии:** {len(session_manager.sessions)}\n"
        f"**Браузер:** {'✅' if session_manager._browser else '❌'}\n"
        f"**Контекст:** {session.context_id or 'нет'}\n"
        f"**Вкладка:** {'✅' if session.tab else '❌'}\n"
        f"**Ошибок:** {len(error_tracker.errors)}\n"
        f"**Логи:** `{LOG_DIR.absolute()}`\n"
        f"**Память:** `{MEMORY_DIR.absolute()}`\n"
        f"**Шаблоны:** `{TEMPLATES_DIR.absolute()}`\n\n"
        f"🧠 **Память:**\n"
        f"  - Сайтов: {memory_stats.get('stats', {}).get('sites_learned', 0)}\n"
        f"  - Шаблонов: {memory_stats.get('stats', {}).get('templates_saved', 0)}"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def clear_errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает лог ошибок (только для админов)"""
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде")
        return

    error_tracker.clear()
    await update.message.reply_text("🧹 Ошибки очищены")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    user_message = update.message.text

    if user_message.startswith('/'):
        return

    audit_logger.info(f"User {user_id}: {user_message}")
    await update.message.reply_text("🤔 Думаю...")

    try:
        result = await process_with_agnes(user_message, user_id)

        if result["type"] == "screenshot":
            try:
                screenshot_bytes = base64.b64decode(result["data"])
                await update.message.reply_photo(
                    screenshot_bytes,
                    caption=result.get("message", "📸 Скриншот")
                )
            except Exception as e:
                error_tracker.add_error(e, {"user_id": user_id, "action": "send_screenshot"})
                await update.message.reply_text(f"❌ Ошибка отправки скриншота: {str(e)}")
        else:
            await update.message.reply_text(result["content"])

    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id, "message": user_message})
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    error = context.error
    error_tracker.add_error(error, {
        "update": update.to_dict() if update else None,
        "user_id": update.effective_user.id if update else None
    })
    error_logger.error(f"Ошибка: {error}\n{traceback.format_exc()}")

# ============================================================
# 11. ФОНОВЫЕ ЗАДАЧИ
# ============================================================

async def cleanup_task():
    """Фоновая очистка неактивных сессий"""
    while True:
        await asyncio.sleep(300)  # Каждые 5 минут
        try:
            await session_manager.cleanup_inactive(max_age_seconds=1800)
        except Exception as e:
            logger.error(f"Ошибка в cleanup_task: {e}")

async def health_check_task():
    """Проверка здоровья браузера"""
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
    """Главная асинхронная функция"""
    try:
        init_agnes()

        application = Application.builder().token(TOKEN).build()

        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open", open_command))
        application.add_handler(CommandHandler("close", close_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("memory", memory_command))
        application.add_handler(CommandHandler("errors", errors_command))
        application.add_handler(CommandHandler("clear_errors", clear_errors_command))
        application.add_handler(CommandHandler("debug", debug_command))

        # Обработчики
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        # Фоновые задачи
        asyncio.create_task(cleanup_task())
        asyncio.create_task(health_check_task())

        logger.info("=" * 60)
        logger.info("🚀 Бот с Agnes AI агентом запущен!")
        logger.info(f"📁 Логи: {LOG_DIR.absolute()}")
        logger.info(f"🧠 Память: {MEMORY_DIR.absolute()}")
        logger.info(f"📋 Шаблоны: {TEMPLATES_DIR.absolute()}")
        logger.info(f"👥 Админы: {ADMIN_IDS or 'нет'}")
        logger.info(f"💾 Persistent: {PERSISTENT_SESSION}")
        logger.info(f"🌐 Прокси: {PROXY_SERVER or 'нет'}")
        logger.info(f"📦 Инструментов: {len(TOOLS)}")
        logger.info("=" * 60)

        # Запуск бота
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
    finally:
        try:
            if 'application' in locals():
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            await session_manager.close_all()
        except Exception as e:
            logger.error(f"Ошибка при завершении: {e}")
        logger.info("✅ Бот корректно завершил работу")

if __name__ == "__main__":
    asyncio.run(main())