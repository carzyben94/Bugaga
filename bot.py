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


# ============================================================
# 1. LOGGER
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
# 3. SETTINGS
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
# 4. GLOBAL STATE
# ============================================================

camoufox_manager = None
camoufox_context = None
current_page = None

browser_ready = False

browser_lock = asyncio.Lock()

dspy_agent_instance = None

# ОСНОВНОЙ asyncio loop.
# Camoufox живёт именно в нём.
main_event_loop = None


# ============================================================
# 5. CAMOUFOX INIT
# ============================================================

async def init_browser():

    global camoufox_manager
    global camoufox_context
    global current_page
    global browser_ready

    if not CAMOUFOX_AVAILABLE:
        logger.error("❌ Camoufox недоступен")
        return False

    logger.info("🚀 Запускаем Camoufox...")

    try:

        camoufox_manager = AsyncCamoufox(
            headless=True,
            persistent_context=True,
            user_data_dir=CAMOUFOX_PROFILE,
        )

        camoufox_context = (
            await camoufox_manager.__aenter__()
        )

        if camoufox_context is None:
            raise RuntimeError(
                "Camoufox вернул None"
            )

        logger.info(
            f"✅ BrowserContext: "
            f"{type(camoufox_context).__name__}"
        )

        current_page = (
            await camoufox_context.new_page()
        )

        await current_page.goto(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        title = await current_page.title()

        logger.info(
            f"✅ Camoufox работает. "
            f"Title: {title}"
        )

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

        try:

            if camoufox_manager is not None:

                await camoufox_manager.__aexit__(
                    None,
                    None,
                    None,
                )

        except Exception:
            pass

        camoufox_manager = None
        camoufox_context = None
        current_page = None

        return False


# ============================================================
# 6. CURRENT PAGE
# ============================================================

async def get_current_page():

    global current_page

    if (
        not browser_ready
        or camoufox_context is None
    ):
        raise RuntimeError(
            "Camoufox не запущен"
        )

    if current_page is None:

        current_page = (
            await camoufox_context.new_page()
        )

    try:

        await current_page.title()

    except Exception:

        current_page = (
            await camoufox_context.new_page()
        )

    return current_page


# ============================================================
# 7. CLOSE BROWSER
# ============================================================

async def close_browser():

    global camoufox_manager
    global camoufox_context
    global current_page
    global browser_ready

    browser_ready = False

    if current_page is not None:

        try:
            await current_page.close()
        except Exception:
            pass

    current_page = None

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


# ============================================================
# 8. BROWSER OPERATIONS
# ============================================================

async def browser_goto(url: str):

    async with browser_lock:

        page = await get_current_page()

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        return (
            f"✅ Открыто\n"
            f"URL: {page.url}\n"
            f"Title: {await page.title()}"
        )


async def browser_back():

    async with browser_lock:

        page = await get_current_page()

        await page.go_back(
            wait_until="domcontentloaded",
            timeout=30000,
        )

        return (
            f"URL: {page.url}\n"
            f"Title: {await page.title()}"
        )


async def browser_forward():

    async with browser_lock:

        page = await get_current_page()

        await page.go_forward(
            wait_until="domcontentloaded",
            timeout=30000,
        )

        return (
            f"URL: {page.url}\n"
            f"Title: {await page.title()}"
        )


async def browser_reload():

    async with browser_lock:

        page = await get_current_page()

        await page.reload(
            wait_until="domcontentloaded",
            timeout=30000,
        )

        return (
            f"URL: {page.url}\n"
            f"Title: {await page.title()}"
        )


async def browser_page_info():

    async with browser_lock:

        page = await get_current_page()

        return (
            f"URL: {page.url}\n"
            f"Title: {await page.title()}\n"
            f"Pages: {len(camoufox_context.pages)}"
        )


async def browser_get_text(
    selector: str = "body"
):

    async with browser_lock:

        page = await get_current_page()

        text = await page.locator(
            selector
        ).inner_text(
            timeout=10000
        )

        if not text:
            return "❌ Текст не найден"

        return text[:20000]


async def browser_get_html(
    selector: str = "body"
):

    async with browser_lock:

        page = await get_current_page()

        html = await page.locator(
            selector
        ).inner_html(
            timeout=10000
        )

        return html[:30000]


async def browser_get_links():

    async with browser_lock:

        page = await get_current_page()

        links = await page.locator(
            "a"
        ).evaluate_all(
            """
            elements => elements.map(el => ({
                text: (el.innerText || "").trim(),
                href: el.href
            })).filter(x => x.href)
            """
        )

        if not links:
            return "❌ Ссылок не найдено"

        result = []

        for item in links[:200]:

            result.append(
                f"{item.get('text', '')[:100]} "
                f"→ {item.get('href', '')}"
            )

        return "\n".join(result)


async def browser_click(
    selector: str
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).first.click(
            timeout=15000
        )

        await page.wait_for_timeout(500)

        return (
            f"✅ Клик выполнен\n"
            f"Selector: {selector}\n"
            f"URL: {page.url}"
        )


async def browser_fill(
    selector: str,
    text: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).first.fill(
            text,
            timeout=15000
        )

        return (
            f"✅ Текст введён\n"
            f"Selector: {selector}"
        )


async def browser_type(
    selector: str,
    text: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).first.type(
            text,
            timeout=15000
        )

        return (
            f"✅ Текст напечатан\n"
            f"Selector: {selector}"
        )


async def browser_press(
    selector: str,
    key: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).first.press(
            key,
            timeout=15000
        )

        return (
            f"✅ Нажата клавиша {key}"
        )


async def browser_key(
    key: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.keyboard.press(key)

        return (
            f"✅ Нажата клавиша {key}"
        )


async def browser_wait(
    milliseconds: int = 1000,
):

    async with browser_lock:

        page = await get_current_page()

        milliseconds = max(
            0,
            min(int(milliseconds), 30000),
        )

        await page.wait_for_timeout(
            milliseconds
        )

        return (
            f"✅ Ожидание "
            f"{milliseconds} мс"
        )


async def browser_wait_selector(
    selector: str,
    timeout: int = 10000,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).wait_for(
            state="visible",
            timeout=timeout,
        )

        return (
            f"✅ Элемент найден: "
            f"{selector}"
        )


async def browser_select(
    selector: str,
    value: str,
):

    async with browser_lock:

        page = await get_current_page()

        result = await page.locator(
            selector
        ).select_option(
            value=value,
            timeout=15000,
        )

        return (
            f"✅ Выбрано: {result}"
        )


async def browser_check(
    selector: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).check(
            timeout=15000,
        )

        return (
            f"✅ Checkbox отмечен: "
            f"{selector}"
        )


async def browser_uncheck(
    selector: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).uncheck(
            timeout=15000,
        )

        return (
            f"✅ Checkbox снят: "
            f"{selector}"
        )


async def browser_hover(
    selector: str,
):

    async with browser_lock:

        page = await get_current_page()

        await page.locator(
            selector
        ).hover(
            timeout=15000,
        )

        return (
            f"✅ Наведение выполнено: "
            f"{selector}"
        )


async def browser_attribute(
    selector: str,
    attribute: str,
):

    async with browser_lock:

        page = await get_current_page()

        value = await page.locator(
            selector
        ).first.get_attribute(
            attribute
        )

        return str(value)


async def browser_count(
    selector: str,
):

    async with browser_lock:

        page = await get_current_page()

        count = await page.locator(
            selector
        ).count()

        return (
            f"Количество элементов: {count}"
        )


async def browser_js(
    expression: str,
):

    async with browser_lock:

        page = await get_current_page()

        result = await page.evaluate(
            expression
        )

        return str(result)[:30000]


async def browser_screenshot():

    async with browser_lock:

        page = await get_current_page()

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


async def browser_content():

    async with browser_lock:

        page = await get_current_page()

        content = await page.content()

        return content[:30000]


# ============================================================
# 9. DSPy → ASYNC BRIDGE
# ============================================================

def run_async_from_dspy(coro):

    """
    DSPy работает в отдельном потоке.

    Camoufox работает в основном asyncio loop.

    Поэтому отправляем coroutine обратно
    в основной loop.
    """

    global main_event_loop

    if main_event_loop is None:

        raise RuntimeError(
            "Основной asyncio loop не установлен"
        )

    if main_event_loop.is_closed():

        raise RuntimeError(
            "Основной asyncio loop закрыт"
        )

    future = asyncio.run_coroutine_threadsafe(
        coro,
        main_event_loop,
    )

    try:

        return future.result(
            timeout=60
        )

    except Exception:

        future.cancel()
        raise


# ============================================================
# 10. SYNC DSPy TOOLS
# ============================================================

def create_browser_tools():

    tools = []

    def tool_goto(url: str):

        return run_async_from_dspy(
            browser_goto(url)
        )

    def tool_back():

        return run_async_from_dspy(
            browser_back()
        )

    def tool_forward():

        return run_async_from_dspy(
            browser_forward()
        )

    def tool_reload():

        return run_async_from_dspy(
            browser_reload()
        )

    def tool_page_info():

        return run_async_from_dspy(
            browser_page_info()
        )

    def tool_get_text(
        selector: str = "body"
    ):

        return run_async_from_dspy(
            browser_get_text(selector)
        )

    def tool_get_html(
        selector: str = "body"
    ):

        return run_async_from_dspy(
            browser_get_html(selector)
        )

    def tool_get_links():

        return run_async_from_dspy(
            browser_get_links()
        )

    def tool_click(
        selector: str
    ):

        return run_async_from_dspy(
            browser_click(selector)
        )

    def tool_fill(
        selector: str,
        text: str,
    ):

        return run_async_from_dspy(
            browser_fill(
                selector,
                text,
            )
        )

    def tool_type(
        selector: str,
        text: str,
    ):

        return run_async_from_dspy(
            browser_type(
                selector,
                text,
            )
        )

    def tool_press(
        selector: str,
        key: str,
    ):

        return run_async_from_dspy(
            browser_press(
                selector,
                key,
            )
        )

    def tool_key(
        key: str
    ):

        return run_async_from_dspy(
            browser_key(key)
        )

    def tool_wait(
        milliseconds: int = 1000
    ):

        return run_async_from_dspy(
            browser_wait(milliseconds)
        )

    def tool_wait_selector(
        selector: str,
        timeout: int = 10000,
    ):

        return run_async_from_dspy(
            browser_wait_selector(
                selector,
                timeout,
            )
        )

    def tool_select(
        selector: str,
        value: str,
    ):

        return run_async_from_dspy(
            browser_select(
                selector,
                value,
            )
        )

    def tool_check(
        selector: str
    ):

        return run_async_from_dspy(
            browser_check(selector)
        )

    def tool_uncheck(
        selector: str
    ):

        return run_async_from_dspy(
            browser_uncheck(selector)
        )

    def tool_hover(
        selector: str
    ):

        return run_async_from_dspy(
            browser_hover(selector)
        )

    def tool_attribute(
        selector: str,
        attribute: str,
    ):

        return run_async_from_dspy(
            browser_attribute(
                selector,
                attribute,
            )
        )

    def tool_count(
        selector: str
    ):

        return run_async_from_dspy(
            browser_count(selector)
        )

    def tool_javascript(
        expression: str
    ):

        return run_async_from_dspy(
            browser_js(expression)
        )

    def tool_screenshot():

        return run_async_from_dspy(
            browser_screenshot()
        )

    def tool_content():

        return run_async_from_dspy(
            browser_content()
        )

    tools.extend([
        Tool(tool_goto),
        Tool(tool_back),
        Tool(tool_forward),
        Tool(tool_reload),
        Tool(tool_page_info),
        Tool(tool_get_text),
        Tool(tool_get_html),
        Tool(tool_get_links),
        Tool(tool_click),
        Tool(tool_fill),
        Tool(tool_type),
        Tool(tool_press),
        Tool(tool_key),
        Tool(tool_wait),
        Tool(tool_wait_selector),
        Tool(tool_select),
        Tool(tool_check),
        Tool(tool_uncheck),
        Tool(tool_hover),
        Tool(tool_attribute),
        Tool(tool_count),
        Tool(tool_javascript),
        Tool(tool_screenshot),
        Tool(tool_content),
    ])

    return tools


# ============================================================
# 11. AGNES LM
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
                0.2,
            ),
            max_tokens=kwargs.get(
                "max_tokens",
                4000,
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
                params.get(
                    "temperature",
                    0.2,
                ),
            "max_tokens":
                params.get(
                    "max_tokens",
                    4000,
                ),
        }

        try:

            logger.info(
                "🧠 → Agnes API"
            )

            with httpx.Client(
                timeout=120.0
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

                    result = (
                        data["choices"][0]
                        ["message"]
                        ["content"]
                    )

                    logger.info(
                        "🧠 ← Agnes API"
                    )

                    return [result]

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
# 12. DSPy SIGNATURE
# ============================================================

class BrowserTask(Signature):

    """
    Ты автономный браузерный агент.

    Управляй текущей страницей Camoufox.

    Для действий в браузере ОБЯЗАТЕЛЬНО
    используй инструменты.

    Ты можешь:

    - открывать сайты;
    - переходить назад;
    - переходить вперёд;
    - обновлять страницу;
    - читать текст;
    - читать HTML;
    - получать ссылки;
    - нажимать кнопки;
    - вводить текст;
    - нажимать клавиши;
    - выбирать option;
    - работать с checkbox;
    - наводить мышь;
    - ждать элементы;
    - выполнять JavaScript;
    - получать атрибуты;
    - считать DOM элементы;
    - делать скриншоты.

    Состояние страницы сохраняется между инструментами.

    Если не знаешь selector:
    сначала исследуй страницу.

    Не говори, что действие выполнено,
    пока инструмент не подтвердил его.

    Выполняй несколько инструментов подряд,
    если задача этого требует.
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Результат выполнения задачи"
    )


# ============================================================
# 13. INIT DSPy
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
            temperature=0.2,
            max_tokens=4000,
        )

        settings.configure(
            lm=lm
        )

        tools = create_browser_tools()

        dspy_agent_instance = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=15,
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
# 14. RUN AGENT
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

        logger.info(
            f"🧠 DSPy задача: {question}"
        )

        result = dspy_agent_instance(
            question=question
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
# 15. /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + DSPy Agent\n\n"
        "Команды:\n"
        "/check <url> — открыть сайт\n"
        "/dspy <запрос> — AI агент\n"
        "/status — статус\n"
        "/screenshot — текущая страница"
    )


# ============================================================
# 16. /CHECK
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

        result = await browser_goto(url)

        text = await browser_get_text(
            "body"
        )

        await msg.edit_text(
            f"{result}\n\n"
            f"{text[:1500]}"
        )

    except Exception as e:

        logger.exception(
            "❌ /check"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# 17. /SCREENSHOT
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
                caption="📸 Текущая страница Camoufox",
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
# 18. /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    page_url = "—"
    page_title = "—"

    if browser_ready and current_page:

        try:

            page_url = current_page.url
            page_title = await current_page.title()

        except Exception:
            pass

    status_text = (
        "📦 *Статус системы*\n\n"

        f"🦊 Camoufox: "
        f"{'✅' if CAMOUFOX_AVAILABLE else '❌'}\n"

        f"🌐 Browser: "
        f"{'✅' if browser_ready else '❌'}\n"

        f"🧠 DSPy: "
        f"{'✅' if dspy_agent_instance else '❌'}\n\n"

        f"🌐 URL:\n"
        f"`{page_url}`\n\n"

        f"📄 Title:\n"
        f"{escape_markdown(page_title, version=2)}"
    )

    await update.message.reply_text(
        status_text,
        parse_mode="MarkdownV2",
    )


# ============================================================
# 19. /DSPY
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "🧠 DSPy Agent\n\n"
            "Пример:\n"
            "/dspy открой https://example.com "
            "и покажи заголовок"
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

        # DSPy синхронный.
        # Запускаем его НЕ в Telegram loop.
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
            f"❌ Ошибка:\n{str(e)[:500]}"
        )


# ============================================================
# 20. MAIN
# ============================================================

async def main():

    global main_event_loop

    # Очень важно:
    # сохраняем именно основной loop,
    # в котором живёт Camoufox.

    main_event_loop = (
        asyncio.get_running_loop()
    )

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
# 21. ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )