import os
import asyncio
import logging
import time
import signal
import warnings
from html import escape

import httpx

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError as e:
    CAMOUFOX_AVAILABLE = False
    AsyncCamoufox = None
    print(f"⚠️ Camoufox не найден: {e}")


# ============================================================
# LOGGER
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")


# ============================================================
# SETTINGS
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

SCREENSHOTS_DIR = "/app/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ============================================================
# GLOBALS
# ============================================================

# BrowserContext returned by AsyncCamoufox.__aenter__()
browser_instance = None

# AsyncCamoufox context manager
camoufox_manager = None

# Current page used by DSPy tools
agent_page = None

# Main asyncio loop. DSPy itself is synchronous, so browser
# operations from its worker thread are submitted here.
main_loop = None

dspy_agent_instance = None


# ============================================================
# AGNES LM
# ============================================================

class AgnesLM(dspy.LM):

    def __init__(
        self,
        model="agnes-2.0-flash",
        api_key=None,
        **kwargs,
    ):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model

        super().__init__(
            model=model,
            model_type="chat",
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
            cache=False,
        )

        self.provider = "agnes-ai"
        self.forward_contract = "legacy"

    def forward(self, prompt=None, messages=None, **kwargs):

        if not self.api_key:
            return ["Ошибка: AGNES_API_KEY не задан"]

        params = {**self.kwargs, **kwargs}

        api_messages = messages or [
            {
                "role": "user",
                "content": prompt or "",
            }
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", 0.3),
            "max_tokens": params.get("max_tokens", 2000),
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            choices = data.get("choices", [])

            if choices:
                return [choices[0]["message"]["content"]]

            return ["Ошибка: пустой ответ Agnes API"]

        except Exception as e:
            logger.error("❌ Agnes API: %s", e)
            return [f"Ошибка Agnes API: {e}"]

    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(
            prompt=prompt,
            messages=messages,
            **kwargs,
        )


# ============================================================
# DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с прямым доступом к браузеру Camoufox.

    Доступные инструменты:
    - tool_goto_url(url)
    - tool_page_info()
    - tool_get_text()
    - tool_get_links()
    - tool_screenshot()
    - tool_js(expression)
    """

    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Результат выполнения задачи")


# ============================================================
# ASYNC -> SYNC BRIDGE FOR DSPY
# ============================================================

def run_on_main_loop(coro):
    """
    DSPy выполняется синхронно.
    Его tools могут оказаться в worker thread.
    Эта функция безопасно передаёт async-операцию
    в главный asyncio loop, где живёт Camoufox.
    """
    if main_loop is None:
        raise RuntimeError("Главный asyncio loop не инициализирован")

    if main_loop.is_closed():
        raise RuntimeError("Главный asyncio loop закрыт")

    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=60)


# ============================================================
# CAMOUFOX
# ============================================================

async def init_browser():

    global browser_instance
    global camoufox_manager

    if not CAMOUFOX_AVAILABLE:
        logger.error("❌ Camoufox недоступен")
        return False

    try:
        logger.info("🚀 Запускаем Camoufox...")

        camoufox_manager = AsyncCamoufox(
            headless=True,
            fingerprint=True,
        )

        # AsyncCamoufox = context manager.
        # __aenter__() возвращает BrowserContext.
        browser_instance = await camoufox_manager.__aenter__()

        logger.info(
            "✅ Camoufox запущен: %s",
            type(browser_instance).__name__,
        )

        if not hasattr(browser_instance, "new_page"):
            logger.error(
                "❌ Полученный объект не имеет new_page(): %s",
                type(browser_instance),
            )
            return False

        # Реальная проверка браузера.
        page = None

        try:
            page = await browser_instance.new_page()

            await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            title = await page.title()

            logger.info(
                "✅ Браузер работает. Title: %s",
                title,
            )

        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

        return True

    except Exception as e:
        logger.exception(
            "❌ Ошибка запуска Camoufox: %s",
            e,
        )

        browser_instance = None
        camoufox_manager = None

        return False


# ============================================================
# DSPY BROWSER TOOLS
# ============================================================

def create_browser_tools():

    tools = []

    # --------------------------------------------------------
    # GOTO
    # --------------------------------------------------------

    def tool_goto_url(url: str) -> str:

        async def _goto():
            global agent_page

            if agent_page is not None:
                try:
                    await agent_page.close()
                except Exception:
                    pass

            if not url.startswith(("http://", "https://")):
                target = "https://" + url
            else:
                target = url

            agent_page = await browser_instance.new_page()

            await agent_page.goto(
                target,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            return target

        try:
            if browser_instance is None:
                return "❌ Браузер не запущен"

            target = run_on_main_loop(_goto())

            return f"✅ Открыл {target}"

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_goto_url))

    # --------------------------------------------------------
    # PAGE INFO
    # --------------------------------------------------------

    def tool_page_info() -> str:

        async def _info():
            if agent_page is None:
                return None

            return (
                await agent_page.url,
                await agent_page.title(),
            )

        try:
            result = run_on_main_loop(_info())

            if result is None:
                return "❌ Страница не открыта"

            url, title = result

            return (
                f"URL: {url}\n"
                f"Title: {title}"
            )

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_page_info))

    # --------------------------------------------------------
    # GET TEXT
    # --------------------------------------------------------

    def tool_get_text() -> str:

        async def _text():
            if agent_page is None:
                return None

            return await agent_page.locator(
                "body"
            ).inner_text(timeout=10000)

        try:
            text = run_on_main_loop(_text())

            if not text:
                return "❌ Страница не открыта или текст не найден"

            return text[:10000]

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_get_text))

    # --------------------------------------------------------
    # GET LINKS
    # --------------------------------------------------------

    def tool_get_links() -> str:

        async def _links():
            if agent_page is None:
                return None

            return await agent_page.locator(
                "a"
            ).evaluate_all(
                "(els) => els.map(e => e.href).filter(Boolean)"
            )

        try:
            links = run_on_main_loop(_links())

            if not links:
                return "❌ Страница не открыта или ссылок нет"

            return (
                f"Ссылки ({len(links)}):\n"
                + "\n".join(str(x) for x in links[:50])
            )[:10000]

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_get_links))

    # --------------------------------------------------------
    # SCREENSHOT
    # --------------------------------------------------------

    def tool_screenshot() -> str:

        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        path = os.path.join(SCREENSHOTS_DIR, filename)

        async def _screenshot():
            if agent_page is None:
                return False

            await agent_page.screenshot(
                path=path,
                full_page=True,
            )

            return True

        try:
            ok = run_on_main_loop(_screenshot())

            if not ok:
                return "❌ Страница не открыта"

            return f"✅ Скриншот сохранён: {filename}"

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_screenshot))

    # --------------------------------------------------------
    # JAVASCRIPT
    # --------------------------------------------------------

    def tool_js(expression: str) -> str:

        async def _js():
            if agent_page is None:
                return None

            return await agent_page.evaluate(expression)

        try:
            result = run_on_main_loop(_js())

            if result is None:
                return "❌ Страница не открыта"

            return str(result)

        except Exception as e:
            return f"❌ Ошибка: {e}"

    tools.append(Tool(tool_js))

    return tools


# ============================================================
# DSPY INITIALIZATION
# ============================================================

def init_dspy():

    global dspy_agent_instance

    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return False

    try:
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000,
        )

        settings.configure(lm=lm)

        tools = create_browser_tools()

        dspy_agent_instance = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )

        logger.info(
            "✅ DSPy агент создан с %s инструментами",
            len(tools),
        )

        return True

    except Exception as e:
        logger.exception("❌ Ошибка DSPy: %s", e)
        dspy_agent_instance = None
        return False


# ============================================================
# RUN DSPY
# ============================================================

def run_agent(question: str) -> str:

    if not dspy_agent_instance:
        return "❌ DSPy агент не инициализирован"

    try:
        result = dspy_agent_instance(question=question)

        answer = getattr(
            result,
            "answer",
            str(result),
        )

        if answer and answer.strip():
            return answer

        return "❌ Пустой ответ"

    except Exception as e:
        logger.exception("❌ DSPy error: %s", e)
        return f"❌ Ошибка DSPy: {e}"


# ============================================================
# /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + DSPy\n\n"
        "Команды:\n"
        "/check <url> — открыть сайт\n"
        "/dspy <запрос> — DSPy агент\n"
        "/status — статус системы\n"
        "/screenshot — сделать скриншот"
    )


# ============================================================
# /CHECK
# ============================================================

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "❌ Укажи URL:\n"
            "/check https://example.com"
        )
        return

    url = context.args[0]

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    msg = await update.message.reply_text(
        "⏳ Открываю через Camoufox..."
    )

    global browser_instance

    if not CAMOUFOX_AVAILABLE:
        await msg.edit_text("❌ Camoufox не установлен")
        return

    if browser_instance is None:
        await msg.edit_text("❌ Браузер не запущен. Проверь /status")
        return

    try:
        page = await browser_instance.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await asyncio.sleep(2)

            title = await page.title()

            try:
                text = await page.locator(
                    "body"
                ).inner_text(timeout=10000)
            except Exception:
                text = ""

            if not text:
                text = "Текст страницы не найден."

            result = (
                "✅ <b>Страница открыта</b>\n\n"
                f"🌐 <b>URL:</b> {escape(url)}\n"
                f"📌 <b>Title:</b> {escape(title or 'Без заголовка')}\n\n"
                "<b>Текст:</b>\n"
                f"{escape(text[:3500])}"
            )

            await msg.edit_text(
                result,
                parse_mode="HTML",
            )

        finally:
            try:
                await page.close()
            except Exception:
                pass

    except Exception as e:
        logger.exception("❌ /check error: %s", e)

        await msg.edit_text(
            "❌ <b>Ошибка:</b>\n"
            f"<code>{escape(str(e)[:1500])}</code>",
            parse_mode="HTML",
        )


# ============================================================
# /SCREENSHOT
# ============================================================

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )

    global browser_instance

    if not CAMOUFOX_AVAILABLE:
        await msg.edit_text("❌ Camoufox не установлен")
        return

    if browser_instance is None:
        await msg.edit_text("❌ Браузер не запущен")
        return

    page = None

    try:
        page = await browser_instance.new_page()

        await page.goto(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await asyncio.sleep(1)

        screenshot_bytes = await page.screenshot(
            full_page=True
        )

        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption="📸 Скриншот через Camoufox",
        )

        await msg.delete()

    except Exception as e:
        logger.exception("❌ Screenshot error: %s", e)

        await msg.edit_text(
            "❌ <b>Ошибка:</b>\n"
            f"<code>{escape(str(e)[:1500])}</code>",
            parse_mode="HTML",
        )

    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass


# ============================================================
# /STATUS
# ============================================================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    browser_ok = (
        browser_instance is not None
        and hasattr(browser_instance, "new_page")
    )

    status_text = (
        "📦 <b>Статус системы</b>\n\n"
        f"🦊 Camoufox: {'✅' if CAMOUFOX_AVAILABLE else '❌'}\n"
        f"🌐 Браузер: {'✅' if browser_ok else '❌'}\n"
        f"🧠 DSPy: {'✅' if dspy_agent_instance else '❌'}\n"
        "📁 Profile: /app/camoufox-profile\n"
    )

    if browser_instance is not None:
        status_text += (
            "\n📌 <b>Browser type:</b> "
            f"<code>{type(browser_instance).__name__}</code>"
        )

    await update.message.reply_text(
        status_text,
        parse_mode="HTML",
    )


# ============================================================
# /DSPY
# ============================================================

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "🧠 <b>DSPy Agent</b>\n\n"
            "Примеры:\n\n"
            "<code>/dspy открой google.com и покажи заголовок</code>\n\n"
            "<code>/dspy найди все ссылки на python.org</code>\n\n"
            "<code>/dspy сделай скриншот</code>",
            parse_mode="HTML",
        )
        return

    if not dspy_agent_instance:
        await update.message.reply_text(
            "❌ DSPy не инициализирован.\n"
            "Проверьте AGNES_API_KEY"
        )
        return

    if browser_instance is None:
        await update.message.reply_text(
            "❌ Camoufox не запущен."
        )
        return

    query = " ".join(context.args)

    msg = await update.message.reply_text(
        "🧠 Думаю..."
    )

    try:
        loop = asyncio.get_running_loop()

        answer = await loop.run_in_executor(
            None,
            run_agent,
            query,
        )

        if len(answer) > 4000:
            answer = answer[:4000] + "..."

        safe_answer = escape_markdown(
            answer,
            version=2,
        )

        await msg.edit_text(
            "✅ *Результат:*\n\n" + safe_answer,
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        logger.exception("❌ /dspy error: %s", e)

        await msg.edit_text(
            f"❌ Ошибка: {str(e)[:1000]}"
        )


# ============================================================
# CLOSE CAMOUFOX
# ============================================================

async def close_browser():

    global browser_instance
    global camoufox_manager
    global agent_page

    logger.info("🛑 Закрываем браузер...")

    if agent_page is not None:
        try:
            await agent_page.close()
        except Exception:
            pass

        agent_page = None

    if camoufox_manager is not None:
        try:
            await camoufox_manager.__aexit__(
                None,
                None,
                None,
            )

            logger.info("✅ Camoufox закрыт")

        except Exception as e:
            logger.warning(
                "⚠️ Ошибка закрытия Camoufox: %s",
                e,
            )

    browser_instance = None
    camoufox_manager = None


# ============================================================
# MAIN
# ============================================================

async def main():

    global main_loop

    main_loop = asyncio.get_running_loop()

    logger.info("🚀 Инициализация...")

    # --------------------------------------------------------
    # CAMOUFOX
    # --------------------------------------------------------

    browser_ok = await init_browser()

    # --------------------------------------------------------
    # DSPY
    # --------------------------------------------------------

    dspy_ok = init_dspy()

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    app = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dspy", dspy_command))

    logger.info("🚀 Бот запускается...")
    logger.info(
        "🦊 Camoufox: %s",
        "✅" if CAMOUFOX_AVAILABLE else "❌",
    )
    logger.info(
        "🌐 Browser: %s",
        "✅" if browser_ok else "❌",
    )
    logger.info(
        "🧠 DSPy: %s",
        "✅" if dspy_ok else "❌",
    )

    if browser_instance is not None:
        logger.info(
            "📌 Browser object: %s",
            type(browser_instance).__name__,
        )

    try:
        await app.initialize()
        await app.start()

        await app.updater.start_polling(
            drop_pending_updates=True
        )

        logger.info("🤖 Telegram бот запущен!")

        stop_signal = asyncio.Event()

        def signal_handler():
            logger.info("🛑 Получен сигнал остановки")
            stop_signal.set()

        try:
            loop = asyncio.get_running_loop()

            loop.add_signal_handler(
                signal.SIGINT,
                signal_handler,
            )

            loop.add_signal_handler(
                signal.SIGTERM,
                signal_handler,
            )

        except (
            NotImplementedError,
            RuntimeError,
        ):
            pass

        while not stop_signal.is_set():
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")

    except Exception as e:
        logger.exception(
            "❌ Ошибка основного цикла: %s",
            e,
        )

    finally:
        logger.info("🛑 Останавливаем бота...")

        try:
            if app.updater:
                await app.updater.stop()
        except Exception:
            pass

        try:
            await app.stop()
        except Exception:
            pass

        try:
            await app.shutdown()
        except Exception:
            pass

        await close_browser()

        logger.info("👋 Бот остановлен")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершение...")