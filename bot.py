#!/usr/bin/env python3
"""
Telegram Bot с Agnes AI агентом для управления браузером через Pydoll
Версия: 3.1 - Исправлены все импорты
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

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ============================================================
# ПРАВИЛЬНЫЕ ИМПОРТЫ PYDOLL
# ============================================================
from pydoll.browser import Chrome  # ✅ ПРАВИЛЬНО
from pydoll.browser.options import ChromiumOptions  # ✅ ПРАВИЛЬНО
from pydoll.constants import Key  # ✅ ПРАВИЛЬНО

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
    # Заглушки
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
# 4. УПРАВЛЕНИЕ КОНТЕКСТАМИ БРАУЗЕРА
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

                session.tab = await browser.start()
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
                    session.tab = await browser.start()

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
# 5. AGNES AI КЛИЕНТ
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
# 6. ИНСТРУМЕНТЫ ДЛЯ AGNES AI
# ============================================================

TOOLS = [
    # Навигация
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
            "description": "Находит элемент по селектору",
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
    # Скриншоты
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
    # Скролл
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
            "name": "get_page_source",
            "description": "Получает HTML код страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    # JavaScript
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
    # Клавиатура
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
    # HTTP
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
    # Cookies
    {
        "type": "function",
        "function": {
            "name": "get_cookies",
            "description": "Получает cookies",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]

# ============================================================
# 7. ИСПОЛНЕНИЕ ИНСТРУМЕНТОВ
# ============================================================

@log_error
async def execute_tool(tool_name: str, arguments: Dict, user_id: int) -> Dict:
    """Выполняет инструмент"""
    session = await session_manager.get_session(user_id)
    tab = session.tab

    if not tab:
        return {"success": False, "error": "⚠️ Браузер не открыт"}

    try:
        # Навигация
        if tool_name == "go_to_url":
            url = arguments.get("url", "")
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
            return {"success": True, "message": "↩️ Назад"}

        elif tool_name == "refresh_page":
            await tab.refresh()
            return {"success": True, "message": "🔄 Обновлено"}

        # Поиск
        elif tool_name == "find_element":
            element = await tab.query(arguments["selector"])
            text = await element.text
            return {"success": True, "found": True, "text": text[:200] if text else ""}

        elif tool_name == "click_element":
            element = await tab.query(arguments["selector"])
            await element.click()
            return {"success": True, "message": f"🖱️ Кликнут: {arguments['selector']}"}

        elif tool_name == "type_text":
            element = await tab.query(arguments["selector"])
            await element.clear()
            await element.type_text(arguments["text"])
            return {"success": True, "message": f"⌨️ Введён текст"}

        elif tool_name == "clear_field":
            element = await tab.query(arguments["selector"])
            await element.clear()
            return {"success": True, "message": "🧹 Поле очищено"}

        elif tool_name == "get_element_text":
            element = await tab.query(arguments["selector"])
            text = await element.text
            return {"success": True, "text": text[:500] if text else ""}

        # Скриншоты
        elif tool_name == "take_screenshot":
            try:
                screenshot = await tab.take_screenshot(
                    beyond_viewport=arguments.get("full_page", True),
                    as_base64=True
                )
                return {"success": True, "screenshot": screenshot}
            except:
                screenshot = await tab.take_screenshot(as_base64=True)
                return {"success": True, "screenshot": screenshot}

        # Скролл
        elif tool_name == "scroll_to_bottom":
            await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            return {"success": True, "message": "📜 Вниз"}

        elif tool_name == "scroll_to_top":
            await tab.execute_script("window.scrollTo(0, 0)")
            return {"success": True, "message": "📜 Вверх"}

        # Данные
        elif tool_name == "get_page_title":
            title = await tab.title
            return {"success": True, "title": title}

        elif tool_name == "get_current_url":
            url = await tab.current_url
            return {"success": True, "url": url}

        elif tool_name == "get_page_source":
            source = await tab.page_source
            return {"success": True, "source": source[:2000] + "..." if len(source) > 2000 else source}

        # JavaScript
        elif tool_name == "execute_javascript":
            result = await tab.execute_script(arguments["script"])
            return {"success": True, "result": str(result)[:500]}

        # Клавиатура
        elif tool_name == "press_key":
            key_map = {
                "Enter": Key.ENTER, "Tab": Key.TAB, "Escape": Key.ESCAPE,
                "ArrowUp": Key.ARROWUP, "ArrowDown": Key.ARROWDOWN,
                "ArrowLeft": Key.ARROWLEFT, "ArrowRight": Key.ARROWRIGHT,
            }
            key = key_map.get(arguments["key"], arguments["key"])
            await tab.keyboard.press(key)
            return {"success": True, "message": f"⌨️ Нажата: {arguments['key']}"}

        # HTTP
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

        # Cookies
        elif tool_name == "get_cookies":
            try:
                cookies = await tab.execute_script("return document.cookie")
                return {"success": True, "cookies": cookies}
            except:
                return {"success": True, "cookies": "Не удалось получить"}

        else:
            return {"success": False, "error": f"❌ Неизвестный инструмент: {tool_name}"}

    except Exception as e:
        error_tracker.add_error(e, {"tool": tool_name, "user_id": user_id})
        return {"success": False, "error": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 8. ОБРАБОТКА ЧЕРЕЗ AGNES AI
# ============================================================

@log_error
async def process_with_agnes(user_message: str, user_id: int) -> Dict:
    """Обрабатывает запрос через Agnes AI"""
    global agnes_client

    if agnes_client is None:
        init_agnes()

    try:
        session = await session_manager.get_session(user_id)

        system_prompt = f"""
Ты — AI агент, управляющий браузером через Pydoll.

Состояние браузера:
- Браузер: {'открыт' if session.is_active else 'закрыт'}
- URL: {session.current_url or 'нет'}
- Заголовок: {session.page_title or 'нет'}

Правила:
1. Если браузер закрыт — сначала открой его
2. Используй инструменты для действий
3. Для скриншотов используй take_screenshot
4. Отвечай понятно и по делу
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

        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                logger.info(f"🔧 Вызов: {tool_name}")

                result = await execute_tool(tool_name, arguments, user_id)
                results.append({"tool": tool_name, "result": result})

                if tool_name == "take_screenshot" and result.get("success") and result.get("screenshot"):
                    return {
                        "type": "screenshot",
                        "data": result["screenshot"],
                        "message": "📸 Скриншот готов"
                    }

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
        error_tracker.add_error(e, {"user_id": user_id})
        return {"type": "text", "content": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 9. КОМАНДЫ ТЕЛЕГРАМ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    await update.message.reply_text(
        "🤖 **Бот с AI агентом**\n\n"
        "Управляю браузером через естественный язык!\n\n"
        "📌 **Примеры:**\n"
        "• `Открой браузер`\n"
        "• `Перейди на google.com`\n"
        "• `Найди кнопку и кликни`\n"
        "• `Сделай скриншот`\n\n"
        "🔧 **Команды:**\n"
        "/open — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/status — Статус\n"
        "/debug — Отладка\n"
        "/errors — Ошибки",
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
        await update.message.reply_text("✅ Браузер открыт!")
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
    """Статус"""
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)

    message = (
        f"📊 **Статус**\n\n"
        f"🆔 Пользователь: `{user_id}`\n"
        f"🌐 Браузер: {'✅ Активен' if session.is_active else '❌ Не активен'}\n"
        f"🔗 URL: `{session.current_url or 'нет'}`\n"
        f"📄 Заголовок: `{session.page_title or 'нет'}`\n"
        f"⚡ Действие: {session.last_action or 'нет'}"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ошибки (админ)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    errors = error_tracker.get_recent(10)
    if not errors:
        await update.message.reply_text("✅ Ошибок нет")
        return

    message = "📊 **Ошибки:**\n\n"
    for i, error in enumerate(errors, 1):
        message += f"**{i}. {error['error_type']}**\n"
        message += f"💬 {error['error_message'][:100]}\n---\n"

    await update.message.reply_text(message[:4000], parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отладка (админ)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    message = (
        f"🔍 **Отладка**\n\n"
        f"**Сессии:** {len(session_manager.sessions)}\n"
        f"**Браузер:** {'✅' if session_manager._browser else '❌'}\n"
        f"**Ошибок:** {len(error_tracker.errors)}\n"
        f"**Логи:** `{LOG_DIR.absolute()}`"
    )

    await update.message.reply_text(message, parse_mode='Markdown')

async def clear_errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить ошибки (админ)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    error_tracker.clear()
    await update.message.reply_text("🧹 Ошибки очищены")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
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
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        else:
            await update.message.reply_text(result["content"])

    except Exception as e:
        error_tracker.add_error(e, {"user_id": user_id})
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    error = context.error
    error_tracker.add_error(error, {
        "user_id": update.effective_user.id if update else None
    })
    error_logger.error(f"Ошибка: {error}\n{traceback.format_exc()}")

# ============================================================
# 10. ФОНОВЫЕ ЗАДАЧИ
# ============================================================

async def cleanup_task():
    """Очистка неактивных сессий"""
    while True:
        await asyncio.sleep(300)
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
# 11. ЗАПУСК
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
        logger.info("🚀 Бот запущен!")
        logger.info(f"📁 Логи: {LOG_DIR.absolute()}")
        logger.info(f"👥 Админы: {ADMIN_IDS or 'нет'}")
        logger.info(f"💾 Persistent: {PERSISTENT_SESSION}")
        logger.info(f"📦 Инструментов: {len(TOOLS)}")
        logger.info("=" * 60)

        await application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    asyncio.run(main())