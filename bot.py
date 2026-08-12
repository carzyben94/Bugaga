# bot.py - Browser Harness + DSPy через облачный браузер Browser Use
import os
import sys
import asyncio
import logging
import base64
import json
import time

# ============================================================
# 1. НАСТРОЙКА ЛОГГЕРА
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
# 2. ПАПКИ
# ============================================================

SCREENSHOTS_DIR = '/app/screenshots'
LOGS_DIR = '/app/logs'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ============================================================
# 3. ИМПОРТ КУК
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"🍪 Загружено {len(COOKIES)} кук")
except ImportError:
    logger.warning("⚠️ cookies.py не найден, куки не загружены")
    COOKIES = []

# ============================================================
# 4. ПУТЬ К BROWSER HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

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

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

# ============================================================
# 5. ТОКЕНЫ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

BROWSER_USE_API_KEY = os.environ.get("BROWSER_USE_API_KEY")
if not BROWSER_USE_API_KEY:
    raise ValueError("❌ BROWSER_USE_API_KEY не задан! Получите на cloud.browser-use.com/new-api-key")

# ============================================================
# 6. DSPy ИНТЕГРАЦИЯ
# ============================================================

import warnings
import httpx
import dspy
from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool

warnings.filterwarnings("ignore")


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


class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру через Browser Harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    - tool_goto_url(url) - перейти на сайт
    - tool_wait_for_load() - дождаться загрузки
    - tool_new_tab() - открыть новую вкладку
    - tool_close_tab() - закрыть вкладку
    - tool_switch_tab(tab_id) - переключить вкладку
    - tool_list_tabs() - список вкладок
    - tool_current_tab() - текущая вкладка
    - tool_page_info() - URL и заголовок
    - tool_get_text() - весь текст на странице
    - tool_get_links() - все ссылки
    - tool_get_buttons() - все кнопки
    - tool_get_headings() - все заголовки
    - tool_js(expression) - выполнить JavaScript
    - tool_fill_input(selector, text) - заполнить поле
    - tool_click_at_xy(x, y) - кликнуть по координатам
    - tool_type_text(text) - ввести текст
    - tool_press_key(key) - нажать клавишу
    - tool_scroll(x, y) - прокрутить
    - tool_capture_screenshot(filename) - сделать скриншот
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу с использованием Browser Harness")


