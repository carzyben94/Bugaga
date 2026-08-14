import os
import asyncio
import logging
import time
import signal
import warnings
from html import escape

import httpx

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.helpers import escape_markdown


# ============================================================
# 1. LOGGER
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")


# ============================================================
# 2. DSPY
# ============================================================

import dspy

from dspy import (
    Signature,
    InputField,
    OutputField,
    settings,
    ReActV2,
    Tool,
)


# ============================================================
# 3. CAMOUFOX
# ============================================================

try:
    from camoufox.async_api import AsyncCamoufox

    CAMOUFOX_AVAILABLE = True

    logger.info("✅ Camoufox загружен")

except ImportError as e:

    CAMOUFOX_AVAILABLE = False

    logger.warning(
        f"⚠️ Camoufox не найден: {e}"
    )


# ============================================================
# 4. ENV
# ============================================================

TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

if not TELEGRAM_TOKEN:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN не задан!"
    )


AGNES_API_KEY = os.environ.get(
    "AGNES_API_KEY"
)


SCREENSHOTS_DIR = "/app/screenshots"

os.makedirs(
    SCREENSHOTS_DIR,
    exist_ok=True
)


# ============================================================
# 5. GLOBAL BROWSER STATE
# ============================================================

# ВАЖНО:
#
# browser_instance = Browser
#
# НЕ AsyncCamoufox manager.
#
# AsyncCamoufox manager живёт внутри main().
#
browser_instance = None

# Текущая страница.
#
# Это позволяет DSPy использовать одну вкладку
# между несколькими инструментами.
#
current_page = None

# Lock, чтобы два Telegram запроса одновременно
# не ломали одну и ту же страницу.
browser_lock = asyncio.Lock()

# DSPy
dspy_agent_instance = None

# LM
agnes_lm = None


# ============================================================
# 6. AGNES LM
# ============================================================

class AgnesLM(dspy.LM):

    def __init__(
        self,
        model="agnes-2.0-flash",
        api_key=None,
        **kwargs
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
                0.3
            ),
            max_tokens=kwargs.get(
                "max_tokens",
                2000
            ),
            cache=False
        )

        self.provider = "agnes-ai"

        self.forward_contract = "legacy"


    def forward(
        self,
        prompt=None,
        messages=None,
        **kwargs
    ):

        if not self.api_key:

            return [
                "Ошибка: AGNES_API_KEY не задан"
            ]


        params = {
            **self.kwargs,
            **kwargs
        }


        api_messages = (
            messages
            or [
                {
                    "role": "user",
                    "content": prompt or ""
                }
            ]
        )


        headers = {
            "Authorization":
                f"Bearer {self.api_key}",

            "Content-Type":
                "application/json"
        }


        payload = {

            "model":
                self.model,

            "messages":
                api_messages,

            "temperature":
                params.get(
                    "temperature",
                    0.3
                ),

            "max_tokens":
                params.get(
                    "max_tokens",
                    2000
                )
        }


        try:

            with httpx.Client(
                timeout=60.0
            ) as client:

                response = client.post(

                    "https://apihub.agnes-ai.com/v1/chat/completions",

                    headers=headers,

                    json=payload
                )


                response.raise_for_status()

                data = response.json()


                choices = data.get(
                    "choices",
                    []
                )


                if choices:

                    return [
                        choices[0]["message"]["content"]
                    ]


                return [
                    "Ошибка: пустой ответ Agnes API"
                ]


        except Exception as e:

            logger.error(
                f"❌ Agnes API: {e}"
            )

            return [
                f"Ошибка Agnes API: {e}"
            ]


    def __call__(
        self,
        prompt=None,
        messages=None,
        **kwargs
    ):

        return self.forward(
            prompt=prompt,
            messages=messages,
            **kwargs
        )


# ============================================================
# 7. BROWSER HELPERS
# ============================================================

def get_browser():

    global browser_instance

    if browser_instance is None:

        raise RuntimeError(
            "Camoufox не запущен"
        )

    if not hasattr(
        browser_instance,
        "new_page"
    ):

        raise RuntimeError(
            "Объект Camoufox не является Browser: "
            f"{type(browser_instance).__name__}"
        )

    return browser_instance


