import os
import sys
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
# 2. PATH К BROWSER HARNESS
# ============================================================

sys.path.insert(
    0,
    "/app/browser-harness/src"
)


# ============================================================
# 3. ИМПОРТ DSPY
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
# 4. CAMOUFOX
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
# 5. BROWSER HARNESS
# ============================================================

try:

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

    HARNESS_AVAILABLE = True

    logger.info(
        "✅ Browser Harness загружен"
    )

except ImportError as e:

    HARNESS_AVAILABLE = False

    logger.warning(
        f"⚠️ Browser Harness не найден: {e}"
    )


# ============================================================
# 6. НАСТРОЙКИ
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
# 7. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

# Это именно BrowserContext, полученный
# из AsyncCamoufox.__aenter__()
browser_instance = None

# Сам менеджер AsyncCamoufox.
# Его нужно сохранить, чтобы корректно вызвать __aexit__().
camoufox_manager = None

harness_ready = False

dspy_agent_instance = None


# ============================================================
# 8. AGNES LM ДЛЯ DSPY
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
# 9. DSPY SIGNATURE
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
# 10. ИНИЦИАЛИЗАЦИЯ CAMOUFOX
# ============================================================

async def init_browser_and_harness():

    global browser_instance
    global camoufox_manager
    global harness_ready


    if not CAMOUFOX_AVAILABLE:

        logger.error(
            "❌ Camoufox недоступен"
        )

        return False


    try:

        logger.info(
            "🚀 Запускаем Camoufox..."
        )


        # ----------------------------------------------------
        # ВАЖНО
        #
        # Не сохраняем AsyncCamoufox как browser_instance.
        #
        # AsyncCamoufox -> менеджер
        # __aenter__() -> BrowserContext
        #
        # Именно BrowserContext имеет new_page().
        # ----------------------------------------------------

        camoufox_manager = AsyncCamoufox(

            headless=True,

            fingerprint=True,

        )


        browser_instance = (
            await camoufox_manager.__aenter__()
        )


        logger.info(
            "✅ Camoufox запущен: "
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
                "❌ Полученный объект не имеет new_page()"
            )

            logger.error(
                f"Тип: {type(browser_instance)}"
            )

            return False


        logger.info(
            "🔍 Проверяем браузер..."
        )


        page = None


        try:

            page = await browser_instance.new_page()


            await page.goto(

                "https://example.com",

                wait_until="domcontentloaded",

                timeout=30000
            )


            title = await page.title()


            logger.info(
                f"✅ Браузер работает. "
                f"Title: {title}"
            )


        finally:

            if page is not None:

                try:
                    await page.close()

                except Exception:
                    pass


        # ----------------------------------------------------
        # HARNESS
        # ----------------------------------------------------

        if HARNESS_AVAILABLE:

            try:

                logger.info(
                    "🔗 Подключаем Browser Harness..."
                )


                ensure_daemon()


                new_tab(
                    "about:blank"
                )


                wait_for_load()


                harness_ready = True


                logger.info(
                    "✅ Browser Harness готов"
                )


            except Exception as e:

                harness_ready = False

                logger.warning(
                    f"⚠️ Harness не подключился: {e}"
                )


        return True


    except Exception as e:

        logger.exception(
            f"❌ Ошибка запуска Camoufox: {e}"
        )


        browser_instance = None

        camoufox_manager = None

        harness_ready = False


        return False


# ============================================================
# 11. DSPY TOOLS
# ============================================================

def create_harness_tools():

    tools = []


    # --------------------------------------------------------
    # GOTO
    # --------------------------------------------------------

    def tool_goto_url(
        url: str
    ) -> str:

        try:

            if not url.startswith(
                ("http://", "https://")
            ):

                url = "https://" + url


            goto_url(url)

            wait_for_load()


            return (
                f"✅ Перешел на {url}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_goto_url)
    )


    # --------------------------------------------------------
    # PAGE INFO
    # --------------------------------------------------------

    def tool_page_info() -> str:

        try:

            info = page_info()


            return (
                f"URL: "
                f"{info.get('url', 'unknown')}\n"
                f"Title: "
                f"{info.get('title', 'unknown')}"
            )


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_page_info)
    )


    # --------------------------------------------------------
    # GET TEXT
    # --------------------------------------------------------

    def tool_get_text() -> str:

        try:

            result = js(
                "() => document.body.innerText"
            )


            if isinstance(
                result,
                dict
            ):

                text = str(
                    result.get(
                        "result",
                        ""
                    )
                )

            else:

                text = str(result)


            if (
                not text
                or len(text) < 2
            ):

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


    # --------------------------------------------------------
    # GET LINKS
    # --------------------------------------------------------

    def tool_get_links() -> str:

        try:

            result = js(

                '() => Array.from('
                'document.querySelectorAll("a")'
                ').map(el => el.href)'
                '.filter(h => h)'

            )


            if isinstance(
                result,
                dict
            ):

                result = result.get(
                    "result",
                    result
                )


            if isinstance(
                result,
                list
            ):

                links = [
                    str(x)
                    for x in result
                    if x
                ]

            else:

                links = []


            if not links:

                return (
                    "❌ Ссылок не найдено"
                )


            result_text = (
                f"Ссылки ({len(links)}):\n"
            )


            result_text += "\n".join(
                links[:50]
            )


            return result_text[:10000]


        except Exception as e:

            return (
                f"❌ Ошибка: {e}"
            )


    tools.append(
        Tool(tool_get_links)
    )


    # --------------------------------------------------------
    # SCREENSHOT
    # --------------------------------------------------------

    def tool_screenshot() -> str:

        try:

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


            capture_screenshot(
                path=full_path
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


    # --------------------------------------------------------
    # JAVASCRIPT
    # --------------------------------------------------------

    def tool_js(
        expression: str
    ) -> str:

        try:

            result = js(
                expression
            )


            if isinstance(
                result,
                dict
            ):

                return str(
                    result.get(
                        "result",
                        result
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


        tools = create_harness_tools()


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

        "🦊 Camoufox + Browser Harness + DSPy\n\n"

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

        url = (
            "https://" + url
        )


    msg = await update.message.reply_text(

        "⏳ Открываю через Camoufox..."

    )


    try:

        global browser_instance


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

                "❌ Неверный объект браузера.\n"
                f"Тип: "
                f"{type(browser_instance).__name__}"

            )

            return


        logger.info(
            f"🌐 /check -> {url}"
        )


        page = None


        try:

            page = await browser_instance.new_page()


            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=30000

            )


            # Даём JS немного времени
            await asyncio.sleep(2)


            title = await page.title()


            # Получаем текст
            try:

                text = (
                    await page
                    .locator("body")
                    .inner_text(
                        timeout=10000
                    )
                )

            except Exception:

                text = ""


            if not text:

                text = (
                    "Текст страницы не найден."
                )


            text = text[:3500]


            # Telegram HTML escaping
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


        finally:

            if page is not None:

                try:

                    await page.close()

                except Exception:

                    pass


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

    msg = await update.message.reply_text(
        "📸 Делаю скриншот..."
    )


    try:

        global browser_instance


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


        if not hasattr(
            browser_instance,
            "new_page"
        ):

            await msg.edit_text(

                "❌ Неверный объект браузера:\n"
                f"{type(browser_instance).__name__}"

            )

            return


        page = None


        try:

            page = await browser_instance.new_page()


            await page.goto(

                "https://example.com",

                wait_until="domcontentloaded",

                timeout=30000

            )


            await asyncio.sleep(1)


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


        finally:

            if page is not None:

                try:

                    await page.close()

                except Exception:

                    pass


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

        f"🔧 Harness: "
        f"{'✅' if harness_ready else '❌'}\n"

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


    logger.info(
        "🛑 Закрываем браузер..."
    )


    # --------------------------------------------------------
    # ВАЖНО:
    #
    # browser_instance = BrowserContext
    #
    # camoufox_manager = AsyncCamoufox
    #
    # Поэтому закрываем через __aexit__().
    # --------------------------------------------------------

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

                "⚠️ Ошибка закрытия Camoufox: "
                f"{e}"

            )


    else:

        # На случай старого/нестандартного состояния
        if browser_instance is not None:

            try:

                await browser_instance.close()

            except Exception as e:

                logger.warning(
                    f"⚠️ Ошибка close(): {e}"
                )


    browser_instance = None
    camoufox_manager = None


# ============================================================
# 20. MAIN
# ============================================================

async def main():

    global browser_instance


    logger.info(
        "🚀 Инициализация..."
    )


    # --------------------------------------------------------
    # CAMOUFOX
    # --------------------------------------------------------

    browser_ok = (
        await init_browser_and_harness()
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


    if browser_instance is not None:

        logger.info(
            "📌 Browser object: "
            f"{type(browser_instance).__name__}"
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


        # ----------------------------------------------------
        # SIGNALS
        # ----------------------------------------------------

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