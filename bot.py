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
# COOKIE NORMALIZATION
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

    normalized, errors = [], []

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
                f"Открыто\nURL: {page.url}\n"
                f"Title: {await page.title()}"
            )
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
            links = await page.locator("a").evaluate_all("""
                els => els.map(e => ({
                    text: (e.innerText || '').trim(),
                    href: e.href || ''
                })).filter(x => x.href)
            """)
            if not links:
                return "Ссылок не найдено"
            return "\n".join(
                f"- {x.get('text','')[:120]} → {x.get('href','')}"
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


async def browser_fill(selector: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.locator(selector).first.fill(text, timeout=15000)
            return f"Поле заполнено\nSelector: {selector}"
        return await browser_operation(operation)


async def browser_fill_placeholder(placeholder: str, text: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            await page.get_by_placeholder(placeholder).first.fill(
                text, timeout=15000
            )
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
                state="visible",
                timeout=int(timeout),
            )
            return f"Элемент найден: {selector}"
        return await browser_operation(operation)


async def browser_select(selector: str, value: str):
    async with browser_lock:
        async def operation():
            page = await get_current_page()
            result = await page.locator(selector).select_option(
                value=value,
                timeout=15000,
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
# MASTER INSPECTOR
# ============================================================

async def browser_inspect(
    max_interactive=120,
    max_links=80,
    max_text=12000,
    include_hidden=False,
):
    """
    Глубокий UI/DOM inspector.

    Возвращает:
      - URL/title
      - viewport
      - интерактивные элементы
      - стабильные CSS selectors
      - aria/name/placeholder/value
      - состояния disabled/checked/selected/required
      - forms
      - headings
      - tables
      - iframes
      - видимый текст

    Selector строится внутри страницы и предназначен для
    последующей передачи click/fill/press/etc.
    """

    async with browser_lock:
        async def operation():
            page = await get_current_page()

            js = r"""
            ({maxInteractive, maxLinks, maxText, includeHidden}) => {
                const clean = v =>
                    String(v ?? '')
                        .replace(/\s+/g, ' ')
                        .trim();

                const esc = value => {
                    value = String(value ?? '');
                    if (window.CSS && CSS.escape) return CSS.escape(value);
                    return value.replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, '\\$1');
                };

                const visible = el => {
                    if (!el || !(el instanceof Element)) return false;
                    const s = getComputedStyle(el);
                    if (s.display === 'none' ||
                        s.visibility === 'hidden' ||
                        s.opacity === '0') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };

                const enabled = el =>
                    !el.hasAttribute('disabled') &&
                    el.getAttribute('aria-disabled') !== 'true';

                const textOf = el =>
                    clean(
                        el.innerText ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('title') ||
                        el.getAttribute('alt') ||
                        el.value ||
                        ''
                    );

                const nth = el => {
                    if (!el.parentElement) return 1;
                    const same = [...el.parentElement.children]
                        .filter(x => x.tagName === el.tagName);
                    return same.indexOf(el) + 1;
                };

                const uniqueSelector = el => {
                    if (!(el instanceof Element)) return '';

                    if (el.id) {
                        const s = '#' + esc(el.id);
                        try {
                            if (document.querySelectorAll(s).length === 1) return s;
                        } catch (_) {}
                    }

                    const attrs = [
                        ['name', el.getAttribute('name')],
                        ['data-testid', el.getAttribute('data-testid')],
                        ['data-test', el.getAttribute('data-test')],
                        ['data-qa', el.getAttribute('data-qa')],
                        ['aria-label', el.getAttribute('aria-label')]
                    ];

                    for (const [key, value] of attrs) {
                        if (!value) continue;
                        const s = `${el.tagName.toLowerCase()}[${key}="${esc(value)}"]`;
                        try {
                            if (document.querySelectorAll(s).length === 1) return s;
                        } catch (_) {}
                    }

                    const parts = [];
                    let node = el;

                    while (node && node.nodeType === 1 && node !== document.body) {
                        let part = node.tagName.toLowerCase();

                        if (node.id) {
                            part = '#' + esc(node.id);
                            parts.unshift(part);
                            break;
                        }

                        const cls = [...node.classList]
                            .filter(c => /^[A-Za-z_][A-Za-z0-9_-]*$/.test(c))
                            .slice(0, 2);

                        if (cls.length) {
                            const candidate = part + cls.map(c => '.' + esc(c)).join('');
                            try {
                                if (document.querySelectorAll(candidate).length === 1) {
                                    part = candidate;
                                    parts.unshift(part);
                                    break;
                                }
                            } catch (_) {}
                            part = candidate;
                        }

                        const index = nth(node);
                        if (index > 1) part += `:nth-of-type(${index})`;

                        parts.unshift(part);

                        const candidate = parts.join(' > ');
                        try {
                            if (document.querySelectorAll(candidate).length === 1) {
                                return candidate;
                            }
                        } catch (_) {}

                        node = node.parentElement;
                    }

                    return parts.join(' > ');
                };

                const xpath = el => {
                    if (!el || el.nodeType !== 1) return '';
                    if (el.id) return `//*[@id="${String(el.id).replace(/"/g, '&quot;')}"]`;

                    const parts = [];
                    let node = el;

                    while (node && node.nodeType === 1) {
                        let index = 1;
                        let sibling = node.previousElementSibling;

                        while (sibling) {
                            if (sibling.tagName === node.tagName) index++;
                            sibling = sibling.previousElementSibling;
                        }

                        parts.unshift(
                            `${node.tagName.toLowerCase()}[${index}]`
                        );
                        node = node.parentElement;
                    }

                    return '/' + parts.join('/');
                };

                const roleOf = el => {
                    const explicit = el.getAttribute('role');
                    if (explicit) return explicit;

                    const tag = el.tagName.toLowerCase();
                    if (tag === 'button') return 'button';
                    if (tag === 'a' && el.hasAttribute('href')) return 'link';
                    if (tag === 'input') return 'textbox';
                    if (tag === 'textarea') return 'textbox';
                    if (tag === 'select') return 'combobox';
                    return '';
                };

                const describe = (el, index) => {
                    const rect = el.getBoundingClientRect();

                    return {
                        index,
                        tag: el.tagName.toLowerCase(),
                        role: roleOf(el),
                        selector: uniqueSelector(el),
                        xpath: xpath(el),
                        text: textOf(el).slice(0, 300),
                        ariaLabel: clean(el.getAttribute('aria-label')),
                        ariaLabelledby: clean(el.getAttribute('aria-labelledby')),
                        title: clean(el.getAttribute('title')),
                        id: clean(el.id),
                        name: clean(el.getAttribute('name')),
                        type: clean(el.getAttribute('type')),
                        placeholder: clean(el.getAttribute('placeholder')),
                        href: clean(el.getAttribute('href')),
                        value: clean(el.value).slice(0, 300),
                        autocomplete: clean(el.getAttribute('autocomplete')),
                        visible: visible(el),
                        enabled: enabled(el),
                        disabled: el.hasAttribute('disabled'),
                        checked: 'checked' in el ? !!el.checked : false,
                        selected: 'selected' in el ? !!el.selected : false,
                        required: el.hasAttribute('required'),
                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    };
                };

                const selectorParts = [
                    'button',
                    'a[href]',
                    'input',
                    'textarea',
                    'select',
                    'option',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="textbox"]',
                    '[role="combobox"]',
                    '[role="checkbox"]',
                    '[role="radio"]',
                    '[role="tab"]',
                    '[role="menuitem"]',
                    '[contenteditable="true"]',
                    '[tabindex]:not([tabindex="-1"])'
                ];

                const allInteractive = [
                    ...document.querySelectorAll(selectorParts.join(','))
                ];

                const seen = new Set();
                const interactive = [];

                for (const el of allInteractive) {
                    if (seen.has(el)) continue;
                    seen.add(el);

                    if (!includeHidden && !visible(el)) continue;

                    interactive.push(
                        describe(el, interactive.length + 1)
                    );

                    if (interactive.length >= maxInteractive) break;
                }

                const links = [...document.querySelectorAll('a[href]')]
                    .filter(x => includeHidden || visible(x))
                    .slice(0, maxLinks)
                    .map((el, i) => ({
                        index: i + 1,
                        text: textOf(el).slice(0, 200),
                        href: el.href,
                        selector: uniqueSelector(el),
                        target: clean(el.getAttribute('target')),
                        rel: clean(el.getAttribute('rel')),
                        visible: visible(el)
                    }));

                const forms = [...document.forms].map((form, i) => ({
                    index: i + 1,
                    selector: uniqueSelector(form),
                    action: form.action || '',
                    method: (form.method || 'get').toUpperCase(),
                    name: clean(form.getAttribute('name')),
                    id: clean(form.id),
                    fields: [...form.elements].slice(0, 80).map((el, j) => ({
                        index: j + 1,
                        tag: el.tagName.toLowerCase(),
                        type: clean(el.getAttribute('type')),
                        name: clean(el.getAttribute('name')),
                        id: clean(el.id),
                        placeholder: clean(el.getAttribute('placeholder')),
                        selector: uniqueSelector(el),
                        required: el.hasAttribute('required'),
                        disabled: el.hasAttribute('disabled')
                    }))
                }));

                const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                    .filter(x => includeHidden || visible(x))
                    .slice(0, 100)
                    .map(x => ({
                        level: Number(x.tagName.substring(1)),
                        text: clean(x.innerText).slice(0, 300),
                        selector: uniqueSelector(x)
                    }));

                const tables = [...document.querySelectorAll('table')]
                    .filter(x => includeHidden || visible(x))
                    .slice(0, 30)
                    .map((table, i) => ({
                        index: i + 1,
                        selector: uniqueSelector(table),
                        caption: clean(table.querySelector('caption')?.innerText),
                        headers: [...table.querySelectorAll('th')]
                            .slice(0, 30)
                            .map(x => clean(x.innerText)),
                        rows: [...table.querySelectorAll('tr')]
                            .slice(0, 10)
                            .map(row =>
                                [...row.querySelectorAll('th,td')]
                                    .slice(0, 20)
                                    .map(cell => clean(cell.innerText).slice(0, 150))
                            )
                    }));

                const iframes = [...document.querySelectorAll('iframe,frame')]
                    .slice(0, 30)
                    .map((el, i) => ({
                        index: i + 1,
                        selector: uniqueSelector(el),
                        src: el.src || el.getAttribute('src') || '',
                        name: clean(el.getAttribute('name')),
                        title: clean(el.getAttribute('title')),
                        visible: visible(el)
                    }));

                const bodyClone = document.body.cloneNode(true);
                bodyClone.querySelectorAll(
                    'script,style,noscript,svg,path,template'
                ).forEach(x => x.remove());

                const visibleText = clean(bodyClone.innerText || '')
                    .slice(0, maxText);

                const meta = [...document.querySelectorAll(
                    'meta[name],meta[property]'
                )]
                .slice(0, 80)
                .map(x => ({
                    name: x.getAttribute('name') || x.getAttribute('property') || '',
                    content: clean(x.getAttribute('content')).slice(0, 500)
                }));

                return {
                    url: location.href,
                    title: document.title,
                    lang: document.documentElement.lang || '',
                    viewport: {
                        width: window.innerWidth,
                        height: window.innerHeight,
                        scrollX: Math.round(window.scrollX),
                        scrollY: Math.round(window.scrollY),
                        documentWidth: document.documentElement.scrollWidth,
                        documentHeight: document.documentElement.scrollHeight
                    },
                    interactive,
                    links,
                    forms,
                    headings,
                    tables,
                    iframes,
                    meta,
                    visibleText
                };
            }
            """

            data = await page.evaluate(
                js,
                {
                    "maxInteractive": int(max_interactive),
                    "maxLinks": int(max_links),
                    "maxText": int(max_text),
                    "includeHidden": bool(include_hidden),
                },
            )

            out = []
            out.append("=== PAGE ===")
            out.append(f"URL: {data['url']}")
            out.append(f"TITLE: {data['title']}")
            out.append(f"LANG: {data['lang']}")
            vp = data["viewport"]
            out.append(
                "VIEWPORT: "
                f"{vp['width']}x{vp['height']} "
                f"scroll=({vp['scrollX']},{vp['scrollY']}) "
                f"document={vp['documentWidth']}x{vp['documentHeight']}"
            )

            out.append("\n=== INTERACTIVE ELEMENTS ===")
            if not data["interactive"]:
                out.append("None")
            else:
                for x in data["interactive"]:
                    out.append(
                        f"[{x['index']}] {x['tag'].upper()}"
                        f" role={x['role'] or '-'}"
                    )
                    out.append(f"  selector: {x['selector']}")
                    out.append(f"  xpath: {x['xpath']}")
                    if x["text"]:
                        out.append(f"  text: {x['text']}")
                    if x["ariaLabel"]:
                        out.append(f"  aria-label: {x['ariaLabel']}")
                    if x["name"]:
                        out.append(f"  name: {x['name']}")
                    if x["id"]:
                        out.append(f"  id: {x['id']}")
                    if x["type"]:
                        out.append(f"  type: {x['type']}")
                    if x["placeholder"]:
                        out.append(f"  placeholder: {x['placeholder']}")
                    if x["href"]:
                        out.append(f"  href: {x['href']}")
                    if x["value"]:
                        out.append(f"  value: {x['value']}")
                    out.append(
                        f"  visible={x['visible']} "
                        f"enabled={x['enabled']} "
                        f"disabled={x['disabled']} "
                        f"checked={x['checked']} "
                        f"selected={x['selected']} "
                        f"required={x['required']}"
                    )

            out.append("\n=== FORMS ===")
            for form in data["forms"]:
                out.append(
                    f"[FORM {form['index']}] "
                    f"method={form['method']} action={form['action']}"
                )
                out.append(f"  selector: {form['selector']}")
                for field in form["fields"]:
                    out.append(
                        f"  - {field['tag']} "
                        f"type={field['type'] or '-'} "
                        f"name={field['name'] or '-'} "
                        f"id={field['id'] or '-'}"
                    )
                    out.append(f"    selector: {field['selector']}")
                    if field["placeholder"]:
                        out.append(
                            f"    placeholder: {field['placeholder']}"
                        )

            out.append("\n=== HEADINGS ===")
            for h in data["headings"]:
                out.append(
                    f"H{h['level']}: {h['text']} "
                    f"| {h['selector']}"
                )

            out.append("\n=== LINKS ===")
            for link in data["links"]:
                out.append(
                    f"[{link['index']}] {link['text'] or '(no text)'} "
                    f"→ {link['href']}"
                )
                out.append(f"  selector: {link['selector']}")

            out.append("\n=== TABLES ===")
            for table in data["tables"]:
                out.append(
                    f"[TABLE {table['index']}] "
                    f"{table['selector']}"
                )
                if table["caption"]:
                    out.append(f"  caption: {table['caption']}")
                if table["headers"]:
                    out.append(
                        "  headers: " + " | ".join(table["headers"])
                    )
                for row in table["rows"]:
                    out.append(
                        "  row: " + " | ".join(row)
                    )

            out.append("\n=== IFRAMES ===")
            for frame in data["iframes"]:
                out.append(
                    f"[{frame['index']}] "
                    f"src={frame['src'] or '-'} "
                    f"title={frame['title'] or '-'}"
                )
                out.append(f"  selector: {frame['selector']}")

            out.append("\n=== META ===")
            for meta in data["meta"][:40]:
                out.append(
                    f"{meta['name']}: {meta['content']}"
                )

            out.append("\n=== VISIBLE TEXT ===")
            out.append(data["visibleText"] or "(empty)")

            return "\n".join(out)[:50000]

        return await browser_operation(operation)


# ============================================================
# DSPY ASYNC BRIDGE
# ============================================================

def run_async_from_dspy(coro):
    if main_event_loop is None:
        raise RuntimeError("Основной asyncio loop не установлен")
    if main_event_loop.is_closed():
        raise RuntimeError("Основной asyncio loop закрыт")

    future = asyncio.run_coroutine_threadsafe(coro, main_event_loop)

    try:
        return future.result(timeout=90)
    except Exception as e:
        future.cancel()
        raise RuntimeError(f"Browser tool error: {e}") from e


# ============================================================
# DSPY TOOLS
# ============================================================

def create_browser_tools():

    def tool_goto(url: str):
        return run_async_from_dspy(browser_goto(url))

    def tool_back():
        return run_async_from_dspy(browser_back())

    def tool_forward():
        return run_async_from_dspy(browser_forward())

    def tool_reload():
        return run_async_from_dspy(browser_reload())

    def tool_page_info():
        return run_async_from_dspy(browser_page_info())

    def tool_inspect_page(
        max_interactive: int = 120,
        max_links: int = 80,
        max_text: int = 12000,
    ):
        return run_async_from_dspy(
            browser_inspect(
                max_interactive=max_interactive,
                max_links=max_links,
                max_text=max_text,
            )
        )

    def tool_get_text(selector: str = "body"):
        return run_async_from_dspy(browser_get_text(selector))

    def tool_get_html(selector: str = "body"):
        return run_async_from_dspy(browser_get_html(selector))

    def tool_get_links():
        return run_async_from_dspy(browser_get_links())

    def tool_click(selector: str):
        return run_async_from_dspy(browser_click(selector))

    def tool_click_text(text: str):
        return run_async_from_dspy(browser_click_text(text))

    def tool_fill(selector: str, text: str):
        return run_async_from_dspy(browser_fill(selector, text))

    def tool_fill_placeholder(placeholder: str, text: str):
        return run_async_from_dspy(
            browser_fill_placeholder(placeholder, text)
        )

    def tool_type(selector: str, text: str):
        return run_async_from_dspy(browser_type(selector, text))

    def tool_press(selector: str, key: str):
        return run_async_from_dspy(browser_press(selector, key))

    def tool_key(key: str):
        return run_async_from_dspy(browser_key(key))

    def tool_wait(milliseconds: int = 1000):
        return run_async_from_dspy(browser_wait(milliseconds))

    def tool_wait_selector(selector: str, timeout: int = 10000):
        return run_async_from_dspy(
            browser_wait_selector(selector, timeout)
        )

    def tool_select(selector: str, value: str):
        return run_async_from_dspy(browser_select(selector, value))

    def tool_check(selector: str):
        return run_async_from_dspy(browser_check(selector))

    def tool_uncheck(selector: str):
        return run_async_from_dspy(browser_uncheck(selector))

    def tool_hover(selector: str):
        return run_async_from_dspy(browser_hover(selector))

    def tool_attribute(selector: str, attribute: str):
        return run_async_from_dspy(
            browser_attribute(selector, attribute)
        )

    def tool_count(selector: str):
        return run_async_from_dspy(browser_count(selector))

    def tool_javascript(expression: str):
        return run_async_from_dspy(browser_js(expression))

    def tool_screenshot():
        return run_async_from_dspy(browser_screenshot())

    def tool_content():
        return run_async_from_dspy(browser_content())

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
# AGNES LM
# ============================================================

class AgnesLM(dspy.LM):

    def __init__(
        self,
        model="agnes-2.0-flash",
        api_key=None,
        **kwargs,
    ):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        self.temperature = kwargs.get("temperature", 0.2)
        self.max_tokens = kwargs.get("max_tokens", 4000)

        super().__init__(
            model=model,
            model_type="chat",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            cache=False,
        )
        self.provider = "agnes-ai"

    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            raise RuntimeError("AGNES_API_KEY не задан")

        params = {**self.kwargs, **kwargs}
        api_messages = messages or [
            {"role": "user", "content": prompt or ""}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get(
                "temperature", self.temperature
            ),
            "max_tokens": params.get(
                "max_tokens", self.max_tokens
            ),
        }

        if params.get("tools"):
            payload["tools"] = params["tools"]
        if params.get("tool_choice"):
            payload["tool_choice"] = params["tool_choice"]

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
                f"Agnes HTTP {e.response.status_code}: {body}"
            ) from e

        except Exception as e:
            logger.exception("Agnes API")
            raise RuntimeError(f"Agnes API error: {e}") from e

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Agnes вернул пустой ответ: {data}")

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        return [content]

    def __call__(self, prompt=None, messages=None, **kwargs):
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

    Порядок работы:
    1. Открой сайт через tool_goto.
    2. Если DOM неизвестен — используй tool_inspect_page.
    3. Используй selector из inspector для click/fill/press.
    4. Для чтения используй tool_get_text.
    5. Для ссылок используй tool_get_links.
    6. После изменения страницы при необходимости снова inspect.
    7. Для динамических элементов используй wait/wait_selector.
    8. Не утверждай, что действие выполнено, пока tool не подтвердил его.
    9. Если selector не сработал, повторно inspect_page и измени стратегию.
    10. Используй несколько инструментов, когда это необходимо.
    11. В конце дай только краткий итог.
    """

    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Краткий итоговый результат")


def init_dspy():
    global dspy_agent_instance

    if not AGNES_API_KEY:
        logger.warning("AGNES_API_KEY не задан")
        return False

    try:
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.2,
            max_tokens=4000,
        )
        dspy.configure(lm=lm)

        tools = create_browser_tools()

        if REACT_V2_AVAILABLE:
            try:
                dspy_agent_instance = ReActV2(
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )
                logger.info("Используется ReActV2")
            except Exception as e:
                logger.warning("ReActV2 error: %s", e)
                dspy_agent_instance = dspy.ReAct(
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )
        else:
            dspy_agent_instance = dspy.ReAct(
                BrowserTask,
                tools=tools,
                max_iters=15,
            )

        logger.info("DSPy создан. Tools: %s", len(tools))
        return True

    except Exception:
        logger.exception("DSPy init error")
        dspy_agent_instance = None
        return False


def run_agent(question: str):
    if not dspy_agent_instance:
        return "DSPy агент не инициализирован"

    with agent_lock:
        try:
            result = dspy_agent_instance(question=question)

            answer = getattr(result, "answer", None)
            if answer is None and isinstance(result, dict):
                answer = result.get("answer")

            if answer is None:
                answer = str(result)

            answer = str(answer).strip()
            return answer or "Пустой ответ DSPy"

        except Exception as e:
            logger.exception("DSPy error")
            return f"Ошибка агента: {type(e).__name__}: {e}"


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "🦊 Camoufox + DSPy Browser Agent\n\n"
        "Команды:\n"
        "/check <url>\n"
        "/dspy <задача>\n"
        "/inspect\n"
        "/cookies\n"
        "/cancel\n"
        "/status\n"
        "/screenshot"
    )


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажи URL:\n/check https://example.com"
        )
        return

    msg = await update.message.reply_text("Открываю...")

    try:
        result = await browser_goto(context.args[0])
        text = await browser_get_text()
        await msg.edit_text(f"{result}\n\n{text[:1500]}")
    except Exception as e:
        logger.exception("/check")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def inspect_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    msg = await update.message.reply_text("🔎 Глубоко инспектирую страницу...")

    try:
        result = await browser_inspect()
        if len(result) > 4000:
            result = result[:4000] + "\n\n... [обрезано]"
        await msg.edit_text(result)
    except Exception as e:
        logger.exception("/inspect")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1500]}")


async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📸 Делаю скриншот...")

    try:
        path = await browser_screenshot()
        with open(path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="📸 Текущая страница",
            )
        await msg.delete()
    except Exception as e:
        logger.exception("/screenshot")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"🦊 Camoufox: {'✅' if CAMOUFOX_AVAILABLE else '❌'}\n"
        f"🌐 Browser: {'✅' if browser_ready else '❌'}\n"
        f"🧠 DSPy: {'✅' if dspy_agent_instance else '❌'}\n\n"
        f"🌐 URL:\n`{escape_markdown(url, version=2)}`\n\n"
        f"📄 Title:\n{escape_markdown(title, version=2)}"
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
        await update.message.reply_text("Camoufox не запущен")
        return

    user_id = update.effective_user.id
    waiting_for_cookies.add(user_id)

    await update.message.reply_text(
        "🍪 Жду JSON-файл с cookies.\n\n"
        "Отправь файл следующим сообщением.\n\n"
        "Для отмены: /cancel"
    )


async def cancel_cookies(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user_id = update.effective_user.id

    if user_id in waiting_for_cookies:
        waiting_for_cookies.discard(user_id)
        await update.message.reply_text("Загрузка cookies отменена.")
    else:
        await update.message.reply_text("Нечего отменять.")


async def cookies_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user_id = update.effective_user.id

    if user_id not in waiting_for_cookies:
        return

    document = update.message.document
    if not document:
        return

    filename = (document.file_name or "").lower()

    if not filename.endswith(".json"):
        await update.message.reply_text("Нужен именно JSON-файл.")
        return

    waiting_for_cookies.discard(user_id)
    msg = await update.message.reply_text("Загружаю cookies...")

    temp_path = (
        f"/tmp/cookies_{user_id}_{int(time.time())}.json"
    )

    try:
        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(temp_path)

        with open(temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = await load_cookies_from_json(data)
        loaded = result["loaded"]
        total = result["total"]
        errors = result["errors"]

        if loaded == 0:
            response = (
                "Не удалось загрузить ни одной cookie.\n\n"
                + "\n".join(f"• {e}" for e in errors[:15])
            )
        else:
            response = (
                "🍪 *Cookies обработаны!*\n\n"
                f"✅ Загружено: `{loaded}`\n"
                f"📦 Всего в файле: `{total}`"
            )

            if errors:
                response += "\n\n⚠️ Ошибки:\n"
                response += "\n".join(
                    f"• {e}" for e in errors[:10]
                )

        await msg.edit_text(
            response,
            parse_mode="Markdown",
        )

    except json.JSONDecodeError:
        await msg.edit_text("Файл не является корректным JSON.")
    except Exception as e:
        logger.exception("Ошибка загрузки cookies")
        await msg.edit_text(
            f"Ошибка загрузки cookies:\n\n{str(e)[:2000]}"
        )
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
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
            "/dspy открой https://example.com и покажи заголовок\n\n"
            "/dspy найди Python на Google\n\n"
            "/dspy открой сайт и найди форму входа"
        )
        return

    if not dspy_agent_instance:
        await update.message.reply_text("DSPy не инициализирован")
        return

    if not browser_ready:
        await update.message.reply_text("Camoufox не запущен")
        return

    query = " ".join(context.args)
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
            "✅ *Результат:*\n\n" + safe_answer,
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        logger.exception("/dspy")
        await msg.edit_text(f"Ошибка:\n{str(e)[:1000]}")


async def telegram_error_handler(update, context):
    logger.error(
        "Telegram error",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    global main_event_loop

    main_event_loop = asyncio.get_running_loop()

    logger.info("Инициализация...")

    browser_ok = await init_browser()
    dspy_ok = init_dspy()

    app = (
        Application
        .builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_error_handler(telegram_error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("inspect", inspect_command))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("cancel", cancel_cookies))

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

        logger.info("Telegram бот запущен!")

        stop_signal = asyncio.Event()

        def signal_handler():
            logger.info("Получен сигнал остановки")
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
        except (NotImplementedError, RuntimeError):
            pass

        while not stop_signal.is_set():
            await asyncio.sleep(60)
            logger.info("Bot alive")

    except Exception:
        logger.exception("Main error")

    finally:
        logger.info("Завершение...")

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
    asyncio.run(main())