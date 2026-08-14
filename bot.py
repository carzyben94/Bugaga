import os
import asyncio
import logging
import time
import signal
import warnings
import httpx

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.helpers import escape_markdown


# ============================================================
# 1. ЛОГГЕР
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
# 4. НАСТРОЙКИ
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
# 5. ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# ============================================================

# ВАЖНО:
#
# AsyncCamoufox = менеджер контекста
#
# browser_instance = BrowserContext
#
# Именно BrowserContext имеет new_page().
#

browser_instance = None

camoufox_manager = None

dspy_agent_instance = None


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


                if (
                    "choices" in data
                    and len(data["choices"]) > 0
                ):

                    return [
                        data["choices"][0]["message"]["content"]
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
# 7. DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):

    """
    Ты агент с доступом к браузеру Camoufox.

    Доступные инструменты:

    tool_goto_url(url)
    tool_page_info()
    tool_get_text()
    tool_get_links()
    tool_screenshot()
    tool_js(expression)
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Результат выполнения задачи"
    )


# ============================================================
# 8. ИНИЦИАЛИЗАЦИЯ CAMOUFOX
# ============================================================

async def init_browser():

    global browser_instance
    global camoufox_manager


    if not CAMOUFOX_AVAILABLE:

        logger.error(
            "❌ Camoufox недоступен"
        )

        return False


    try:

        logger.info(
            "🚀 Запускаем Camoufox..."
        )


        camoufox_manager = AsyncCamoufox(

            headless=True,

            fingerprint=True,

        )


        # AsyncCamoufox.__aenter__()
        # возвращает BrowserContext

        browser_instance = (
            await camoufox_manager.__aenter__()
        )


        logger.info(
            "✅ Camoufox запущен"
        )

        logger.info(
            f"📌 Browser type: "
            f"{type(browser_instance).__name__}"
        )


        # ----------------------------------------------------
        # ПРОВЕРКА
        # ----------------------------------------------------

        if not hasattr(
            browser_instance,
            "new_page"
        ):

            logger.error(
                "❌ BrowserContext не имеет new_page()"
            )

            logger.error(
                f"Тип объекта: "
                f"{type(browser_instance)}"
            )

            return False


        page = None


        try:

            logger.info(
                "🔍 Проверяем Camoufox..."
            )


            page = await browser_instance.new_page()


            await page.goto(

                "https://example.com",

                wait_until="domcontentloaded",

                timeout=30000

            )


            title = await page.title()


            logger.info(
                f"✅ Camoufox работает. "
                f"Title: {title}"
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
            f"❌ Ошибка запуска Camoufox: {e}"
        )


        browser_instance = None

        camoufox_manager = None


        return False


# ============================================================
# 9. DSPY TOOLS
# ============================================================

def create_browser_tools():

    tools = []


    # ========================================================
    # GOTO URL
    # ========================================================

    def tool_goto_url(
        url: str
    ) -> str:

        global browser_instance


        try:

            if browser_instance is None:

                return (
                    "❌ Браузер не запущен"
                )


            if not url.startswith(
                ("http://", "https://")
            ):

                url = "https://" + url


            async def navigate():

                page = await browser_instance.new_page()

                await page.goto(

                    url,

                    wait_until="domcontentloaded",

                    timeout=30000

                )

                title = await page.title()

                return page, title


            try:

                loop = asyncio.get_running_loop()

                if loop.is_running():

                    # DSPy выполняется в executor,
                    # поэтому здесь обычно нет
                    # активного event loop.
                    pass

            except RuntimeError:
                pass


            # Инструменты DSPy синхронные.
            # Используем отдельный helper,
            # который выполняет coroutine.
            result = run_async(navigate())


            page, title = result


            # Сохраняем последнюю страницу
            set_current_page(page)


            return (
                f"✅ Перешел на {url}\n"
                f"📌 Title: {title}"
            )


        except Exception as e:

            logger.exception(
                f"❌ tool_goto_url: {e}"
            )

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_goto_url)
    )


    # ========================================================
    # PAGE INFO
    # ========================================================

    def tool_page_info() -> str:

        try:

            page = get_current_page()


            if page is None:

                return (
                    "❌ Нет открытой страницы"
                )


            url = run_async(
                page.url
                if not callable(page.url)
                else page.url()
            )


            title = run_async(
                page.title()
            )


            return (
                f"URL: {url}\n"
                f"Title: {title}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_page_info)
    )


    # ========================================================
    # GET TEXT
    # ========================================================

    def tool_get_text() -> str:

        try:

            page = get_current_page()


            if page is None:

                return (
                    "❌ Нет открытой страницы"
                )


            text = run_async(
                page.locator("body").inner_text(
                    timeout=10000
                )
            )


            if not text:

                return (
                    "❌ Текст не найден"
                )


            return text[:10000]


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_get_text)
    )


    # ========================================================
    # GET LINKS
    # ========================================================

    def tool_get_links() -> str:

        try:

            page = get_current_page()


            if page is None:

                return (
                    "❌ Нет открытой страницы"
                )


            links = run_async(

                page.locator("a").evaluate_all(

                    """elements =>
                    elements
                    .map(el => el.href)
                    .filter(href => href)
                    """

                )

            )


            if not links:

                return (
                    "❌ Ссылок не найдено"
                )


            result = (
                f"Ссылки ({len(links)}):\n"
            )


            result += "\n".join(
                str(x)
                for x in links[:50]
            )


            return result[:10000]


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_get_links)
    )


    # ========================================================
    # SCREENSHOT
    # ========================================================

    def tool_screenshot() -> str:

        try:

            page = get_current_page()


            if page is None:

                return (
                    "❌ Нет открытой страницы"
                )


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


            run_async(

                page.screenshot(
                    path=full_path,
                    full_page=True
                )

            )


            return (
                f"✅ Скриншот сохранен: "
                f"{filename}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_screenshot)
    )


    # ========================================================
    # JAVASCRIPT
    # ========================================================

    def tool_js(
        expression: str
    ) -> str:

        try:

            page = get_current_page()


            if page is None:

                return (
                    "❌ Нет открытой страницы"
                )


            result = run_async(

                page.evaluate(
                    expression
                )

            )


            return str(result)


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_js)
    )


    return tools


# ============================================================
# 10. ТЕКУЩАЯ СТРАНИЦА
# ============================================================

current_page = None


def set_current_page(page):

    global current_page

    current_page = page


def get_current_page():

    return current_page


# ============================================================
# 11. ASYNC HELPER
# ============================================================

def run_async(coro):

    """
    Выполняет coroutine из синхронного DSPy Tool.

    DSPy агент запускается в отдельном executor,
    поэтому здесь можно создать отдельный event loop.
    """

    try:

        loop = asyncio.get_running_loop()

        if loop.is_running():

            raise RuntimeError(
                "run_async вызван внутри работающего event loop"
            )

    except RuntimeError as e:

        if (
            "no running event loop"
            not in str(e).lower()
            and
            "run_async вызван"
            in str(e)
        ):

            raise


    return asyncio.run(coro)


# ============================================================
# 12. ИНИЦИАЛИЗАЦИЯ DSPY
# ============================================================

def init_dspy():

    global dspy_agent_instance


    api_key = os.environ.get(
        "AGNES_API_KEY"
    )


    if not api_key:

        logger.warning(
            "⚠️ AGNES_API_KEY не задан"
        )

        return False


    try:

        lm = AgnesLM(

            api_key=api_key,

            temperature=0.3,

            max_tokens=2000

        )


        settings.configure(
            lm=lm
        )


        tools = create_browser_tools()


        dspy_agent_instance = ReActV2(

            signature=BrowserTask,

            tools=tools,

            max_iters=10

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


        dspy_agent_instance = None

        return False


# ============================================================
# 13. RUN DSPY
# ============================================================

def run_agent(
    question: str
) -> str:

    if not dspy_agent_instance:

        return (
            "❌ DSPy агент не инициализирован"
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
            str(result)
        )


        if (
            answer
            and answer.strip()
        ):

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
# 14. /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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
# 15. /CHECK
# ============================================================

async def check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global current_page


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

        if not CAMOUFOX_AVAILABLE:

            await msg.edit_text(
                "❌ Camoufox не установлен"
            )

            return


        if browser_instance is None:

            await msg.edit_text(
                "❌ Браузер не запущен.\n"
                "Используйте /status"
            )

            return


        if not hasattr(
            browser_instance,
            "new_page"
        ):

            await msg.edit_text(

                "❌ Неверный объект BrowserContext.\n"
                f"Тип: "
                f"{type(browser_instance).__name__}"

            )

            return


        logger.info(
            f"🌐 /check -> {url}"
        )


        page = await browser_instance.new_page()


        current_page = page


        await page.goto(

            url,

            wait_until="domcontentloaded",

            timeout=30000

        )


        await asyncio.sleep(2)


        title = await page.title()


        try:

            text = await page.locator(
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


        from html import escape


        safe_title = escape(
            title or "Без заголовка"
        )


        safe_url = escape(
            url
        )


        safe_text = escape(
            text
        )


        result = (

            "✅ <b>Страница открыта</b>\n\n"

            f"🌐 <b>URL:</b> "
            f"{safe_url}\n"

            f"📌 <b>Title:</b> "
            f"{safe_title}\n\n"

            "<b>Текст:</b>\n"

            f"{safe_text}"

        )


        await msg.edit_text(

            result,

            parse_mode="HTML"

        )


        # Здесь страницу НЕ закрываем.
        #
        # Она становится текущей страницей
        # для DSPy /screenshot /page_info.


    except Exception as e:

        logger.exception(
            f"❌ /check error: {e}"
        )


        from html import escape


        error_text = escape(
            str(e)[:1500]
        )


        await msg.edit_text(

            "❌ <b>Ошибка:</b>\n"
            f"<code>{error_text}</code>",

            parse_mode="HTML"

        )


# ============================================================
# 16. /SCREENSHOT
# ============================================================

async def screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global current_page


    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )


    try:

        if not CAMOUFOX_AVAILABLE:

            await msg.edit_text(
                "❌ Camoufox не установлен"
            )

            return


        if browser_instance is None:

            await msg.edit_text(
                "❌ Браузер не запущен"
            )

            return


        page = current_page


        if page is None:

            page = await browser_instance.new_page()


            await page.goto(

                "https://example.com",

                wait_until="domcontentloaded",

                timeout=30000

            )


            current_page = page


        screenshot_bytes = (
            await page.screenshot(
                full_page=True
            )
        )


        await update.message.reply_photo(

            photo=screenshot_bytes,

            caption=(
                "📸 Скриншот через Camoufox"
            )

        )


        await msg.delete()


    except Exception as e:

        logger.exception(
            f"❌ Screenshot error: {e}"
        )


        from html import escape


        await msg.edit_text(

            "❌ <b>Ошибка:</b>\n"
            f"<code>{escape(str(e)[:1500])}</code>",

            parse_mode="HTML"

        )


# ============================================================
# 17. /STATUS
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

        f"🌐 Браузер: "
        f"{'✅' if browser_ok else '❌'}\n"

        f"🧠 DSPy: "
        f"{'✅' if dspy_agent_instance else '❌'}\n"

        "📁 Profile: "
        "/app/camoufox-profile\n"

    )


    if browser_instance is not None:

        status_text += (

            "\n📌 <b>Browser type:</b> "

            f"<code>"
            f"{type(browser_instance).__name__}"
            f"</code>"

        )


    if current_page is not None:

        status_text += (
            "\n📄 <b>Current page:</b> ✅"
        )

    else:

        status_text += (
            "\n📄 <b>Current page:</b> ❌"
        )


    await update.message.reply_text(

        status_text,

        parse_mode="HTML"

    )


# ============================================================
# 18. /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(

            "🧠 <b>DSPy Agent</b>\n\n"

            "Примеры:\n\n"

            "<code>/dspy "
            "открой google.com "
            "и покажи заголовок</code>\n\n"

            "<code>/dspy "
            "найди все ссылки на python.org"
            "</code>\n\n"

            "<code>/dspy "
            "сделай скриншот</code>",

            parse_mode="HTML"

        )

        return


    if not dspy_agent_instance:

        await update.message.reply_text(

            "❌ DSPy не инициализирован.\n"
            "Проверьте AGNES_API_KEY"

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

            f"❌ Ошибка: "
            f"{str(e)[:1000]}"

        )


# ============================================================
# 19. ЗАКРЫТИЕ CAMOUFOX
# ============================================================

async def close_browser():

    global browser_instance
    global camoufox_manager
    global current_page


    logger.info(
        "🛑 Закрываем Camoufox..."
    )


    current_page = None


    if camoufox_manager is not None:

        try:

            await camoufox_manager.__aexit__(
                None,
                None,
                None
            )


            logger.info(
                "✅ Camoufox закрыт"
            )


        except Exception as e:

            logger.warning(

                f"⚠️ Ошибка закрытия Camoufox: {e}"

            )


    browser_instance = None

    camoufox_manager = None


# ============================================================
# 20. MAIN
# ============================================================

async def main():

    logger.info(
        "🚀 Инициализация..."
    )


    # --------------------------------------------------------
    # CAMOUFOX
    # --------------------------------------------------------

    browser_ok = (
        await init_browser()
    )


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
        "🚀 Бот запускается..."
    )


    logger.info(
        f"🦊 Camoufox: "
        f"{'✅' if CAMOUFOX_AVAILABLE else '❌'}"
    )


    logger.info(
        f"🌐 Browser: "
        f"{'✅' if browser_ok else '❌'}"
    )


    logger.info(
        f"🧠 DSPy: "
        f"{'✅' if dspy_ok else '❌'}"
    )


    # --------------------------------------------------------
    # TELEGRAM START
    # --------------------------------------------------------

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


        # ----------------------------------------------------
        # MAIN LOOP
        # ----------------------------------------------------

        while not stop_signal.is_set():

            await asyncio.sleep(60)

            logger.info(
                "💓 Bot alive"
            )


    except Exception as e:

        logger.exception(
            f"❌ Ошибка основного цикла: {e}"
        )


    finally:

        logger.info(
            "🛑 Останавливаем бота..."
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


        await close_browser()


        logger.info(
            "👋 Бот остановлен"
        )


# ============================================================
# 21. START
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