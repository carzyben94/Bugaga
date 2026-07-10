#!/usr/bin/env python3
"""
Telegram Bot с Agnes AI агентом для управления браузером через Pydoll
Версия: Full 2.0
"""

import asyncio
import logging
import os
import base64
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    MessageHandler, 
    filters
)
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key, ScrollPosition
from pydoll.network import NetworkEvent
from pydoll.exceptions import ElementNotFound, NetworkError
from pydoll.decorators import retry
from openai import OpenAI

# ============================================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

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
# 4. УПРАВЛЕНИЕ КОНТЕКСТАМИ БРАУЗЕРА (Browser Contexts)
# ============================================================

@dataclass
class BrowserSession:
    browser: Optional[Chrome] = None
    context_id: Optional[str] = None
    tab: Optional[Any] = None
    is_active: bool = False
    is_persistent: bool = False
    current_url: str = ""
    page_title: str = ""
    last_action: str = ""
    last_action_time: datetime = field(default_factory=datetime.now)
    context_variables: Dict[str, Any] = field(default_factory=dict)
    cookies: List[Dict] = field(default_factory=list)

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
            options.start_timeout = 30
            
            # Persistent session
            if PERSISTENT_SESSION:
                options.add_argument("--user-data-dir=/data/browser-profile")
                logger.info("💾 Используется Persistent Session")
            
            # Proxy
            if PROXY_SERVER:
                proxy_parts = PROXY_SERVER.split('://')
                proxy_type = proxy_parts[0] if len(proxy_parts) > 1 else 'http'
                proxy_host = proxy_parts[1] if len(proxy_parts) > 1 else PROXY_SERVER
                
                if PROXY_USER and PROXY_PASS:
                    options.add_argument(
                        f"--proxy-server={proxy_type}://{PROXY_USER}:{PROXY_PASS}@{proxy_host}"
                    )
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
            
            # Если нет контекста — создаём изолированный контекст
            if not session.context_id:
                browser = await self._get_or_create_browser()
                session.context_id = await browser.create_browser_context()
                session.tab = await browser.new_tab(
                    browser_context_id=session.context_id
                )
                session.is_active = True
                session.last_action_time = datetime.now()
                logger.info(f"🔒 Создан контекст {session.context_id} для пользователя {user_id}")
            
            # Проверяем, жив ли таб
            if session.tab:
                try:
                    session.current_url = await session.tab.current_url
                    session.page_title = await session.tab.title
                except:
                    logger.warning(f"⚠️ Вкладка пользователя {user_id} умерла, пересоздаём")
                    browser = await self._get_or_create_browser()
                    session.tab = await browser.new_tab(
                        browser_context_id=session.context_id
                    )
            
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
                if session.context_id and session.browser:
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
            logger.info(f"🧹 Сессия {user_id} очищена (неактивна {max_age_seconds}с)")
    
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
# 5. AGNES AI КЛИЕНТ
# ============================================================

agnes_client: Optional[OpenAI] = None

def init_agnes():
    global agnes_client
    agnes_client = OpenAI(
        api_key=AGNES_API_KEY,
        base_url="https://apihub.agnes-ai.com/v1",
    )
    logger.info("✅ Agnes AI клиент инициализирован")
    return agnes_client

# ============================================================
# 6. ОПРЕДЕЛЕНИЕ ВСЕХ ИНСТРУМЕНТОВ ДЛЯ AGNES AI
# ============================================================

TOOLS = [
    # --- НАВИГАЦИЯ ---
    {
        "type": "function",
        "function": {
            "name": "go_to_url",
            "description": "Переходит на указанный URL",
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
            "name": "go_forward",
            "description": "Переходит вперёд по истории",
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
    {
        "type": "function",
        "function": {
            "name": "close_tab",
            "description": "Закрывает текущую вкладку",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- ПОИСК ЭЛЕМЕНТОВ ---
    {
        "type": "function",
        "function": {
            "name": "find_element",
            "description": "Находит элемент по атрибутам (id, class_name, tag_name, name, text)",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "class_name": {"type": "string"},
                    "tag_name": {"type": "string"},
                    "name": {"type": "string"},
                    "text": {"type": "string"}
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
            "name": "find_element_by_xpath",
            "description": "Находит элемент по XPath",
            "parameters": {
                "type": "object",
                "properties": {"xpath": {"type": "string"}},
                "required": ["xpath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_elements",
            "description": "Находит все элементы по атрибутам",
            "parameters": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "tag_name": {"type": "string"}
                }
            }
        }
    },
    
    # --- ВЗАИМОДЕЙСТВИЕ С ЭЛЕМЕНТАМИ ---
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
            "name": "get_element_text",
            "description": "Получает текст элемента",
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
            "name": "get_element_attribute",
            "description": "Получает атрибут элемента",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "attribute": {"type": "string"}
                },
                "required": ["selector", "attribute"]
            }
        }
    },
    
    # --- DOM НАВИГАЦИЯ ---
    {
        "type": "function",
        "function": {
            "name": "get_children_elements",
            "description": "Получает дочерние элементы",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 1}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sibling_elements",
            "description": "Получает соседние элементы",
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
            "name": "get_parent_element",
            "description": "Получает родительский элемент",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    
    # --- КЛАВИАТУРА И МЫШЬ ---
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Нажимает клавишу на клавиатуре",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": ["Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Control", "Shift", "Alt"]}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey",
            "description": "Нажимает комбинацию клавиш",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_move",
            "description": "Перемещает курсор мыши",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Кликает мышью в позиции",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "humanize": {"type": "boolean", "default": True}
                },
                "required": ["x", "y"]
            }
        }
    },
    
    # --- ПРОКРУТКА ---
    {
        "type": "function",
        "function": {
            "name": "scroll_by",
            "description": "Прокручивает страницу",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "amount": {"type": "integer"},
                    "smooth": {"type": "boolean", "default": True}
                },
                "required": ["direction", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_to_bottom",
            "description": "Прокручивает страницу вниз",
            "parameters": {
                "type": "object",
                "properties": {"smooth": {"type": "boolean", "default": True}}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_to_top",
            "description": "Прокручивает страницу вверх",
            "parameters": {
                "type": "object",
                "properties": {"smooth": {"type": "boolean", "default": True}}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_to_element",
            "description": "Прокручивает к элементу",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "smooth": {"type": "boolean", "default": True}
                },
                "required": ["selector"]
            }
        }
    },
    
    # --- СКРИНШОТЫ ---
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Делает скриншот всей страницы",
            "parameters": {
                "type": "object",
                "properties": {"full_page": {"type": "boolean", "default": True}}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_element_screenshot",
            "description": "Делает скриншот конкретного элемента",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    
    # --- ПОЛУЧЕНИЕ ДАННЫХ ---
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
    {
        "type": "function",
        "function": {
            "name": "get_cookies",
            "description": "Получает все cookies текущей сессии",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- JAVASCRIPT ---
    {
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": "Выполняет JavaScript код",
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
            "name": "execute_javascript_on_element",
            "description": "Выполняет JS на конкретном элементе",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "script": {"type": "string"}
                },
                "required": ["selector", "script"]
            }
        }
    },
    
    # --- SHADOW DOM ---
    {
        "type": "function",
        "function": {
            "name": "get_shadow_root",
            "description": "Получает shadow root элемента",
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
            "name": "find_shadow_roots",
            "description": "Находит все shadow roots на странице",
            "parameters": {
                "type": "object",
                "properties": {"deep": {"type": "boolean", "default": True}}
            }
        }
    },
    
    # --- IFRAME ---
    {
        "type": "function",
        "function": {
            "name": "switch_to_iframe",
            "description": "Переключается в iframe",
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
            "name": "get_iframe_content",
            "description": "Получает содержимое iframe",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    
    # --- HTTP ЗАПРОСЫ ---
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": "Выполняет HTTP GET запрос с сессией браузера",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "headers": {"type": "array", "items": {"type": "object"}}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "http_post",
            "description": "Выполняет HTTP POST запрос с сессией браузера",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "json": {"type": "object"},
                    "headers": {"type": "array", "items": {"type": "object"}}
                },
                "required": ["url"]
            }
        }
    },
    
    # --- КУКИ ---
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
                    "domain": {"type": "string"},
                    "path": {"type": "string", "default": "/"},
                    "secure": {"type": "boolean", "default": False}
                },
                "required": ["name", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_cookie",
            "description": "Удаляет cookie",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cookies",
            "description": "Удаляет все cookies",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    
    # --- ХРАНИЛИЩЕ ---
    {
        "type": "function",
        "function": {
            "name": "get_local_storage",
            "description": "Получает значение из localStorage",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_local_storage",
            "description": "Устанавливает значение в localStorage",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_storage",
            "description": "Получает значение из sessionStorage",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_session_storage",
            "description": "Устанавливает значение в sessionStorage",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },
    
    # --- БЛОКИРОВКА КАПЧИ ---
    {
        "type": "function",
        "function": {
            "name": "bypass_cloudflare",
            "description": "Автоматически обходит Cloudflare капчу",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    
    # --- PAGE BUNDLE ---
    {
        "type": "function",
        "function": {
            "name": "save_page_bundle",
            "description": "Сохраняет страницу со всеми ресурсами в ZIP",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "inline_assets": {"type": "boolean", "default": False}
                },
                "required": ["filename"]
            }
        }
    },
    
    # --- СТРУКТУРИРОВАННОЕ ИЗВЛЕЧЕНИЕ ---
    {
        "type": "function",
        "function": {
            "name": "extract_structured_data",
            "description": "Извлекает структурированные данные с помощью Pydantic модели",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_definition": {"type": "object"},
                    "scope": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30}
                },
                "required": ["model_definition"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_all_structured_data",
            "description": "Извлекает все элементы как список структурированных данных",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_definition": {"type": "object"},
                    "scope": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                    "limit": {"type": "integer"}
                },
                "required": ["model_definition"]
            }
        }
    },
]

# ============================================================
# 7. ИСПОЛНЕНИЕ ИНСТРУМЕНТОВ
# ============================================================

@log_error
async def execute_tool(tool_name: str, arguments: Dict, user_id: int) -> Dict:
    """Выполняет инструмент с сохранением контекста пользователя"""
    session = await session_manager.get_session(user_id)
    tab = session.tab
    
    if not tab:
        return {"success": False, "error": "⚠️ Браузер не открыт. Используйте /open"}
    
    try:
        # --- НАВИГАЦИЯ ---
        if tool_name == "go_to_url":
            url = arguments["url"]
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await tab.go_to(url)
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.last_action = "go_to_url"
            session.last_action_time = datetime.now()
            return {"success": True, "url": session.current_url, "title": session.page_title}
        
        elif tool_name == "go_back":
            await tab.go_back()
            return {"success": True, "message": "↩️ Возврат на предыдущую страницу"}
        
        elif tool_name == "go_forward":
            await tab.go_forward()
            return {"success": True, "message": "↪️ Переход вперёд"}
        
        elif tool_name == "refresh_page":
            await tab.refresh()
            return {"success": True, "message": "🔄 Страница обновлена"}
        
        elif tool_name == "close_tab":
            await tab.close()
            session.is_active = False
            return {"success": True, "message": "❌ Вкладка закрыта"}
        
        # --- ПОИСК ---
        elif tool_name == "find_element":
            params = {k: v for k, v in arguments.items() if k in ['id', 'class_name', 'tag_name', 'name', 'text']}
            element = await tab.find(**params)
            text = await element.text
            return {"success": True, "found": True, "text": text[:200] if text else ""}
        
        elif tool_name == "find_element_by_css":
            element = await tab.query(arguments["selector"])
            text = await element.text
            return {"success": True, "found": True, "text": text[:200] if text else ""}
        
        elif tool_name == "find_element_by_xpath":
            element = await tab.query(arguments["xpath"])
            text = await element.text
            return {"success": True, "found": True, "text": text[:200] if text else ""}
        
        elif tool_name == "find_elements":
            params = {k: v for k, v in arguments.items() if k in ['class_name', 'tag_name']}
            elements = await tab.find(find_all=True, **params)
            count = len(elements)
            return {"success": True, "count": count}
        
        # --- ВЗАИМОДЕЙСТВИЕ ---
        elif tool_name == "click_element":
            element = await tab.query(arguments["selector"])
            await element.click()
            return {"success": True, "message": f"🖱️ Кликнут элемент: {arguments['selector']}"}
        
        elif tool_name == "type_text":
            element = await tab.query(arguments["selector"])
            await element.clear()
            await element.type_text(arguments["text"])
            return {"success": True, "message": f"⌨️ Введён текст в {arguments['selector']}"}
        
        elif tool_name == "clear_field":
            element = await tab.query(arguments["selector"])
            await element.clear()
            return {"success": True, "message": "🧹 Поле очищено"}
        
        elif tool_name == "get_element_text":
            element = await tab.query(arguments["selector"])
            text = await element.text
            return {"success": True, "text": text[:500] if text else ""}
        
        elif tool_name == "get_element_attribute":
            element = await tab.query(arguments["selector"])
            attr = await element.get_attribute(arguments["attribute"])
            return {"success": True, "attribute": arguments["attribute"], "value": attr}
        
        # --- DOM НАВИГАЦИЯ ---
        elif tool_name == "get_children_elements":
            element = await tab.query(arguments["selector"])
            children = await element.get_children_elements(
                max_depth=arguments.get("max_depth", 1)
            )
            return {"success": True, "children_count": len(children)}
        
        elif tool_name == "get_sibling_elements":
            element = await tab.query(arguments["selector"])
            siblings = await element.get_siblings_elements()
            return {"success": True, "siblings_count": len(siblings)}
        
        elif tool_name == "get_parent_element":
            element = await tab.query(arguments["selector"])
            parent = await element.get_parent_element()
            parent_text = await parent.text
            return {"success": True, "parent_text": parent_text[:200] if parent_text else ""}
        
        # --- КЛАВИАТУРА ---
        elif tool_name == "press_key":
            key_map = {
                "Enter": Key.ENTER, "Tab": Key.TAB, "Escape": Key.ESCAPE,
                "ArrowUp": Key.ARROWUP, "ArrowDown": Key.ARROWDOWN,
                "ArrowLeft": Key.ARROWLEFT, "ArrowRight": Key.ARROWRIGHT,
                "Control": Key.CONTROL, "Shift": Key.SHIFT, "Alt": Key.ALT
            }
            key = key_map.get(arguments["key"], arguments["key"])
            await tab.keyboard.press(key)
            return {"success": True, "message": f"⌨️ Нажата клавиша: {arguments['key']}"}
        
        elif tool_name == "hotkey":
            keys = arguments["keys"]
            await tab.keyboard.hotkey(*keys)
            return {"success": True, "message": f"⌨️ Комбинация: {'+'.join(keys)}"}
        
        elif tool_name == "mouse_move":
            await tab.mouse.move(arguments["x"], arguments["y"])
            return {"success": True, "message": f"🖱️ Мышь перемещена на ({arguments['x']}, {arguments['y']})"}
        
        elif tool_name == "mouse_click":
            await tab.mouse.click(
                arguments["x"], 
                arguments["y"],
                humanize=arguments.get("humanize", True)
            )
            return {"success": True, "message": f"🖱️ Клик в ({arguments['x']}, {arguments['y']})"}
        
        # --- ПРОКРУТКА ---
        elif tool_name == "scroll_by":
            direction_map = {"up": ScrollPosition.UP, "down": ScrollPosition.DOWN}
            await tab.scroll.by(
                direction_map[arguments["direction"]],
                arguments["amount"],
                smooth=arguments.get("smooth", True)
            )
            return {"success": True, "message": f"📜 Прокрутка {arguments['direction']} на {arguments['amount']}px"}
        
        elif tool_name == "scroll_to_bottom":
            await tab.scroll.to_bottom(smooth=arguments.get("smooth", True))
            return {"success": True, "message": "📜 Прокрутка вниз"}
        
        elif tool_name == "scroll_to_top":
            await tab.scroll.to_top(smooth=arguments.get("smooth", True))
            return {"success": True, "message": "📜 Прокрутка вверх"}
        
        elif tool_name == "scroll_to_element":
            element = await tab.query(arguments["selector"])
            await tab.scroll.to_element(element, smooth=arguments.get("smooth", True))
            return {"success": True, "message": f"📜 Прокрутка к элементу {arguments['selector']}"}
        
        # --- СКРИНШОТЫ ---
        elif tool_name == "take_screenshot":
            screenshot = await tab.take_screenshot(
                beyond_viewport=arguments.get("full_page", True),
                as_base64=True
            )
            return {"success": True, "screenshot": screenshot}
        
        elif tool_name == "take_element_screenshot":
            element = await tab.query(arguments["selector"])
            screenshot = await element.take_screenshot(as_base64=True)
            return {"success": True, "screenshot": screenshot}
        
        # --- ПОЛУЧЕНИЕ ДАННЫХ ---
        elif tool_name == "get_page_title":
            title = await tab.title
            return {"success": True, "title": title}
        
        elif tool_name == "get_current_url":
            url = await tab.current_url
            return {"success": True, "url": url}
        
        elif tool_name == "get_page_source":
            source = await tab.page_source
            return {"success": True, "source": source[:2000] + "..." if len(source) > 2000 else source}
        
        elif tool_name == "get_cookies":
            cookies = await session.browser.get_cookies(
                browser_context_id=session.context_id
            )
            return {"success": True, "cookies": cookies}
        
        # --- JAVASCRIPT ---
        elif tool_name == "execute_javascript":
            result = await tab.execute_script(arguments["script"])
            return {"success": True, "result": str(result)[:500]}
        
        elif tool_name == "execute_javascript_on_element":
            element = await tab.query(arguments["selector"])
            result = await tab.execute_script(arguments["script"], element=element)
            return {"success": True, "result": str(result)[:500]}
        
        # --- SHADOW DOM ---
        elif tool_name == "get_shadow_root":
            element = await tab.query(arguments["selector"])
            shadow = await element.get_shadow_root()
            shadow_content = await shadow.query("*")
            return {"success": True, "shadow_root_exists": True}
        
        elif tool_name == "find_shadow_roots":
            roots = await tab.find_shadow_roots(deep=arguments.get("deep", True))
            return {"success": True, "shadow_roots_count": len(roots)}
        
        # --- IFRAME ---
        elif tool_name == "switch_to_iframe":
            iframe = await tab.query(arguments["selector"])
            # В Pydoll iframe работает как обычный WebElement
            button = await iframe.find(tag_name="button")
            return {"success": True, "message": f"Переключение в iframe {arguments['selector']}"}
        
        elif tool_name == "get_iframe_content":
            iframe = await tab.query(arguments["selector"])
            content = await iframe.execute_script("document.body.innerText")
            return {"success": True, "content": content[:500] if content else ""}
        
        # --- HTTP ЗАПРОСЫ ---
        elif tool_name == "http_get":
            headers = arguments.get("headers", [])
            response = await tab.request.get(
                arguments["url"],
                headers=headers
            )
            return {"success": True, "status": response.status_code, "data": response.json() if response.content else {}}
        
        elif tool_name == "http_post":
            headers = arguments.get("headers", [])
            response = await tab.request.post(
                arguments["url"],
                json=arguments.get("json", {}),
                headers=headers
            )
            return {"success": True, "status": response.status_code, "data": response.json() if response.content else {}}
        
        # --- КУКИ ---
        elif tool_name == "set_cookie":
            await tab.set_cookie(
                name=arguments["name"],
                value=arguments["value"],
                domain=arguments.get("domain"),
                path=arguments.get("path", "/"),
                secure=arguments.get("secure", False)
            )
            return {"success": True, "message": f"🍪 Cookie установлен: {arguments['name']}"}
        
        elif tool_name == "delete_cookie":
            cookies = await session.browser.get_cookies(
                browser_context_id=session.context_id
            )
            for cookie in cookies:
                if cookie.get('name') == arguments["name"]:
                    await tab.delete_cookie(arguments["name"])
            return {"success": True, "message": f"🍪 Cookie удалён: {arguments['name']}"}
        
        elif tool_name == "clear_cookies":
            await tab.clear_browser_cookies()
            return {"success": True, "message": "🍪 Все cookies удалены"}
        
        # --- ХРАНИЛИЩЕ ---
        elif tool_name == "get_local_storage":
            value = await tab.execute_script(f"return localStorage.getItem('{arguments['key']}')")
            return {"success": True, "key": arguments["key"], "value": value}
        
        elif tool_name == "set_local_storage":
            await tab.execute_script(
                f"localStorage.setItem('{arguments['key']}', '{arguments['value']}')"
            )
            return {"success": True, "message": f"💾 localStorage установлен: {arguments['key']}"}
        
        elif tool_name == "get_session_storage":
            value = await tab.execute_script(f"return sessionStorage.getItem('{arguments['key']}')")
            return {"success": True, "key": arguments["key"], "value": value}
        
        elif tool_name == "set_session_storage":
            await tab.execute_script(
                f"sessionStorage.setItem('{arguments['key']}', '{arguments['value']}')"
            )
            return {"success": True, "message": f"💾 sessionStorage установлен: {arguments['key']}"}
        
        # --- КАПЧА ---
        elif tool_name == "bypass_cloudflare":
            async with tab.expect_and_bypass_cloudflare_captcha():
                await tab.go_to(arguments["url"])
            return {"success": True, "message": "✅ Cloudflare капча обойдена"}
        
        # --- PAGE BUNDLE ---
        elif tool_name == "save_page_bundle":
            filename = arguments["filename"]
            if not filename.endswith('.zip'):
                filename += '.zip'
            await tab.save_bundle(
                filename,
                inline_assets=arguments.get("inline_assets", False)
            )
            return {"success": True, "message": f"📦 Страница сохранена в {filename}"}
        
        # --- СТРУКТУРИРОВАННОЕ ИЗВЛЕЧЕНИЕ ---
        elif tool_name == "extract_structured_data":
            # Простая реализация - извлекаем через JavaScript
            model_def = arguments["model_definition"]
            scope = arguments.get("scope", "body")
            timeout = arguments.get("timeout", 30)
            
            result = await tab.execute_script(f"""
                (function() {{
                    const elements = document.querySelectorAll('{scope}');
                    return Array.from(elements).map(el => {{
                        let data = {{}};
                        const fields = {json.dumps(model_def)};
                        for (let [key, value] of Object.entries(fields)) {{
                            const selector = value.selector || '';
                            const element = el.querySelector(selector);
                            data[key] = element ? element.innerText.trim() : '';
                        }}
                        return data;
                    }});
                }})()
            """)
            return {"success": True, "data": result}
        
        elif tool_name == "extract_all_structured_data":
            # Аналогично, но с ограничением
            model_def = arguments["model_definition"]
            scope = arguments.get("scope", "body")
            limit = arguments.get("limit", 50)
            
            result = await tab.execute_script(f"""
                (function() {{
                    const elements = document.querySelectorAll('{scope}');
                    const limited = Array.from(elements).slice(0, {limit});
                    return limited.map(el => {{
                        let data = {{}};
                        const fields = {json.dumps(model_def)};
                        for (let [key, value] of Object.entries(fields)) {{
                            const selector = value.selector || '';
                            const element = el.querySelector(selector);
                            data[key] = element ? element.innerText.trim() : '';
                        }}
                        return data;
                    }});
                }})()
            """)
            return {"success": True, "data": result, "count": len(result)}
        
        else:
            return {"success": False, "error": f"❌ Неизвестный инструмент: {tool_name}"}
            
    except Exception as e:
        error_tracker.add_error(e, {"tool": tool_name, "user_id": user_id})
        return {"success": False, "error": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 8. ОБРАБОТКА ЗАПРОСОВ ЧЕРЕЗ AGNES AI
# ============================================================

@log_error
async def process_with_agnes(user_message: str, user_id: int) -> Dict:
    """Обрабатывает запрос через Agnes AI с контекстом"""
    global agnes_client
    
    if agnes_client is None:
        init_agnes()
    
    try:
        session = await session_manager.get_session(user_id)
        
        # Получаем состояние браузера
        state = {
            "browser_open": session.is_active,
            "current_url": session.current_url or "нет",
            "page_title": session.page_title or "нет",
            "last_action": session.last_action or "нет"
        }
        
        # Формируем системный промпт
        system_prompt = f"""
Ты — AI агент, который управляет браузером через Pydoll.

Текущее состояние браузера:
- Браузер: {'открыт' if state['browser_open'] else 'закрыт'}
- Текущий URL: {state['current_url']}
- Заголовок: {state['page_title']}
- Последнее действие: {state['last_action']}

Правила:
1. Если пользователь просит перейти на сайт или сделать скриншот, а браузер закрыт — сначала открой его
2. Если пользователь просит что-то найти на странице — сначала перейди на нужный URL
3. Используй инструменты для выполнения действий
4. Отвечай понятно и по делу
5. Для скриншотов используй take_screenshot
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
        
        # Обработка вызовов инструментов
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                logger.info(f"🔧 Вызов: {tool_name} с аргументами: {arguments}")
                
                result = await execute_tool(tool_name, arguments, user_id)
                results.append({
                    "tool": tool_name,
                    "result": result
                })
                
                # Если скриншот — возвращаем сразу
                if tool_name in ["take_screenshot", "take_element_screenshot"] and result.get("success"):
                    return {
                        "type": "screenshot",
                        "data": result["screenshot"],
                        "message": "📸 Скриншот готов"
                    }
            
            # Формируем текстовый ответ
            if message.content:
                content = message.content
            else:
                content = "\n".join([
                    r["result"].get("message", r["result"].get("error", "✅ Готово"))
                    for r in results
                    if r["result"].get("success", False)
                ])
                
            errors = [
                r["result"].get("error", "")
                for r in results
                if not r["result"].get("success", False)
            ]
            
            if errors:
                content += "\n\n⚠️ Ошибки:\n" + "\n".join(errors)
            
            return {"type": "text", "content": content}
        else:
            return {"type": "text", "content": message.content or "✅ Готово!"}
            
    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id, "action": "process_with_agnes"})
        return {"type": "text", "content": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 9. КОМАНДЫ ТЕЛЕГРАМ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    user_id = update.effective_user.id
    audit_logger.info(f"User {user_id} запустил бота")
    
    await update.message.reply_text(
        "🤖 **Бот с AI агентом на Agnes AI**\n\n"
        "Я умею управлять браузером через естественный язык!\n\n"
        "📌 **Примеры команд:**\n"
        "• `Открой браузер`\n"
        "• `Перейди на google.com`\n"
        "• `Найди кнопку Войти и кликни`\n"
        "• `Сделай скриншот`\n"
        "• `Собери все цены с этой страницы`\n\n"
        "🔧 **Команды:**\n"
        "/open — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/status — Статус сессии\n"
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
        
        # Проверяем, что браузер работает
        await session.tab.current_url
        await update.message.reply_text("✅ Браузер успешно открыт!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    user_id = update.effective_user.id
    await update.message.reply_text("❌ Закрываю браузер...")
    
    try:
        await session_manager.close_session(user_id)
        await update.message.reply_text("✅ Браузер закрыт!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус сессии"""
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)
    
    status = "🟢 Активен" if session.is_active else "🔴 Не активен"
    
    message = (
        f"📊 **Статус сессии**\n\n"
        f"🆔 Пользователь: `{user_id}`\n"
        f"🌐 Браузер: {status}\n"
        f"🔒 Контекст: `{session.context_id or 'нет'}`\n"
        f"🔗 URL: `{session.current_url or 'нет'}`\n"
        f"📄 Заголовок: `{session.page_title or 'нет'}`\n"
        f"⚡ Последнее действие: {session.last_action or 'нет'}\n"
        f"⏰ Обновлено: {session.last_action_time.strftime('%H:%M:%S')}\n"
        f"🧠 Переменных: {len(session.context_variables)}"
    )
    
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
    
    message = (
        f"🔍 **Отладка**\n\n"
        f"**Сессии:** {len(session_manager.sessions)}\n"
        f"**Браузер:** {'✅' if session._browser else '❌'}\n"
        f"**Контекст:** {session.context_id or 'нет'}\n"
        f"**Вкладка:** {'✅' if session.tab else '❌'}\n"
        f"**Ошибок:** {len(error_tracker.errors)}\n"
        f"**Логи:** `{LOG_DIR.absolute()}`"
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
# 10. ФОНОВЫЕ ЗАДАЧИ
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
                # Проверяем, жив ли браузер
                await session_manager._browser.active_page
        except:
            logger.warning("⚠️ Браузер умер, пересоздаём")
            session_manager._browser = None

# ============================================================
# 11. ЗАПУСК
# ============================================================

def main():
    """Главная функция"""
    try:
        init_agnes()
        
        # Создаём приложение
        application = Application.builder().token(TOKEN).build()
        
        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open", open_command))
        application.add_handler(CommandHandler("close", close_command))
        application.add_handler(CommandHandler("status", status_command))
        
        # Админские команды
        application.add_handler(CommandHandler("errors", errors_command))
        application.add_handler(CommandHandler("clear_errors", clear_errors_command))
        application.add_handler(CommandHandler("debug", debug_command))
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO, handle_message))
        
        # Глобальный обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем фоновые задачи
        loop = asyncio.get_event_loop()
        loop.create_task(cleanup_task())
        loop.create_task(health_check_task())
        
        logger.info("=" * 60)
        logger.info("🚀 Бот с Agnes AI агентом запущен!")
        logger.info(f"📁 Логи: {LOG_DIR.absolute()}")
        logger.info(f"👥 Админы: {ADMIN_IDS or 'нет'}")
        logger.info(f"💾 Persistent: {PERSISTENT_SESSION}")
        logger.info(f"🌐 Прокси: {PROXY_SERVER or 'нет'}")
        logger.info(f"📦 Инструментов: {len(TOOLS)}")
        logger.info("=" * 60)
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()