import os
import sys
import asyncio
import logging
import time
import signal
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

# ============================================================
# 1. ЛОГГЕР
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. ПУТЬ К BROWSER HARNESS
# ============================================================

sys.path.insert(0, "/app/browser-harness/src")

# ============================================================
# 3. ИМПОРТЫ
# ============================================================

import warnings
import httpx
import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

# CAMOUFOX
try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
    logger.info("✅ Camoufox загружен")
except ImportError as e:
    CAMOUFOX_AVAILABLE = False
    logger.warning(f"⚠️ Camoufox не найден: {e}")

# BROWSER HARNESS
try:
    from browser_harness.helpers import (
        new_tab, goto_url, wait_for_load, close_tab,
        page_info, current_tab, capture_screenshot, js,
        list_tabs, switch_tab, fill_input, click_at_xy,
        type_text, press_key, scroll,
    )
    from browser_harness.admin import ensure_daemon
    HARNESS_AVAILABLE = True
    logger.info("✅ Browser Harness загружен")
except ImportError as e:
    HARNESS_AVAILABLE = False
    logger.warning(f"⚠️ Browser Harness не найден: {e}")

warnings.filterwarnings("ignore")

# ============================================================
# 4. НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
browser_instance = None
harness_ready = False
dspy_agent_instance = None

# ============================================================
# 5. AGNES LM АДАПТЕР ДЛЯ DSPy
# ============================================================

class AgnesLM(dspy.LM):
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
        api_messages = messages or [{"role": "user", "content": prompt or ""}]
        
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
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ"]
        except Exception as e:
            logger.error(f"❌ Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================================
# 6. DSPy СИГНАТУРА
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру Camoufox через Browser Harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    - tool_goto_url(url) - перейти на сайт
    - tool_page_info() - информация о странице
    - tool_get_text() - весь текст на странице
    - tool_get_links() - все ссылки
    - tool_screenshot() - сделать скриншот
    - tool_js(expression) - выполнить JavaScript
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Результат выполнения задачи")

# ============================================================
# 7. ИНИЦИАЛИЗАЦИЯ CAMOUFOX (С ДИАГНОСТИКОЙ)
# ============================================================

async def init_browser_and_harness():
    """Запустить Camoufox и сохранить экземпляр браузера"""
    global browser_instance, harness_ready
    
    if not CAMOUFOX_AVAILABLE:
        logger.error("❌ Camoufox не доступен")
        return False
    
    logger.info("🚀 Запускаем Camoufox...")
    
    try:
        # Пробуем разные варианты
        browser = None
        
        # Вариант 1: с persistent_context (если поддерживается)
        try:
            logger.info("🔧 Пробуем с persistent_context=True...")
            browser = AsyncCamoufox(
                headless=True,
                fingerprint=True,
                persistent_context=True
            )
            browser_instance = await browser.__aenter__()
            logger.info("✅ Запущено с persistent_context=True")
        except TypeError as e:
            # Вариант 2: без persistent_context
            logger.warning(f"⚠️ persistent_context не поддерживается: {e}")
            logger.info("🔧 Пробуем без persistent_context...")
            browser = AsyncCamoufox(
                headless=True,
                fingerprint=True
            )
            browser_instance = await browser.__aenter__()
            logger.info("✅ Запущено без persistent_context")
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске: {e}")
            browser_instance = None
            return False
        
        # Проверка: если browser_instance — bool, значит ошибка
        if isinstance(browser_instance, bool):
            logger.error(f"❌ browser_instance вернул bool: {browser_instance}")
            browser_instance = None
            return False
        
        logger.info(f"✅ Camoufox запущен, тип: {type(browser_instance)}")
        
        # Проверка: создаём тестовую страницу
        try:
            logger.info("🔍 Проверяем браузер...")
            test_page = await browser_instance.new_page()
            await test_page.goto("about:blank", wait_until="load")
            await test_page.close()
            logger.info("✅ Проверка браузера пройдена")
        except Exception as e:
            logger.error(f"❌ Проверка браузера не пройдена: {e}")
            browser_instance = None
            return False
        
        await asyncio.sleep(2)
        
        if HARNESS_AVAILABLE:
            logger.info("🔗 Подключаем Browser Harness...")
            try:
                ensure_daemon()
                new_tab("about:blank")
                wait_for_load()
                harness_ready = True
                logger.info("✅ Browser Harness готов")
            except Exception as e:
                logger.error(f"❌ Ошибка подключения Harness: {e}")
                harness_ready = False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Camoufox: {e}")
        browser_instance = None
        return False

# ============================================================
# 8. СОЗДАНИЕ ИНСТРУМЕНТОВ ДЛЯ DSPy
# ============================================================

def create_harness_tools():
    """Создать инструменты для DSPy агента"""
    tools = []
    
    def tool_goto_url(url: str) -> str:
        try:
            goto_url(url)
            wait_for_load()
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_goto_url))
    
    def tool_page_info() -> str:
        try:
            info = page_info()
            return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_page_info))
    
    def tool_get_text() -> str:
        try:
            result = js('() => document.body.innerText')
            text = str(result.get('result', result)) if isinstance(result, dict) else str(result)
            return text[:5000] if text and len(text) > 10 else "❌ Текст не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_text))
    
    def tool_get_links() -> str:
        try:
            result = js('() => Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
            if isinstance(result, list) and result:
                links = [str(item) for item in result if item]
                return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
            return "❌ Ссылок не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_links))
    
    def tool_screenshot() -> str:
        try:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
            full_path = os.path.join(SCREENSHOTS_DIR, filename)
            capture_screenshot(path=full_path)
            return f"✅ Скриншот сохранен: {filename}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_screenshot))
    
    def tool_js(expression: str) -> str:
        try:
            result = js(expression)
            return str(result.get('result', result)) if isinstance(result, dict) else str(result)
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_js))
    
    return tools

