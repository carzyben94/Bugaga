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


# ============================================================
# 1. LOGGER
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# 2. SETTINGS
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

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
# 3. GLOBAL STATE
# ============================================================

camoufox_manager = None
browser_context = None

browser_ready = False
x_authenticated = False

browser_lock = asyncio.Lock()

dspy_agent_instance = None


# ============================================================
# 4. X COOKIES
# ============================================================

def get_x_cookies():

    cookie_values = {
        "__cuid": os.getenv("X_CUID"),
        "personalization_id": os.getenv(
            "X_PERSONALIZATION_ID"
        ),
        "g_state": os.getenv(
            "X_G_STATE"
        ),
        "lang": "ru",
        "dnt": "1",
        "guest_id": os.getenv(
            "X_GUEST_ID"
        ),
        "twid": os.getenv(
            "X_TWID"
        ),
        "auth_token": os.getenv(
            "X_AUTH_TOKEN"
        ),
        "guest_id_ads": os.getenv(
            "X_GUEST_ID_ADS"
        ),
        "guest_id_marketing": os.getenv(
            "X_GUEST_ID_MARKETING"
        ),
        "ct0": os.getenv(
            "X_CT0"
        ),
        "__cf_bm": os.getenv(
            "X_CF_BM"
        ),
    }

    cookies = []

    for name, value in cookie_values.items():

        if not value:
            continue

        cookie = {
            "name": name,
            "value": value,
            "domain": ".x.com",
            "path": "/",
            "secure": True,
        }

        if name in {
            "auth_token",
            "__cf_bm",
        }:
            cookie["httpOnly"] = True

        cookies.append(cookie)

    return cookies


# ============================================================
# 5. INSTALL X COOKIES
# ============================================================

async def install_x_cookies():

    if browser_context is None:
        raise RuntimeError(
            "BrowserContext не создан"
        )

    cookies = get_x_cookies()

    if not cookies:

        logger.warning(
            "🍪 X cookies не заданы"
        )

        return False

    try:

        await browser_context.add_cookies(
            cookies
        )

        logger.info(
            f"🍪 X cookies установлены: "
            f"{len(cookies)}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка установки X cookies: {e}"
        )

        return False


# ============================================================
# 6. CHECK X AUTH
# ============================================================

async def check_x_auth():

    global x_authenticated

    if browser_context is None:
        return False

    page = None

    try:

        page = await browser_context.new_page()

        await page.goto(
            "https://x.com/home",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await page.wait_for_timeout(3000)

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
                "❌ X: авторизация не подтверждена"
            )

            return False

        cookies = await browser_context.cookies(
            "https://x.com"
        )

        names = {
            cookie["name"]
            for cookie in cookies
        }

        if "auth_token" in names:

            x_authenticated = True

            logger.info(
                "✅ X: auth_token найден"
            )

            return True

        x_authenticated = False

        logger.warning(
            "⚠️ X открыт, но auth_token не найден"
        )

        return False

    except Exception as e:

        x_authenticated = False

        logger.exception(
            f"❌ X auth check: {e}"
        )

        return False

    finally:

        if page:

            try:
                await page.close()
            except Exception:
                pass


# ============================================================
# 7. INIT CAMOUFOX
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

        # ВАЖНО:
        # cookies устанавливаются ДО X
        await install_x_cookies()

        # Проверяем браузер
        page = await browser_context.new_page()

        try:

            await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            logger.info(
                f"🌐 Browser OK: "
                f"{await page.title()}"
            )

        finally:

            await page.close()

        browser_ready = True

        # Проверяем X
        await check_x_auth()

        logger.info(
            "================================"
        )

        logger.info(
            f"🦊 Camoufox: "
            f"{'✅' if browser_ready else '❌'}"
        )

        logger.info(
            f"🐦 X auth: "
            f"{'✅' if x_authenticated else '❌'}"
        )

        logger.info(
            "================================"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка запуска Camoufox: {e}"
        )

        browser_ready = False

        return False


# ============================================================
# 8. NEW PAGE
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
# 9. CLOSE BROWSER
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

        logger.info(
            "✅ Camoufox закрыт"
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
# 10. BROWSER GOTO
# ============================================================

async def browser_goto(
    url: str,
):

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
                "✅ Открыто\n"
                f"URL: {page.url}\n"
                f"Title: {title}"
            )

        finally:

            await page.close()


# ============================================================
# 11. PAGE INFO
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
# 12. GET TEXT
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

            if not text:
                return "Текст не найден"

            return text[:15000]

        finally:

            await page.close()


# ============================================================
# 13. GET LINKS
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

            links = links[:100]

            if not links:
                return "Ссылки не найдены"

            return "\n".join(
                str(link)
                for link in links
            )

        finally:

            await page.close()


# ============================================================
# 14. GET HTML
# ============================================================

async def browser_get_html(
    selector: str = "body",
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
# 15. JAVASCRIPT
# ============================================================

async def browser_js(
    expression: str,
):

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
# 16. SCREENSHOT
# ============================================================

async def browser_screenshot():

    async with browser_lock:

        page = await new_page()

        try:

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


# ============================================================
# 17. ASYNC BRIDGE FOR DSPY
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
# 18. DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):

    question = InputField(
        desc=(
            "Задача пользователя. "
            "Используй браузерные инструменты "
            "для выполнения задачи."
        )
    )

    answer = OutputField(
        desc=(
            "Краткий результат выполнения задачи. "
            "Не возвращай внутренний Prediction."
        )
    )


# ============================================================
# 19. DSPY TOOLS
# ============================================================

def create_browser_tools():

    def tool_goto(
        url: str,
    ):

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
        selector: str = "body",
    ):

        return run_async_from_dspy(
            browser_get_html(selector)
        )

    def tool_js(
        expression: str,
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
# 20. AGNES LM
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
                params.get(
                    "temperature",
                    0.3,
                ),
            "max_tokens":
                params.get(
                    "max_tokens",
                    2000,
                ),
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
                f"Ошибка Agnes: {e}"
            ]


# ============================================================
# 21. INIT DSPY
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
            max_iters=12,
        )

        logger.info(
            f"🧠 DSPy готов: "
            f"{len(tools)} tools"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ DSPy init: {e}"
        )

        return False


# ============================================================
# 22. RUN DSPY
# ============================================================

def run_agent(
    question: str,
):

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

        if answer:
            return str(answer)

        return str(result)

    except Exception as e:

        logger.exception(
            "❌ DSPy ошибка"
        )

        return f"❌ Ошибка: {e}"


# ============================================================
# 23. /START
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
# 24. /CHECK
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

                text = text[:2000]

            finally:

                await page.close()

        await msg.edit_text(
            f"✅ Открыто\n"
            f"URL: {url}\n"
            f"Title: {title}\n\n"
            f"{text}"
        )

    except Exception as e:

        logger.exception(
            "❌ /check"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:1000]}"
        )


# ============================================================
# 25. /STATUS
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
# 26. /SCREENSHOT
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

        logger.exception(
            "❌ /screenshot"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# 27. /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "🧠 Пример:\n\n"
            "/dspy открой https://example.com "
            "и покажи заголовок\n\n"
            "/dspy найди новости про Трампа "
            "на BBC\n\n"
            "/dspy открой мой профиль X"
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
# 28. MAIN
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
                "💓 Bot alive | "
                f"X: "
                f"{'✅' if x_authenticated else '❌'}"
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
# 29. ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )