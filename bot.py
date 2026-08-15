
import os
import asyncio
import logging
import time
import signal
import threading
import json
import re
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
from dspy import Signature, InputField, OutputField, Tool

try:
    from dspy import ReActV2
    REACT_V2_AVAILABLE = True
except ImportError:
    ReActV2 = None
    REACT_V2_AVAILABLE = False

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    AsyncCamoufox = None
    CAMOUFOX_AVAILABLE = False


# ============================================================
# LOGGER / SETTINGS
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

SCREENSHOTS_DIR = "/app/screenshots"
CAMOUFOX_PROFILE = "/app/camoufox-profile"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(CAMOUFOX_PROFILE, exist_ok=True)


# ============================================================
# GLOBAL STATE
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
# CAMOUFOX
# ============================================================

async def init_browser():
    global camoufox_manager
    global camoufox_context
    global current_page
    global browser_ready

    if not CAMOUFOX_AVAILABLE:
        logger.error("Camoufox не установлен")
        return False

    logger.info("Запускаем Camoufox...")

    try:
        camoufox_manager = AsyncCamoufox(
            headless=True,
            persistent_context=True,
            user_data_dir=CAMOUFOX_PROFILE,
        )

        camoufox_context = await camoufox_manager.__aenter__()

        if camoufox_context is None:
            raise RuntimeError("Camoufox вернул None")

        current_page = await camoufox_context.new_page()

        await current_page.goto(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        logger.info(
            "Camoufox работает: %s",
            await current_page.title(),
        )

        browser_ready = True
        return True

    except Exception as e:
        logger.exception(
            "Ошибка запуска Camoufox: %s",
            e,
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
            logger.info("Закрываем Camoufox...")

            await camoufox_manager.__aexit__(
                None,
                None,
                None,
            )

        except Exception as e:
            logger.warning(
                "Ошибка закрытия Camoufox: %s",
                e,
            )

    camoufox_manager = None
    camoufox_context = None

    logger.info("Camoufox закрыт")


async def page_is_alive(page):
    try:
        if page is None or page.is_closed():
            return False

        await page.title()

        return True

    except Exception:
        return False


async def get_current_page():
    global current_page

    if not browser_ready:
        raise RuntimeError("Camoufox не запущен")

    if camoufox_context is None:
        raise RuntimeError("BrowserContext отсутствует")

    if await page_is_alive(current_page):
        return current_page

    logger.warning("Текущая страница закрыта")

    try:
        current_page = await camoufox_context.new_page()
        return current_page

    except Exception:
        await close_browser()

        if not await init_browser():
            raise RuntimeError(
                "Не удалось восстановить Camoufox"
            )

        return current_page


def is_browser_closed_error(error):
    text = str(error).lower()

    patterns = (
        "targetclosederror",
        "target page",
        "browser has been closed",
        "browsercontext",
        "context has been closed",
        "page has been closed",
        "target has been closed",
    )

    return any(x in text for x in patterns)


async def browser_operation(operation):
    global current_page

    try:
        return await operation()

    except Exception as e:

        if not is_browser_closed_error(e):
            raise

        logger.warning(
            "Camoufox закрыт. Восстанавливаем..."
        )

        current_page = None

        await close_browser()

        if not await init_browser():
            raise RuntimeError(
                "Camoufox не удалось восстановить"
            )

        return await operation()


# ============================================================
# COOKIE NORMALIZATION
# ============================================================

def normalize_cookie(cookie: dict):
    if not isinstance(cookie, dict):
        raise ValueError(
            "Cookie должен быть объектом"
        )

    name = cookie.get("name")

    if not name:
        raise ValueError(
            "Cookie не содержит name"
        )

    result = {
        "name": str(name),
        "value": str(
            cookie.get("value", "")
        ),
    }

    domain = cookie.get("domain")

    if domain and not isinstance(domain, bool):

        domain = str(domain).strip()

        domain = re.sub(
            r"^https?://",
            "",
            domain,
        )

        domain = domain.split(
            "/",
            1,
        )[0]

        if domain:
            result["domain"] = domain

    url = cookie.get("url")

    if url:

        url = str(url).strip()

        if url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            result["url"] = url

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

    path = str(
        cookie.get("path") or "/"
    )

    result["path"] = (
        path
        if path.startswith("/")
        else "/" + path
    )

    result["secure"] = bool(
        cookie.get(
            "secure",
            False,
        )
    )

    result["httpOnly"] = bool(
        cookie.get(
            "httpOnly",
            False,
        )
    )

    same_site = cookie.get(
        "sameSite"
    )

    if same_site:

        same_site = (
            str(same_site)
            .strip()
            .lower()
        )

        result["sameSite"] = {
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

    expires = cookie.get(
        "expires",
        cookie.get(
            "expirationDate"
        ),
    )

    if expires is not None:

        try:

            expires = float(expires)

            if expires > 0:
                result["expires"] = expires

        except (
            ValueError,
            TypeError,
        ):
            pass

    return result


async def load_cookies_from_json(data):

    if isinstance(data, dict):

        cookies = data.get(
            "cookies"
        )

        if cookies is None:
            raise ValueError(
                "JSON должен содержать "
                "поле 'cookies'"
            )

    elif isinstance(data, list):

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

    for index, cookie in enumerate(
        cookies
    ):

        try:

            normalized.append(
                normalize_cookie(
                    cookie
                )
            )

        except Exception as e:

            errors.append(
                f"Cookie #{index + 1}: {e}"
            )

    if not normalized:

        raise ValueError(
            "Не удалось обработать "
            "ни одного cookie:\n"
            + "\n".join(
                errors[:20]
            )
        )

    async with browser_lock:

        async def operation():

            if camoufox_context is None:
                raise RuntimeError(
                    "BrowserContext отсутствует"
                )

            loaded = 0
            load_errors = list(errors)

            for index, cookie in enumerate(
                normalized
            ):

                try:

                    await camoufox_context.add_cookies(
                        [cookie]
                    )

                    loaded += 1

                except Exception as e:

                    name = cookie.get(
                        "name",
                        "unknown",
                    )

                    load_errors.append(
                        f"Cookie #{index + 1} "
                        f"({name}): {e}"
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
# BASIC BROWSER TOOLS
# ============================================================

async def browser_goto(url: str):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            return (
                f"Открыто\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


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
                    "Назад перейти невозможно\n"
                    f"URL: {page.url}"
                )

            return (
                f"Назад\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


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
                    "Вперёд перейти невозможно\n"
                    f"URL: {page.url}"
                )

            return (
                f"Вперёд\n"
                f"URL: {page.url}\n"
                f"Title: {await page.title()}"
            )

        return await browser_operation(
            operation
        )


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


async def browser_page_info():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}\n"
                f"Pages: "
                f"{len(camoufox_context.pages)}"
            )

        return await browser_operation(
            operation
        )


async def browser_get_text(
    selector="body"
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            text = await page.locator(
                selector
            ).inner_text(
                timeout=10000
            )

            return (
                text[:20000]
                if text
                else "Текст не найден"
            )

        return await browser_operation(
            operation
        )


async def browser_get_html(
    selector="body"
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


async def browser_get_links():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            links = await page.locator(
                "a"
            ).evaluate_all(
                """
                els => els.map(e => ({
                    text: (e.innerText || '').trim(),
                    href: e.href || ''
                })).filter(x => x.href)
                """
            )

            if not links:
                return "Ссылок не найдено"

            return "\n".join(
                f"- {x.get('text','')[:120]} "
                f"→ {x.get('href','')}"
                for x in links[:200]
            )

        return await browser_operation(
            operation
        )


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
                "Клик выполнен\n"
                f"Selector: {selector}\n"
                f"URL: {page.url}"
            )

        return await browser_operation(
            operation
        )


async def browser_click_text(
    text: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.get_by_text(
                text,
                exact=True,
            ).first.click(
                timeout=15000
            )

            await page.wait_for_timeout(
                500
            )

            return (
                "Клик по тексту выполнен\n"
                f"Text: {text}\n"
                f"URL: {page.url}"
            )

        return await browser_operation(
            operation
        )


async def browser_click_role(
    role: str,
    name: str = "",
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            locator = page.get_by_role(
                role,
                name=name or None,
            ).first

            await locator.click(
                timeout=15000
            )

            await page.wait_for_timeout(
                500
            )

            return (
                "Semantic click выполнен\n"
                f"Role: {role}\n"
                f"Name: {name}\n"
                f"URL: {page.url}"
            )

        return await browser_operation(
            operation
        )


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
                timeout=15000,
            )

            return (
                "Поле заполнено\n"
                f"Selector: {selector}"
            )

        return await browser_operation(
            operation
        )


async def browser_fill_label(
    label: str,
    text: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.get_by_label(
                label,
                exact=True,
            ).first.fill(
                text,
                timeout=15000,
            )

            return (
                "Поле заполнено\n"
                f"Label: {label}"
            )

        return await browser_operation(
            operation
        )


async def browser_fill_placeholder(
    placeholder: str,
    text: str,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.get_by_placeholder(
                placeholder,
                exact=True,
            ).first.fill(
                text,
                timeout=15000,
            )

            return (
                "Поле заполнено\n"
                f"Placeholder: {placeholder}"
            )

        return await browser_operation(
            operation
        )


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
                timeout=15000,
            )

            return "Текст введён"

        return await browser_operation(
            operation
        )


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
                timeout=15000,
            )

            return (
                f"Нажата клавиша: {key}"
            )

        return await browser_operation(
            operation
        )


async def browser_key(key: str):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.keyboard.press(key)

            return (
                f"Клавиша: {key}"
            )

        return await browser_operation(
            operation
        )


async def browser_wait(
    milliseconds=1000
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
                f"Ожидание "
                f"{milliseconds} мс"
            )

        return await browser_operation(
            operation
        )


async def browser_wait_selector(
    selector: str,
    timeout=10000,
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            await page.locator(
                selector
            ).wait_for(
                state="visible",
                timeout=int(timeout),
            )

            return (
                f"Элемент найден: "
                f"{selector}"
            )

        return await browser_operation(
            operation
        )


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

            return f"Выбрано: {result}"

        return await browser_operation(
            operation
        )


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

            return "Checkbox отмечен"

        return await browser_operation(
            operation
        )


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

            return "Checkbox снят"

        return await browser_operation(
            operation
        )


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

            return "Наведение выполнено"

        return await browser_operation(
            operation
        )


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


async def browser_count(
    selector: str
):

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            return (
                "Количество: "
                f"{await page.locator(selector).count()}"
            )

        return await browser_operation(
            operation
        )


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


async def browser_content():

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            return (
                await page.content()
            )[:30000]

        return await browser_operation(
            operation
        )


# ============================================================
# ADVANCED INSPECTOR
# ============================================================

INSPECTOR_JS = r"""
({
    maxInteractive,
    maxLinks,
    maxText,
    includeHidden
}) => {

    const clean = value =>
        String(value ?? "")
            .replace(/\s+/g, " ")
            .trim();

    const cssEscape = value => {
        value = String(value ?? "");

        if (
            window.CSS &&
            typeof CSS.escape === "function"
        ) {
            return CSS.escape(value);
        }

        return value.replace(
            /([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g,
            "\\$1"
        );
    };

    const visible = element => {

        if (
            !element ||
            !(element instanceof Element)
        ) {
            return false;
        }

        const style =
            window.getComputedStyle(element);

        if (
            style.display === "none" ||
            style.visibility === "hidden" ||
            style.visibility === "collapse" ||
            style.opacity === "0"
        ) {
            return false;
        }

        const rect =
            element.getBoundingClientRect();

        return (
            rect.width > 0 &&
            rect.height > 0
        );
    };

    const inViewport = element => {

        if (!element) return false;

        const rect =
            element.getBoundingClientRect();

        return (
            rect.bottom > 0 &&
            rect.right > 0 &&
            rect.top < window.innerHeight &&
            rect.left < window.innerWidth
        );
    };

    const enabled = element => {

        if (!element) return false;

        return (
            !element.hasAttribute("disabled") &&
            element.getAttribute(
                "aria-disabled"
            ) !== "true"
        );
    };

    const textOf = element => {

        if (!element) return "";

        return clean(
            element.innerText ||
            element.getAttribute(
                "aria-label"
            ) ||
            element.getAttribute(
                "title"
            ) ||
            element.getAttribute(
                "alt"
            ) ||
            element.value ||
            ""
        );
    };

    const accessibleName = element => {

        if (!element) return "";

        const ariaLabel =
            clean(
                element.getAttribute(
                    "aria-label"
                )
            );

        if (ariaLabel) {
            return ariaLabel;
        }

        const labelledBy =
            clean(
                element.getAttribute(
                    "aria-labelledby"
                )
            );

        if (labelledBy) {

            const ids =
                labelledBy.split(/\s+/);

            const text = ids
                .map(id => {
                    const node =
                        document.getElementById(
                            id
                        );

                    return node
                        ? clean(node.innerText)
                        : "";
                })
                .filter(Boolean)
                .join(" ");

            if (text) return text;
        }

        const id =
            element.getAttribute("id");

        if (id) {

            const label =
                document.querySelector(
                    `label[for="${cssEscape(id)}"]`
                );

            if (label) {
                return clean(
                    label.innerText
                );
            }
        }

        const parentLabel =
            element.closest("label");

        if (parentLabel) {
            return clean(
                parentLabel.innerText
            );
        }

        return textOf(element);
    };

    const roleOf = element => {

        const explicit =
            clean(
                element.getAttribute("role")
            );

        if (explicit) return explicit;

        const tag =
            element.tagName.toLowerCase();

        const type =
            clean(
                element.getAttribute("type")
            ).toLowerCase();

        if (tag === "button") {
            return "button";
        }

        if (
            tag === "a" &&
            element.hasAttribute("href")
        ) {
            return "link";
        }

        if (tag === "textarea") {
            return "textbox";
        }

        if (tag === "select") {
            return "combobox";
        }

        if (tag === "input") {

            if (
                [
                    "checkbox"
                ].includes(type)
            ) {
                return "checkbox";
            }

            if (
                [
                    "radio"
                ].includes(type)
            ) {
                return "radio";
            }

            if (
                [
                    "button",
                    "submit",
                    "reset"
                ].includes(type)
            ) {
                return "button";
            }

            return "textbox";
        }

        if (
            element.getAttribute(
                "contenteditable"
            ) === "true"
        ) {
            return "textbox";
        }

        return "";
    };

    const nthOfType = element => {

        if (
            !element ||
            !element.parentElement
        ) {
            return 1;
        }

        const siblings =
            [
                ...element.parentElement.children
            ].filter(
                x =>
                    x.tagName ===
                    element.tagName
            );

        return (
            siblings.indexOf(element) + 1
        );
    };

    const stableClass = value => {

        if (!value) return false;

        const x = String(value);

        if (x.length > 80) {
            return false;
        }

        if (
            /(^|[-_])(
                css|jsx|emotion|styled|sc|
                ng|chakra|mantine
            )/ix.test(x)
        ) {
            return false;
        }

        if (
            /[a-f0-9]{8,}/i.test(x)
        ) {
            return false;
        }

        if (
            /[0-9]{3,}/.test(x)
        ) {
            return false;
        }

        return /^[A-Za-z_][A-Za-z0-9_-]*$/.test(x);
    };

    const uniqueSelector = element => {

        if (
            !element ||
            !(element instanceof Element)
        ) {
            return "";
        }

        if (element.id) {

            const selector =
                "#" +
                cssEscape(
                    element.id
                );

            try {

                if (
                    document.querySelectorAll(
                        selector
                    ).length === 1
                ) {
                    return selector;
                }

            } catch (_) {}
        }

        const priorityAttributes = [
            "data-testid",
            "data-test",
            "data-qa",
            "data-cy",
            "name"
        ];

        for (
            const attribute
            of priorityAttributes
        ) {

            const value =
                element.getAttribute(
                    attribute
                );

            if (!value) continue;

            const selector =
                `${element.tagName.toLowerCase()}` +
                `[${attribute}="${cssEscape(value)}"]`;

            try {

                if (
                    document.querySelectorAll(
                        selector
                    ).length === 1
                ) {
                    return selector;
                }

            } catch (_) {}
        }

        const parts = [];
        let node = element;

        while (
            node &&
            node.nodeType === 1 &&
            node !== document.body
        ) {

            let part =
                node.tagName.toLowerCase();

            if (node.id) {

                parts.unshift(
                    "#" +
                    cssEscape(
                        node.id
                    )
                );

                break;
            }

            const classes =
                [
                    ...node.classList
                ]
                .filter(stableClass)
                .slice(0, 2);

            if (classes.length) {

                part += classes
                    .map(
                        c =>
                            "." +
                            cssEscape(c)
                    )
                    .join("");
            }

            const index =
                nthOfType(node);

            if (index > 1) {
                part +=
                    `:nth-of-type(${index})`;
            }

            parts.unshift(part);

            const candidate =
                parts.join(" > ");

            try {

                if (
                    document.querySelectorAll(
                        candidate
                    ).length === 1
                ) {
                    return candidate;
                }

            } catch (_) {}

            node =
                node.parentElement;
        }

        return parts.join(" > ");
    };

    const xpath = element => {

        if (
            !element ||
            element.nodeType !== 1
        ) {
            return "";
        }

        if (element.id) {

            return (
                `//*[@id="` +
                String(
                    element.id
                ).replace(
                    /"/g,
                    "&quot;"
                ) +
                `"]`
            );
        }

        const parts = [];
        let node = element;

        while (
            node &&
            node.nodeType === 1
        ) {

            let index = 1;
            let sibling =
                node.previousElementSibling;

            while (sibling) {

                if (
                    sibling.tagName ===
                    node.tagName
                ) {
                    index++;
                }

                sibling =
                    sibling.previousElementSibling;
            }

            parts.unshift(
                `${node.tagName.toLowerCase()}[${index}]`
            );

            node =
                node.parentElement;
        }

        return (
            "/" +
            parts.join("/")
        );
    };

    const selectorForLabel = element => {

        const label =
            accessibleName(element);

        return label
            ? `get_by_label("${label}")`
            : "";
    };

    const semanticLocator = element => {

        const role =
            roleOf(element);

        const name =
            accessibleName(element);

        if (
            role &&
            name &&
            [
                "button",
                "link",
                "checkbox",
                "radio",
                "tab",
                "menuitem",
                "combobox",
                "textbox"
            ].includes(role)
        ) {
            return (
                `get_by_role("${role}", ` +
                `name="${name}")`
            );
        }

        const placeholder =
            clean(
                element.getAttribute(
                    "placeholder"
                )
            );

        if (
            placeholder &&
            [
                "input",
                "textarea"
            ].includes(
                element.tagName.toLowerCase()
            )
        ) {
            return (
                `get_by_placeholder(` +
                `"${placeholder}")`
            );
        }

        if (name) {
            return (
                `get_by_text("${name}")`
            );
        }

        return "";
    };

    const hitTest = element => {

        if (!visible(element)) {
            return {
                clickable: false,
                reason: "not-visible"
            };
        }

        const rect =
            element.getBoundingClientRect();

        const x =
            Math.round(
                rect.left +
                rect.width / 2
            );

        const y =
            Math.round(
                rect.top +
                rect.height / 2
            );

        if (
            x < 0 ||
            y < 0 ||
            x >= window.innerWidth ||
            y >= window.innerHeight
        ) {
            return {
                clickable: false,
                reason: "outside-viewport",
                point: {x, y}
            };
        }

        const top =
            document.elementFromPoint(
                x,
                y
            );

        if (!top) {

            return {
                clickable: false,
                reason: "no-hit-target",
                point: {x, y}
            };
        }

        const same =
            top === element ||
            element.contains(top);

        return {
            clickable:
                same &&
                enabled(element),
            covered:
                !same,
            topTag:
                top.tagName
                    ? top.tagName.toLowerCase()
                    : "",
            topText:
                textOf(top).slice(
                    0,
                    120
                ),
            point: {x, y}
        };
    };

    const describe = (
        element,
        index,
        frameUrl,
        shadow
    ) => {

        const rect =
            element.getBoundingClientRect();

        const style =
            window.getComputedStyle(
                element
            );

        const type =
            clean(
                element.getAttribute(
                    "type"
                )
            );

        const hit =
            hitTest(element);

        return {
            index,

            tag:
                element.tagName.toLowerCase(),

            role:
                roleOf(element),

            text:
                textOf(element).slice(
                    0,
                    300
                ),

            accessibleName:
                accessibleName(
                    element
                ).slice(
                    0,
                    300
                ),

            selector:
                uniqueSelector(
                    element
                ),

            xpath:
                xpath(element),

            semanticLocator:
                semanticLocator(
                    element
                ),

            labelLocator:
                selectorForLabel(
                    element
                ),

            id:
                clean(
                    element.id
                ),

            name:
                clean(
                    element.getAttribute(
                        "name"
                    )
                ),

            type,

            placeholder:
                clean(
                    element.getAttribute(
                        "placeholder"
                    )
                ),

            value:
                clean(
                    element.value
                ).slice(
                    0,
                    300
                ),

            href:
                clean(
                    element.getAttribute(
                        "href"
                    )
                ),

            title:
                clean(
                    element.getAttribute(
                        "title"
                    )
                ),

            autocomplete:
                clean(
                    element.getAttribute(
                        "autocomplete"
                    )
                ),

            aria: {
                label:
                    clean(
                        element.getAttribute(
                            "aria-label"
                        )
                    ),

                labelledby:
                    clean(
                        element.getAttribute(
                            "aria-labelledby"
                        )
                    ),

                describedby:
                    clean(
                        element.getAttribute(
                            "aria-describedby"
                        )
                    ),

                expanded:
                    element.getAttribute(
                        "aria-expanded"
                    ),

                controls:
                    element.getAttribute(
                        "aria-controls"
                    ),

                haspopup:
                    element.getAttribute(
                        "aria-haspopup"
                    ),

                selected:
                    element.getAttribute(
                        "aria-selected"
                    ),

                checked:
                    element.getAttribute(
                        "aria-checked"
                    ),

                pressed:
                    element.getAttribute(
                        "aria-pressed"
                    ),

                current:
                    element.getAttribute(
                        "aria-current"
                    ),

                disabled:
                    element.getAttribute(
                        "aria-disabled"
                    )
            },

            state: {
                visible:
                    visible(element),

                inViewport:
                    inViewport(element),

                enabled:
                    enabled(element),

                disabled:
                    element.hasAttribute(
                        "disabled"
                    ),

                checked:
                    "checked" in element
                        ? !!element.checked
                        : false,

                selected:
                    "selected" in element
                        ? !!element.selected
                        : false,

                required:
                    element.hasAttribute(
                        "required"
                    ),

                readonly:
                    element.hasAttribute(
                        "readonly"
                    ),

                contenteditable:
                    element.getAttribute(
                        "contenteditable"
                    ) === "true",

                focused:
                    document.activeElement ===
                    element,

                clickable:
                    !!hit.clickable,

                covered:
                    !!hit.covered
            },

            hitTest: hit,

            rect: {
                x:
                    Math.round(rect.x),

                y:
                    Math.round(rect.y),

                width:
                    Math.round(rect.width),

                height:
                    Math.round(rect.height)
            },

            style: {
                display:
                    style.display,

                visibility:
                    style.visibility,

                pointerEvents:
                    style.pointerEvents,

                position:
                    style.position,

                zIndex:
                    style.zIndex
            },

            frameUrl:
                frameUrl || location.href,

            shadowRoot:
                !!shadow
        };
    };

    const isInteractive = element => {

        if (
            !element ||
            !(element instanceof Element)
        ) {
            return false;
        }

        const tag =
            element.tagName.toLowerCase();

        const role =
            element.getAttribute("role");

        const tabindex =
            element.getAttribute(
                "tabindex"
            );

        const contenteditable =
            element.getAttribute(
                "contenteditable"
            );

        return (
            [
                "button",
                "a",
                "input",
                "textarea",
                "select",
                "option"
            ].includes(tag) ||

            [
                "button",
                "link",
                "textbox",
                "combobox",
                "checkbox",
                "radio",
                "tab",
                "menuitem",
                "switch",
                "slider",
                "spinbutton",
                "searchbox"
            ].includes(role) ||

            contenteditable === "true" ||

            (
                tabindex !== null &&
                tabindex !== "-1"
            )
        );
    };

    const allElements = [];

    const walk = (
        root,
        shadow = false
    ) => {

        const elements =
            root.querySelectorAll
                ? root.querySelectorAll("*")
                : [];

        for (
            const element
            of elements
        ) {

            allElements.push({
                element,
                shadow
            });

            if (
                element.shadowRoot
            ) {

                walk(
                    element.shadowRoot,
                    true
                );
            }
        }
    };

    walk(document);

    const interactive =
        [];

    for (
        const item
        of allElements
    ) {

        const element =
            item.element;

        if (
            !isInteractive(element)
        ) {
            continue;
        }

        if (
            !includeHidden &&
            !visible(element)
        ) {
            continue;
        }

        interactive.push(
            describe(
                element,
                interactive.length + 1,
                location.href,
                item.shadow
            )
        );

        if (
            interactive.length >=
            maxInteractive
        ) {
            break;
        }
    }

    const links =
        allElements
            .filter(
                item =>
                    item.element.tagName
                        .toLowerCase() === "a"
            )
            .filter(
                item =>
                    item.element.hasAttribute(
                        "href"
                    )
            )
            .filter(
                item =>
                    includeHidden ||
                    visible(item.element)
            )
            .slice(
                0,
                maxLinks
            )
            .map(
                (item, i) => ({
                    index: i + 1,

                    text:
                        textOf(
                            item.element
                        ).slice(
                            0,
                            200
                        ),

                    href:
                        item.element.href,

                    selector:
                        uniqueSelector(
                            item.element
                        ),

                    semanticLocator:
                        semanticLocator(
                            item.element
                        ),

                    visible:
                        visible(
                            item.element
                        ),

                    shadowRoot:
                        item.shadow
                })
            );

    const forms =
        [
            ...document.forms
        ].map(
            (form, i) => ({
                index: i + 1,

                selector:
                    uniqueSelector(
                        form
                    ),

                action:
                    form.action || "",

                method:
                    (
                        form.method ||
                        "get"
                    ).toUpperCase(),

                name:
                    clean(
                        form.getAttribute(
                            "name"
                        )
                    ),

                id:
                    clean(form.id),

                fields:
                    [
                        ...form.elements
                    ]
                    .slice(
                        0,
                        100
                    )
                    .map(
                        (element, j) => ({
                            index: j + 1,

                            tag:
                                element.tagName
                                    .toLowerCase(),

                            type:
                                clean(
                                    element.getAttribute(
                                        "type"
                                    )
                                ),

                            name:
                                clean(
                                    element.getAttribute(
                                        "name"
                                    )
                                ),

                            id:
                                clean(
                                    element.id
                                ),

                            placeholder:
                                clean(
                                    element.getAttribute(
                                        "placeholder"
                                    )
                                ),

                            accessibleName:
                                accessibleName(
                                    element
                                ),

                            selector:
                                uniqueSelector(
                                    element
                                ),

                            semanticLocator:
                                semanticLocator(
                                    element
                                ),

                            required:
                                element.hasAttribute(
                                    "required"
                                ),

                            disabled:
                                element.hasAttribute(
                                    "disabled"
                                )
                        })
                    )
            })
        );

    const headings =
        allElements
            .filter(
                item =>
                    /^H[1-6]$/.test(
                        item.element.tagName
                    )
            )
            .filter(
                item =>
                    includeHidden ||
                    visible(item.element)
            )
            .slice(
                0,
                100
            )
            .map(
                item => ({
                    level:
                        Number(
                            item.element.tagName
                                .substring(1)
                        ),

                    text:
                        clean(
                            item.element.innerText
                        ).slice(
                            0,
                            300
                        ),

                    selector:
                        uniqueSelector(
                            item.element
                        )
                })
            );

    const tables =
        [
            ...document.querySelectorAll(
                "table"
            )
        ]
        .filter(
            x =>
                includeHidden ||
                visible(x)
        )
        .slice(
            0,
            30
        )
        .map(
            (table, i) => ({
                index: i + 1,

                selector:
                    uniqueSelector(
                        table
                    ),

                caption:
                    clean(
                        table.querySelector(
                            "caption"
                        )?.innerText
                    ),

                headers:
                    [
                        ...table.querySelectorAll(
                            "th"
                        )
                    ]
                    .slice(
                        0,
                        30
                    )
                    .map(
                        x =>
                            clean(
                                x.innerText
                            )
                    ),

                rows:
                    [
                        ...table.querySelectorAll(
                            "tr"
                        )
                    ]
                    .slice(
                        0,
                        10
                    )
                    .map(
                        row =>
                            [
                                ...row.querySelectorAll(
                                    "th,td"
                                )
                            ]
                            .slice(
                                0,
                                20
                            )
                            .map(
                                cell =>
                                    clean(
                                        cell.innerText
                                    ).slice(
                                        0,
                                        150
                                    )
                            )
                    )
            })
        );

    const dialogs =
        allElements
            .filter(
                item => {

                    const role =
                        item.element.getAttribute(
                            "role"
                        );

                    const tag =
                        item.element.tagName
                            .toLowerCase();

                    return (
                        role === "dialog" ||
                        role === "alertdialog" ||
                        tag === "dialog"
                    );
                }
            )
            .filter(
                item =>
                    includeHidden ||
                    visible(item.element)
            )
            .slice(
                0,
                30
            )
            .map(
                (item, i) => ({
                    index: i + 1,

                    role:
                        item.element.getAttribute(
                            "role"
                        ),

                    text:
                        clean(
                            item.element.innerText
                        ).slice(
                            0,
                            1000
                        ),

                    accessibleName:
                        accessibleName(
                            item.element
                        ),

                    selector:
                        uniqueSelector(
                            item.element
                        ),

                    semanticLocator:
                        semanticLocator(
                            item.element
                        )
                })
            );

    const iframes =
        [
            ...document.querySelectorAll(
                "iframe,frame"
            )
        ]
        .slice(
            0,
            50
        )
        .map(
            (element, i) => ({
                index: i + 1,

                selector:
                    uniqueSelector(
                        element
                    ),

                src:
                    element.src ||
                    element.getAttribute(
                        "src"
                    ) ||
                    "",

                name:
                    clean(
                        element.getAttribute(
                            "name"
                        )
                    ),

                title:
                    clean(
                        element.getAttribute(
                            "title"
                        )
                    ),

                visible:
                    visible(element)
            })
        );

    const meta =
        [
            ...document.querySelectorAll(
                "meta[name],meta[property]"
            )
        ]
        .slice(
            0,
            80
        )
        .map(
            element => ({
                name:
                    element.getAttribute(
                        "name"
                    ) ||
                    element.getAttribute(
                        "property"
                    ) ||
                    "",

                content:
                    clean(
                        element.getAttribute(
                            "content"
                        )
                    ).slice(
                        0,
                        500
                    )
            })
        );

    const bodyClone =
        document.body
            ? document.body.cloneNode(
                true
            )
            : null;

    if (bodyClone) {

        bodyClone
            .querySelectorAll(
                "script,style,noscript,svg,path,template"
            )
            .forEach(
                x => x.remove()
            );
    }

    const visibleText =
        clean(
            bodyClone?.innerText || ""
        ).slice(
            0,
            maxText
        );

    const active =
        document.activeElement;

    return {

        url:
            location.href,

        title:
            document.title,

        lang:
            document.documentElement
                .lang || "",

        readyState:
            document.readyState,

        viewport: {
            width:
                window.innerWidth,

            height:
                window.innerHeight,

            scrollX:
                Math.round(
                    window.scrollX
                ),

            scrollY:
                Math.round(
                    window.scrollY
                ),

            documentWidth:
                document.documentElement
                    .scrollWidth,

            documentHeight:
                document.documentElement
                    .scrollHeight
        },

        activeElement: active
            ? {
                tag:
                    active.tagName
                        ?.toLowerCase(),

                text:
                    textOf(active)
                        .slice(
                            0,
                            200
                        ),

                selector:
                    uniqueSelector(
                        active
                    )
            }
            : null,

        interactive,

        links,

        forms,

        headings,

        tables,

        dialogs,

        iframes,

        meta,

        shadowDomElements:
            interactive.filter(
                x =>
                    x.shadowRoot
            ).length,

        visibleText
    };
}
"""


async def inspect_frame(
    frame,
    max_interactive,
    max_links,
    max_text,
    include_hidden,
):

    try:

        return await frame.evaluate(
            INSPECTOR_JS,
            {
                "maxInteractive":
                    int(max_interactive),

                "maxLinks":
                    int(max_links),

                "maxText":
                    int(max_text),

                "includeHidden":
                    bool(include_hidden),
            },
        )

    except Exception as e:

        return {
            "url":
                getattr(
                    frame,
                    "url",
                    ""
                ),

            "title":
                "",

            "error":
                str(e)[:1000],

            "interactive":
                [],

            "links":
                [],

            "forms":
                [],

            "headings":
                [],

            "tables":
                [],

            "dialogs":
                [],

            "iframes":
                [],

            "meta":
                [],

            "visibleText":
                ""
        }


async def browser_inspect(
    max_interactive=150,
    max_links=100,
    max_text=15000,
    include_hidden=False,
    inspect_frames=True,
):

    """
    Advanced browser inspector.

    Анализирует:
      - main document
      - Playwright frames
      - shadow DOM
      - interactive elements
      - semantic locators
      - CSS selectors
      - XPath
      - ARIA
      - element state
      - hit testing
      - overlays/covered elements
      - viewport
      - forms
      - dialogs
      - links
      - tables
      - headings
      - active element
      - visible text
    """

    async with browser_lock:

        async def operation():

            page = await get_current_page()

            frames_data = []

            frames = (
                page.frames
                if inspect_frames
                else [page.main_frame]
            )

            for frame_index, frame in enumerate(
                frames
            ):

                data = await inspect_frame(
                    frame,
                    max_interactive,
                    max_links,
                    max_text,
                    include_hidden,
                )

                data["frameIndex"] = (
                    frame_index
                )

                data["isMainFrame"] = (
                    frame == page.main_frame
                )

                data["frameUrl"] = (
                    frame.url
                )

                frames_data.append(data)

            main_data = (
                frames_data[0]
                if frames_data
                else {
                    "url": page.url,
                    "title": await page.title(),
                    "interactive": [],
                    "links": [],
                    "forms": [],
                    "headings": [],
                    "tables": [],
                    "dialogs": [],
                    "iframes": [],
                    "meta": [],
                    "visibleText": "",
                }
            )

            out = []

            out.append(
                "=== PAGE ==="
            )

            out.append(
                f"URL: {main_data.get('url', page.url)}"
            )

            out.append(
                f"TITLE: {main_data.get('title', '')}"
            )

            out.append(
                f"LANG: {main_data.get('lang', '')}"
            )

            out.append(
                "READY STATE: "
                f"{main_data.get('readyState', '')}"
            )

            vp = main_data.get(
                "viewport",
                {}
            )

            out.append(
                "VIEWPORT: "
                f"{vp.get('width', '?')}x"
                f"{vp.get('height', '?')} "
                f"scroll=("
                f"{vp.get('scrollX', '?')},"
                f"{vp.get('scrollY', '?')}) "
                f"document="
                f"{vp.get('documentWidth', '?')}x"
                f"{vp.get('documentHeight', '?')}"
            )

            active = main_data.get(
                "activeElement"
            )

            if active:

                out.append(
                    "\n=== ACTIVE ELEMENT ==="
                )

                out.append(
                    f"tag: "
                    f"{active.get('tag', '')}"
                )

                out.append(
                    f"text: "
                    f"{active.get('text', '')}"
                )

                out.append(
                    f"selector: "
                    f"{active.get('selector', '')}"
                )

            out.append(
                "\n=== FRAMES ==="
            )

            out.append(
                f"Playwright frames: "
                f"{len(frames_data)}"
            )

            for frame_data in frames_data:

                out.append(
                    f"\n[FRAME "
                    f"{frame_data.get('frameIndex', '?')}] "
                    f"{frame_data.get('frameUrl', '')}"
                )

                if frame_data.get(
                    "isMainFrame"
                ):
                    out.append(
                        "  main frame: yes"
                    )

                if frame_data.get("error"):
                    out.append(
                        "  ERROR: "
                        f"{frame_data['error']}"
                    )

            out.append(
                "\n=== INTERACTIVE ELEMENTS ==="
            )

            global_index = 1

            for frame_data in frames_data:

                elements =
                    frame_data.get(
                        "interactive",
                        []
                    )

                for element in elements:

                    out.append(
                        f"\n[{global_index}] "
                        f"{element.get('tag', '').upper()} "
                        f"role="
                        f"{element.get('role') or '-'}"
                    )

                    global_index += 1

                    out.append(
                        "  frame: "
                        f"{frame_data.get('frameIndex', 0)}"
                    )

                    out.append(
                        "  selector: "
                        f"{element.get('selector', '')}"
                    )

                    if element.get(
                        "semanticLocator"
                    ):
                        out.append(
                            "  semantic: "
                            f"{element['semanticLocator']}"
                        )

                    if element.get(
                        "labelLocator"
                    ):
                        out.append(
                            "  label: "
                            f"{element['labelLocator']}"
                        )

                    if element.get(
                        "xpath"
                    ):
                        out.append(
                            "  xpath: "
                            f"{element['xpath']}"
                        )

                    for field in (
                        "text",
                        "accessibleName",
                        "id",
                        "name",
                        "type",
                        "placeholder",
                        "value",
                        "href",
                        "title",
                    ):

                        value = element.get(
                            field
                        )

                        if value:
                            out.append(
                                f"  {field}: "
                                f"{value}"
                            )

                    state = element.get(
                        "state",
                        {}
                    )

                    out.append(
                        "  state: "
                        f"visible={state.get('visible')} "
                        f"inViewport="
                        f"{state.get('inViewport')} "
                        f"enabled="
                        f"{state.get('enabled')} "
                        f"disabled="
                        f"{state.get('disabled')} "
                        f"checked="
                        f"{state.get('checked')} "
                        f"selected="
                        f"{state.get('selected')} "
                        f"required="
                        f"{state.get('required')} "
                        f"readonly="
                        f"{state.get('readonly')} "
                        f"focused="
                        f"{state.get('focused')} "
                        f"clickable="
                        f"{state.get('clickable')} "
                        f"covered="
                        f"{state.get('covered')}"
                    )

                    aria = element.get(
                        "aria",
                        {}
                    )

                    aria_values = []

                    for key, value in aria.items():

                        if value is not None:
                            aria_values.append(
                                f"{key}={value}"
                            )

                    if aria_values:

                        out.append(
                            "  aria: "
                            +
                            " ".join(
                                aria_values
                            )
                        )

                    rect = element.get(
                        "rect",
                        {}
                    )

                    out.append(
                        "  rect: "
                        f"x={rect.get('x')} "
                        f"y={rect.get('y')} "
                        f"w={rect.get('width')} "
                        f"h={rect.get('height')}"
                    )

                    hit = element.get(
                        "hitTest",
                        {}
                    )

                    if hit:

                        out.append(
                            "  hit-test: "
                            f"clickable="
                            f"{hit.get('clickable')} "
                            f"covered="
                            f"{hit.get('covered')} "
                            f"reason="
                            f"{hit.get('reason', '')}"
                        )

                        if hit.get(
                            "topTag"
                        ):
                            out.append(
                                "  top-at-center: "
                                f"{hit.get('topTag')} "
                                f"\""
                                f"{hit.get('topText', '')}"
                                f"\""
                            )

                    if element.get(
                        "shadowRoot"
                    ):
                        out.append(
                            "  shadow-root: yes"
                        )

            out.append(
                "\n=== FORMS ==="
            )

            for frame_data in frames_data:

                for form in frame_data.get(
                    "forms",
                    []
                ):

                    out.append(
                        f"\n[FORM "
                        f"{form.get('index')}] "
                        f"frame="
                        f"{frame_data.get('frameIndex')}"
                    )

                    out.append(
                        f"  method="
                        f"{form.get('method')} "
                        f"action="
                        f"{form.get('action')}"
                    )

                    out.append(
                        f"  selector="
                        f"{form.get('selector')}"
                    )

                    for field in form.get(
                        "fields",
                        []
                    ):

                        out.append(
                            f"  - "
                            f"{field.get('tag')} "
                            f"type="
                            f"{field.get('type') or '-'} "
                            f"name="
                            f"{field.get('name') or '-'} "
                            f"id="
                            f"{field.get('id') or '-'}"
                        )

                        if field.get(
                            "accessibleName"
                        ):
                            out.append(
                                "    accessible: "
                                f"{field['accessibleName']}"
                            )

                        out.append(
                            "    selector: "
                            f"{field.get('selector')}"
                        )

                        if field.get(
                            "semanticLocator"
                        ):
                            out.append(
                                "    semantic: "
                                f"{field['semanticLocator']}"
                            )

            out.append(
                "\n=== DIALOGS ==="
            )

            dialogs_found = False

            for frame_data in frames_data:

                for dialog in frame_data.get(
                    "dialogs",
                    []
                ):

                    dialogs_found = True

                    out.append(
                        f"[DIALOG "
                        f"{dialog.get('index')}] "
                        f"frame="
                        f"{frame_data.get('frameIndex')}"
                    )

                    out.append(
                        f"  role="
                        f"{dialog.get('role')}"
                    )

                    out.append(
                        f"  name="
                        f"{dialog.get('accessibleName')}"
                    )

                    out.append(
                        f"  selector="
                        f"{dialog.get('selector')}"
                    )

                    out.append(
                        f"  text="
                        f"{dialog.get('text', '')[:1000]}"
                    )

            if not dialogs_found:
                out.append(
                    "None"
                )

            out.append(
                "\n=== HEADINGS ==="
            )

            for frame_data in frames_data:

                for heading in frame_data.get(
                    "headings",
                    []
                ):

                    out.append(
                        f"H{heading.get('level')}: "
                        f"{heading.get('text')} "
                        f"| "
                        f"{heading.get('selector')}"
                    )

            out.append(
                "\n=== LINKS ==="
            )

            link_index = 1

            for frame_data in frames_data:

                for link in frame_data.get(
                    "links",
                    []
                ):

                    out.append(
                        f"[{link_index}] "
                        f"{link.get('text') or '(no text)'} "
                        f"→ "
                        f"{link.get('href')}"
                    )

                    out.append(
                        "  frame: "
                        f"{frame_data.get('frameIndex')}"
                    )

                    out.append(
                        "  selector: "
                        f"{link.get('selector')}"
                    )

                    if link.get(
                        "semanticLocator"
                    ):
                        out.append(
                            "  semantic: "
                            f"{link['semanticLocator']}"
                        )

                    link_index += 1

            out.append(
                "\n=== TABLES ==="
            )

            for frame_data in frames_data:

                for table in frame_data.get(
                    "tables",
                    []
                ):

                    out.append(
                        f"[TABLE "
                        f"{table.get('index')}] "
                        f"frame="
                        f"{frame_data.get('frameIndex')}"
                    )

                    out.append(
                        f"  selector: "
                        f"{table.get('selector')}"
                    )

                    if table.get(
                        "caption"
                    ):
                        out.append(
                            "  caption: "
                            f"{table['caption']}"
                        )

                    if table.get(
                        "headers"
                    ):
                        out.append(
                            "  headers: "
                            +
                            " | ".join(
                                table["headers"]
                            )
                        )

                    for row in table.get(
                        "rows",
                        []
                    ):
                        out.append(
                            "  row: "
                            +
                            " | ".join(
                                row
                            )
                        )

            out.append(
                "\n=== IFRAME ELEMENTS ==="
            )

            iframe_found = False

            for frame_data in frames_data:

                for iframe in frame_data.get(
                    "iframes",
                    []
                ):

                    iframe_found = True

                    out.append(
                        f"[{iframe.get('index')}] "
                        f"frame="
                        f"{frame_data.get('frameIndex')}"
                    )

                    out.append(
                        f"  src="
                        f"{iframe.get('src') or '-'}"
                    )

                    out.append(
                        f"  name="
                        f"{iframe.get('name') or '-'}"
                    )

                    out.append(
                        f"  title="
                        f"{iframe.get('title') or '-'}"
                    )

                    out.append(
                        f"  selector="
                        f"{iframe.get('selector')}"
                    )

            if not iframe_found:
                out.append(
                    "None"
                )

            out.append(
                "\n=== META ==="
            )

            for meta in main_data.get(
                "meta",
                []
            )[:40]:

                out.append(
                    f"{meta.get('name')}: "
                    f"{meta.get('content')}"
                )

            out.append(
                "\n=== VISIBLE TEXT ==="
            )

            out.append(
                main_data.get(
                    "visibleText",
                    ""
                ) or "(empty)"
            )

            return "\n".join(
                out
            )[:60000]

        return await browser_operation(
            operation
        )


# ============================================================
# DSPY ASYNC BRIDGE
# ============================================================

def run_async_from_dspy(coro):

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
            timeout=90
        )

    except Exception as e:

        future.cancel()

        raise RuntimeError(
            f"Browser tool error: {e}"
        ) from e


# ============================================================
# DSPY TOOLS
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

    def tool_inspect_page(
        max_interactive: int = 150,
        max_links: int = 100,
        max_text: int = 15000,
    ):

        return run_async_from_dspy(
            browser_inspect(
                max_interactive=
                    max_interactive,
                max_links=
                    max_links,
                max_text=
                    max_text,
            )
        )

    def tool_get_text(
        selector: str = "body"
    ):

        return run_async_from_dspy(
            browser_get_text(
                selector
            )
        )

    def tool_get_html(
        selector: str = "body"
    ):

        return run_async_from_dspy(
            browser_get_html(
                selector
            )
        )

    def tool_get_links():

        return run_async_from_dspy(
            browser_get_links()
        )

    def tool_click(
        selector: str
    ):

        return run_async_from_dspy(
            browser_click(
                selector
            )
        )

    def tool_click_text(
        text: str
    ):

        return run_async_from_dspy(
            browser_click_text(
                text
            )
        )

    def tool_click_role(
        role: str,
        name: str = "",
    ):

        return run_async_from_dspy(
            browser_click_role(
                role,
                name,
            )
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

    def tool_fill_label(
        label: str,
        text: str,
    ):

        return run_async_from_dspy(
            browser_fill_label(
                label,
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
            browser_key(
                key
            )
        )

    def tool_wait(
        milliseconds: int = 1000
    ):

        return run_async_from_dspy(
            browser_wait(
                milliseconds
            )
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
            browser_check(
                selector
            )
        )

    def tool_uncheck(
        selector: str
    ):

        return run_async_from_dspy(
            browser_uncheck(
                selector
            )
        )

    def tool_hover(
        selector: str
    ):

        return run_async_from_dspy(
            browser_hover(
                selector
            )
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
            browser_count(
                selector
            )
        )

    def tool_javascript(
        expression: str
    ):

        return run_async_from_dspy(
            browser_js(
                expression
            )
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
        Tool(tool_click_role),

        Tool(tool_fill),
        Tool(tool_fill_label),
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
# AGNES LM
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

        if params.get("tools"):
            payload["tools"] = (
                params["tools"]
            )

        if params.get("tool_choice"):
            payload["tool_choice"] = (
                params["tool_choice"]
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
                "Agnes HTTP %s: %s",
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
                "Agnes API"
            )

            raise RuntimeError(
                f"Agnes API error: {e}"
            ) from e

        choices = (
            data.get("choices")
            or []
        )

        if not choices:

            raise RuntimeError(
                "Agnes вернул пустой ответ: "
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
# DSPY SIGNATURE / AGENT
# ============================================================

class BrowserTask(Signature):

    """
    Ты автономный браузерный агент.

    Работай непосредственно через Camoufox.

    ОБЯЗАТЕЛЬНАЯ СТРАТЕГИЯ:

    1. Если пользователь дал URL —
       открой его через tool_goto.

    2. Если структура страницы неизвестна —
       сначала используй tool_inspect_page.

    3. Inspector предоставляет:
       - CSS selector
       - XPath
       - semantic locator
       - ARIA
       - состояние элемента
       - hit-test
       - frame
       - shadow DOM

    4. Для стандартных элементов
       предпочитай semantic tools:
       - tool_click_role
       - tool_click_text
       - tool_fill_label
       - tool_fill_placeholder

    5. Если semantic locator невозможно
       использовать — используй selector.

    6. Не кликай элемент, если inspector
       показывает:
       - disabled
       - covered
       - invisible

       если только нет очевидной причины
       сначала изменить состояние страницы.

    7. Для динамических элементов используй:
       - tool_wait
       - tool_wait_selector

    8. После значимого click/fill/submit:
       снова используй tool_inspect_page,
       если нужно понять новое состояние UI.

    9. Если selector не сработал:
       НЕ повторяй тот же selector бесконечно.
       Сначала повторно inspect_page.

    10. Для iframe учитывай frame index
        и состояние соответствующего frame.

    11. Для Shadow DOM учитывай,
        что Playwright умеет работать
        с открытым shadow DOM.

    12. Никогда не утверждай,
        что действие выполнено,
        если browser tool это не подтвердил.

    13. Не выдумывай содержимое страницы.

    14. В конце дай только краткий итог.
    """

    question = InputField(
        desc="Задача пользователя"
    )

    answer = OutputField(
        desc="Краткий итоговый результат"
    )


def init_dspy():

    global dspy_agent_instance

    if not AGNES_API_KEY:

        logger.warning(
            "AGNES_API_KEY не задан"
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

                dspy_agent_instance = ReActV2(
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )

                logger.info(
                    "Используется ReActV2"
                )

            except Exception as e:

                logger.warning(
                    "ReActV2 error: %s",
                    e,
                )

                dspy_agent_instance = (
                    dspy.ReAct(
                        BrowserTask,
                        tools=tools,
                        max_iters=15,
                    )
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
            "DSPy создан. Tools: %s",
            len(tools),
        )

        return True

    except Exception:

        logger.exception(
            "DSPy init error"
        )

        dspy_agent_instance = None

        return False


def run_agent(
    question: str
):

    if not dspy_agent_instance:

        return (
            "DSPy агент "
            "не инициализирован"
        )

    with agent_lock:

        try:

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
                    dict
                )
            ):
                answer = result.get(
                    "answer"
                )

            if answer is None:
                answer = str(result)

            answer = str(
                answer
            ).strip()

            return (
                answer
                or "Пустой ответ DSPy"
            )

        except Exception as e:

            logger.exception(
                "DSPy error"
            )

            return (
                "Ошибка агента: "
                f"{type(e).__name__}: {e}"
            )


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(

        "👋 Привет!\n\n"

        "🦊 Camoufox + DSPy "
        "Browser Agent\n\n"

        "Команды:\n"

        "/check <url>\n"
        "/dspy <задача>\n"
        "/inspect\n"
        "/cookies\n"
        "/cancel\n"
        "/status\n"
        "/screenshot"
    )


async def check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "Укажи URL:\n"
            "/check https://example.com"
        )

        return

    msg = await update.message.reply_text(
        "Открываю..."
    )

    try:

        result = await browser_goto(
            context.args[0]
        )

        text = await browser_get_text()

        await msg.edit_text(
            f"{result}\n\n"
            f"{text[:1500]}"
        )

    except Exception as e:

        logger.exception(
            "/check"
        )

        await msg.edit_text(
            f"Ошибка:\n"
            f"{str(e)[:1000]}"
        )


async def inspect_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = await update.message.reply_text(
        "🔎 Глубоко инспектирую страницу..."
    )

    try:

        result = await browser_inspect()

        if len(result) > 4000:

            result = (
                result[:4000]
                + "\n\n... [обрезано]"
            )

        await msg.edit_text(
            result
        )

    except Exception as e:

        logger.exception(
            "/inspect"
        )

        await msg.edit_text(
            f"Ошибка:\n"
            f"{str(e)[:1500]}"
        )


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
            "/screenshot"
        )

        await msg.edit_text(
            f"Ошибка:\n"
            f"{str(e)[:1000]}"
        )


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


async def cookies_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not browser_ready:

        await update.message.reply_text(
            "Camoufox не запущен"
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

        "Для отмены: /cancel"
    )


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
            "Загрузка cookies отменена."
        )

    else:

        await update.message.reply_text(
            "Нечего отменять."
        )


async def cookies_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = (
        update.effective_user.id
    )

    if (
        user_id
        not in waiting_for_cookies
    ):
        return

    document = (
        update.message.document
    )

    if not document:
        return

    filename = (
        document.file_name or ""
    ).lower()

    if not filename.endswith(
        ".json"
    ):

        await update.message.reply_text(
            "Нужен именно JSON-файл."
        )

        return

    waiting_for_cookies.discard(
        user_id
    )

    msg = await update.message.reply_text(
        "Загружаю cookies..."
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
                "Не удалось загрузить "
                "ни одной cookie.\n\n"
                +
                "\n".join(
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
                    "\n\n⚠️ Ошибки:\n"
                )

                response += "\n".join(
                    f"• {e}"
                    for e in errors[:10]
                )

        await msg.edit_text(
            response,
            parse_mode="Markdown",
        )

    except json.JSONDecodeError:

        await msg.edit_text(
            "Файл не является "
            "корректным JSON."
        )

    except Exception as e:

        logger.exception(
            "Ошибка загрузки cookies"
        )

        await msg.edit_text(
            "Ошибка загрузки cookies:\n\n"
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


async def dspy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(

            "🧠 DSPy Browser Agent\n\n"

            "Примеры:\n\n"

            "/dspy открой "
            "https://example.com "
            "и покажи заголовок\n\n"

            "/dspy найди Python на Google\n\n"

            "/dspy открой сайт "
            "и найди форму входа"
        )

        return

    if not dspy_agent_instance:

        await update.message.reply_text(
            "DSPy не инициализирован"
        )

        return

    if not browser_ready:

        await update.message.reply_text(
            "Camoufox не запущен"
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

        answer = answer[:4000]

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
            "/dspy"
        )

        await msg.edit_text(
            f"Ошибка:\n"
            f"{str(e)[:1000]}"
        )


async def telegram_error_handler(
    update,
    context,
):

    logger.error(
        "Telegram error",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    global main_event_loop

    main_event_loop = (
        asyncio.get_running_loop()
    )

    logger.info(
        "Инициализация..."
    )

    browser_ok = (
        await init_browser()
    )

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
            "inspect",
            inspect_command,
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

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            cookies_file,
        )
    )

    logger.info(
        "Camoufox: %s",
        "OK" if browser_ok else "FAIL",
    )

    logger.info(
        "DSPy: %s",
        "OK" if dspy_ok else "FAIL",
    )

    try:

        await app.initialize()

        await app.start()

        await app.updater.start_polling()

        logger.info(
            "Telegram бот запущен!"
        )

        stop_signal = (
            asyncio.Event()
        )

        def signal_handler():

            logger.info(
                "Получен сигнал остановки"
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
                "Bot alive"
            )

    except Exception:

        logger.exception(
            "Main error"
        )

    finally:

        logger.info(
            "Завершение..."
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


if __name__ == "__main__":

    asyncio.run(
        main()
    )
