# bot.py - bsw запускает браузер с маскировкой, работа через CDP + DSPy
import os
import sys
import asyncio
import logging
import base64
import json
import time

# Добавляем путь к Browser Harness
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

# Папки
SCREENSHOTS_DIR = '/app/screenshots'
LOGS_DIR = '/app/logs'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
# СИГНАТУРА ТОЛЬКО С BROWSER HARNESS
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру через Browser Harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ BROWSER HARNESS:
    
    1. Навигация:
       - tool_goto_url(url) - перейти на сайт
       - tool_wait_for_load() - дождаться загрузки
       - tool_new_tab() - открыть новую вкладку
       - tool_close_tab() - закрыть вкладку
       - tool_switch_tab(tab_id) - переключить вкладку
       - tool_list_tabs() - список всех вкладок
       - tool_current_tab() - текущая вкладка
    
    2. Информация о странице:
       - tool_page_info() - URL и заголовок
       - tool_get_text() - весь текст на странице
       - tool_get_links() - все ссылки
       - tool_get_buttons() - все кнопки
       - tool_get_headings() - все заголовки (h1-h6)
    
    3. Взаимодействие со страницей:
       - tool_js(expression) - выполнить JavaScript
       - tool_fill_input(selector, text) - заполнить поле ввода
       - tool_click_at_xy(x, y) - кликнуть по координатам
       - tool_type_text(text) - ввести текст
       - tool_press_key(key) - нажать клавишу
       - tool_scroll(x, y) - прокрутить страницу
    
    4. Скриншоты:
       - tool_capture_screenshot(filename) - сделать скриншот
    
    ПРАВИЛА:
    - Всегда используй инструменты Browser Harness
    - Для получения текста со страницы используй tool_get_text
    - Для кликов используй tool_click_at_xy
    - Для заполнения форм используй tool_fill_input
    - Если нужно выполнить сложные действия - используй tool_js
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу с использованием Browser Harness")


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
        """Запуск браузера через bsw + подключение через CDP"""
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
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 2. Устанавливаем переменные для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        # 3. Запускаем daemon
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # 4. Создаём вкладку через Harness
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 5. Ждём загрузки
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        # 6. Инициализация DSPy с инструментами
        await self._init_dspy()
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def _init_dspy(self):
        """Инициализация DSPy агента с инструментами Browser Harness"""
        AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
        
        if not AGNES_API_KEY:
            logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
            return
        
        try:
            # ============================================================
            # ВСЕ ИНСТРУМЕНТЫ BROWSER HARNESS ДЛЯ DSPy
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
            
            def tool_page_info() -> str:
                """Получить информацию о странице (URL, Title)"""
                try:
                    info = page_info()
                    return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
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
            
            # ============================================================
            # СОБИРАЕМ ВСЕ ИНСТРУМЕНТЫ В СПИСОК
            # ============================================================
            
            tools = [
                Tool(tool_new_tab),
                Tool(tool_goto_url),
                Tool(tool_wait_for_load),
                Tool(tool_js),
                Tool(tool_capture_screenshot),
                Tool(tool_page_info),
                Tool(tool_get_text),
                Tool(tool_get_links),
                Tool(tool_get_buttons),
                Tool(tool_get_headings),
                Tool(tool_list_tabs),
                Tool(tool_current_tab),
                Tool(tool_switch_tab),
                Tool(tool_close_tab),
                Tool(tool_fill_input),
                Tool(tool_click_at_xy),
                Tool(tool_type_text),
                Tool(tool_press_key),
                Tool(tool_scroll),
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
    
    async def get_text(self, selector: str = "body") -> str:
        """Получение текста через CDP"""
        try:
            result = await self._cdp_send("Runtime.evaluate", {
                "expression": f"document.querySelector('{selector}')?.textContent || ''",
                "returnByValue": True
            })
            if result and "result" in result and "result" in result["result"]:
                return result["result"]["result"].get("value", "")
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
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
            # Запускаем агента в отдельном потоке
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
# TELEGRAM КОМАНДА /dspy
# ============================================================

bot = None  # Глобальный экземпляр

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
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
    
    # Запускаем HarnessBot
    bot = HarnessBot()
    await bot.start()
    
    # Создаём Telegram приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команду /dspy
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен! Команда: /dspy")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if bot.dspy_agent else '❌ Отключен'}")
    
    # Запускаем polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Бесконечное ожидание
    while True:
        await asyncio.sleep(60)
        logger.info("💓 Bot alive")


if __name__ == "__main__":
    asyncio.run(main())