def create_browser_agent(tools, max_iters=10):
    """Создать ReActV2 агента"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=max_iters,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")
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
            logger.error(f"❌ Fallback не работает: {e3}")
            return None


def init_dspy(api_key=None, tools=None, max_iters=10):
    """Инициализировать DSPy"""
    api_key = api_key or os.environ.get("AGNES_API_KEY")
    
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return None, None
    
    try:
        lm = AgnesLM(api_key=api_key, temperature=0.3, max_tokens=2000)
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен")
        
        if tools:
            agent = create_browser_agent(tools, max_iters)
        else:
            agent = None
        
        return lm, agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None, None


def run_agent(agent, question: str) -> str:
    """Запустить агента"""
    if not agent:
        return "❌ Агент не инициализирован"
    
    try:
        result = agent(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка агента: {e}")
        return f"❌ Ошибка: {str(e)}"


# ============================================================
# 7. ОСНОВНОЙ КЛАСС HarnessBot (ОБЛАЧНАЯ ВЕРСИЯ)
# ============================================================

class HarnessBot:
    def __init__(self):
        self.page = None
        self.daemon = None
        self.is_ready = False
        self.dspy_agent = None
        self.dspy_lm = None
        self.browser_id = None  # ID сессии в облаке
    
    async def start(self):
        """Запуск через облачный браузер Browser Use"""
        logger.info("☁️ Подключение к облачному браузеру Browser Use...")
        
        # Устанавливаем переменные для Harness
        os.environ["BROWSER_USE_API_KEY"] = BROWSER_USE_API_KEY
        
        # Запускаем daemon (автоматически подхватит облачный режим)
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # Создаём вкладку в облаке
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана в облаке: {self.page}")
        
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        # Устанавливаем куки
        await self._set_cookies()
        
        # Инициализация DSPy
        await self._init_dspy()
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов (облачный режим)!")
        return self
    
    async def _set_cookies(self):
        """Установить куки через CDP"""
        if not COOKIES:
            logger.info("ℹ️ Нет кук для установки")
            return
        
        try:
            # Используем js для установки кук
            for cookie in COOKIES:
                name = cookie.get("name")
                value = cookie.get("value")
                domain = cookie.get("domain", "")
                if name and value:
                    js_script = f'document.cookie = "{name}={value}; domain={domain}; path=/";'
                    js(js_script)
            
            logger.info(f"✅ Установлено {len(COOKIES)} кук")
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
    
    async def _init_dspy(self):
        """Инициализация DSPy с инструментами"""
        AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
        
        if not AGNES_API_KEY:
            logger.warning("⚠️ AGNES_API_KEY не задан")
            return
        
        try:
            # Инструменты Browser Harness для DSPy
            def tool_new_tab() -> str:
                try:
                    new_tab()
                    return "✅ Новая вкладка открыта"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_goto_url(url: str) -> str:
                try:
                    goto_url(url)
                    wait_for_load()
                    return f"✅ Перешел на {url}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_wait_for_load() -> str:
                try:
                    wait_for_load()
                    return "✅ Страница загружена"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_js(expression: str) -> str:
                try:
                    result = js(expression)
                    if isinstance(result, dict):
                        return str(result.get('result', result))
                    return str(result) if result is not None else "✅ JS выполнен"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_capture_screenshot(filename: str = None) -> str:
                try:
                    if not filename:
                        timestamp = int(time.time())
                        filename = f"screenshot_{timestamp}.png"
                    full_path = os.path.join(SCREENSHOTS_DIR, filename)
                    capture_screenshot(path=full_path)
                    return f"✅ Скриншот: {filename}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_page_info() -> str:
                try:
                    info = page_info()
                    return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_text() -> str:
                try:
                    result = js('() => document.body.innerText')
                    text = str(result.get('result', result)) if isinstance(result, dict) else str(result)
                    if text and len(text) > 10:
                        return text[:5000]
                    return "❌ Текст не найден"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_links() -> str:
                try:
                    result = js('() => Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
                    if isinstance(result, list) and result:
                        links = [str(item) for item in result if item]
                        return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
                    return "❌ Ссылок не найдено"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_buttons() -> str:
                try:
                    result = js('() => Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())')
                    if isinstance(result, list) and result:
                        buttons = [str(item).strip() for item in result if item and str(item).strip()]
                        return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
                    return "❌ Кнопок не найдено"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_headings() -> str:
                try:
                    result = js('() => Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t.trim())')
                    if isinstance(result, list) and result:
                        return "Заголовки:\n" + "\n".join([str(item).strip() for item in result if item])
                    return "❌ Заголовков не найдено"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_list_tabs() -> str:
                try:
                    return f"Вкладки: {list_tabs()}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_current_tab() -> str:
                try:
                    return f"Текущая вкладка: {current_tab()}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_switch_tab(tab_id: int) -> str:
                try:
                    switch_tab(tab_id)
                    return f"✅ Переключился на {tab_id}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_close_tab() -> str:
                try:
                    close_tab()
                    return "✅ Вкладка закрыта"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_fill_input(selector: str, text: str) -> str:
                try:
                    fill_input(selector, text)
                    return f"✅ Заполнено: {selector} -> {text}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_click_at_xy(x: int, y: int) -> str:
                try:
                    click_at_xy(x, y)
                    return f"✅ Клик по ({x}, {y})"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_type_text(text: str) -> str:
                try:
                    type_text(text)
                    return f"✅ Введено: {text}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_press_key(key: str) -> str:
                try:
                    press_key(key)
                    return f"✅ Нажата клавиша: {key}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_scroll(dx: int, dy: int) -> str:
                try:
                    scroll(dx, dy)
                    return f"✅ Прокрутка на ({dx}, {dy})"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            tools = [
                Tool(tool_new_tab), Tool(tool_goto_url), Tool(tool_wait_for_load),
                Tool(tool_js), Tool(tool_capture_screenshot), Tool(tool_page_info),
                Tool(tool_get_text), Tool(tool_get_links), Tool(tool_get_buttons),
                Tool(tool_get_headings), Tool(tool_list_tabs), Tool(tool_current_tab),
                Tool(tool_switch_tab), Tool(tool_close_tab), Tool(tool_fill_input),
                Tool(tool_click_at_xy), Tool(tool_type_text), Tool(tool_press_key),
                Tool(tool_scroll),
            ]
            
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
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        goto_url(url)
        wait_for_load()
        logger.info(f"✅ Страница загружена")
    
    async def get_page_info(self) -> dict:
        return page_info()
    
    async def ask_dspy(self, question: str) -> str:
        """Задать вопрос DSPy агенту"""
        if not self.dspy_agent:
            return "❌ DSPy агент не инициализирован"
        
        logger.info(f"🧠 DSPy запрос: {question}")
        
        try:
            loop = asyncio.get_running_loop()
            answer = await loop.run_in_executor(None, run_agent, self.dspy_agent, question)
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
            except Exception as e:
                logger.warning(f"⚠️ Ошибка: {e}")
        self.is_ready = False


# ============================================================
# 8. TELEGRAM КОМАНДА
# ============================================================

bot = None

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /dspy"""
    if not update or not update.message:
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу:\n"
            "`/dspy открыть google.com и сделать скриншот`",
            parse_mode='Markdown'
        )
        return
    
    user_query = " ".join(context.args)
    logger.info(f"👤 DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        if not bot or not bot.dspy_agent:
            await status_msg.edit_text("❌ DSPy агент не инициализирован")
            return
        
        answer = await bot.ask_dspy(user_query)
        
        if not answer or not answer.strip():
            await status_msg.edit_text("❌ Пустой ответ")
            return
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# 9. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен! Команда: /dspy")
    logger.info(f"🧠 DSPy: {'✅ Активен' if bot.dspy_agent else '❌ Отключен'}")
    logger.info(f"☁️ Браузер: Облачный Browser Use")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(60)
        logger.info("💓 Bot alive")


if __name__ == "__main__":
    asyncio.run(main())