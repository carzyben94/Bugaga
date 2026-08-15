"""
browser.py - Camoufox браузер + Inspector 2.0
"""

import os
import asyncio
import logging
import time
import json
import re
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    AsyncCamoufox = None
    CAMOUFOX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================
# GLOBAL STATE
# ============================================================

camoufox_manager = None
camoufox_context = None
current_page = None
browser_ready = False
browser_lock = asyncio.Lock()

SCREENSHOTS_DIR = "/app/screenshots"
CAMOUFOX_PROFILE = "/app/camoufox-profile"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(CAMOUFOX_PROFILE, exist_ok=True)

# ============================================================
# BROWSER FUNCTIONS
# ============================================================

async def init_browser():
    global camoufox_manager, camoufox_context, current_page, browser_ready

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

        logger.info("Camoufox работает: %s", await current_page.title())
        browser_ready = True
        return True

    except Exception as e:
        logger.exception("Ошибка запуска Camoufox: %s", e)
        browser_ready = False
        current_page = None
        camoufox_context = None

        try:
            if camoufox_manager:
                await camoufox_manager.__aexit__(None, None, None)
        except Exception:
            pass

        camoufox_manager = None
        return False


async def close_browser():
    global camoufox_manager, camoufox_context, current_page, browser_ready

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
            await camoufox_manager.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Ошибка закрытия Camoufox: %s", e)

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
            raise RuntimeError("Не удалось восстановить Camoufox")
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

        logger.warning("Camoufox закрыт. Восстанавливаем...")
        current_page = None
        await close_browser()

        if not await init_browser():
            raise RuntimeError("Camoufox не удалось восстановить")

        return await operation()

# ============================================================
# BROWSER TOOLS
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
            return f"Открыто\nURL: {page.url}\nTitle: {await page.title()}"
        return await browser_operation(operation)


