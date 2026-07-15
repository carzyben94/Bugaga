import logging
import json  # ← ДОБАВИТЬ
logger = logging.getLogger(__name__)


class Eval:
    def __init__(self, browser):
        self.browser = browser

    async def execute(self, js_code: str, return_by_value: bool = True, await_promise: bool = False):
        result = await self.browser.send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": return_by_value,
            "awaitPromise": await_promise
        })
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        remote = result.get("result", {})
        if "value" in remote:
            return remote["value"]
        return remote

    # ===== DOM =====
    async def get_text(self, selector: str) -> str:
        return await self.execute(
            f"document.querySelector('{selector}')?.innerText || ''"
        )

    async def get_html(self, selector: str = None) -> str:
        if selector:
            return await self.execute(
                f"document.querySelector('{selector}')?.outerHTML || ''"
            )
        return await self.execute("document.documentElement.outerHTML")

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
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return getComputedStyle(el)['{property_name}'] || '';
            }})()
        """)

    async def get_class_list(self, selector: str) -> list:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.classList);
            }})()
        """)

    async def get_dataset(self, selector: str) -> dict:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return {{}};
                return {{...el.dataset}};
            }})()
        """)

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
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.options).map(opt => ({{
                    text: opt.text,
                    value: opt.value,
                    selected: opt.selected
                }}));
            }})()
        """)

    async def get_position(self, selector: str) -> dict:
        return await self.execute(f"""
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
        """)

    async def get_count(self, selector: str) -> int:
        return await self.execute(
            f"document.querySelectorAll('{selector}').length"
        )

    # ===== ПРОВЕРКИ =====
    async def is_visible(self, selector: str) -> bool:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }})()
        """)

    async def is_enabled(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.disabled === false || true"
        )

    async def is_checked(self, selector: str) -> bool:
        return await self.execute(
            f"document.querySelector('{selector}')?.checked || false"
        )

    async def exists(self, selector: str) -> bool:
        safe_selector = json.dumps(selector)
        return await self.execute(
            f"document.querySelector({safe_selector}) !== null"
        )

    # ===== ОЖИДАНИЯ =====
    async def wait_for(self, selector: str, timeout: int = 10) -> bool:
        js = f"""
            (function() {{
                return new Promise((resolve) => {{
                    const start = Date.now();
                    const timeout = {timeout * 1000};
                    function check() {{
                        const el = document.querySelector('{selector}');
                        if (el) {{ resolve(true); return; }}
                        if (Date.now() - start > timeout) {{ resolve(false); return; }}
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
                        if (Date.now() - start > timeout) {{ resolve(false); return; }}
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
                        if (Date.now() - start > timeout) {{ resolve(false); return; }}
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
                        if (Date.now() - start > timeout) {{ resolve(false); return; }}
                        requestAnimationFrame(check);
                    }}
                    check();
                }});
            }})()
        """
        return await self.execute(js, await_promise=True)

    # ===== ДЕЙСТВИЯ =====
    async def click_js(self, selector: str) -> bool:
        """Клик через JS с безопасным экранированием"""
        safe_selector = json.dumps(selector)
        return await self.execute(
            f"""
            (function() {{
                const el = document.querySelector({safe_selector});
                if (!el) return false;
                el.click();
                return true;
            }})()
            """
        )

    async def type_js(self, selector: str, text: str) -> bool:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.value = '{text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
        """)

    async def scroll_to(self, selector: str) -> bool:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return true;
            }})()
        """)

    async def scroll_to_top(self) -> None:
        await self.execute("window.scrollTo({top: 0, behavior: 'smooth'})")

    async def scroll_to_bottom(self) -> None:
        await self.execute("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")

    async def focus(self, selector: str) -> bool:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.focus();
                return true;
            }})()
        """)

    async def blur(self, selector: str) -> bool:
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.blur();
                return true;
            }})()
        """)

    # ===== ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ =====
    async def get_all_buttons(self) -> list:
        return await self.execute("""
            (function() {
                return Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="link"]')).map(el => ({
                    text: el.innerText || el.value || el.title || el.getAttribute('aria-label') || '',
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
        """)

    async def get_all_inputs(self) -> list:
        return await self.execute("""
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
        """)

    async def get_all_checkboxes(self) -> list:
        return await self.execute("""
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
        """)

    async def get_all_selects(self) -> list:
        return await self.execute("""
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
        """)

    async def get_all_links(self) -> list:
        return await self.execute("""
            (function() {
                return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim(),
                    href: a.href,
                    target: a.target || '',
                    testId: a.getAttribute('data-testid') || ''
                }));
            })()
        """)

    async def get_all_forms(self) -> list:
        return await self.execute("""
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
        """)

    async def get_button(self, selector: str) -> dict:
        return await self.execute(f"""
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
        """)

    async def get_input(self, selector: str) -> dict:
        return await self.execute(f"""
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
        """)

    async def click_button(self, selector: str) -> bool:
        safe_selector = json.dumps(selector)
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector({safe_selector});
                if (!el) return false;
                el.click();
                return true;
            }})()
        """)

    async def fill_input(self, selector: str, text: str) -> bool:
        safe_selector = json.dumps(selector)
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector({safe_selector});
                if (!el) return false;
                el.focus();
                el.value = '{text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.blur();
                return true;
            }})()
        """)

    async def check_checkbox(self, selector: str, checked: bool = True) -> bool:
        safe_selector = json.dumps(selector)
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector({safe_selector});
                if (!el) return false;
                if (el.checked !== {str(checked).lower()}) {{
                    el.click();
                }}
                return true;
            }})()
        """)

    async def select_option(self, selector: str, value: str) -> bool:
        safe_selector = json.dumps(selector)
        return await self.execute(f"""
            (function() {{
                const el = document.querySelector({safe_selector});
                if (!el) return false;
                el.value = '{value}';
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
        """)

    # ===== STORAGE =====
    async def get_local_storage(self, key: str) -> str:
        return await self.execute(f"localStorage.getItem('{key}') || ''")

    async def set_local_storage(self, key: str, value: str) -> None:
        await self.execute(f"localStorage.setItem('{key}', '{value}')")

    async def get_session_storage(self, key: str) -> str:
        return await self.execute(f"sessionStorage.getItem('{key}') || ''")

    async def set_session_storage(self, key: str, value: str) -> None:
        await self.execute(f"localStorage.setItem('{key}', '{value}')")

    async def get_cookies(self) -> list:
        cookies_str = await self.execute("document.cookie")
        if not cookies_str:
            return []
        return [c.strip() for c in cookies_str.split(';')]

    # ===== СТРУКТУРА СТРАНИЦЫ =====
    async def get_page_info(self) -> dict:
        return await self.execute("""
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
        """)

    async def get_all_images(self) -> list:
        return await self.execute("""
            (function() {
                return Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.width,
                    height: img.height
                }));
            })()
        """)

    # ===== КОНТЕКСТ =====
    async def get_elements_with_context(self, scroll: bool = True) -> dict:
        if scroll:
            await self.scroll_page(times=3, pause=0.8)
        
        return await self.execute("""
            (function() {
                const result = {
                    navigation: [],
                    header: [],
                    main: [],
                    articles: [],
                    footer: [],
                    complementary: [],
                    other: []
                };

                const elements = document.querySelectorAll('button, input:not([type="hidden"]), a[href], form, [role="button"], [role="link"]');
                
                elements.forEach(el => {
                    const info = {
                        tag: el.tagName,
                        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim(),
                        testId: el.getAttribute('data-testid') || '',
                        id: el.id || '',
                        class: el.className || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        role: el.getAttribute('role') || ''
                    };

                    let parent = el;
                    let zone = 'other';
                    let depth = 0;
                    
                    while (parent && parent !== document.body && depth < 10) {
                        const tag = parent.tagName.toLowerCase();
                        const role = parent.getAttribute('role') || '';
                        const testId = parent.getAttribute('data-testid') || '';
                        
                        if (tag === 'nav' || role === 'navigation') { zone = 'navigation'; break; }
                        if (tag === 'header' || role === 'banner') { zone = 'header'; break; }
                        if (tag === 'main' || role === 'main') { zone = 'main'; break; }
                        if (tag === 'article' || role === 'article') { zone = 'articles'; break; }
                        if (tag === 'footer' || role === 'contentinfo') { zone = 'footer'; break; }
                        if (tag === 'aside' || role === 'complementary') { zone = 'complementary'; break; }
                        
                        if (testId.includes('SideNav')) { zone = 'navigation'; break; }
                        if (testId.includes('Search')) { zone = 'header'; break; }
                        if (testId.includes('tweet') || testId.includes('post')) { zone = 'main'; break; }
                        
                        parent = parent.parentElement;
                        depth++;
                    }
                    
                    if (result[zone]) result[zone].push(info);
                    else result.other.push(info);
                });

                return result;
            })()
        """)

    async def scroll_page(self, times: int = 3, pause: float = 0.8):
        for i in range(times):
            await self.execute(f"window.scrollTo(0, document.body.scrollHeight * {(i+1) / times})")
            await asyncio.sleep(pause)
        await self.execute("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)