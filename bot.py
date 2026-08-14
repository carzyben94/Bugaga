import os
import asyncio
import logging
import time
import signal

import httpx

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool


# ============================================================
# 1. ЛОГГЕР
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# 2. CAMOUFOX
# ============================================================

try:
    from camoufox.async_api import AsyncCamoufox

    CAMOUFOX_AVAILABLE = True
    logger.info("✅ Camoufox загружен")

except ImportError as e:
    CAMOUFOX_AVAILABLE = False
    logger.error(f"❌ Camoufox не найден: {e}")


# ============================================================
# 3. НАСТРОЙКИ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

SCREENSHOTS_DIR = "/app/screenshots"
CAMOUFOX_PROFILE = "/app/camoufox-profile"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(CAMOUFOX_PROFILE, exist_ok=True)


# ============================================================
# 4. ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# ============================================================

# ВАЖНО:
# camoufox_manager = объект AsyncCamoufox
# camoufox_context = BrowserContext, который возвращает __aenter__()

camoufox_manager = None
camoufox_context = None

browser_ready = False

browser_lock = asyncio.Lock()

dspy_agent_instance = None


# ============================================================
# 5. CAMOUFOX
# ============================================================

async def init_browser():

    global camoufox_manager
    global camoufox_context
    global browser_ready

    if not CAMOUFOX_AVAILABLE:
        logger.error("❌ Camoufox недоступен")
        return False

    logger.info("🚀 Запускаем Camoufox...")

    try:

        # ----------------------------------------------------
        # Создаём manager
        # ----------------------------------------------------

        camoufox_manager = AsyncCamoufox(
            headless=True,
            persistent_context=True,
            user_data_dir=CAMOUFOX_PROFILE,
        )

        # ----------------------------------------------------
        # Получаем настоящий BrowserContext
        # ----------------------------------------------------

        camoufox_context = (
            await camoufox_manager.__aenter__()
        )

        if camoufox_context is None:
            raise RuntimeError(
                "Camoufox вернул None"
            )

        logger.info(
            f"✅ Camoufox запущен: "
            f"{type(camoufox_context).__name__}"
        )

        # ----------------------------------------------------
        # Тестовая страница
        # ----------------------------------------------------

        logger.info("🔍 Проверяем браузер...")

        page = await camoufox_context.new_page()

        try:

            await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            title = await page.title()

            logger.info(
                f"✅ Браузер работает. "
                f"Title: {title}"
            )

        finally:

            await page.close()

        browser_ready = True

        logger.info("🦊 Camoufox: ✅")
        logger.info(
            f"📁 Profile: {CAMOUFOX_PROFILE}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка запуска Camoufox: {e}"
        )

        browser_ready = False

        # Если запуск частично состоялся —
        # корректно закрываем manager

        if camoufox_manager is not None:

            try:

                await camoufox_manager.__aexit__(
                    None,
                    None,
                    None,
                )

            except Exception:

                pass

        camoufox_manager = None
        camoufox_context = None

        return False


# ============================================================
# 6. ПОЛУЧЕНИЕ НОВОЙ СТРАНИЦЫ
# ============================================================

async def new_page():

    if (
        not browser_ready
        or camoufox_context is None
    ):

        raise RuntimeError(
            "Camoufox не запущен"
        )

    return await camoufox_context.new_page()


# ============================================================
# 7. ЗАКРЫТИЕ БРАУЗЕРА
# ============================================================

async def close_browser():

    global camoufox_manager
    global camoufox_context
    global browser_ready

    if camoufox_manager is None:
        return

    try:

        logger.info(
            "🛑 Закрываем Camoufox..."
        )

        await camoufox_manager.__aexit__(
            None,
            None,
            None,
        )

        logger.info(
            "✅ Camoufox закрыт"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ Ошибка закрытия Camoufox: {e}"
        )

    finally:

        camoufox_manager = None
        camoufox_context = None
        browser_ready = False


# ============================================================
# 8. AGNES LM
# ============================================================

class AgnesLM(dspy.LM):

    def __init__(
        self,
        model="agnes-2.0-flash",
        api_key=None,
        **kwargs,
    ):

        self.api_key = (
            api_key
            or os.environ.get("AGNES_API_KEY")
        )

        self.model = model

        super().__init__(
            model=model,
            model_type="chat",
            temperature=kwargs.get(
                "temperature",
                0.3,
            ),
            max_tokens=kwargs.get(
                "max_tokens",
                2000,
            ),
            cache=False,
        )

        self.provider = "agnes-ai"
        self.forward_contract = "legacy"

    def forward(
        self,
        prompt=None,
        messages=None,
        **kwargs,
    ):

        if not self.api_key:

            return [
                "Ошибка: AGNES_API_KEY не задан"
            ]

        params = {
            **self.kwargs,
            **kwargs,
        }

        api_messages = (
            messages
            or [
                {
                    "role": "user",
                    "content": prompt or "",
                }
            ]
        )

        headers = {
            "Authorization":
                f"Bearer {self.api_key}",

            "Content-Type":
                "application/json",
        }

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature":
                params.get("temperature", 0.3),
            "max_tokens":
                params.get("max_tokens", 2000),
        }

        try:

            with httpx.Client(
                timeout=60.0
            ) as client:

                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                if (
                    "choices" in data
                    and data["choices"]
                ):

                    return [
                        data["choices"][0]
                        ["message"]
                        ["content"]
                    ]

                return [
                    "Ошибка: пустой ответ"
                ]

        except Exception as e:

            logger.error(
                f"❌ Agnes API: {e}"
            )

            return [
                f"Ошибка: {e}"
            ]

    def __call__(
        self,
        prompt=None,
        messages=None,
        **kwargs,
    ):

        return self.forward(
            prompt=prompt,
            messages=messages,
            **kwargs,
        )