# ============================================================
# 9. ИНИЦИАЛИЗАЦИЯ DSPy
# ============================================================

def init_dspy():
    global dspy_agent_instance
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return False
    
    try:
        lm = AgnesLM(api_key=api_key, temperature=0.3, max_tokens=2000)
        settings.configure(lm=lm)
        tools = create_harness_tools()
        dspy_agent_instance = ReActV2(signature=BrowserTask, tools=tools, max_iters=10)
        logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка DSPy: {e}")
        return False

def run_agent(question: str) -> str:
    if not dspy_agent_instance:
        return "❌ DSPy агент не инициализирован"
    try:
        result = dspy_agent_instance(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Пустой ответ"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# 10. TELEGRAM КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 **Camoufox + Browser Harness + DSPy**\n\n"
        "Команды:\n"
        "/check <url> - открыть сайт\n"
        "/dspy <запрос> - DSPy агент\n"
        "/status - статус системы\n"
        "/screenshot - сделать скриншот",
        parse_mode='Markdown'
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text("⏳ Открываю через Camoufox...")
    
    try:
        global browser_instance
        
        if not CAMOUFOX_AVAILABLE:
            await msg.edit_text("❌ Camoufox не установлен")
            return
        
        if browser_instance is None:
            await msg.edit_text("❌ Браузер не запущен. Используйте /status")
            return
        
        if isinstance(browser_instance, bool):
            await msg.edit_text(f"❌ Ошибка: browser_instance = {browser_instance}")
            return
        
        # Используем сохранённый браузер
        page = await browser_instance.new_page()
        await page.goto(url, wait_until="networkidle")
        title = await page.title()
        content = await page.content()
        await page.close()
        
        await msg.edit_text(f"✅ {title}\n\n{content[:500]}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        global browser_instance
        
        if not CAMOUFOX_AVAILABLE:
            await msg.edit_text("❌ Camoufox не установлен")
            return
        
        if browser_instance is None:
            await msg.edit_text("❌ Браузер не запущен. Используйте /status")
            return
        
        if isinstance(browser_instance, bool):
            await msg.edit_text(f"❌ Ошибка: browser_instance = {browser_instance}")
            return
        
        # Используем сохранённый браузер
        page = await browser_instance.new_page()
        await page.goto("https://example.com", wait_until="networkidle")
        screenshot_bytes = await page.screenshot()
        await page.close()
        
        await update.message.reply_photo(photo=screenshot_bytes, caption="📸 Скриншот через Camoufox")
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = (
        f"📦 **Статус системы**\n\n"
        f"🦊 Camoufox: {'✅ Доступен' if CAMOUFOX_AVAILABLE else '❌ Не установлен'}\n"
        f"🔧 Harness: {'✅ Готов' if harness_ready else '❌ Не готов'}\n"
        f"🧠 DSPy: {'✅ Активен' if dspy_agent_instance else '❌ Отключен'}\n"
        f"🌐 Браузер: {'✅ Запущен' if browser_instance and not isinstance(browser_instance, bool) else '❌ Не запущен'}\n"
    )
    if browser_instance:
        status_text += f"📌 Тип: {type(browser_instance).__name__}"
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Примеры:\n"
            "`/dspy открой google.com и покажи заголовок`\n"
            "`/dspy найди все ссылки на python.org`\n"
            "`/dspy сделай скриншот`",
            parse_mode='Markdown'
        )
        return
    
    if not dspy_agent_instance:
        await update.message.reply_text("❌ DSPy не инициализирован. Проверьте AGNES_API_KEY")
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, run_agent, query)
        
        if len(answer) > 4000:
            answer = answer[:4000] + "..."
        
        await msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 11. ЗАКРЫТИЕ БРАУЗЕРА
# ============================================================

async def close_browser():
    global browser_instance
    if browser_instance and not isinstance(browser_instance, bool):
        try:
            await browser_instance.close()
            logger.info("✅ Браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии браузера: {e}")

# ============================================================
# 12. ЗАПУСК
# ============================================================

async def main():
    global browser_instance
    
    logger.info("🚀 Инициализация...")
    
    # Запускаем Camoufox
    await init_browser_and_harness()
    
    # Инициализируем DSPy
    init_dspy()
    
    # Создаём бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🦊 Camoufox: {'✅' if CAMOUFOX_AVAILABLE else '❌'}")
    logger.info(f"🔧 Harness: {'✅' if harness_ready else '❌'}")
    logger.info(f"🧠 DSPy: {'✅' if dspy_agent_instance else '❌'}")
    logger.info(f"🌐 Браузер: {'✅' if browser_instance and not isinstance(browser_instance, bool) else '❌'}")
    if browser_instance:
        logger.info(f"📌 Тип browser_instance: {type(browser_instance)}")
    logger.info("📋 Команды: /start, /check, /screenshot, /status, /dspy")
    
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Обработка сигналов
        stop_signal = asyncio.Event()
        
        def signal_handler():
            stop_signal.set()
        
        if hasattr(asyncio, 'add_signal_handler'):
            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(signal.SIGINT, signal_handler)
                loop.add_signal_handler(signal.SIGTERM, signal_handler)
            except NotImplementedError:
                pass
        
        while not stop_signal.is_set():
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в основном цикле: {e}")
    finally:
        logger.info("🛑 Останавливаем бота...")
        await close_browser()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())