async def browser_back():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            response = await page.go_back(
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if response is None:
                return f"Назад перейти невозможно\nURL: {page.url}"
            return f"Назад\nURL: {page.url}\nTitle: {await page.title()}"
        return await browser_operation(operation)


async def browser_forward():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            response = await page.go_forward(
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if response is None:
                return f"Вперёд перейти невозможно\nURL: {page.url}"
            return f"Вперёд\nURL: {page.url}\nTitle: {await page.title()}"
        return await browser_operation(operation)


async def browser_reload():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.reload(
                wait_until="domcontentloaded",
                timeout=30000,
            )
            return f"URL: {page.url}\nTitle: {await page.title()}"
        return await browser_operation(operation)


async def browser_page_info():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            return (
                f"URL: {page.url}\n"
                f"Title: {await page.title()}\n"
                f"Pages: {len(camoufox_context.pages)}"
            )
        return await browser_operation(operation)


async def browser_get_text(selector="body"):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            text = await page.locator(selector).inner_text(timeout=10000)
            return text[:20000] if text else "Текст не найден"
        return await browser_operation(operation)


async def browser_get_html(selector="body"):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            html = await page.locator(selector).inner_html(timeout=10000)
            return html[:30000]
        return await browser_operation(operation)


async def browser_get_links():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            links = await page.locator("a").evaluate_all(
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
                f"- {x.get('text', '')[:120]} → {x.get('href', '')}"
                for x in links[:200]
            )
        return await browser_operation(operation)


async def browser_click(selector: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).first.click(timeout=15000)
            await page.wait_for_timeout(500)
            return f"Клик выполнен\nSelector: {selector}\nURL: {page.url}"
        return await browser_operation(operation)


async def browser_click_text(text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.get_by_text(text, exact=True).first.click(timeout=15000)
            await page.wait_for_timeout(500)
            return f"Клик по тексту выполнен\nText: {text}\nURL: {page.url}"
        return await browser_operation(operation)


async def browser_click_role(role: str, name: str = ""):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            locator = page.get_by_role(role, name=name or None).first
            await locator.click(timeout=15000)
            await page.wait_for_timeout(500)
            return (
                f"Semantic click выполнен\n"
                f"Role: {role}\nName: {name}\nURL: {page.url}"
            )
        return await browser_operation(operation)


async def browser_fill(selector: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).first.fill(text, timeout=15000)
            return f"Поле заполнено\nSelector: {selector}"
        return await browser_operation(operation)


async def browser_fill_label(label: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.get_by_label(label, exact=True).first.fill(
                text, timeout=15000
            )
            return f"Поле заполнено\nLabel: {label}"
        return await browser_operation(operation)


async def browser_fill_placeholder(placeholder: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.get_by_placeholder(
                placeholder, exact=True
            ).first.fill(text, timeout=15000)
            return f"Поле заполнено\nPlaceholder: {placeholder}"
        return await browser_operation(operation)


async def browser_type(selector: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).first.type(text, timeout=15000)
            return "Текст введён"
        return await browser_operation(operation)


async def browser_press(selector: str, key: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).first.press(key, timeout=15000)
            return f"Нажата клавиша: {key}"
        return await browser_operation(operation)


async def browser_key(key: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.keyboard.press(key)
            return f"Клавиша: {key}"
        return await browser_operation(operation)


async def browser_wait(milliseconds=1000):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            milliseconds = max(0, min(int(milliseconds), 30000))
            await page.wait_for_timeout(milliseconds)
            return f"Ожидание {milliseconds} мс"
        return await browser_operation(operation)


async def browser_wait_selector(selector: str, timeout=10000):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).wait_for(
                state="visible", timeout=int(timeout)
            )
            return f"Элемент найден: {selector}"
        return await browser_operation(operation)


async def browser_select(selector: str, value: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            result = await page.locator(selector).select_option(
                value=value, timeout=15000
            )
            return f"Выбрано: {result}"
        return await browser_operation(operation)


async def browser_check(selector: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).check(timeout=15000)
            return "Checkbox отмечен"
        return await browser_operation(operation)


async def browser_uncheck(selector: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).uncheck(timeout=15000)
            return "Checkbox снят"
        return await browser_operation(operation)


async def browser_hover(selector: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).hover(timeout=15000)
            return "Наведение выполнено"
        return await browser_operation(operation)


async def browser_attribute(selector: str, attribute: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            value = await page.locator(selector).first.get_attribute(attribute)
            return str(value)
        return await browser_operation(operation)


async def browser_count(selector: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            return f"Количество: {await page.locator(selector).count()}"
        return await browser_operation(operation)


async def browser_js(expression: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            result = await page.evaluate(expression)
            return str(result)[:30000]
        return await browser_operation(operation)


async def browser_screenshot():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            filename = f"screenshot_{int(time.time())}.png"
            path = os.path.join(SCREENSHOTS_DIR, filename)
            await page.screenshot(path=path, full_page=True)
            return path
        return await browser_operation(operation)


async def browser_content():
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            return (await page.content())[:30000]
        return await browser_operation(operation)

# ============================================================
# COOKIES
# ============================================================

def normalize_cookie(cookie: dict):
    if not isinstance(cookie, dict):
        raise ValueError("Cookie должен быть объектом")

    name = cookie.get("name")
    if not name:
        raise ValueError("Cookie не содержит name")

    result = {
        "name": str(name),
        "value": str(cookie.get("value", "")),
    }

    domain = cookie.get("domain")
    if domain and not isinstance(domain, bool):
        domain = str(domain).strip()
        domain = re.sub(r"^https?://", "", domain)
        domain = domain.split("/", 1)[0]
        if domain:
            result["domain"] = domain

    url = cookie.get("url")
    if url:
        url = str(url).strip()
        if url.startswith(("http://", "https://")):
            result["url"] = url

    if "domain" not in result and "url" not in result:
        try:
            if current_page and not current_page.is_closed():
                page_url = current_page.url
                if page_url.startswith(("http://", "https://")):
                    result["url"] = page_url
        except Exception:
            pass

    if "domain" not in result and "url" not in result:
        raise ValueError(f"Cookie '{name}' не содержит domain или url")

    path = str(cookie.get("path") or "/")
    result["path"] = path if path.startswith("/") else "/" + path
    result["secure"] = bool(cookie.get("secure", False))
    result["httpOnly"] = bool(cookie.get("httpOnly", False))

    same_site = cookie.get("sameSite")
    if same_site:
        same_site = str(same_site).strip().lower()
        result["sameSite"] = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
            "no_restriction": "None",
            "no-restriction": "None",
            "unspecified": "Lax",
            "default": "Lax",
        }.get(same_site, "Lax")

    expires = cookie.get("expires", cookie.get("expirationDate"))
    if expires is not None:
        try:
            expires = float(expires)
            if expires > 0:
                result["expires"] = expires
        except (ValueError, TypeError):
            pass

    return result


async def load_cookies_from_json(data):
    if isinstance(data, dict):
        cookies = data.get("cookies")
        if cookies is None:
            raise ValueError("JSON должен содержать поле 'cookies'")
    elif isinstance(data, list):
        cookies = data
    else:
        raise ValueError("Неверный формат JSON cookies")

    if not cookies:
        raise ValueError("Файл cookies пустой")

    normalized = []
    errors = []

    for index, cookie in enumerate(cookies):
        try:
            normalized.append(normalize_cookie(cookie))
        except Exception as e:
            errors.append(f"Cookie #{index + 1}: {e}")

    if not normalized:
        raise ValueError(
            "Не удалось обработать ни одного cookie:\n" + "\n".join(errors[:20])
        )

    async with browser_lock:
        async def operation():
            if camoufox_context is None:
                raise RuntimeError("BrowserContext отсутствует")

            loaded = 0
            load_errors = list(errors)

            for index, cookie in enumerate(normalized):
                try:
                    await camoufox_context.add_cookies([cookie])
                    loaded += 1
                except Exception as e:
                    name = cookie.get("name", "unknown")
                    load_errors.append(
                        f"Cookie #{index + 1} ({name}): {e}"
                    )

            return {
                "loaded": loaded,
                "errors": load_errors,
                "total": len(cookies),
            }

        return await browser_operation(operation)

# ============================================================
# INSPECTOR 2.0
# ============================================================

INSPECTOR_JS = r"""
({
    maxInteractive = 120,
    maxLinks = 80,
    maxText = 12000,
    includeHidden = false,
    mode = "full",
    includeShadow = true,
    includeEvents = true,
    includeForms = true,
    includeTables = true,
    includeDialogs = true
}) => {
    const clean = value =>
        String(value ?? "").replace(/\s+/g, " ").trim();

    const cssEscape = value => {
        value = String(value ?? "");
        if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
        return value.replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
    };

    const visible = element => {
        if (!element || !(element instanceof Element)) return false;
        const style = window.getComputedStyle(element);
        if (
            style.display === "none" ||
            style.visibility === "hidden" ||
            style.visibility === "collapse" ||
            style.opacity === "0"
        ) return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const inViewport = element => {
        if (!element) return false;
        const rect = element.getBoundingClientRect();
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
            element.getAttribute("aria-disabled") !== "true"
        );
    };

    const textOf = element => {
        if (!element) return "";
        return clean(
            element.innerText ||
            element.getAttribute("aria-label") ||
            element.getAttribute("title") ||
            element.getAttribute("alt") ||
            element.value ||
            ""
        );
    };

    const accessibleName = element => {
        if (!element) return "";

        const ariaLabel = clean(element.getAttribute("aria-label"));
        if (ariaLabel) return ariaLabel;

        const labelledBy = clean(element.getAttribute("aria-labelledby"));
        if (labelledBy) {
            const text = labelledBy.split(/\s+/).map(id => {
                const node = document.getElementById(id);
                return node ? clean(node.innerText) : "";
            }).filter(Boolean).join(" ");
            if (text) return text;
        }

        const id = element.getAttribute("id");
        if (id) {
            const label = document.querySelector(`label[for="${cssEscape(id)}"]`);
            if (label) return clean(label.innerText);
        }

        const parentLabel = element.closest("label");
        if (parentLabel) return clean(parentLabel.innerText);

        return textOf(element);
    };

    const roleOf = element => {
        const explicit = clean(element.getAttribute("role"));
        if (explicit) return explicit;

        const tag = element.tagName.toLowerCase();
        const type = clean(element.getAttribute("type")).toLowerCase();

        if (tag === "button") return "button";
        if (tag === "a" && element.hasAttribute("href")) return "link";
        if (tag === "textarea") return "textbox";
        if (tag === "select") return "combobox";

        if (tag === "input") {
            if (type === "checkbox") return "checkbox";
            if (type === "radio") return "radio";
            if (["button", "submit", "reset"].includes(type)) return "button";
            if (type === "search") return "searchbox";
            return "textbox";
        }

        if (element.getAttribute("contenteditable") === "true") return "textbox";
        return "";
    };

    const nthOfType = element => {
        if (!element || !element.parentElement) return 1;
        const siblings = [...element.parentElement.children]
            .filter(x => x.tagName === element.tagName);
        return siblings.indexOf(element) + 1;
    };

    const stableClass = value => {
        if (!value) return false;
        const x = String(value);
        if (x.length > 80) return false;
        if (/(^|[-_])(css|jsx|emotion|styled|sc|ng|chakra|mantine)/i.test(x)) return false;
        if (/[a-f0-9]{8,}/i.test(x)) return false;
        if (/[0-9]{3,}/.test(x)) return false;
        return /^[A-Za-z_][A-Za-z0-9_-]*$/.test(x);
    };

    const uniqueSelector = element => {
        if (!element || !(element instanceof Element)) return "";

        if (element.id) {
            const selector = "#" + cssEscape(element.id);
            try {
                if (document.querySelectorAll(selector).length === 1) return selector;
            } catch (_) {}
        }

        for (const attribute of ["data-testid", "data-test", "data-qa", "data-cy", "name"]) {
            const value = element.getAttribute(attribute);
            if (!value) continue;
            const selector =
                `${element.tagName.toLowerCase()}[${attribute}="${cssEscape(value)}"]`;
            try {
                if (document.querySelectorAll(selector).length === 1) return selector;
            } catch (_) {}
        }

        const parts = [];
        let node = element;

        while (node && node.nodeType === 1 && node !== document.body) {
            let part = node.tagName.toLowerCase();

            const classes = [...node.classList].filter(stableClass).slice(0, 2);
            if (classes.length) {
                part += classes.map(c => "." + cssEscape(c)).join("");
            }

            const index = nthOfType(node);
            if (index > 1) part += `:nth-of-type(${index})`;

            parts.unshift(part);
            const candidate = parts.join(" > ");

            try {
                if (document.querySelectorAll(candidate).length === 1) return candidate;
            } catch (_) {}

            if (node.id) {
                parts.unshift("#" + cssEscape(node.id));
                break;
            }

            node = node.parentElement;
        }

        return parts.join(" > ");
    };

    const xpath = element => {
        if (!element || element.nodeType !== 1) return "";

        if (element.id) {
            return `//*[@id="${String(element.id).replace(/"/g, "&quot;")}"]`;
        }

        const parts = [];
        let node = element;

        while (node && node.nodeType === 1) {
            let index = 1;
            let sibling = node.previousElementSibling;

            while (sibling) {
                if (sibling.tagName === node.tagName) index++;
                sibling = sibling.previousElementSibling;
            }

            parts.unshift(`${node.tagName.toLowerCase()}[${index}]`);
            node = node.parentElement;
        }

        return "/" + parts.join("/");
    };

    const semanticLocator = element => {
        const role = roleOf(element);
        const name = accessibleName(element);

        if (
            role &&
            name &&
            [
                "button", "link", "checkbox", "radio", "tab",
                "menuitem", "combobox", "textbox", "searchbox"
            ].includes(role)
        ) {
            return `get_by_role("${role}", name="${name}")`;
        }

        const placeholder = clean(element.getAttribute("placeholder"));
        if (placeholder && ["input", "textarea"].includes(element.tagName.toLowerCase())) {
            return `get_by_placeholder("${placeholder}")`;
        }

        if (name) return `get_by_text("${name}")`;
        return "";
    };

    const labelLocator = element => {
        const name = accessibleName(element);
        return name ? `get_by_label("${name}")` : "";
    };

    const hitTest = element => {
        if (!visible(element)) return { clickable: false, reason: "not-visible" };

        const rect = element.getBoundingClientRect();
        const points = [
            [rect.left + rect.width / 2, rect.top + rect.height / 2],
            [rect.left + Math.min(Math.max(rect.width * .25, 1), rect.width), rect.top + Math.min(Math.max(rect.height * .25, 1), rect.height)],
            [rect.left + Math.min(Math.max(rect.width * .75, 1), rect.width), rect.top + Math.min(Math.max(rect.height * .75, 1), rect.height)]
        ];

        let covered = 0;
        let tested = 0;

        for (const [x, y] of points) {
            if (
                x < 0 || y < 0 ||
                x >= window.innerWidth ||
                y >= window.innerHeight
            ) continue;

            tested++;
            const top = document.elementFromPoint(x, y);
            if (!(top === element || element.contains(top))) covered++;
        }

        return {
            clickable: enabled(element) && tested > 0 && covered === 0,
            covered: tested > 0 && covered > 0,
            testedPoints: tested,
            coveredPoints: covered,
            coverageRatio: tested ? covered / tested : 1
        };
    };

    const isInteractive = element => {
        if (!element || !(element instanceof Element)) return false;

        const tag = element.tagName.toLowerCase();
        const role = element.getAttribute("role");
        const tabindex = element.getAttribute("tabindex");
        const contenteditable = element.getAttribute("contenteditable");

        return (
            ["button", "a", "input", "textarea", "select", "option"].includes(tag) ||
            [
                "button", "link", "textbox", "searchbox", "combobox",
                "checkbox", "radio", "tab", "menuitem", "switch",
                "slider", "spinbutton"
            ].includes(role) ||
            contenteditable === "true" ||
            (tabindex !== null && tabindex !== "-1")
        );
    };

    const eventHints = element => {
        if (!includeEvents) return [];

        const result = [];

        for (const attr of element.attributes || []) {
            if (/^on/i.test(attr.name)) result.push(attr.name);
        }

        if (element.hasAttribute("onclick")) result.push("onclick");

        const role = roleOf(element);
        if (role === "button" || role === "link") result.push("semantic-activation");

        if (["input", "textarea", "select"].includes(element.tagName.toLowerCase())) {
            result.push("input-events-possible");
        }

        return [...new Set(result)];
    };

    const relationshipData = element => {
        const result = {
            labelledBy: [],
            describedBy: [],
            controls: [],
            controlledBy: [],
            form: null,
            label: null
        };

        const ids = value => clean(value).split(/\s+/).filter(Boolean);

        for (const id of ids(element.getAttribute("aria-labelledby"))) {
            const node = document.getElementById(id);
            if (node) result.labelledBy.push({
                id,
                text: clean(node.innerText).slice(0, 300)
            });
        }

        for (const id of ids(element.getAttribute("aria-describedby"))) {
            const node = document.getElementById(id);
            if (node) result.describedBy.push({
                id,
                text: clean(node.innerText).slice(0, 300)
            });
        }

        for (const id of ids(element.getAttribute("aria-controls"))) {
            const node = document.getElementById(id);
            if (node) result.controls.push({
                id,
                tag: node.tagName.toLowerCase(),
                text: textOf(node).slice(0, 300),
                selector: uniqueSelector(node)
            });
        }

        const form = element.closest("form");
        if (form) {
            result.form = {
                id: form.id || "",
                name: form.getAttribute("name") || "",
                selector: uniqueSelector(form)
            };
        }

        const id = element.getAttribute("id");
        if (id) {
            const label = document.querySelector(`label[for="${cssEscape(id)}"]`);
            if (label) result.label = {
                text: clean(label.innerText).slice(0, 300),
                selector: uniqueSelector(label)
            };
        }

        return result;
    };

    const describe = (element, index, frameUrl, shadow) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        const type = clean(element.getAttribute("type"));
        const hit = hitTest(element);

        const state = {
            visible: visible(element),
            inViewport: inViewport(element),
            enabled: enabled(element),
            disabled: element.hasAttribute("disabled"),
            ariaDisabled: element.getAttribute("aria-disabled") === "true",
            checked: "checked" in element ? !!element.checked : false,
            indeterminate: "indeterminate" in element ? !!element.indeterminate : false,
            selected: "selected" in element ? !!element.selected : false,
            required: element.hasAttribute("required"),
            readonly: element.hasAttribute("readonly"),
            contenteditable: element.getAttribute("contenteditable") === "true",
            focused: document.activeElement === element,
            clickable: !!hit.clickable,
            covered: !!hit.covered,
            pointerEvents: style.pointerEvents !== "none"
        };

        const result = {
            index,
            tag: element.tagName.toLowerCase(),
            role: roleOf(element),
            text: textOf(element).slice(0, 300),
            accessibleName: accessibleName(element).slice(0, 300),
            selector: uniqueSelector(element),
            xpath: xpath(element),
            semanticLocator: semanticLocator(element),
            labelLocator: labelLocator(element),
            id: clean(element.id),
            name: clean(element.getAttribute("name")),
            type,
            placeholder: clean(element.getAttribute("placeholder")),
            value: clean(element.value).slice(0, 300),
            href: clean(element.getAttribute("href")),
            title: clean(element.getAttribute("title")),
            autocomplete: clean(element.getAttribute("autocomplete")),
            aria: {
                label: clean(element.getAttribute("aria-label")),
                labelledby: clean(element.getAttribute("aria-labelledby")),
                describedby: clean(element.getAttribute("aria-describedby")),
                expanded: element.getAttribute("aria-expanded"),
                controls: element.getAttribute("aria-controls"),
                haspopup: element.getAttribute("aria-haspopup"),
                selected: element.getAttribute("aria-selected"),
                checked: element.getAttribute("aria-checked"),
                pressed: element.getAttribute("aria-pressed"),
                current: element.getAttribute("aria-current"),
                disabled: element.getAttribute("aria-disabled")
            },
            relationships: relationshipData(element),
            state,
            hitTest: hit,
            events: eventHints(element),
            rect: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            style: {
                display: style.display,
                visibility: style.visibility,
                pointerEvents: style.pointerEvents,
                position: style.position,
                zIndex: style.zIndex
            },
            frameUrl: frameUrl || location.href,
            shadowRoot: !!shadow
        };

        return result;
    };

    const allElements = [];
    const shadowHosts = [];

    const walk = (root, shadow = false, host = null) => {
        const elements = root.querySelectorAll ? root.querySelectorAll("*") : [];

        for (const element of elements) {
            allElements.push({ element, shadow, host });

            if (includeShadow && element.shadowRoot) {
                shadowHosts.push({
                    hostSelector: uniqueSelector(element),
                    hostTag: element.tagName.toLowerCase()
                });
                walk(element.shadowRoot, true, element);
            }
        }
    };

    walk(document);

    const interactive = [];
    for (const item of allElements) {
        if (!isInteractive(item.element)) continue;
        if (!includeHidden && !visible(item.element)) continue;

        interactive.push(
            describe(
                item.element,
                interactive.length + 1,
                location.href,
                item.shadow
            )
        );

        if (interactive.length >= maxInteractive) break;
    }

    const links = allElements
        .filter(item => item.element.tagName.toLowerCase() === "a")
        .filter(item => item.element.hasAttribute("href"))
        .filter(item => includeHidden || visible(item.element))
        .slice(0, maxLinks)
        .map((item, i) => ({
            index: i + 1,
            text: textOf(item.element).slice(0, 200),
            href: item.element.href,
            selector: uniqueSelector(item.element),
            semanticLocator: semanticLocator(item.element),
            visible: visible(item.element),
            shadowRoot: item.shadow
        }));

    const forms = includeForms ? [...document.forms].map((form, i) => ({
        index: i + 1,
        selector: uniqueSelector(form),
        action: form.action || "",
        method: (form.method || "get").toUpperCase(),
        name: clean(form.getAttribute("name")),
        id: clean(form.id),
        fields: [...form.elements].slice(0, 100).map((element, j) => ({
            index: j + 1,
            tag: element.tagName.toLowerCase(),
            type: clean(element.getAttribute("type")),
            name: clean(element.getAttribute("name")),
            id: clean(element.id),
            placeholder: clean(element.getAttribute("placeholder")),
            accessibleName: accessibleName(element),
            selector: uniqueSelector(element),
            semanticLocator: semanticLocator(element),
            required: element.hasAttribute("required"),
            disabled: element.hasAttribute("disabled"),
            readonly: element.hasAttribute("readonly"),
            autocomplete: clean(element.getAttribute("autocomplete"))
        }))
    })) : [];

    const headings = allElements
        .filter(item => /^H[1-6]$/.test(item.element.tagName))
        .filter(item => includeHidden || visible(item.element))
        .slice(0, 100)
        .map(item => ({
            level: Number(item.element.tagName.substring(1)),
            text: clean(item.element.innerText).slice(0, 300),
            selector: uniqueSelector(item.element)
        }));

    const tables = includeTables ? [...document.querySelectorAll("table")]
        .filter(x => includeHidden || visible(x))
        .slice(0, 30)
        .map((table, i) => ({
            index: i + 1,
            selector: uniqueSelector(table),
            caption: clean(table.querySelector("caption")?.innerText),
            headers: [...table.querySelectorAll("th")].slice(0, 30)
                .map(x => clean(x.innerText)),
            rows: [...table.querySelectorAll("tr")].slice(0, 10).map(row =>
                [...row.querySelectorAll("th,td")].slice(0, 20)
                    .map(cell => clean(cell.innerText).slice(0, 150))
            )
        })) : [];

    const dialogs = includeDialogs ? allElements
        .filter(item => {
            const role = item.element.getAttribute("role");
            const tag = item.element.tagName.toLowerCase();
            return role === "dialog" || role === "alertdialog" || tag === "dialog";
        })
        .filter(item => includeHidden || visible(item.element))
        .slice(0, 30)
        .map((item, i) => ({
            index: i + 1,
            role: item.element.getAttribute("role"),
            text: clean(item.element.innerText).slice(0, 1000),
            accessibleName: accessibleName(item.element),
            selector: uniqueSelector(item.element),
            semanticLocator: semanticLocator(item.element)
        })) : [];

    const iframes = [...document.querySelectorAll("iframe,frame")]
        .slice(0, 50)
        .map((element, i) => ({
            index: i + 1,
            selector: uniqueSelector(element),
            src: element.src || element.getAttribute("src") || "",
            name: clean(element.getAttribute("name")),
            title: clean(element.getAttribute("title")),
            visible: visible(element),
            sandbox: element.getAttribute("sandbox") || "",
            loading: element.getAttribute("loading") || ""
        }));

    const meta = [...document.querySelectorAll("meta[name],meta[property]")]
        .slice(0, 80)
        .map(element => ({
            name: element.getAttribute("name") ||
                  element.getAttribute("property") || "",
            content: clean(element.getAttribute("content")).slice(0, 500)
        }));

    const bodyClone = document.body ? document.body.cloneNode(true) : null;
    if (bodyClone) {
        bodyClone.querySelectorAll(
            "script,style,noscript,svg,path,template"
        ).forEach(x => x.remove());
    }

    const visibleText = clean(bodyClone?.innerText || "").slice(0, maxText);

    const active = document.activeElement;

    const fingerprintSource = [
        location.href,
        document.title,
        document.body?.innerText?.slice(0, 5000) || "",
        interactive.map(x => `${x.tag}|${x.role}|${x.selector}|${x.text}`).join("||"),
        dialogs.map(x => `${x.role}|${x.selector}|${x.text}`).join("||")
    ].join("\n");

    let fingerprint = 0;
    for (let i = 0; i < fingerprintSource.length; i++) {
        fingerprint = ((fingerprint << 5) - fingerprint + fingerprintSource.charCodeAt(i)) | 0;
    }

    const navigation = {
        url: location.href,
        origin: location.origin,
        pathname: location.pathname,
        hash: location.hash,
        readyState: document.readyState,
        referrer: document.referrer,
        hasHistoryAPI: !!(window.history && window.history.pushState),
        scrollRestoration: window.history?.scrollRestoration || "",
        likelySPA:
            !!window.history?.pushState &&
            !!window.history?.replaceState &&
            !document.querySelector("html[amp]")
    };

    const result = {
        mode,
        url: location.href,
        title: document.title,
        lang: document.documentElement.lang || "",
        readyState: document.readyState,
        fingerprint,
        navigation,

        viewport: {
            width: window.innerWidth,
            height: window.innerHeight,
            scrollX: Math.round(window.scrollX),
            scrollY: Math.round(window.scrollY),
            documentWidth: document.documentElement.scrollWidth,
            documentHeight: document.documentElement.scrollHeight
        },

        activeElement: active ? {
            tag: active.tagName?.toLowerCase(),
            text: textOf(active).slice(0, 200),
            selector: uniqueSelector(active)
        } : null,

        interactive,
        links,
        forms,
        headings,
        tables,
        dialogs,
        iframes,
        meta,
        shadowDom: {
            hosts: shadowHosts,
            hostCount: shadowHosts.length,
            interactiveCount: interactive.filter(x => x.shadowRoot).length
        },

        visibleText
    };

    if (mode === "map") {
        return {
            mode: "map",
            url: result.url,
            title: result.title,
            readyState: result.readyState,
            fingerprint: result.fingerprint,
            navigation: result.navigation,
            viewport: result.viewport,
            counts: {
                interactive: interactive.length,
                links: links.length,
                forms: forms.length,
                dialogs: dialogs.length,
                iframes: iframes.length,
                shadowHosts: shadowHosts.length
            },
            activeElement: result.activeElement,
            interactive: interactive.map(x => ({
                index: x.index,
                tag: x.tag,
                role: x.role,
                text: x.text,
                accessibleName: x.accessibleName,
                selector: x.selector,
                semanticLocator: x.semanticLocator,
                state: x.state,
                frameUrl: x.frameUrl,
                shadowRoot: x.shadowRoot
            })),
            headings,
            dialogs,
            iframes
        };
    }

    return result;
}
"""


async def inspect_frame(
    frame,
    max_interactive,
    max_links,
    max_text,
    include_hidden,
    mode="full",
):
    try:
        return await frame.evaluate(
            INSPECTOR_JS,
            {
                "maxInteractive": int(max_interactive),
                "maxLinks": int(max_links),
                "maxText": int(max_text),
                "includeHidden": bool(include_hidden),
                "mode": mode,
                "includeShadow": True,
                "includeEvents": True,
                "includeForms": True,
                "includeTables": mode == "full",
                "includeDialogs": True,
            },
        )
    except Exception as e:
        return {
            "url": getattr(frame, "url", ""),
            "title": "",
            "error": str(e)[:1000],
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


async def browser_inspect(
    max_interactive=150,
    max_links=100,
    max_text=15000,
    include_hidden=False,
    inspect_frames=True,
    mode="full",
):
    async with browser_lock:
        async def operation():
            page = await get_current_page()

            frames = (
                page.frames if inspect_frames else [page.main_frame]
            )

            frames_data = []

            for frame_index, frame in enumerate(frames):
                data = await inspect_frame(
                    frame,
                    max_interactive,
                    max_links,
                    max_text,
                    include_hidden,
                    mode=mode,
                )
                data["frameIndex"] = frame_index
                data["isMainFrame"] = frame == page.main_frame
                data["frameUrl"] = frame.url
                frames_data.append(data)

            main_data = frames_data[0] if frames_data else {
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

            if mode == "map":
                out = [
                    "=== PAGE MAP ===",
                    f"URL: {main_data.get('url', page.url)}",
                    f"TITLE: {main_data.get('title', '')}",
                    f"READY: {main_data.get('readyState', '')}",
                    f"FINGERPRINT: {main_data.get('fingerprint', '')}",
                    f"FRAMES: {len(frames_data)}",
                    "",
                    "COUNTS:",
                    f"interactive={len(main_data.get('interactive', []))}",
                    f"links={len(main_data.get('links', []))}",
                    f"forms={len(main_data.get('forms', []))}",
                    f"dialogs={len(main_data.get('dialogs', []))}",
                    f"iframes={len(main_data.get('iframes', []))}",
                    f"shadowHosts={main_data.get('shadowDom', {}).get('hostCount', 0)}",
                    "",
                    "=== INTERACTIVE MAP ===",
                ]

                global_index = 1
                for frame_data in frames_data:
                    for element in frame_data.get("interactive", []):
                        state = element.get("state", {})
                        out.append(
                            f"[{global_index}] "
                            f"{element.get('tag', '').upper()} "
                            f"role={element.get('role') or '-'} "
                            f"name={element.get('accessibleName') or '-'}"
                        )
                        out.append(
                            f"  selector={element.get('selector', '')}"
                        )
                        out.append(
                            f"  semantic={element.get('semanticLocator') or '-'}"
                        )
                        out.append(
                            f"  frame={frame_data.get('frameIndex')} "
                            f"visible={state.get('visible')} "
                            f"enabled={state.get('enabled')} "
                            f"clickable={state.get('clickable')} "
                            f"covered={state.get('covered')}"
                        )
                        global_index += 1

                out.append("\n=== HEADINGS ===")
                for heading in main_data.get("headings", []):
                    out.append(
                        f"H{heading.get('level')}: "
                        f"{heading.get('text')} | {heading.get('selector')}"
                    )

                out.append("\n=== DIALOGS ===")
                dialogs = main_data.get("dialogs", [])
                if dialogs:
                    for dialog in dialogs:
                        out.append(
                            f"[{dialog.get('index')}] "
                            f"{dialog.get('role')} "
                            f"{dialog.get('accessibleName')} "
                            f"| {dialog.get('selector')}"
                        )
                else:
                    out.append("None")

                out.append("\n=== IFRAMES ===")
                iframes = main_data.get("iframes", [])
                if iframes:
                    for iframe in iframes:
                        out.append(
                            f"[{iframe.get('index')}] "
                            f"{iframe.get('src') or '-'} "
                            f"| {iframe.get('selector')}"
                        )
                else:
                    out.append("None")

                return "\n".join(out)[:30000]

            out = [
                "=== PAGE ===",
                f"URL: {main_data.get('url', page.url)}",
                f"TITLE: {main_data.get('title', '')}",
                f"LANG: {main_data.get('lang', '')}",
                f"READY STATE: {main_data.get('readyState', '')}",
                f"FINGERPRINT: {main_data.get('fingerprint', '')}",
            ]

            navigation = main_data.get("navigation", {})
            out += [
                "",
                "=== NAVIGATION / SPA ===",
                f"origin: {navigation.get('origin', '')}",
                f"pathname: {navigation.get('pathname', '')}",
                f"hash: {navigation.get('hash', '')}",
                f"referrer: {navigation.get('referrer', '')}",
                f"historyAPI: {navigation.get('hasHistoryAPI', False)}",
                f"likelySPA: {navigation.get('likelySPA', False)}",
            ]

            vp = main_data.get("viewport", {})
            out += [
                "",
                "=== VIEWPORT ===",
                f"{vp.get('width', '?')}x{vp.get('height', '?')} "
                f"scroll=({vp.get('scrollX', '?')},{vp.get('scrollY', '?')}) "
                f"document={vp.get('documentWidth', '?')}x{vp.get('documentHeight', '?')}",
            ]

            active = main_data.get("activeElement")
            if active:
                out += [
                    "",
                    "=== ACTIVE ELEMENT ===",
                    f"tag: {active.get('tag', '')}",
                    f"text: {active.get('text', '')}",
                    f"selector: {active.get('selector', '')}",
                ]

            out += [
                "",
                "=== FRAMES ===",
                f"Playwright frames: {len(frames_data)}",
            ]

            for frame_data in frames_data:
                out.append(
                    f"[FRAME {frame_data.get('frameIndex', '?')}] "
                    f"{frame_data.get('frameUrl', '')}"
                )
                if frame_data.get("isMainFrame"):
                    out.append("  main frame: yes")
                if frame_data.get("error"):
                    out.append(f"  ERROR: {frame_data['error']}")

            out.append("\n=== INTERACTIVE ELEMENTS ===")
            global_index = 1

            for frame_data in frames_data:
                for element in frame_data.get("interactive", []):
                    out.append(
                        f"\n[{global_index}] "
                        f"{element.get('tag', '').upper()} "
                        f"role={element.get('role') or '-'}"
                    )
                    global_index += 1

                    out.append(f"  frame: {frame_data.get('frameIndex')}")
                    out.append(f"  selector: {element.get('selector', '')}")

                    for field in (
                        "semanticLocator",
                        "labelLocator",
                        "xpath",
                        "text",
                        "accessibleName",
                        "id",
                        "name",
                        "type",
                        "placeholder",
                        "value",
                        "href",
                        "title",
                        "autocomplete",
                    ):
                        value = element.get(field)
                        if value:
                            out.append(f"  {field}: {value}")

                    state = element.get("state", {})
                    out.append(
                        "  state: "
                        f"visible={state.get('visible')} "
                        f"inViewport={state.get('inViewport')} "
                        f"enabled={state.get('enabled')} "
                        f"disabled={state.get('disabled')} "
                        f"ariaDisabled={state.get('ariaDisabled')} "
                        f"checked={state.get('checked')} "
                        f"indeterminate={state.get('indeterminate')} "
                        f"selected={state.get('selected')} "
                        f"required={state.get('required')} "
                        f"readonly={state.get('readonly')} "
                        f"focused={state.get('focused')} "
                        f"clickable={state.get('clickable')} "
                        f"covered={state.get('covered')} "
                        f"pointerEvents={state.get('pointerEvents')}"
                    )

                    hit = element.get("hitTest", {})
                    out.append(
                        "  hit-test: "
                        f"clickable={hit.get('clickable')} "
                        f"covered={hit.get('covered')} "
                        f"tested={hit.get('testedPoints')} "
                        f"coveredPoints={hit.get('coveredPoints')} "
                        f"coverageRatio={hit.get('coverageRatio')}"
                    )

                    relationships = element.get("relationships", {})
                    if relationships:
                        out.append(
                            f"  relationships: "
                            f"label={relationships.get('label')} "
                            f"form={relationships.get('form')}"
                        )
                        if relationships.get("controls"):
                            out.append(
                                f"  controls: {relationships['controls']}"
                            )

                    aria = element.get("aria", {})
                    aria_values = [
                        f"{key}={value}"
                        for key, value in aria.items()
                        if value is not None
                    ]
                    if aria_values:
                        out.append("  aria: " + " ".join(aria_values))

                    events = element.get("events", [])
                    if events:
                        out.append("  event-hints: " + ", ".join(events))

                    rect = element.get("rect", {})
                    out.append(
                        "  rect: "
                        f"x={rect.get('x')} "
                        f"y={rect.get('y')} "
                        f"w={rect.get('width')} "
                        f"h={rect.get('height')}"
                    )

                    if element.get("shadowRoot"):
                        out.append("  shadow-root: yes")

            out.append("\n=== FORMS ===")
            for frame_data in frames_data:
                for form in frame_data.get("forms", []):
                    out.append(
                        f"\n[FORM {form.get('index')}] "
                        f"frame={frame_data.get('frameIndex')}"
                    )
                    out.append(
                        f"  method={form.get('method')} "
                        f"action={form.get('action')}"
                    )
                    out.append(f"  selector={form.get('selector')}")

                    for field in form.get("fields", []):
                        out.append(
                            f"  - {field.get('tag')} "
                            f"type={field.get('type') or '-'} "
                            f"name={field.get('name') or '-'} "
                            f"id={field.get('id') or '-'}"
                        )
                        if field.get("accessibleName"):
                            out.append(
                                f"    accessible: {field['accessibleName']}"
                            )
                        out.append(f"    selector: {field.get('selector')}")
                        if field.get("semanticLocator"):
                            out.append(
                                f"    semantic: {field['semanticLocator']}"
                            )
                        out.append(
                            f"    required={field.get('required')} "
                            f"disabled={field.get('disabled')} "
                            f"readonly={field.get('readonly')} "
                            f"autocomplete={field.get('autocomplete')}"
                        )

            out.append("\n=== DIALOGS ===")
            dialogs_found = False
            for frame_data in frames_data:
                for dialog in frame_data.get("dialogs", []):
                    dialogs_found = True
                    out.append(
                        f"[DIALOG {dialog.get('index')}] "
                        f"frame={frame_data.get('frameIndex')}"
                    )
                    out.append(f"  role={dialog.get('role')}")
                    out.append(f"  name={dialog.get('accessibleName')}")
                    out.append(f"  selector={dialog.get('selector')}")
                    out.append(f"  text={dialog.get('text', '')[:1000]}")
            if not dialogs_found:
                out.append("None")

            out.append("\n=== HEADINGS ===")
            for frame_data in frames_data:
                for heading in frame_data.get("headings", []):
                    out.append(
                        f"H{heading.get('level')}: "
                        f"{heading.get('text')} | {heading.get('selector')}"
                    )

            out.append("\n=== LINKS ===")
            link_index = 1
            for frame_data in frames_data:
                for link in frame_data.get("links", []):
                    out.append(
                        f"[{link_index}] "
                        f"{link.get('text') or '(no text)'} → "
                        f"{link.get('href')}"
                    )
                    out.append(f"  frame: {frame_data.get('frameIndex')}")
                    out.append(f"  selector: {link.get('selector')}")
                    if link.get("semanticLocator"):
                        out.append(
                            f"  semantic: {link['semanticLocator']}"
                        )
                    link_index += 1

            out.append("\n=== TABLES ===")
            for frame_data in frames_data:
                for table in frame_data.get("tables", []):
                    out.append(
                        f"[TABLE {table.get('index')}] "
                        f"frame={frame_data.get('frameIndex')}"
                    )
                    out.append(f"  selector: {table.get('selector')}")
                    if table.get("caption"):
                        out.append(f"  caption: {table['caption']}")
                    if table.get("headers"):
                        out.append(
                            "  headers: " + " | ".join(table["headers"])
                        )
                    for row in table.get("rows", []):
                        out.append("  row: " + " | ".join(row))

            out.append("\n=== IFRAME ELEMENTS ===")
            iframe_found = False
            for frame_data in frames_data:
                for iframe in frame_data.get("iframes", []):
                    iframe_found = True
                    out.append(
                        f"[{iframe.get('index')}] "
                        f"frame={frame_data.get('frameIndex')}"
                    )
                    out.append(f"  src={iframe.get('src') or '-'}")
                    out.append(f"  name={iframe.get('name') or '-'}")
                    out.append(f"  title={iframe.get('title') or '-'}")
                    out.append(f"  selector={iframe.get('selector')}")
                    out.append(f"  sandbox={iframe.get('sandbox') or '-'}")
            if not iframe_found:
                out.append("None")

            out.append("\n=== SHADOW DOM ===")
            shadow = main_data.get("shadowDom", {})
            out.append(f"hosts: {shadow.get('hostCount', 0)}")
            out.append(
                f"interactive elements inside shadow roots: "
                f"{shadow.get('interactiveCount', 0)}"
            )
            for host in shadow.get("hosts", [])[:50]:
                out.append(
                    f"- {host.get('hostTag')} "
                    f"{host.get('hostSelector')}"
                )

            out.append("\n=== META ===")
            for meta in main_data.get("meta", [])[:40]:
                out.append(
                    f"{meta.get('name')}: {meta.get('content')}"
                )

            out.append("\n=== VISIBLE TEXT ===")
            out.append(main_data.get("visibleText", "") or "(empty)")

            return "\n".join(out)[:60000]

        return await browser_operation(operation)


def _extract_inspect_fingerprint(text: str) -> Optional[str]:
    match = re.search(r"^FINGERPRINT:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _section(text: str, title: str) -> str:
    marker = f"=== {title} ==="
    if marker not in text:
        return ""
    part = text.split(marker, 1)[1]
    next_match = re.search(r"\n=== [^=]+ ===", part)
    return part[:next_match.start()] if next_match else part


async def browser_inspect_diff(
    before_text: str,
    max_interactive=150,
    max_links=100,
    max_text=12000,
):
    after = await browser_inspect(
        max_interactive=max_interactive,
        max_links=max_links,
        max_text=max_text,
        mode="full",
    )

    before_fp = _extract_inspect_fingerprint(before_text)
    after_fp = _extract_inspect_fingerprint(after)

    changes = [
        "=== ACTION DIFF ===",
        f"fingerprint before: {before_fp or '-'}",
        f"fingerprint after: {after_fp or '-'}",
        f"DOM/UI changed: {'YES' if before_fp != after_fp else 'NO'}",
    ]

    before_dialogs = _section(before_text, "DIALOGS").strip()
    after_dialogs = _section(after, "DIALOGS").strip()

    if before_dialogs != after_dialogs:
        changes.append("dialogs: CHANGED")
        changes.append("--- before dialogs ---")
        changes.append(before_dialogs[:3000] or "None")
        changes.append("--- after dialogs ---")
        changes.append(after_dialogs[:3000] or "None")

    before_active = _section(before_text, "ACTIVE ELEMENT").strip()
    after_active = _section(after, "ACTIVE ELEMENT").strip()

    if before_active != after_active:
        changes.append("active element: CHANGED")
        changes.append(f"before: {before_active[:1000]}")
        changes.append(f"after: {after_active[:1000]}")

    before_url = re.search(r"^URL:\s*(.+)$", before_text, re.MULTILINE)
    after_url = re.search(r"^URL:\s*(.+)$", after, re.MULTILINE)

    before_url = before_url.group(1).strip() if before_url else ""
    after_url = after_url.group(1).strip() if after_url else ""

    if before_url != after_url:
        changes.append(f"URL changed: YES")
        changes.append(f"before URL: {before_url}")
        changes.append(f"after URL: {after_url}")
    else:
        changes.append("URL changed: NO")

    changes.append("\n=== AFTER INSPECT ===")
    changes.append(after[:16000])

    return "\n".join(changes)[:30000]