async def get_current_page():

    global current_page

    if current_page is None:

        browser = get_browser()

        current_page = (
            await browser.new_page()
        )

    return current_page


# ============================================================
# 8. OPEN URL
# ============================================================

async def browser_open(
    url: str
) -> str:

    global current_page

    if not url.startswith(
        ("http://", "https://")
    ):

        url = "https://" + url


    async with browser_lock:

        try:

            browser = get_browser()


            if current_page is not None:

                try:
                    await current_page.close()
                except Exception:
                    pass

                current_page = None


            current_page = (
                await browser.new_page()
            )


            await current_page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=30000
            )


            await asyncio.sleep(1)


            title = await current_page.title()


            return (
                f"✅ Открыта страница\n"
                f"URL: {url}\n"
                f"Title: {title}"
            )


        except Exception as e:

            logger.exception(
                f"❌ browser_open: {e}"
            )

            return (
                f"❌ Ошибка открытия страницы: {e}"
            )


# ============================================================
# 9. PAGE INFO
# ============================================================

async def browser_page_info() -> str:

    async with browser_lock:

        try:

            page = await get_current_page()

            url = page.url

            title = await page.title()


            return (
                f"URL: {url}\n"
                f"Title: {title}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


# ============================================================
# 10. GET PAGE TEXT
# ============================================================

async def browser_get_text() -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            text = await page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )


            if not text:

                return (
                    "❌ Текст страницы не найден"
                )


            return text[:12000]


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


# ============================================================
# 11. GET LINKS
# ============================================================

async def browser_get_links() -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            links = await page.locator(
                "a"
            ).evaluate_all(
                """
                elements => elements
                    .map(el => el.href)
                    .filter(Boolean)
                """
            )


            links = [
                str(x)
                for x in links
                if x
            ]


            if not links:

                return (
                    "❌ Ссылок не найдено"
                )


            result = (
                f"Ссылки ({len(links)}):\n"
            )


            result += "\n".join(
                links[:100]
            )


            return result[:12000]


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


# ============================================================
# 12. JAVASCRIPT
# ============================================================

async def browser_js(
    expression: str
) -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            result = await page.evaluate(
                expression
            )


            return str(result)


        except Exception as e:

            return (
                f"❌ Ошибка JavaScript: {e}"
            )


# ============================================================
# 13. SCREENSHOT
# ============================================================

async def browser_screenshot() -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            timestamp = int(
                time.time()
            )


            filename = (
                f"screenshot_{timestamp}.png"
            )


            full_path = os.path.join(
                SCREENSHOTS_DIR,
                filename
            )


            await page.screenshot(
                path=full_path,
                full_page=True
            )


            return (
                f"✅ Скриншот сохранён: "
                f"{filename}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


# ============================================================
# 14. CLICK
# ============================================================

async def browser_click(
    selector: str
) -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            await page.locator(
                selector
            ).click(
                timeout=10000
            )


            await asyncio.sleep(1)


            return (
                f"✅ Нажат элемент: {selector}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка клика: {e}"
            )


# ============================================================
# 15. TYPE
# ============================================================

async def browser_type(
    selector: str,
    text: str
) -> str:

    async with browser_lock:

        try:

            page = await get_current_page()


            await page.locator(
                selector
            ).fill(
                text,
                timeout=10000
            )


            return (
                f"✅ Введён текст в {selector}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка ввода: {e}"
            )


# ============================================================
# 16. DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):

    """
    Ты автономный браузерный AI-агент.

    Ты управляешь браузером Camoufox напрямую.

    Доступные инструменты:

    browser_open(url)
    browser_page_info()
    browser_get_text()
    browser_get_links()
    browser_js(expression)
    browser_screenshot()
    browser_click(selector)
    browser_type(selector, text)

    Сначала используй инструменты для получения
    реальных данных страницы.

    Не выдумывай содержимое страницы.

    Если пользователь просит открыть сайт —
    используй browser_open.

    Если пользователь просит прочитать страницу —
    используй browser_get_text.

    Если пользователь просит ссылки —
    используй browser_get_links.

    Если нужно взаимодействовать со страницей —
    используй browser_click или browser_type.

    В конце дай короткий понятный ответ пользователю.
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Результат выполнения задачи"
    )


# ============================================================
# 17. DSPY TOOLS
# ============================================================

def create_dspy_tools():

    return [

        Tool(
            browser_open
        ),

        Tool(
            browser_page_info
        ),

        Tool(
            browser_get_text
        ),

        Tool(
            browser_get_links
        ),

        Tool(
            browser_js
        ),

        Tool(
            browser_screenshot
        ),

        Tool(
            browser_click
        ),

        Tool(
            browser_type
        ),
    ]


# ============================================================
# 18. INIT DSPY
# ============================================================

def init_dspy():

    global dspy_agent_instance
    global agnes_lm


    if not AGNES_API_KEY:

        logger.warning(
            "⚠️ AGNES_API_KEY не задан"
        )

        return False


    try:

        agnes_lm = AgnesLM(

            api_key=AGNES_API_KEY,

            temperature=0.3,

            max_tokens=2000
        )


        settings.configure(
            lm=agnes_lm
        )


        tools = create_dspy_tools()


        dspy_agent_instance = ReActV2(

            signature=BrowserTask,

            tools=tools,

            max_iters=10
        )


        logger.info(
            "✅ DSPy агент создан: %d tools",
            len(tools)
        )


        return True


    except Exception as e:

        logger.exception(
            f"❌ Ошибка DSPy: {e}"
        )

        dspy_agent_instance = None

        return False


# ============================================================
# 19. RUN DSPY
# ============================================================

def run_agent(
    question: str
) -> str:

    if not dspy_agent_instance:

        return (
            "❌ DSPy агент не инициализирован"
        )


    try:

        # DSPy Tool'ы async.
        #
        # ReActV2 умеет работать с инструментами,
        # а здесь запускаем агент в текущем execution context.
        #

        result = dspy_agent_instance(
            question=question
        )


        answer = getattr(
            result,
            "answer",
            str(result)
        )


        if answer and answer.strip():

            return answer


        return (
            "❌ Пустой ответ"
        )


    except Exception as e:

        logger.exception(
            f"❌ DSPy error: {e}"
        )

        return (
            f"❌ Ошибка DSPy: {e}"
        )


# ============================================================
# 20. /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "👋 Привет!\n\n"

        "🦊 Camoufox + 🧠 DSPy\n\n"

        "Browser Harness полностью удалён.\n\n"

        "Команды:\n"

        "/check <url> — открыть сайт\n"

        "/dspy <запрос> — AI браузерный агент\n"

        "/status — статус системы\n"

        "/screenshot — скриншот текущей страницы"

    )


# ============================================================
# 21. /CHECK
# ============================================================

async def check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(

            "❌ Укажи URL:\n"
            "/check https://example.com"

        )

        return


    url = context.args[0]


    if not url.startswith(
        ("http://", "https://")
    ):

        url = "https://" + url


    msg = await update.message.reply_text(
        "⏳ Открываю через Camoufox..."
    )


    try:

        global current_page


        if not CAMOUFOX_AVAILABLE:

            await msg.edit_text(
                "❌ Camoufox не установлен"
            )

            return


        if browser_instance is None:

            await msg.edit_text(
                "❌ Camoufox не запущен"
            )

            return


        async with browser_lock:

            if current_page is not None:

                try:
                    await current_page.close()
                except Exception:
                    pass

                current_page = None


            current_page = (
                await browser_instance.new_page()
            )


            await current_page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=30000
            )


            await asyncio.sleep(2)


            title = await current_page.title()


            try:

                text = await current_page.locator(
                    "body"
                ).inner_text(
                    timeout=10000
                )

            except Exception:

                text = ""


            if not text:

                text = (
                    "Текст страницы не найден."
                )


            text = text[:3500]


            result = (

                "✅ <b>Страница открыта</b>\n\n"

                f"🌐 <b>URL:</b> "
                f"{escape(url)}\n"

                f"📌 <b>Title:</b> "
                f"{escape(title or 'Без заголовка')}\n\n"

                "<b>Текст:</b>\n"

                f"{escape(text)}"

            )


        await msg.edit_text(

            result,

            parse_mode="HTML"

        )


    except Exception as e:

        logger.exception(
            f"❌ /check error: {e}"
        )


        await msg.edit_text(

            "❌ <b>Ошибка:</b>\n"
            f"<code>{escape(str(e)[:1500])}</code>",

            parse_mode="HTML"

        )


# ============================================================
# 22. /SCREENSHOT
# ============================================================

async def screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )


    try:

        global current_page


        if browser_instance is None:

            await msg.edit_text(
                "❌ Camoufox не запущен"
            )

            return


        async with browser_lock:

            if current_page is None:

                current_page = (
                    await browser_instance.new_page()
                )

                await current_page.goto(
                    "https://example.com",
                    wait_until="domcontentloaded",
                    timeout=30000
                )


            screenshot_bytes = (
                await current_page.screenshot(
                    full_page=True
                )
            )


        await update.message.reply_photo(

            photo=screenshot_bytes,

            caption=(
                "📸 Скриншот через Camoufox"
            )

        )


        try:
            await msg.delete()
        except Exception:
            pass


    except Exception as e:

        logger.exception(
            f"❌ Screenshot error: {e}"
        )


        await msg.edit_text(

            "❌ <b>Ошибка:</b>\n"
            f"<code>{escape(str(e)[:1500])}</code>",

            parse_mode="HTML"

        )


# ============================================================
# 23. /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    browser_ok = (

        browser_instance is not None

        and hasattr(
            browser_instance,
            "new_page"
        )

    )


    status_text = (

        "📦 <b>Статус системы</b>\n\n"

        f"🦊 Camoufox: "
        f"{'✅' if CAMOUFOX_AVAILABLE else '❌'}\n"

        f"🌐 Browser: "
        f"{'✅' if browser_ok else '❌'}\n"

        f"🧠 DSPy: "
        f"{'✅' if dspy_agent_instance else '❌'}\n"

        "🔧 Harness: ❌ УДАЛЁН\n"

        "📁 Profile: "
        "/app/camoufox-profile\n"

    )


    if browser_instance is not None:

        status_text += (

            "\n📌 <b>Browser object:</b> "

            f"<code>"
            f"{type(browser_instance).__name__}"
            f"</code>"

        )


    if current_page is not None:

        status_text += (

            "\n📄 <b>Current page:</b> "

            f"<code>"
            f"{escape(current_page.url)}"
            f"</code>"

        )


    await update.message.reply_text(

        status_text,

        parse_mode="HTML"

    )


# ============================================================
# 24. /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(

            "🧠 <b>DSPy Browser Agent</b>\n\n"

            "Примеры:\n\n"

            "<code>/dspy "
            "открой example.com "
            "и покажи заголовок</code>\n\n"

            "<code>/dspy "
            "открой python.org "
            "и найди все ссылки</code>\n\n"

            "<code>/dspy "
            "открой google.com "
            "и получи текст страницы</code>",

            parse_mode="HTML"

        )

        return


    if not dspy_agent_instance:

        await update.message.reply_text(

            "❌ DSPy не инициализирован.\n"
            "Проверь AGNES_API_KEY"

        )

        return


    query = " ".join(
        context.args
    )


    msg = await update.message.reply_text(
        "🧠 Думаю..."
    )


    try:

        # DSPy может выполнять синхронный вызов,
        # поэтому выносим сам LM/agent execution
        # из Telegram event loop.
        #
        # ВАЖНО:
        # браузерные async Tool'ы должны выполняться
        # через DSPy async execution в актуальной версии.
        #

        loop = asyncio.get_running_loop()


        answer = await loop.run_in_executor(

            None,

            run_agent,

            query

        )


        if len(answer) > 4000:

            answer = (
                answer[:4000]
                + "..."
            )


        safe_answer = escape_markdown(

            answer,

            version=2

        )


        await msg.edit_text(

            "✅ *Результат:*\n\n"
            + safe_answer,

            parse_mode="MarkdownV2"

        )


    except Exception as e:

        logger.exception(
            f"❌ /dspy error: {e}"
        )


        await msg.edit_text(

            "❌ Ошибка: "
            f"{str(e)[:1000]}"

        )


# ============================================================
# 25. CLOSE CURRENT PAGE
# ============================================================

async def close_current_page():

    global current_page

    if current_page is not None:

        try:

            await current_page.close()

        except Exception:
            pass

        current_page = None


# ============================================================
# 26. MAIN
# ============================================================

async def main():

    global browser_instance


    logger.info(
        "🚀 Инициализация..."
    )


    if not CAMOUFOX_AVAILABLE:

        raise RuntimeError(
            "Camoufox недоступен"
        )


    # --------------------------------------------------------
    # CAMOUFOX
    # --------------------------------------------------------

    logger.info(
        "🚀 Запускаем Camoufox..."
    )


    # ========================================================
    # ВАЖНО
    #
    # AsyncCamoufox — context manager.
    #
    # Внутри `async with` переменная browser
    # является Browser.
    #
    # Именно этот объект имеет new_page().
    # ========================================================

    async with AsyncCamoufox(

        headless=True,

        fingerprint=True,

    ) as browser:

        browser_instance = browser


        logger.info(
            "✅ Camoufox запущен"
        )


        logger.info(
            "📌 Browser type: %s",
            type(browser_instance).__name__
        )


        logger.info(
            "📌 Browser has new_page: %s",
            hasattr(
                browser_instance,
                "new_page"
            )
        )


        if not hasattr(
            browser_instance,
            "new_page"
        ):

            raise RuntimeError(
                "Camoufox вернул объект "
                "без new_page(): "
                f"{type(browser_instance).__name__}"
            )


        # ----------------------------------------------------
        # TEST PAGE
        # ----------------------------------------------------

        logger.info(
            "🔍 Проверяем Camoufox..."
        )


        test_page = None


        try:

            test_page = (
                await browser_instance.new_page()
            )


            await test_page.goto(

                "https://example.com",

                wait_until="domcontentloaded",

                timeout=30000
            )


            title = await test_page.title()


            logger.info(
                "✅ Camoufox работает: %s",
                title
            )


        finally:

            if test_page is not None:

                try:
                    await test_page.close()
                except Exception:
                    pass


        # ----------------------------------------------------
        # DSPY
        # ----------------------------------------------------

        dspy_ok = init_dspy()


        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        app = (
            Application
            .builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )


        app.add_handler(
            CommandHandler(
                "start",
                start
            )
        )


        app.add_handler(
            CommandHandler(
                "check",
                check
            )
        )


        app.add_handler(
            CommandHandler(
                "screenshot",
                screenshot
            )
        )


        app.add_handler(
            CommandHandler(
                "status",
                status
            )
        )


        app.add_handler(
            CommandHandler(
                "dspy",
                dspy_command
            )
        )


        logger.info(
            "🚀 Telegram запускается..."
        )


        logger.info(
            f"🦊 Camoufox: "
            f"{'✅' if CAMOUFOX_AVAILABLE else '❌'}"
        )


        logger.info(
            f"🌐 Browser: "
            f"{'✅' if browser_instance else '❌'}"
        )


        logger.info(
            f"🧠 DSPy: "
            f"{'✅' if dspy_ok else '❌'}"
        )


        logger.info(
            "🔧 Browser Harness: ❌ НЕТ"
        )


        # ----------------------------------------------------
        # START TELEGRAM
        # ----------------------------------------------------

        try:

            await app.initialize()

            await app.start()

            await app.updater.start_polling(
                drop_pending_updates=True
            )


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
                    signal_handler
                )


                loop.add_signal_handler(
                    signal.SIGTERM,
                    signal_handler
                )


            except (
                NotImplementedError,
                RuntimeError
            ):

                pass


            # ------------------------------------------------
            # MAIN LOOP
            # ------------------------------------------------

            while not stop_signal.is_set():

                await asyncio.sleep(60)

                logger.info(
                    "💓 Bot alive"
                )


        except Exception as e:

            logger.exception(
                f"❌ Ошибка Telegram: {e}"
            )


        finally:

            logger.info(
                "🛑 Останавливаем Telegram..."
            )


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


            # ------------------------------------------------
            # CLOSE PAGE
            # ------------------------------------------------

            await close_current_page()


            browser_instance = None


            logger.info(
                "👋 Telegram остановлен"
            )


    # ========================================================
    # AsyncCamoufox автоматически закрылся здесь
    # ========================================================

    logger.info(
        "🦊 Camoufox закрыт"
    )


# ============================================================
# 27. ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "👋 Завершение..."
        )