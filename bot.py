# bot.py - bsw запускает браузер с маскировкой, работа через CDP + DSPy  
import os
import sys
import asyncio
import logging
import base64
import json
import time

# ============================================================
# 1. НАСТРОЙКА ТАЙМАУТОВ ДЛЯ BROWSER HARNESS
# ============================================================

os.environ["BU_TIMEOUT"] = "60000"
os.environ["BU_NAVIGATION_TIMEOUT"] = "60000"

# ============================================================
# 2. НАСТРОЙКА ЛОГГЕРА (ДО ВСЕГО ОСТАЛЬНОГО)
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 3. ПАПКИ
# ============================================================

SCREENSHOTS_DIR = '/app/screenshots'
LOGS_DIR = '/app/logs'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ============================================================
# 4. КУКИ ДЛЯ X (TWITTER) - АДАПТИРОВАНЫ ДЛЯ CDP
# ============================================================

COOKIES = [
    {"name": "auth_token", "value": "2a1332f5dada664d8d8dfa10c76857590b52ae35", "domain": "x.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
    {"name": "ct0", "value": "75c731cf498eb30416712d1aaf4159c21ab67c11f63157e728023bb1d584f8ec94ccf03a899f02e1f04e6eee9c9f94531a1800d7f94f3871bfd787e001ed62a3ff5a11bc1178d39310a57035b762b1f1", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "guest_id", "value": "v1%3A178654552534341036", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "guest_id_marketing", "value": "v1%3A178654552534341036", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "guest_id_ads", "value": "v1%3A178654552534341036", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "personalization_id", "value": "\"v1_vCSISZBfJDpEFaPx5Fz5Rg==\"", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "lang", "value": "ru", "domain": "x.com", "path": "/"},
    {"name": "gt", "value": "2087549353716060518", "domain": "x.com", "path": "/", "secure": True, "sameSite": "Lax"},
    {"name": "__cuid", "value": "74718293-b3ec-48aa-9a90-1476c17a8557", "domain": "x.com", "path": "/"},
    {"name": "g_state", "value": "{\"i_l\":2,\"i_ll\":1786545535935,\"i_b\":\"Kj2ZJFn05wJXEtImAaj5lwEgjKzmmXBcu1prDcy9Iks\",\"i_e\":{\"enable_itp_optimization\":24},\"i_et\":1786545535935,\"i_p\":1786631938453}", "domain": "x.com", "path": "/"}
]

logger.info(f"🍪 Загружено {len(COOKIES)} кук для X")

# ============================================================
# 5. ДОБАВЛЯЕМ ПУТЬ К BROWSER HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness
from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    page_info,
    current_tab,
    capture_screenshot,
    js,
    list_tabs,
    switch_tab,
    fill_input,
    click_at_xy,
    type_text,
    press_key,
    scroll,
)
from browser_harness.admin import ensure_daemon

# Импорты Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

# Импортируем маскировку
from bsw import StealthBrowser

# Токен
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")


# ============================================================
# DSPy ИНТЕГРАЦИЯ (ЧИСТЫЙ DSPy 3.3.0b1)
# ============================================================

import warnings
import httpx
import dspy
from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool

warnings.filterwarnings("ignore")


class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI совместимый с DSPy"""
    
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
# СИГНАТУРА С ОПТИМИЗИРОВАННЫМИ ИНСТРУМЕНТАМИ
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру.
    
    ИНСТРУМЕНТЫ:
    
    НАВИГАЦИЯ:
    - tool_goto_url(url) - перейти на сайт
    - tool_new_tab() - открыть новую вкладку
    - tool_close_tab() - закрыть вкладку
    
    ПОИСК ЭЛЕМЕНТОВ (ОСНОВНОЙ):
    - tool_get_ax_tree() - получить все кнопки/поля/ссылки (рекомендовано)
    
    ЧТЕНИЕ КОНТЕНТА:
    - tool_get_text() - прочитать текст на странице (статьи, новости)
    - tool_page_info() - URL и заголовок
    
    ДЕЙСТВИЯ:
    - tool_fill_input(selector, text) - заполнить поле
    - tool_click_at_xy(x, y) - кликнуть по координатам
    - tool_press_key(key) - нажать клавишу
    
    ДОПОЛНИТЕЛЬНО:
    - tool_js(expression) - выполнить JavaScript
    - tool_capture_screenshot() - сделать скриншот
    
    АЛГОРИТМ РАБОТЫ:
    1. tool_goto_url() → перейти на сайт
    2. tool_get_ax_tree() → найти элементы
    3. tool_fill_input() или tool_click_at_xy() → взаимодействовать
    4. tool_get_text() → прочитать результат
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ")


# ============================================================
# СОЗДАНИЕ АГЕНТА
# ============================================================

def create_browser_agent(tools, max_iters=10):
    """Создать ReActV2 агента с инструментами"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=max_iters,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания ReActV2 агента: {e}")
        
        # Fallback: пробуем без Tool
        try:
            tools_fallback = [tool for tool in tools if callable(tool)]
            agent = ReActV2(
                signature=BrowserTask,
                tools=tools_fallback,
                max_iters=max_iters,
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


def init_dspy(api_key=None, tools=None, max_iters=10):
    """Инициализировать DSPy с Agnes AI"""
    api_key = api_key or os.environ.get("AGNES_API_KEY")
    
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")
        return None, None
    
    try:
        lm = AgnesLM(
            api_key=api_key,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        if tools:
            agent = create_browser_agent(tools, max_iters)
        else:
            agent = None
            logger.info("ℹ️ Инструменты не переданы, агент не создан")
        
        return lm, agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None, None


def run_agent(agent, question: str) -> str:
    """Запустить агента с вопросом"""
    if not agent:
        return "❌ Агент не инициализирован"
    
    try:
        result = agent(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Агент вернул пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения агента: {e}")
        return f"❌ Ошибка: {str(e)}"


# ============================================================
# КОНЕЦ DSPy ИНТЕГРАЦИИ
# ============================================================


class HarnessBot:
    def __init__(self):
        self.browser = None
        self.page = None
        self.ws = None
        self.is_ready = False
        self._id = 0
        self.dspy_agent = None
        self.dspy_lm = None
    
    async def start(self):
        """Запуск браузера через bsw + установка кук ДО Harness"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        
        # 1. Запускаем браузер через bsw
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # Сохраняем WebSocket для прямого CDP
        self.ws = self.browser["ws"]
        self._id = self.browser["_id"]
        
        await asyncio.sleep(2)
        
        # ============================================================
        # 2. УСТАНАВЛИВАЕМ КУКИ ДО ПОДКЛЮЧЕНИЯ HARNESS
        # ============================================================
        logger.info("🍪 Устанавливаю куки ДО подключения Browser Harness...")
        await self._set_cookies_direct()
        
        # ============================================================
        # 3. ТЕПЕРЬ ПОДКЛЮЧАЕМ BROWSER HARNESS
        # ============================================================
        logger.info("🔗 Шаг 3: Подключение Browser Harness...")
        
        # Устанавливаем переменные для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        # Запускаем daemon
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # Создаём вкладку через Harness
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # Ждём загрузки
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        # Проверяем, что куки сохранились
        await self._check_cookies()
        
        # 4. Инициализация DSPy с инструментами
        await self._init_dspy()
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def _set_cookies_direct(self):
        """Установка кук через прямой CDP ДО подключения Browser Harness"""
        if not COOKIES:
            logger.info("ℹ️ Нет кук для установки")
            return
        
        try:
            # Формируем список кук
            cookies_list = []
            for cookie in COOKIES:
                cookie_data = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain", "").lstrip("."),
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                }
                
                if "sameSite" in cookie:
                    same_site = cookie["sameSite"]
                    if same_site == "no_restriction":
                        same_site = "None"
                    elif same_site == "unspecified":
                        same_site = "Lax"
                    cookie_data["sameSite"] = same_site
                
                cookies_list.append(cookie_data)
                logger.info(f"🍪 Подготовлена: {cookie_data['name']}")
            
            # Отправляем через CDP (прямой WebSocket)
            self._id += 1
            msg = {
                "id": self._id,
                "method": "Network.setCookies",
                "params": {"cookies": cookies_list}
            }
            await self.ws.send(json.dumps(msg))
            response = await self.ws.recv()
            result = json.loads(response)
            
            if "error" in result:
                logger.error(f"❌ Ошибка CDP: {result['error']}")
            else:
                logger.info(f"✅ Куки отправлены через CDP (до Harness)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
    
    async def _check_cookies(self):
        """Проверка установленных кук"""
        try:
            self._id += 1
            msg = {
                "id": self._id,
                "method": "Network.getCookies",
                "params": {}
            }
            await self.ws.send(json.dumps(msg))
            response = await self.ws.recv()
            result = json.loads(response)
            
            cookies = result.get("result", {}).get("cookies", [])
            
            # Проверяем auth_token
            for cookie in cookies:
                if cookie.get("name") == "auth_token":
                    logger.info(f"🔑 auth_token установлен: {cookie.get('value')[:20]}...")
                    break
            else:
                logger.warning("⚠️ auth_token НЕ найден")
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки кук: {e}")
    
    async def _init_dspy(self):
        """Инициализация DSPy агента с оптимизированными инструментами"""
        AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
        
        if not AGNES_API_KEY:
            logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
            return
        
        try:
            # ============================================================
            # ИНСТРУМЕНТЫ ДЛЯ DSPy (ОПТИМИЗИРОВАННЫЙ СПИСОК)
            # ============================================================
            
            # ---- НАВИГАЦИЯ (4 инструмента) ----
            
            def tool_goto_url(url: str) -> str:
                """Перейти на URL"""
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
            
            def tool_new_tab() -> str:
                """Открыть новую вкладку"""
                try:
                    new_tab()
                    return "✅ Новая вкладка открыта"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_close_tab() -> str:
                """Закрыть текущую вкладку"""
                try:
                    close_tab()
                    return "✅ Вкладка закрыта"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            # ---- ИНФОРМАЦИЯ О СТРАНИЦЕ (3 инструмента) ----
            
            def tool_get_ax_tree() -> str:
                """
                Получить интерактивные элементы через Accessibility Tree.
                Используй для поиска кнопок, полей, ссылок.
                """
                try:
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(bot.get_ax_tree())
                    return result
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_text() -> str:
                """
                Получить весь текст со страницы.
                Используй для чтения контента (статьи, новости).
                """
                try:
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(bot.get_text_cdp())
                    return result
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_page_info() -> str:
                """Получить URL и заголовок страницы"""
                try:
                    info = page_info()
                    return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            # ---- ВЗАИМОДЕЙСТВИЕ (3 инструмента) ----
            
            def tool_fill_input(selector: str, text: str) -> str:
                """Заполнить поле ввода (по CSS селектору)"""
                try:
                    fill_input(selector, text)
                    return f"✅ Заполнено: {selector} -> {text}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_click_at_xy(x: int, y: int) -> str:
                """Кликнуть по координатам (получи из AX Tree)"""
                try:
                    click_at_xy(x, y)
                    return f"✅ Клик по ({x}, {y})"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_press_key(key: str) -> str:
                """Нажать клавишу (Enter, Escape, Tab и др.)"""
                try:
                    press_key(key)
                    return f"✅ Нажата клавиша: {key}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            # ---- ДОПОЛНИТЕЛЬНО (2 инструмента) ----
            
            def tool_js(expression: str) -> str:
                """Выполнить JavaScript (для сложных действий)"""
                try:
                    result = js(expression)
                    return str(result) if result is not None else "✅ JavaScript выполнен"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_capture_screenshot(filename: str = None) -> str:
                """Сделать скриншот страницы"""
                try:
                    if not filename:
                        filename = f"screenshot_{int(time.time())}.png"
                    full_path = os.path.join(SCREENSHOTS_DIR, filename)
                    capture_screenshot(path=full_path)
                    return f"✅ Скриншот: {filename}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            # ============================================================
            # СОБИРАЕМ ОПТИМИЗИРОВАННЫЙ СПИСОК (12 ИНСТРУМЕНТОВ)
            # ============================================================
            
            tools = [
                # Навигация
                Tool(tool_goto_url),
                Tool(tool_wait_for_load),
                Tool(tool_new_tab),
                Tool(tool_close_tab),
                
                # Информация
                Tool(tool_get_ax_tree),    # ОСНОВНОЙ для поиска элементов
                Tool(tool_get_text),       # ОСНОВНОЙ для чтения контента
                Tool(tool_page_info),
                
                # Взаимодействие
                Tool(tool_fill_input),
                Tool(tool_click_at_xy),
                Tool(tool_press_key),
                
                # Дополнительно
                Tool(tool_js),
                Tool(tool_capture_screenshot),
            ]
            
            # Инициализируем DSPy с инструментами
            self.dspy_lm, self.dspy_agent = init_dspy(
                api_key=AGNES_API_KEY,
                tools=tools,
                max_iters=10
            )
            
            if self.dspy_agent:
                logger.info(f"✅ DSPy агент инициализирован с {len(tools)} инструментами")
            else:
                logger.warning("⚠️ Не удалось создать DSPy агента")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации DSPy: {e}")
            self.dspy_agent = None
    
    # ========== CDP МЕТОДЫ ==========
    
    async def _cdp_send(self, method: str, params: dict = None) -> dict:
        """Асинхронная отправка CDP команды"""
        self._id += 1
        msg = {
            "id": self._id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        return json.loads(response)
    
    # ========== ПУБЛИЧНЫЕ МЕТОДЫ ==========
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        goto_url(self.page, url)
        wait_for_load()
        logger.info(f"✅ Страница {url} загружена")
    
    async def get_text_cdp(self) -> str:
        """Получение текста через прямой CDP (надёжнее)"""
        try:
            # Ждём загрузки через CDP
            for _ in range(30):
                state_result = await self._cdp_send("Runtime.evaluate", {
                    "expression": "document.readyState",
                    "returnByValue": True
                })
                state = state_result.get("result", {}).get("result", {}).get("value", "")
                if state == "complete":
                    break
                await asyncio.sleep(0.5)
            
            # Получаем текст
            result = await self._cdp_send("Runtime.evaluate", {
                "expression": "document.body.innerText || document.documentElement.innerText",
                "returnByValue": True
            })
            
            text = result.get("result", {}).get("result", {}).get("value", "")
            if text and len(text) > 10:
                return text[:10000]
            return "❌ Текст не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_ax_tree(self) -> str:
        """Получить интерактивные элементы через Accessibility Tree (рекомендовано browser-harness)"""
        try:
            # Получаем AX дерево через CDP
            result = await self._cdp_send("Accessibility.getFullAXTree")
            
            if not result or "result" not in result:
                return "❌ Не удалось получить Accessibility Tree"
            
            nodes = result.get("result", {}).get("nodes", [])
            
            if not nodes:
                return "❌ Нет узлов в Accessibility Tree"
            
            # Фильтруем интерактивные элементы
            interactive = []
            for node in nodes:
                role = node.get("role", {}).get("value", "")
                name = node.get("name", {}).get("value", "")
                
                # Интерактивные роли
                interactive_roles = {
                    "button", "link", "textbox", "checkbox", "radio",
                    "combobox", "listbox", "menuitem", "tab", "treeitem",
                    "slider", "spinbutton", "switch", "searchbox"
                }
                
                if role in interactive_roles and name:
                    interactive.append({
                        "role": role,
                        "name": name[:50]
                    })
            
            if not interactive:
                return "ℹ️ Нет интерактивных элементов на странице"
            
            # Форматируем для агента
            info = page_info()
            result_text = f"📄 {info.get('title', 'No title')}\n"
            result_text += f"🔗 {info.get('url', 'No URL')}\n\n"
            result_text += f"📋 Найдено {len(interactive)} интерактивных элементов:\n\n"
            
            for idx, el in enumerate(interactive[:30], 1):
                result_text += f"  {idx}. [{el['role']}] {el['name']}\n"
            
            return result_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка AX Tree: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def screenshot(self, path: str = None) -> bytes:
        """Скриншот через CDP"""
        try:
            result = await self._cdp_send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            })
            if result and "result" in result and "data" in result["result"]:
                data = base64.b64decode(result["result"]["data"])
                if path:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(data)
                    logger.info(f"📸 Скриншот сохранён в {path}")
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    async def click(self, selector: str) -> bool:
        """Клик через CDP"""
        try:
            result = await self._cdp_send("Runtime.evaluate", {
                "expression": f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        return {{
                            x: rect.left + rect.width/2,
                            y: rect.top + rect.height/2
                        }};
                    }})()
                """,
                "returnByValue": True
            })
            if result and "result" in result and "result" in result["result"]:
                pos = result["result"]["result"].get("value")
                if pos:
                    await self._cdp_send("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    await asyncio.sleep(0.05)
                    await self._cdp_send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    logger.info(f"🖱️ Клик на {selector}")
                    return True
            logger.warning(f"⚠️ Элемент {selector} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            return False
    
    async def type_text(self, selector: str, text: str) -> bool:
        """Ввод текста"""
        try:
            await self._cdp_send("Runtime.evaluate", {
                "expression": f"""
                    const el = document.querySelector('{selector}');
                    if (el) {{ el.focus(); el.value = '{text}'; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                """
            })
            logger.info(f"⌨️ Введено: {text} в {selector}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка ввода: {e}")
            return False
    
    async def scroll(self, x: int = 0, y: int = 100) -> bool:
        """Прокрутка"""
        try:
            await self._cdp_send("Runtime.evaluate", {
                "expression": f"window.scrollBy({x}, {y})"
            })
            logger.info(f"📜 Прокрутка на ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка прокрутки: {e}")
            return False
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        return page_info()
    
    async def ask_dspy(self, question: str) -> str:
        """Задать вопрос DSPy агенту"""
        if not self.dspy_agent:
            return "❌ DSPy агент не инициализирован. Проверьте AGNES_API_KEY"
        
        logger.info(f"🧠 DSPy запрос: {question}")
        
        try:
            loop = asyncio.get_running_loop()
            answer = await loop.run_in_executor(
                None, run_agent, self.dspy_agent, question
            )
            return answer
        except Exception as e:
            logger.error(f"❌ DSPy ошибка: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def close(self):
        """Закрытие"""
        logger.info("🔚 Закрываю...")
        
        if self.page:
            try:
                close_tab(self.page)
                logger.info("✅ Вкладка закрыта")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка закрытия вкладки: {e}")
        
        if self.browser:
            await StealthBrowser.close(self.browser)
            logger.info("✅ Браузер закрыт")
        
        self.is_ready = False
        logger.info("✅ Закрыто")


# ============================================================
# TELEGRAM КОМАНДА /start
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - показывает меню"""
    if not update or not update.message:
        return
    
    menu_text = "/dspy - выполнить задачу в браузере"
    
    await update.message.reply_text(menu_text, parse_mode='Markdown')


# ============================================================
# TELEGRAM КОМАНДА /dspy
# ============================================================

bot = None  # Глобальный экземпляр

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
    if not update or not update.message:
        logger.warning("⚠️ update.message is None")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу агенту:\n"
            "`/dspy открыть google.com и сделать скриншот`\n\n"
            "Или просто опиши что нужно сделать.",
            parse_mode='Markdown'
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        if not bot or not bot.dspy_agent:
            await status_msg.edit_text(
                "❌ **DSPy агент не инициализирован.**\n"
                "Проверьте переменную окружения `AGNES_API_KEY`."
            )
            return
        
        answer = await bot.ask_dspy(user_query)
        
        if not answer or answer.strip() == "":
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
            return
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        answer_escaped = escape_markdown(answer, version=2)
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{answer_escaped}",
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен! Команды: /start, /dspy")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if bot.dspy_agent else '❌ Отключен'}")
    logger.info(f"🍪 Куки: {'✅ Загружены' if COOKIES else '❌ Нет'}")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(60)
        logger.info("💓 Bot alive")


if __name__ == "__main__":
    asyncio.run(main())