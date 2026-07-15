import logging
import json
import asyncio

logger = logging.getLogger(__name__)


class Eval:
    """
    Выполнение JavaScript на странице через CDP.
    Все методы возвращают результат выполнения JS.
    """
    
    def __init__(self, browser):
        self.browser = browser
    
    async def execute(self, js_code: str, return_by_value: bool = True, await_promise: bool = False):
        result = await self.browser.send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": return_by_value,
            "awaitPromise": await_promise
        })

        if "exceptionDetails" in result:
            exception = result["exceptionDetails"]
            error_text = exception.get("text", "Unknown JS error")
            logger.error(f"JavaScript error: {error_text}")
            raise RuntimeError(f"JavaScript execution failed: {error_text}")

        remote_object = result.get("result", {})
        if not remote_object:
            logger.error(f"No 'result' field in CDP response: {result}")
            return None

        if "value" in remote_object:
            return remote_object["value"]
        elif "objectId" in remote_object:
            logger.warning(f"Received objectId instead of value for: {js_code[:50]}...")
            return f"<ObjectReference: {remote_object['objectId']}>"
        else:
            logger.error(f"Unexpected RemoteObject structure: {remote_object}")
            return None
    
    # ========== DOM ==========
    
    async def get_text(self, selector: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.innerText || ''"
        )
    
    async def get_html(self, selector: str = None) -> str:
        if selector:
            js = f"document.querySelector('{selector}')?.outerHTML || ''"
        else:
            js = "document.documentElement.outerHTML"
        return await self.execute(js)
    
    async def get_title(self) -> str:
        return await self.execute("document.title")
    
    async def get_url(self) -> str:
        return await self.execute("window.location.href")
    
    async def get_attribute(self, selector: str, attr: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.getAttribute('{attr}') || ''"
        )
    
    async def get_inner_html(self, selector: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.innerHTML || ''"
        )
    
    async def get_outer_html(self, selector: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.outerHTML || ''"
        )
    
    async def get_style(self, selector: str, property_name: str) -> str:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return getComputedStyle(el)['{property_name}'] || '';
            }})()
            """
        )
    
    async def get_class_list(self, selector: str) -> list:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.classList);
            }})()
            """
        )
    
    async def get_dataset(self, selector: str) -> dict:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return {{}};
                return {{...el.dataset}};
            }})()
            """
        )
    
    async def get_value(self, selector: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.value || ''"
        )
    
    async def get_checked(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.checked || false"
        )
    
    async def get_selected(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.selected || false"
        )
    
    async def get_options(self, selector: str) -> list:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.options).map(opt => ({{
                    text: opt.text,
                    value: opt.value,
                    selected: opt.selected
                }}));
            }})()
            """
        )
    
    async def get_position(self, selector: str) -> dict:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    top: rect.top,
                    right: rect.right,
                    bottom: rect.bottom,
                    left: rect.left
                }};
            }})()
            """
        )
    
    async def get_count(self, selector: str) -> int:
        return await self.execute(
            f"document.querySelectorAll('{selector}').length"
        )
    
    # ========== ПРОВЕРКИ ==========
    
    async def is_visible(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }})()
            """
        )
    
    async def is_enabled(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.disabled === false || true"
        )
    
    async def is_checked(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.checked || false"
        )
    
    async def exists(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}') !== null"
        )
    
    # ========== ОЖИДАНИЯ ==========
    
    async def wait_for(self, selector: str, timeout: int = 10) -> bool:
        js = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const timeout = {timeout * 1000};
                
                function check() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve(true);
                        return;
                    }}
                    if (Date.now() - start > timeout) {{
                        resolve(false);
                        return;
                    }}
                    requestAnimationFrame(check);
                }}
                check();
            }});
        }})()
        """
        return await self.execute(js, await_promise=True)
    
    async def wait_for_visible(self, selector: str, timeout: int = 10) -> bool:
        js = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const timeout = {timeout * 1000};
                
                function check() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            resolve(true);
                            return;
                        }}
                    }}
                    if (Date.now() - start > timeout) {{
                        resolve(false);
                        return;
                    }}
                    requestAnimationFrame(check);
                }}
                check();
            }});
        }})()
        """
        return await self.execute(js, await_promise=True)
    
    async def wait_for_text(self, selector: str, text: str, timeout: int = 10) -> bool:
        js = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const timeout = {timeout * 1000};
                
                function check() {{
                    const el = document.querySelector('{selector}');
                    if (el && el.innerText.includes('{text}')) {{
                        resolve(true);
                        return;
                    }}
                    if (Date.now() - start > timeout) {{
                        resolve(false);
                        return;
                    }}
                    requestAnimationFrame(check);
                }}
                check();
            }});
        }})()
        """
        return await self.execute(js, await_promise=True)
    
    async def wait_for_url(self, url_part: str, timeout: int = 10) -> bool:
        js = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const timeout = {timeout * 1000};
                
                function check() {{
                    if (window.location.href.includes('{url_part}')) {{
                        resolve(true);
                        return;
                    }}
                    if (Date.now() - start > timeout) {{
                        resolve(false);
                        return;
                    }}
                    requestAnimationFrame(check);
                }}
                check();
            }});
        }})()
        """
        return await self.execute(js, await_promise=True)
    
    # ========== МАНИПУЛЯЦИИ ==========
    
    async def click_js(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.click();
                return true;
            }})()
            """
        )
    
    async def type_js(self, selector: str, text: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.value = '{text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
            """
        )
    
    async def scroll_to(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return true;
            }})()
            """
        )
    
    async def scroll_to_top(self) -> None:
        await self.execute("window.scrollTo({top: 0, behavior: 'smooth'})")
    
    async def scroll_to_bottom(self) -> None:
        await self.execute("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
    
    async def focus(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.focus();
                return true;
            }})()
            """
        )
    
    async def blur(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.blur();
                return true;
            }})()
            """
        )
    
    # ========== ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ ==========
    
    async def get_all_buttons(self) -> list:
        """Получить все кнопки с data-testid"""
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="link"]')).map(el => ({
                    text: el.innerText || el.value || el.textContent || el.title || el.getAttribute('aria-label') || '',
                    type: el.type || el.tagName.toLowerCase(),
                    id: el.id || '',
                    name: el.name || '',
                    class: el.className || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || '',
                    ariaLabel: el.getAttribute('aria-label') || ''
                }));
            })()
            """
        )
    
    async def get_all_inputs(self) -> list:
        """Получить все поля ввода с data-testid"""
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('input:not([type="submit"]):not([type="button"]):not([type="hidden"]), textarea, select')).map(el => ({
                    type: el.type || el.tagName.toLowerCase(),
                    name: el.name || el.id || '',
                    id: el.id || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    title: el.title || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || ''
                }));
            })()
            """
        )
    
    async def get_all_checkboxes(self) -> list:
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"]')).map(el => ({
                    type: el.type,
                    name: el.name || el.id || '',
                    id: el.id || '',
                    checked: el.checked || false,
                    disabled: el.disabled || false,
                    value: el.value || '',
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || ''
                }));
            })()
            """
        )
    
    async def get_all_selects(self) -> list:
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('select')).map(el => ({
                    name: el.name || el.id || '',
                    id: el.id || '',
                    value: el.value || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || '',
                    options: Array.from(el.options).map(opt => ({
                        text: opt.text,
                        value: opt.value,
                        selected: opt.selected
                    }))
                }));
            })()
            """
        )
    
    async def get_button(self, selector: str) -> dict:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{
                    text: el.innerText || el.value || el.getAttribute('aria-label') || el.title || '',
                    type: el.type || 'button',
                    id: el.id || '',
                    name: el.name || '',
                    class: el.className || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || '',
                    position: {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left
                    }}
                }};
            }})()
            """
        )
    
    async def get_input(self, selector: str) -> dict:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{
                    type: el.type || el.tagName.toLowerCase(),
                    name: el.name || el.id || '',
                    id: el.id || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    title: el.title || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null,
                    testId: el.getAttribute('data-testid') || '',
                    position: {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left
                    }}
                }};
            }})()
            """
        )
    
    async def click_button(self, selector: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.click();
                return true;
            }})()
            """
        )
    
    async def fill_input(self, selector: str, text: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.focus();
                el.value = '{text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.blur();
                return true;
            }})()
            """
        )
    
    async def check_checkbox(self, selector: str, checked: bool = True) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                if (el.checked !== {str(checked).lower()}) {{
                    el.click();
                }}
                return true;
            }})()
            """
        )
    
    async def select_option(self, selector: str, value: str) -> bool:
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.value = '{value}';
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
            """
        )
    
    # ========== STORAGE ==========
    
    async def get_local_storage(self, key: str) -> str:
        return await self.execute(f"localStorage.getItem('{key}') || ''")
    
    async def set_local_storage(self, key: str, value: str) -> None:
        await self.execute(f"localStorage.setItem('{key}', '{value}')")
    
    async def get_session_storage(self, key: str) -> str:
        return await self.execute(f"sessionStorage.getItem('{key}') || ''")
    
    async def set_session_storage(self, key: str, value: str) -> None:
        await self.execute(f"sessionStorage.setItem('{key}', '{value}')")
    
    async def get_cookies(self) -> list:
        cookies_str = await self.execute("document.cookie")
        if not cookies_str:
            return []
        return [c.strip() for c in cookies_str.split(';')]
    
    # ========== ПРОЧЕЕ ==========
    
    async def get_page_info(self) -> dict:
        js = """
        (function() {
            return {
                url: window.location.href,
                title: document.title,
                html: document.documentElement.outerHTML,
                innerText: document.body.innerText,
                language: document.documentElement.lang || navigator.language,
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                screenWidth: screen.width,
                screenHeight: screen.height,
                viewportWidth: window.innerWidth,
                viewportHeight: window.innerHeight,
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                scrollHeight: document.documentElement.scrollHeight,
                scrollWidth: document.documentElement.scrollWidth
            };
        })()
        """
        return await self.execute(js)
    
    async def get_all_links(self) -> list:
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim(),
                    href: a.href,
                    target: a.target || ''
                }));
            })()
            """
        )
    
    async def get_all_images(self) -> list:
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.width,
                    height: img.height
                }));
            })()
            """
        )
    
    async def get_all_forms(self) -> list:
        return await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('form')).map(form => ({
                    action: form.action,
                    method: form.method,
                    id: form.id || '',
                    name: form.name || '',
                    testId: form.getAttribute('data-testid') || '',
                    inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(el => ({
                        type: el.type || el.tagName.toLowerCase(),
                        name: el.name || el.id || '',
                        id: el.id || '',
                        value: el.value || '',
                        testId: el.getAttribute('data-testid') || ''
                    }))
                }));
            })()
            """
        )