# ============================================================
# 9. DSPy SIGNATURE
# ============================================================

class BrowserTask(Signature):

    """
    Агент управляет Camoufox напрямую.

    Инструменты:

    - goto_url
    - page_info
    - get_text
    - get_links
    - screenshot
    - javascript
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Результат выполнения задачи"
    )


# ============================================================
# 10. BROWSER OPERATIONS
# ============================================================

async def browser_goto(url: str) -> str:

    async with browser_lock:

        page = await new_page()

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            title = await page.title()

            return (
                f"✅ Открыта страница\n"
                f"URL: {page.url}\n"
                f"Title: {title}"
            )

        finally:

            await page.close()


async def browser_page_info() -> str:

    async with browser_lock:

        page = await new_page()

        try:

            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        finally:

            await page.close()


async def browser_get_text() -> str:

    async with browser_lock:

        page = await new_page()

        try:

            text = await page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            if not text:
                return "❌ Текст не найден"

            return text[:10000]

        finally:

            await page.close()


async def browser_get_links() -> str:

    async with browser_lock:

        page = await new_page()

        try:

            links = await page.locator(
                "a"
            ).evaluate_all(
                """
                elements =>
                    elements
                    .map(el => el.href)
                    .filter(Boolean)
                """
            )

            if not links:
                return "❌ Ссылок не найдено"

            links = links[:50]

            return (
                f"Ссылки ({len(links)}):\n"
                + "\n".join(
                    str(x)
                    for x in links
                )
            )

        finally:

            await page.close()


async def browser_screenshot() -> str:

    async with browser_lock:

        page = await new_page()

        try:

            await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            filename = (
                f"screenshot_"
                f"{int(time.time())}.png"
            )

            path = os.path.join(
                SCREENSHOTS_DIR,
                filename,
            )

            await page.screenshot(
                path=path,
                full_page=True,
            )

            return path

        finally:

            await page.close()


async def browser_js(expression: str) -> str:

    async with browser_lock:

        page = await new_page()

        try:

            result = await page.evaluate(
                expression
            )

            return str(result)

        finally:

            await page.close()


# ============================================================
# 11. DSPy TOOLS
# ============================================================

def create_browser_tools():

    tools = []

    # --------------------------------------------------------
    # GOTO
    # --------------------------------------------------------

    def tool_goto_url(url: str) -> str:

        return asyncio.run(
            browser_goto(url)
        )

    tools.append(
        Tool(tool_goto_url)
    )

    # --------------------------------------------------------
    # PAGE INFO
    # --------------------------------------------------------

    def tool_page_info() -> str:

        return asyncio.run(
            browser_page_info()
        )

    tools.append(
        Tool(tool_page_info)
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    def tool_get_text() -> str:

        return asyncio.run(
            browser_get_text()
        )

    tools.append(
        Tool(tool_get_text)
    )

    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    def tool_get_links() -> str:

        return asyncio.run(
            browser_get_links()
        )

    tools.append(
        Tool(tool_get_links)
    )

    # --------------------------------------------------------
    # SCREENSHOT
    # --------------------------------------------------------

    def tool_screenshot() -> str:

        return asyncio.run(
            browser_screenshot()
        )

    tools.append(
        Tool(tool_screenshot)
    )

    # --------------------------------------------------------
    # JAVASCRIPT
    # --------------------------------------------------------

    def tool_js(
        expression: str
    ) -> str:

        return asyncio.run(
            browser_js(expression)
        )

    tools.append(
        Tool(tool_js)
    )

    return tools


# ============================================================
# 12. DSPy
# ============================================================

def init_dspy():

    global dspy_agent_instance

    if not AGNES_API_KEY:

        logger.warning(
            "⚠️ AGNES_API_KEY не задан"
        )

        return False

    try:

        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000,
        )

        settings.configure(
            lm=lm
        )

        tools = create_browser_tools()

        dspy_agent_instance = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )

        logger.info(
            f"✅ DSPy агент создан "
            f"с {len(tools)} инструментами"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка DSPy: {e}"
        )

        return False


# ============================================================
# 13. RUN DSPy
# ============================================================

def run_agent(
    question: str
) -> str:

    if not dspy_agent_instance:

        return (
            "❌ DSPy агент "
            "не инициализирован"
        )

    try:

        result = (
            dspy_agent_instance(
                question=question
            )
        )

        answer = getattr(
            result,
            "answer",
            str(result),
        )

        if not answer:

            return "❌ Пустой ответ"

        return answer

    except Exception as e:

        logger.exception(
            "❌ DSPy ошибка"
        )

        return f"❌ Ошибка: {e}"


# ============================================================
# 14. /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + DSPy\n\n"
        "Команды:\n"
        "/check <url> — открыть сайт\n"
        "/dspy <запрос> — AI агент\n"
        "/status — статус\n"
        "/screenshot — скриншот"
    )


# ============================================================
# 15. /CHECK
# ============================================================

async def check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "❌ Укажи URL:\n"
            "/check https://example.com"
        )

        return

    url = context.args[0]

    msg = await update.message.reply_text(
        "⏳ Открываю..."
    )

    if not browser_ready:

        await msg.edit_text(
            "❌ Camoufox не запущен"
        )

        return

    try:

        async with browser_lock:

            page = await new_page()

            try:

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                title = await page.title()

                text = await page.locator(
                    "body"
                ).inner_text(
                    timeout=10000
                )

                text = text[:1500]

            finally:

                await page.close()

        await msg.edit_text(
            f"✅ {title}\n\n{text}"
        )

    except Exception as e:

        logger.exception(
            "❌ /check"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# 16. /SCREENSHOT
# ============================================================

async def screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )

    if not browser_ready:

        await msg.edit_text(
            "❌ Camoufox не запущен"
        )

        return

    try:

        path = await browser_screenshot()

        with open(path, "rb") as photo:

            await update.message.reply_photo(
                photo=photo,
                caption="📸 Camoufox",
            )

        await msg.delete()

    except Exception as e:

        logger.exception(
            "❌ /screenshot"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# 17. /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    status_text = (
        "📦 *Статус системы*\n\n"

        f"🦊 Camoufox: "
        f"{'✅' if CAMOUFOX_AVAILABLE else '❌'}\n"

        f"🌐 Браузер: "
        f"{'✅' if browser_ready else '❌'}\n"

        f"🧠 DSPy: "
        f"{'✅' if dspy_agent_instance else '❌'}\n"

        f"📁 Profile: `{CAMOUFOX_PROFILE}`"
    )

    await update.message.reply_text(
        status_text,
        parse_mode="Markdown",
    )


# ============================================================
# 18. /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "🧠 *DSPy Agent*\n\n"

            "Примеры:\n"

            "`/dspy открой https://example.com "
            "и покажи заголовок`\n\n"

            "`/dspy найди все ссылки "
            "на python.org`\n\n"

            "`/dspy сделай скриншот`",

            parse_mode="Markdown",
        )

        return

    if not dspy_agent_instance:

        await update.message.reply_text(
            "❌ DSPy не инициализирован"
        )

        return

    if not browser_ready:

        await update.message.reply_text(
            "❌ Camoufox не запущен"
        )

        return

    query = " ".join(
        context.args
    )

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

            answer = (
                answer[:4000]
                + "..."
            )

        safe_answer = escape_markdown(
            answer,
            version=2,
        )

        await msg.edit_text(
            "✅ *Результат:*\n\n"
            + safe_answer,
            parse_mode="MarkdownV2",
        )

    except Exception as e:

        logger.exception(
            "❌ DSPy command"
        )

        await msg.edit_text(
            f"❌ Ошибка: {str(e)[:500]}"
        )


# ============================================================
# 19. MAIN
# ============================================================

async def main():

    logger.info(
        "🚀 Инициализация..."
    )

    # --------------------------------------------------------
    # Camoufox
    # --------------------------------------------------------

    browser_ok = await init_browser()

    # --------------------------------------------------------
    # DSPy
    # --------------------------------------------------------

    dspy_ok = init_dspy()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    app = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "check",
            check,
        )
    )

    app.add_handler(
        CommandHandler(
            "screenshot",
            screenshot,
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status,
        )
    )

    app.add_handler(
        CommandHandler(
            "dspy",
            dspy_command,
        )
    )

    logger.info(
        "🚀 Бот запускается..."
    )

    logger.info(
        f"🦊 Camoufox: "
        f"{'✅' if browser_ok else '❌'}"
    )

    logger.info(
        f"🌐 Browser: "
        f"{'✅' if browser_ready else '❌'}"
    )

    logger.info(
        f"🧠 DSPy: "
        f"{'✅' if dspy_ok else '❌'}"
    )

    try:

        await app.initialize()

        await app.start()

        await app.updater.start_polling()

        logger.info(
            "🤖 Telegram бот запущен!"
        )

        stop_signal = asyncio.Event()

        def signal_handler():

            logger.info(
                "🛑 Получен сигнал остановки"
            )

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

            logger.info(
                "💓 Bot alive"
            )

    except Exception as e:

        logger.exception(
            f"❌ Основной цикл: {e}"
        )

    finally:

        logger.info(
            "🛑 Завершение..."
        )

        try:
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


# ============================================================
# 20. ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )