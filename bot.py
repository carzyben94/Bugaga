import os
import asyncio
import logging
import time 
import signal
import threading
import json
from typing import Optional

import httpx

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

import dspy
from dspy import (
    Signature,
    InputField,
    OutputField,
    Tool,
)

try:
    from dspy import ReActV2

    REACT_V2_AVAILABLE = True

except ImportError:

    ReActV2 = None
    REACT_V2_AVAILABLE = False


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

    logger.info(
        "✅ Camoufox загружен"
    )

except ImportError as e:

    CAMOUFOX_AVAILABLE = False

    logger.error(
        f"❌ Camoufox не найден: {e}"
    )


# ============================================================
# 3. SETTINGS
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
# 4. GLOBAL STATE
# ============================================================

camoufox_manager = None

camoufox_context = None

current_page = None

browser_ready = False

browser_lock = asyncio.Lock()

dspy_agent_instance = None

main_event_loop = None

agent_lock = threading.Lock()

waiting_for_cookies = set()


# ============================================================
# 5. CAMOUFOX INIT
# ============================================================

async def init_browser():

    global camoufox_manager
    global camoufox_context
    global current_page
    global browser_ready

    if not CAMOUFOX_AVAILABLE:

        logger.error(
            "❌ Camoufox недоступен"
        )

        return False

    logger.info(
        "🚀 Запускаем Camoufox..."
    )

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

        current_page = (
            await camoufox_context.new_page()
        )

        await current_page.goto(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        title = await current_page.title()

        browser_ready = True

        logger.info(
            f"✅ Camoufox работает: {title}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка запуска Camoufox: {e}"
        )

        browser_ready = False

        current_page = None

        camoufox_context = None

        try:

            if camoufox_manager:

                await camoufox_manager.__aexit__(
                    None,
                    None,
                    None,
                )

        except Exception:
            pass

        camoufox_manager = None

        return False


# ============================================================
# 6. CLOSE BROWSER
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

    if camoufox_manager is not None:

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

    camoufox_manager = None

    camoufox_context = None

    logger.info(
        "✅ Camoufox закрыт"
    )


# ============================================================
# 7. PAGE ALIVE
# ============================================================

async def page_is_alive(page):

    try:

        if page is None:
            return False

        if page.is_closed():
            return False

        await page.title()

        return True

    except Exception:

        return False


# ============================================================
# 8. GET CURRENT PAGE
# ============================================================

async def get_current_page():

    global current_page

    if not browser_ready:

        raise RuntimeError(
            "Camoufox не запущен"
        )

    if camoufox_context is None:

        raise RuntimeError(
            "BrowserContext отсутствует"
        )

    if await page_is_alive(
        current_page
    ):

        return current_page

    logger.warning(
        "⚠️ Текущая страница закрыта"
    )

    try:

        current_page = (
            await camoufox_context.new_page()
        )

        return current_page

    except Exception as e:

        logger.warning(
            f"⚠️ Context недоступен: {e}"
        )

        await close_browser()

        ok = await init_browser()

        if not ok:

            raise RuntimeError(
                "❌ Не удалось восстановить Camoufox"
            )

        return current_page


# ============================================================
# 9. COOKIE NORMALIZATION
# ============================================================

def normalize_cookie(cookie: dict):

    if not isinstance(cookie, dict):

        raise ValueError(
            "Cookie должен быть объектом"
        )

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name = cookie.get("name")

    if not name:

        raise ValueError(
            "Cookie не содержит name"
        )

    # --------------------------------------------------------
    # VALUE
    # --------------------------------------------------------

    value = cookie.get(
        "value",
        "",
    )

    result = {

        "name": str(name),

        "value": str(value),

    }

    # --------------------------------------------------------
    # DOMAIN
    # --------------------------------------------------------

    domain = cookie.get(
        "domain"
    )

    if domain and not isinstance(
        domain,
        bool,
    ):

        domain = str(
            domain
        ).strip()

        if domain.startswith(
            "http://"
        ):

            domain = domain[7:]

        elif domain.startswith(
            "https://"
        ):

            domain = domain[8:]

        domain = domain.split(
            "/",
            1,
        )[0]

        if domain:

            result["domain"] = domain

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    url = cookie.get(
        "url"
    )

    if url:

        url = str(
            url
        ).strip()

        if url.startswith(
            "http://"
        ) or url.startswith(
            "https://"
        ):

            result["url"] = url

    # --------------------------------------------------------
    # FALLBACK URL
    # --------------------------------------------------------

    if (
        "domain" not in result
        and "url" not in result
    ):

        try:

            if (
                current_page
                and not current_page.is_closed()
            ):

                page_url = current_page.url

                if page_url.startswith(
                    (
                        "http://",
                        "https://",
                    )
                ):

                    result["url"] = page_url

        except Exception:
            pass

    if (
        "domain" not in result
        and "url" not in result
    ):

        raise ValueError(
            f"Cookie '{name}' "
            "не содержит domain или url"
        )

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------

    path = cookie.get(
        "path"
    ) or "/"

    path = str(
        path
    )

    if not path.startswith(
        "/"
    ):

        path = "/" + path

    result["path"] = path

    # --------------------------------------------------------
    # SECURE
    # --------------------------------------------------------

    result["secure"] = bool(
        cookie.get(
            "secure",
            False,
        )
    )

    # --------------------------------------------------------
    # HTTP ONLY
    # --------------------------------------------------------

    result["httpOnly"] = bool(
        cookie.get(
            "httpOnly",
            False,
        )
    )

    # --------------------------------------------------------
    # SAME SITE
    # --------------------------------------------------------

    same_site = cookie.get(
        "sameSite"
    )

    if same_site:

        same_site = str(
            same_site
        ).strip().lower()

        same_site = {

            "strict": "Strict",

            "lax": "Lax",

            "none": "None",

            "no_restriction": "None",

            "no-restriction": "None",

            "unspecified": "Lax",

            "default": "Lax",

        }.get(
            same_site,
            "Lax",
        )

        result["sameSite"] = (
            same_site
        )

    # --------------------------------------------------------
    # EXPIRES
    # --------------------------------------------------------

    expires = cookie.get(
        "expires"
    )

    if expires is None:

        expires = cookie.get(
            "expirationDate"
        )

    if expires is not None:

        try:

            expires = float(
                expires
            )

            if expires > 0:

                result["expires"] = (
                    expires
                )

        except (
            ValueError,
            TypeError,
        ):

            pass

    return result


# ============================================================
# 10. LOAD COOKIES
# ============================================================

async def load_cookies_from_json(
    data
):

    if isinstance(
        data,
        dict,
    ):

        cookies = data.get(
            "cookies"
        )

        if cookies is None:

            raise ValueError(
                "JSON должен содержать "
                "поле 'cookies'"
            )

    elif isinstance(
        data,
        list,
    ):

        cookies = data

    else:

        raise ValueError(
            "Неверный формат JSON cookies"
        )

    if not cookies:

        raise ValueError(
            "Файл cookies пустой"
        )

    normalized = []

    errors = []

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    for index, cookie in enumerate(
        cookies
    ):

        try:

            normalized_cookie = (
                normalize_cookie(
                    cookie
                )
            )

            normalized.append(
                normalized_cookie
            )

        except Exception as e:

            errors.append(
                f"Cookie #{index + 1}: {e}"
            )

    if not normalized:

        raise ValueError(
            "Не удалось обработать ни одного "
            "cookie:\n"
            + "\n".join(
                errors[:20]
            )
        )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    async with browser_lock:

        async def operation():

            if camoufox_context is None:

                raise RuntimeError(
                    "BrowserContext отсутствует"
                )

            loaded = 0

            load_errors = list(
                errors
            )

            for index, cookie in enumerate(
                normalized
            ):

                try:

                    await camoufox_context.add_cookies(
                        [cookie]
                    )

                    loaded += 1

                except Exception as e:

                    cookie_name = (
                        cookie.get(
                            "name",
                            "unknown",
                        )
                    )

                    load_errors.append(
                        f"Cookie #{index + 1} "
                        f"({cookie_name}): {e}"
                    )

                    logger.warning(
                        "⚠️ Cookie #%s (%s) "
                        "не загружена: %s",
                        index + 1,
                        cookie_name,
                        e,
                    )

            return {

                "loaded": loaded,

                "errors": load_errors,

                "total": len(cookies),

            }

        return await browser_operation(
            operation
        )


# ============================================================
# 11. BROWSER ERROR
# ============================================================

def is_browser_closed_error(
    error
):

    text = str(
        error
    ).lower()

    patterns = [

        "targetclosederror",

        "target page",

        "browser has been closed",

        "browsercontext",

        "context has been closed",

        "page has been closed",

        "target has been closed",

    ]

    return any(
        pattern in text
        for pattern in patterns
    )


# ============================================================
# 12. BROWSER RECOVERY
# ============================================================

async def browser_operation(
    operation
):

    global current_page

    try:

        return await operation()

    except Exception as e:

        if not is_browser_closed_error(
            e
        ):

            raise

        logger.warning(
            "⚠️ Camoufox закрыт. "
            "Восстанавливаем..."
        )

        current_page = None

        await close_browser()

        ok = await init_browser()

        if not ok:

            raise RuntimeError(
                "❌ Camoufox не удалось восстановить"
            )

        return await operation()


# ============================================================
# 13. GOTO
# ============================================================

async def browser_goto(
    url: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

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

        return await browser_operation(
            operation
        )


# ============================================================
# 14. BACK
# ============================================================

async def browser_back():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            response = await page.go_back(
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if response is None:

                return (
                    "⚠️ Назад перейти невозможно\n"
                    f"URL: {page.url}"
                )

            return (
                f"✅ Назад\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 15. FORWARD
# ============================================================

async def browser_forward():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            response = await page.go_forward(
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if response is None:

                return (
                    "⚠️ Вперёд перейти невозможно\n"
                    f"URL: {page.url}"
                )

            return (
                f"✅ Вперёд\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 16. RELOAD
# ============================================================

async def browser_reload():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.reload(
                wait_until="domcontentloaded",
                timeout=30000,
            )

            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 17. PAGE INFO
# ============================================================

async def browser_page_info():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}\n"
                f"Pages: {len(camoufox_context.pages)}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 18. GET TEXT
# ============================================================

async def browser_get_text(
    selector: str = "body"
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            text = await page.locator(
                selector
            ).inner_text(
                timeout=10000
            )

            if not text:

                return "❌ Текст не найден"

            return text[:20000]

        return await browser_operation(
            operation
        )


# ============================================================
# 19. GET HTML
# ============================================================

async def browser_get_html(
    selector: str = "body"
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            html = await page.locator(
                selector
            ).inner_html(
                timeout=10000
            )

            return html[:30000]

        return await browser_operation(
            operation
        )


# ============================================================
# 20. INSPECT
# ============================================================

async def browser_inspect():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            title = await page.title()

            url = page.url

            buttons = await page.locator(
                "button"
            ).evaluate_all(
                """
                els => els.slice(0,50).map(
                    e => ({
                        text: (
                            e.innerText ||
                            e.getAttribute('aria-label') ||
                            ''
                        ).trim(),
                        type: e.getAttribute('type') || '',
                        id: e.id || '',
                        cls: e.className || ''
                    })
                )
                """
            )

            inputs = await page.locator(
                "input, textarea, select"
            ).evaluate_all(
                """
                els => els.slice(0,50).map(
                    e => ({
                        tag: e.tagName.toLowerCase(),
                        type: e.getAttribute('type') || '',
                        name: e.getAttribute('name') || '',
                        placeholder:
                            e.getAttribute('placeholder') || '',
                        aria:
                            e.getAttribute('aria-label') || '',
                        id: e.id || ''
                    })
                )
                """
            )

            links = await page.locator(
                "a"
            ).evaluate_all(
                """
                els => els.slice(0,80).map(
                    e => ({
                        text: (e.innerText || '').trim(),
                        href: e.href || ''
                    })
                ).filter(
                    x => x.text || x.href
                )
                """
            )

            result = [

                f"URL: {url}",

                f"TITLE: {title}",

                "",

                "BUTTONS:",

            ]

            for b in buttons:

                result.append(
                    f"- text={b.get('text','')[:100]} "
                    f"id={b.get('id','')} "
                    f"type={b.get('type','')}"
                )

            result.append("")
            result.append("INPUTS:")

            for i in inputs:

                result.append(
                    f"- tag={i.get('tag','')} "
                    f"type={i.get('type','')} "
                    f"name={i.get('name','')} "
                    f"placeholder="
                    f"{i.get('placeholder','')} "
                    f"aria={i.get('aria','')} "
                    f"id={i.get('id','')}"
                )

            result.append("")
            result.append("LINKS:")

            for link in links:

                result.append(
                    f"- {link.get('text','')[:100]} "
                    f"→ {link.get('href','')}"
                )

            return "\n".join(
                result
            )[:30000]

        return await browser_operation(
            operation
        )


# ============================================================
# 21. LINKS
# ============================================================

async def browser_get_links():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            links = await page.locator(
                "a"
            ).evaluate_all(
                """
                elements => elements.map(
                    el => ({
                        text:
                            (el.innerText || '').trim(),
                        href: el.href
                    })
                ).filter(
                    x => x.href
                )
                """
            )

            if not links:

                return "❌ Ссылок не найдено"

            result = []

            for link in links[:200]:

                result.append(
                    f"{link.get('text','')[:100]} "
                    f"→ {link.get('href','')}"
                )

            return "\n".join(
                result
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 22. CLICK
# ============================================================

async def browser_click(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).first.click(
                timeout=15000
            )

            await page.wait_for_timeout(
                500
            )

            return (
                "✅ Клик выполнен\n"
                f"Selector: {selector}\n"
                f"URL: {page.url}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 23. CLICK TEXT
# ============================================================

async def browser_click_text(
    text: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            locator = page.get_by_text(
                text,
                exact=True,
            ).first

            await locator.click(
                timeout=15000
            )

            await page.wait_for_timeout(
                500
            )

            return (
                "✅ Клик по тексту выполнен\n"
                f"Text: {text}\n"
                f"URL: {page.url}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 24. FILL
# ============================================================

async def browser_fill(
    selector: str,
    text: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).first.fill(
                text,
                timeout=15000
            )

            return (
                "✅ Поле заполнено\n"
                f"Selector: {selector}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 25. FILL PLACEHOLDER
# ============================================================

async def browser_fill_placeholder(
    placeholder: str,
    text: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.get_by_placeholder(
                placeholder
            ).first.fill(
                text,
                timeout=15000
            )

            return (
                "✅ Поле заполнено\n"
                f"Placeholder: {placeholder}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 26. TYPE
# ============================================================

async def browser_type(
    selector: str,
    text: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).first.type(
                text,
                timeout=15000
            )

            return "✅ Текст введён"

        return await browser_operation(
            operation
        )


# ============================================================
# 27. PRESS
# ============================================================

async def browser_press(
    selector: str,
    key: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).first.press(
                key,
                timeout=15000
            )

            return (
                f"✅ Нажата клавиша: {key}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 28. KEY
# ============================================================

async def browser_key(
    key: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.keyboard.press(
                key
            )

            return (
                f"✅ Клавиша: {key}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 29. WAIT
# ============================================================

async def browser_wait(
    milliseconds: int = 1000
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            milliseconds = max(
                0,
                min(
                    int(milliseconds),
                    30000,
                ),
            )

            await page.wait_for_timeout(
                milliseconds
            )

            return (
                f"✅ Ожидание "
                f"{milliseconds} мс"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 30. WAIT SELECTOR
# ============================================================

async def browser_wait_selector(
    selector: str,
    timeout: int = 10000,
):

    async with browser_lock:

        async def operation():

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

        return await browser_operation(
            operation
        )


# ============================================================
# 31. SELECT
# ============================================================

async def browser_select(
    selector: str,
    value: str,
):

    async with browser_lock:

        async def operation():

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

        return await browser_operation(
            operation
        )


# ============================================================
# 32. CHECK
# ============================================================

async def browser_check(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).check(
                timeout=15000
            )

            return "✅ Checkbox отмечен"

        return await browser_operation(
            operation
        )


# ============================================================
# 33. UNCHECK
# ============================================================

async def browser_uncheck(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).uncheck(
                timeout=15000
            )

            return "✅ Checkbox снят"

        return await browser_operation(
            operation
        )


# ============================================================
# 34. HOVER
# ============================================================

async def browser_hover(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).hover(
                timeout=15000
            )

            return "✅ Наведение выполнено"

        return await browser_operation(
            operation
        )


# ============================================================
# 35. ATTRIBUTE
# ============================================================

async def browser_attribute(
    selector: str,
    attribute: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            value = await page.locator(
                selector
            ).first.get_attribute(
                attribute
            )

            return str(value)

        return await browser_operation(
            operation
        )


# ============================================================
# 36. COUNT
# ============================================================

async def browser_count(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            count = await page.locator(
                selector
            ).count()

            return (
                f"Количество: {count}"
            )

        return await browser_operation(
            operation
        )


# ============================================================
# 37. JAVASCRIPT
# ============================================================

async def browser_js(
    expression: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            result = await page.evaluate(
                expression
            )

            return str(result)[:30000]

        return await browser_operation(
            operation
        )


# ============================================================
# 38. SCREENSHOT
# ============================================================

async def browser_screenshot():

    async with browser_lock:

        async def operation():

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

        return await browser_operation(
            operation
        )


# ============================================================
# 39. CONTENT
# ============================================================

async def browser_content():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            content = await page.content()

            return content[:30000]

        return await browser_operation(
            operation
        )


# ============================================================
# 40. DSPY ASYNC BRIDGE
# ============================================================

def run_async_from_dspy(
    coro
):

    global main_event_loop

    if main_event_loop is None:

        raise RuntimeError(
            "Основной asyncio loop "
            "не установлен"
        )

    if main_event_loop.is_closed():

        raise RuntimeError(
            "Основной asyncio loop закрыт"
        )

    future = (
        asyncio.run_coroutine_threadsafe(
            coro,
            main_event_loop,
        )
    )

    try:

        return future.result(
            timeout=90
        )

    except Exception as e:

        future.cancel()

        raise RuntimeError(
            f"Browser tool error: {e}"
        ) from e


# ============================================================
# 41. DSPY TOOLS
# ============================================================

def create_browser_tools():

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

    def tool_inspect_page():
        return run_async_from_dspy(
            browser_inspect()
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

    def tool_click_text(
        text: str
    ):
        return run_async_from_dspy(
            browser_click_text(text)
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

    def tool_fill_placeholder(
        placeholder: str,
        text: str,
    ):
        return run_async_from_dspy(
            browser_fill_placeholder(
                placeholder,
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

    return [

        Tool(tool_goto),

        Tool(tool_back),

        Tool(tool_forward),

        Tool(tool_reload),

        Tool(tool_page_info),

        Tool(tool_inspect_page),

        Tool(tool_get_text),

        Tool(tool_get_html),

        Tool(tool_get_links),

        Tool(tool_click),

        Tool(tool_click_text),

        Tool(tool_fill),

        Tool(tool_fill_placeholder),

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

    ]


# ============================================================
# 42. AGNES LM
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

        self.temperature = kwargs.get(
            "temperature",
            0.2,
        )

        self.max_tokens = kwargs.get(
            "max_tokens",
            4000,
        )

        super().__init__(
            model=model,
            model_type="chat",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
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

            raise RuntimeError(
                "AGNES_API_KEY не задан"
            )

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

            "model":
                self.model,

            "messages":
                api_messages,

            "temperature":
                params.get(
                    "temperature",
                    self.temperature,
                ),

            "max_tokens":
                params.get(
                    "max_tokens",
                    self.max_tokens,
                ),

        }

        if params.get(
            "tools"
        ):

            payload["tools"] = (
                params["tools"]
            )

        if params.get(
            "tool_choice"
        ):

            payload["tool_choice"] = (
                params["tool_choice"]
            )

        logger.info(
            "🧠 → Agnes API"
        )

        try:

            with httpx.Client(
                timeout=httpx.Timeout(
                    connect=30,
                    read=120,
                    write=120,
                    pool=30,
                )
            ) as client:

                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

        except httpx.HTTPStatusError as e:

            body = e.response.text[:2000]

            logger.error(
                "❌ Agnes HTTP %s: %s",
                e.response.status_code,
                body,
            )

            raise RuntimeError(
                f"Agnes HTTP "
                f"{e.response.status_code}: "
                f"{body}"
            ) from e

        except Exception as e:

            logger.exception(
                "❌ Agnes API"
            )

            raise RuntimeError(
                f"Agnes API error: {e}"
            ) from e

        choices = data.get(
            "choices"
        ) or []

        if not choices:

            raise RuntimeError(
                f"Agnes вернул пустой ответ: "
                f"{data}"
            )

        message = (
            choices[0].get(
                "message"
            )
            or {}
        )

        content = (
            message.get(
                "content"
            )
            or ""
        )

        logger.info(
            "🧠 ← Agnes API"
        )

        return [content]

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
# 43. DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):

    """
    Ты автономный браузерный агент.

    Выполняй задачи пользователя непосредственно
    через Camoufox.

    Правила:

    1. Для открытия сайта используй tool_goto.
    2. Если структура неизвестна — inspect_page.
    3. Для чтения — get_text.
    4. Для поиска элементов — inspect_page.
    5. Для кнопок — click/click_text.
    6. Для полей — fill/fill_placeholder.
    7. Для клавиатуры — press/key.
    8. Не утверждай выполнение действия,
       пока tool не подтвердил его.
    9. При ошибке меняй стратегию.
    10. Можно использовать несколько tools.
    11. Для динамических сайтов используй wait.
    12. Сложные задачи исследуй самостоятельно.
    13. В конце дай только итоговый ответ.
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Краткий итоговый результат"
    )


# ============================================================
# 44. INIT DSPY
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

        dspy.configure(
            lm=lm
        )

        tools = create_browser_tools()

        if REACT_V2_AVAILABLE:

            try:

                dspy_agent_instance = (
                    ReActV2(
                        BrowserTask,
                        tools=tools,
                        max_iters=15,
                    )
                )

                logger.info(
                    "✅ Используется ReActV2"
                )

            except Exception as e:

                logger.warning(
                    "⚠️ ReActV2 error: %s",
                    e,
                )

                dspy_agent_instance = (
                    dspy.ReAct(
                        BrowserTask,
                        tools=tools,
                        max_iters=15,
                    )
                )

                logger.info(
                    "↩️ Используется обычный ReAct"
                )

        else:

            dspy_agent_instance = (
                dspy.ReAct(
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )
            )

            logger.info(
                "✅ Используется обычный ReAct"
            )

        logger.info(
            f"🧠 DSPy создан. "
            f"Tools: {len(tools)}"
        )

        return True

    except Exception as e:

        logger.exception(
            "❌ DSPy init error"
        )

        dspy_agent_instance = None

        return False


# ============================================================
# 45. RUN AGENT
# ============================================================

def run_agent(
    question: str
):

    if not dspy_agent_instance:

        return (
            "❌ DSPy агент не инициализирован"
        )

    with agent_lock:

        try:

            logger.info(
                f"🧠 DSPy task: {question}"
            )

            result = (
                dspy_agent_instance(
                    question=question
                )
            )

            answer = getattr(
                result,
                "answer",
                None,
            )

            if (
                answer is None
                and isinstance(
                    result,
                    dict,
                )
            ):

                answer = result.get(
                    "answer"
                )

            if answer is None:

                answer = str(
                    result
                )

            answer = str(
                answer
            ).strip()

            if not answer:

                return (
                    "❌ Пустой ответ DSPy"
                )

            return answer

        except Exception as e:

            logger.exception(
                "❌ DSPy error"
            )

            return (
                f"❌ Ошибка агента: "
                f"{type(e).__name__}: {e}"
            )


# ============================================================
# 46. START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(

        "👋 Привет!\n\n"

        "🦊 Camoufox + DSPy Browser Agent\n\n"

        "Команды:\n"

        "/check <url>\n"

        "/dspy <задача>\n"

        "/cookies\n"

        "/cancel\n"

        "/status\n"

        "/screenshot"

    )


# ============================================================
# 47. CHECK
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

        result = await browser_goto(
            url
        )

        text = await browser_get_text()

        await msg.edit_text(
            f"{result}\n\n"
            f"{text[:1500]}"
        )

    except Exception as e:

        logger.exception(
            "❌ /check"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n"
            f"{str(e)[:1000]}"
        )


# ============================================================
# 48. SCREENSHOT
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
            "rb"
        ) as photo:

            await update.message.reply_photo(
                photo=photo,
                caption="📸 Текущая страница",
            )

        await msg.delete()

    except Exception as e:

        logger.exception(
            "❌ /screenshot"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n"
            f"{str(e)[:1000]}"
        )


# ============================================================
# 49. STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    url = "—"

    title = "—"

    if browser_ready:

        try:

            page = await get_current_page()

            url = page.url

            title = await page.title()

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
        f"`{escape_markdown(url, version=2)}`\n\n"

        f"📄 Title:\n"
        f"{escape_markdown(title, version=2)}"

    )

    await update.message.reply_text(
        status_text,
        parse_mode="MarkdownV2",
    )


# ============================================================
# 50. COOKIES COMMAND
# ============================================================

async def cookies_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not browser_ready:

        await update.message.reply_text(
            "❌ Camoufox не запущен"
        )

        return

    user_id = (
        update.effective_user.id
    )

    waiting_for_cookies.add(
        user_id
    )

    await update.message.reply_text(

        "🍪 Жду JSON-файл с cookies.\n\n"

        "Отправь файл следующим сообщением.\n\n"

        "❌ Для отмены: /cancel"

    )


# ============================================================
# 51. CANCEL
# ============================================================

async def cancel_cookies(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = (
        update.effective_user.id
    )

    if user_id in waiting_for_cookies:

        waiting_for_cookies.discard(
            user_id
        )

        await update.message.reply_text(
            "❌ Загрузка cookies отменена."
        )

    else:

        await update.message.reply_text(
            "Нечего отменять."
        )


# ============================================================
# 52. COOKIE FILE
# ============================================================

async def cookies_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = (
        update.effective_user.id
    )

    if user_id not in waiting_for_cookies:

        return

    document = (
        update.message.document
    )

    if not document:

        return

    filename = (
        document.file_name
        or ""
    ).lower()

    if not filename.endswith(
        ".json"
    ):

        await update.message.reply_text(
            "❌ Нужен именно JSON-файл."
        )

        return

    waiting_for_cookies.discard(
        user_id
    )

    msg = await update.message.reply_text(
        "⏳ Загружаю cookies..."
    )

    temp_path = (
        f"/tmp/cookies_"
        f"{user_id}_"
        f"{int(time.time())}.json"
    )

    try:

        telegram_file = (
            await context.bot.get_file(
                document.file_id
            )
        )

        await telegram_file.download_to_drive(
            temp_path
        )

        with open(
            temp_path,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        result = (
            await load_cookies_from_json(
                data
            )
        )

        loaded = result[
            "loaded"
        ]

        total = result[
            "total"
        ]

        errors = result[
            "errors"
        ]

        if loaded == 0:

            response = (
                "❌ Не удалось загрузить "
                "ни одной cookie.\n\n"
                + "\n".join(
                    f"• {e}"
                    for e in errors[:15]
                )
            )

        else:

            response = (

                "🍪 *Cookies обработаны!*\n\n"

                f"✅ Загружено: `{loaded}`\n"

                f"📦 Всего в файле: `{total}`"

            )

            if errors:

                response += (
                    "\n\n"
                    "⚠️ Ошибки:\n"
                )

                response += "\n".join(
                    f"• {e}"
                    for e in errors[:10]
                )

                if len(errors) > 10:

                    response += (
                        "\n• ...и ещё "
                        f"{len(errors) - 10}"
                    )

        await msg.edit_text(
            response,
            parse_mode="Markdown",
        )

    except json.JSONDecodeError:

        await msg.edit_text(
            "❌ Файл не является "
            "корректным JSON."
        )

    except Exception as e:

        logger.exception(
            "❌ Ошибка загрузки cookies"
        )

        await msg.edit_text(
            "❌ Ошибка загрузки cookies:\n\n"
            f"{str(e)[:2000]}"
        )

    finally:

        try:

            if os.path.exists(
                temp_path
            ):

                os.remove(
                    temp_path
                )

        except Exception:

            pass


# ============================================================
# 53. DSPY COMMAND
# ============================================================

async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(

            "🧠 DSPy Browser Agent\n\n"

            "Примеры:\n\n"

            "/dspy открой https://example.com "
            "и покажи заголовок\n\n"

            "/dspy найди новости про Трампа "
            "на BBC и кратко перескажи 5 последних\n\n"

            "/dspy открой Google и найди Python"

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

        loop = (
            asyncio.get_running_loop()
        )

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

        safe_answer = (
            escape_markdown(
                answer,
                version=2,
            )
        )

        await msg.edit_text(

            "✅ *Результат:*\n\n"
            + safe_answer,

            parse_mode="MarkdownV2",

        )

    except Exception as e:

        logger.exception(
            "❌ /dspy"
        )

        await msg.edit_text(
            f"❌ Ошибка:\n"
            f"{str(e)[:1000]}"
        )


# ============================================================
# 54. TELEGRAM ERROR HANDLER
# ============================================================

async def telegram_error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "❌ Telegram error",
        exc_info=context.error,
    )


# ============================================================
# 55. MAIN
# ============================================================

async def main():

    global main_event_loop

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

    app.add_error_handler(
        telegram_error_handler
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

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

    app.add_handler(
        CommandHandler(
            "cookies",
            cookies_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel_cookies,
        )
    )

    # --------------------------------------------------------
    # JSON FILE
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            cookies_file,
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

        stop_signal = (
            asyncio.Event()
        )

        def signal_handler():

            logger.info(
                "🛑 Получен сигнал остановки"
            )

            stop_signal.set()

        try:

            loop = (
                asyncio.get_running_loop()
            )

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

            await asyncio.sleep(
                60
            )

            logger.info(
                "💓 Bot alive"
            )

    except Exception as e:

        logger.exception(
            f"❌ Main error: {e}"
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
# 56. ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )