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
from dspy import (
    Signature,
    InputField,
    OutputField,
    settings,
    ReActV2,
    Tool,
)

from camoufox.async_api import AsyncCamoufox

from cookies import X_COOKIES


# ============================================================
# LOGGER
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


# ============================================================
# SETTINGS
# ============================================================

TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

AGNES_API_KEY = os.environ.get(
    "AGNES_API_KEY"
)

if not TELEGRAM_TOKEN:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN не задан!"
    )


SCREENSHOTS_DIR = "/app/screenshots"
CAMOUFOX_PROFILE = "/app/camoufox-profile"

os.makedirs(
    SCREENSHOTS_DIR,
    exist_ok=True,
)

os.makedirs(
    CAMOUFOX_PROFILE,
    exist_ok=True,
)


# ============================================================
# GLOBAL STATE
# ============================================================

camoufox_manager = None
browser_context = None

browser_ready = False
x_authenticated = False

browser_lock = asyncio.Lock()

dspy_agent_instance = None


# ============================================================
# INSTALL COOKIES
# ============================================================

async def install_x_cookies():

    if browser_context is None:
        raise RuntimeError(
            "BrowserContext не создан"
        )

    if not X_COOKIES:

        logger.warning(
            "🍪 X_COOKIES пустой"
        )

        return False

    try:

        await browser_context.add_cookies(
            X_COOKIES
        )

        logger.info(
            f"🍪 Установлено X cookies: "
            f"{len(X_COOKIES)}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка установки cookies: {e}"
        )

        return False


# ============================================================
# CHECK X AUTH
# ============================================================

async def check_x_auth():

    global x_authenticated

    page = None

    try:

        page = await browser_context.new_page()

        await page.goto(
            "https://x.com/home",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await page.wait_for_timeout(
            3000
        )

        current_url = page.url

        title = await page.title()

        logger.info(
            f"🐦 X URL: {current_url}"
        )

        logger.info(
            f"🐦 X Title: {title}"
        )

        if (
            "/login" in current_url
            or "/i/flow/login" in current_url
            or "/signup" in current_url
        ):

            x_authenticated = False

            logger.warning(
                "❌ X авторизация не подтверждена"
            )

            return False

        cookies = await browser_context.cookies(
            "https://x.com"
        )

        cookie_names = {
            cookie["name"]
            for cookie in cookies
        }

        if "auth_token" in cookie_names:

            x_authenticated = True

            logger.info(
                "✅ X auth_token найден"
            )

            return True

        x_authenticated = False

        logger.warning(
            "⚠️ auth_token отсутствует"
        )

        return False

    except Exception as e:

        x_authenticated = False

        logger.exception(
            f"❌ Проверка X: {e}"
        )

        return False

    finally:

        if page:

            try:
                await page.close()
            except Exception:
                pass


# ============================================================
# INIT CAMOUFOX
# ============================================================

async def init_browser():

    global camoufox_manager
    global browser_context
    global browser_ready

    logger.info(
        "🚀 Запускаем Camoufox..."
    )

    try:

        camoufox_manager = AsyncCamoufox(
            headless=True,
            persistent_context=True,
            user_data_dir=CAMOUFOX_PROFILE,
        )

        browser_context = (
            await camoufox_manager.__aenter__()
        )

        if browser_context is None:

            raise RuntimeError(
                "Camoufox вернул None"
            )

        logger.info(
            "✅ BrowserContext создан"
        )

        # ====================================================
        # COOKIES ПОДГРУЖАЮТСЯ ЗДЕСЬ
        # ====================================================

        await install_x_cookies()

        # ====================================================
        # TEST BROWSER
        # ====================================================

        page = await browser_context.new_page()

        try:

            await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            logger.info(
                "🌐 Browser OK: "
                f"{await page.title()}"
            )

        finally:

            await page.close()

        browser_ready = True

        # ====================================================
        # TEST X
        # ====================================================

        await check_x_auth()

        logger.info(
            "================================"
        )

        logger.info(
            "🦊 Camoufox: "
            f"{'✅' if browser_ready else '❌'}"
        )

        logger.info(
            "🐦 X: "
            f"{'✅' if x_authenticated else '❌'}"
        )

        logger.info(
            "================================"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Camoufox ошибка: {e}"
        )

        browser_ready = False

        return False


# ============================================================
# NEW PAGE
# ============================================================

async def new_page():

    if (
        not browser_ready
        or browser_context is None
    ):

        raise RuntimeError(
            "Camoufox не запущен"
        )

    return await browser_context.new_page()


# ============================================================
# CLOSE BROWSER
# ============================================================

async def close_browser():

    global camoufox_manager
    global browser_context
    global browser_ready
    global x_authenticated

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

    except Exception as e:

        logger.warning(
            f"⚠️ Ошибка закрытия: {e}"
        )

    finally:

        camoufox_manager = None
        browser_context = None
        browser_ready = False
        x_authenticated = False


# ============================================================
# BROWSER GOTO
# ============================================================

async def browser_goto(url):

    async with browser_lock:

        page = await new_page()

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            return (
                "✅ Открыто\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        finally:

            await page.close()


# ============================================================
# PAGE INFO
# ============================================================

async def browser_page_info():

    async with browser_lock:

        page = await new_page()

        try:

            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        finally:

            await page.close()


# ============================================================
# TEXT
# ============================================================

async def browser_get_text():

    async with browser_lock:

        page = await new_page()

        try:

            text = await page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            return text[:15000]

        finally:

            await page.close()


# ============================================================
# LINKS
# ============================================================

async def browser_get_links():

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

            return "\n".join(
                links[:100]
            )

        finally:

            await page.close()


# ============================================================
# HTML
# ============================================================

async def browser_get_html(
    selector="body"
):

    async with browser_lock:

        page = await new_page()

        try:

            html = await page.locator(
                selector
            ).inner_html(
                timeout=10000
            )

            return html[:30000]

        finally:

            await page.close()


# ============================================================
# JAVASCRIPT
# ============================================================

async def browser_js(expression):

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
# SCREENSHOT
# ============================================================

async def browser_screenshot():

    async with browser_lock:

        page = await new_page()

        try:

            filename = (
                "screenshot_"
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


# ============================================================
# DSPY ASYNC BRIDGE
# ============================================================

def run_async_from_dspy(coro):

    loop = asyncio.get_event_loop()

    future = asyncio.run_coroutine_threadsafe(
        coro,
        loop,
    )

    return future.result(
        timeout=90
    )


# ============================================================
# DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc=(
            "Итоговый результат выполнения "
            "задачи"
        )
    )


# ============================================================
# DSPY TOOLS
# ============================================================

def create_browser_tools():

    def tool_goto(url: str):

        return run_async_from_dspy(
            browser_goto(url)
        )

    def tool_page_info():

        return run_async_from_dspy(
            browser_page_info()
        )

    def tool_get_text():

        return run_async_from_dspy(
            browser_get_text()
        )

    def tool_get_links():

        return run_async_from_dspy(
            browser_get_links()
        )

    def tool_get_html(
        selector: str = "body"
    ):

        return run_async_from_dspy(
            browser_get_html(selector)
        )

    def tool_js(
        expression: str
    ):

        return run_async_from_dspy(
            browser_js(expression)
        )

    def tool_screenshot():

        return run_async_from_dspy(
            browser_screenshot()
        )

    return [
        Tool(tool_goto),
        Tool(tool_page_info),
        Tool(tool_get_text),
        Tool(tool_get_links),
        Tool(tool_get_html),
        Tool(tool_js),
        Tool(tool_screenshot),
    ]


# ============================================================
# AGNES
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
            or os.environ.get(
                "AGNES_API_KEY"
            )
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

    def forward(
        self,
        prompt=None,
        messages=None,
        **kwargs,
    ):

        if not self.api_key:

            return [
                "AGNES_API_KEY не задан"
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

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get(
                "temperature",
                0.3,
            ),
            "max_tokens": params.get(
                "max_tokens",
                2000,
            ),
        }

        headers = {
            "Authorization":
                f"Bearer {self.api_key}",
            "Content-Type":
                "application/json",
        }

        try:

            with httpx.Client(
                timeout=60
            ) as client:

                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                return [
                    data["choices"][0]
                    ["message"]
                    ["content"]
                ]

        except Exception as e:

            logger.exception(
                "❌ Agnes API"
            )

            return [
                f"Ошибка: {e}"
            ]


# ============================================================
# INIT DSPY
# ============================================================

def init_dspy():

    global dspy_agent_instance

    if not AGNES_API_KEY:

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

        dspy_agent_instance = ReActV2(
            signature=BrowserTask,
            tools=create_browser_tools(),
            max_iters=12,
        )

        logger.info(
            "🧠 DSPy готов"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ DSPy: {e}"
        )

        return False


# ============================================================
# RUN AGENT
# ============================================================

def run_agent(question):

    if not dspy_agent_instance:

        return (
            "❌ DSPy агент "
            "не инициализирован"
        )

    try:

        result = dspy_agent_instance(
            question=question
        )

        answer = getattr(
            result,
            "answer",
            None,
        )

        return (
            str(answer)
            if answer
            else str(result)
        )

    except Exception as e:

        logger.exception(
            "❌ DSPy ошибка"
        )

        return f"❌ Ошибка: {e}"


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + 🧠 DSPy\n\n"
        "/check <url>\n"
        "/dspy <задача>\n"
        "/status\n"
        "/screenshot"
    )


# ============================================================
# /CHECK
# ============================================================

async def check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "/check https://example.com"
        )

        return

    url = context.args[0]

    msg = await update.message.reply_text(
        "⏳ Открываю..."
    )

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

            finally:

                await page.close()

        await msg.edit_text(
            "✅ Открыто\n\n"
            f"Title: {title}\n\n"
            f"{text[:2000]}"
        )

    except Exception as e:

        logger.exception(
            "❌ /check"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:1000]}"
        )


# ============================================================
# /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "📦 Статус системы\n\n"
        f"🦊 Camoufox: "
        f"{'✅' if browser_ready else '❌'}\n"
        f"🌐 Browser: "
        f"{'✅' if browser_ready else '❌'}\n"
        f"🐦 X авторизация: "
        f"{'✅' if x_authenticated else '❌'}\n"
        f"🧠 DSPy: "
        f"{'✅' if dspy_agent_instance else '❌'}"
    )


# ============================================================
# /SCREENSHOT
# ============================================================

async def screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )

    try:

        path = await browser_screenshot()

        with open(
            path,
            "rb",
        ) as photo:

            await update.message.reply_photo(
                photo=photo,
                caption="📸 Camoufox",
            )

        await msg.delete()

    except Exception as e:

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "Пример:\n\n"
            "/dspy открой https://example.com "
            "и покажи заголовок\n\n"
            "/dspy найди новости про Трампа "
            "на BBC"
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
        "🧠 DSPy управляет Camoufox..."
    )

    try:

        loop = asyncio.get_running_loop()

        answer = await loop.run_in_executor(
            None,
            run_agent,
            query,
        )

        answer = str(answer)

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
            f"❌ Ошибка:\n{str(e)[:1000]}"
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    logger.info(
        "🚀 Инициализация..."
    )

    browser_ok = await init_browser()

    dspy_ok = init_dspy()

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
            "status",
            status,
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
            "dspy",
            dspy_command,
        )
    )

    logger.info(
        f"🦊 Camoufox: "
        f"{'✅' if browser_ok else '❌'}"
    )

    logger.info(
        f"🐦 X: "
        f"{'✅' if x_authenticated else '❌'}"
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

    finally:

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
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )