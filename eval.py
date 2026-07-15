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
        """
        Args:
            browser: экземпляр Browser из browser.py
        """
        self.browser = browser
    
    async def execute(self, js_code: str, return_by_value: bool = True) -> dict:
        """
        Выполнить произвольный JS код на странице.
        
        Args:
            js_code: строка с JavaScript кодом
            return_by_value: вернуть результат как JSON (True) или objectId (False)
        
        Returns:
            результат выполнения JS
        """
        result = await self.browser.send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": return_by_value
        })
        return result
    
    # ========== DOM ==========
    
    async def get_text(self, selector: str) -> str:
        """Получить текст элемента по селектору"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.innerText || ''"
        )
        return result.get("value", "")
    
    async def get_html(self, selector: str = None) -> str:
        """Получить HTML элемента или всей страницы"""
        if selector:
            js = f"document.querySelector('{selector}')?.outerHTML || ''"
        else:
            js = "document.documentElement.outerHTML"
        result = await self.execute(js)
        return result.get("value", "")
    
    async def get_title(self) -> str:
        """Получить заголовок страницы"""
        result = await self.execute("document.title")
        return result.get("value", "")
    
    async def get_url(self) -> str:
        """Получить текущий URL"""
        result = await self.execute("window.location.href")
        return result.get("value", "")
    
    async def get_attribute(self, selector: str, attr: str) -> str:
        """Получить атрибут элемента"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.getAttribute('{attr}') || ''"
        )
        return result.get("value", "")
    
    async def get_inner_html(self, selector: str) -> str:
        """Получить innerHTML элемента"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.innerHTML || ''"
        )
        return result.get("value", "")
    
    async def get_outer_html(self, selector: str) -> str:
        """Получить outerHTML элемента"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.outerHTML || ''"
        )
        return result.get("value", "")
    
    async def get_style(self, selector: str, property_name: str) -> str:
        """Получить CSS свойство элемента"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return getComputedStyle(el)['{property_name}'] || '';
            }})()
            """
        )
        return result.get("value", "")
    
    async def get_class_list(self, selector: str) -> list:
        """Получить список классов элемента"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                return Array.from(el.classList);
            }})()
            """
        )
        return result.get("value", [])
    
    async def get_dataset(self, selector: str) -> dict:
        """Получить dataset элемента"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return {{}};
                return {{...el.dataset}};
            }})()
            """
        )
        return result.get("value", {})
    
    async def get_value(self, selector: str) -> str:
        """Получить значение input/textarea/select"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.value || ''"
        )
        return result.get("value", "")
    
    async def get_checked(self, selector: str) -> bool:
        """Получить состояние checkbox/radio"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.checked || false"
        )
        return result.get("value", False)
    
    async def get_selected(self, selector: str) -> bool:
        """Получить состояние option"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.selected || false"
        )
        return result.get("value", False)
    
    async def get_options(self, selector: str) -> list:
        """Получить все options из select"""
        result = await self.execute(
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
        return result.get("value", [])
    
    async def get_position(self, selector: str) -> dict:
        """Получить позицию элемента на странице"""
        result = await self.execute(
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
        return result.get("value", {})
    
    async def get_count(self, selector: str) -> int:
        """Получить количество элементов по селектору"""
        result = await self.execute(
            f"document.querySelectorAll('{selector}').length"
        )
        return result.get("value", 0)
    
    # ========== ПРОВЕРКИ ==========
    
    async def is_visible(self, selector: str) -> bool:
        """Проверить, видим ли элемент"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }})()
            """
        )
        return result.get("value", False)
    
    async def is_enabled(self, selector: str) -> bool:
        """Проверить, включен ли элемент (не disabled)"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.disabled === false || true"
        )
        return result.get("value", True)
    
    async def is_checked(self, selector: str) -> bool:
        """Проверить, выбран ли checkbox/radio"""
        result = await self.execute(
            f"document.querySelector('{selector}')?.checked || false"
        )
        return result.get("value", False)
    
    async def exists(self, selector: str) -> bool:
        """Проверить, существует ли элемент"""
        result = await self.execute(
            f"document.querySelector('{selector}') !== null"
        )
        return result.get("value", False)
    
    # ========== ОЖИДАНИЯ ==========
    
    async def wait_for(self, selector: str, timeout: int = 10) -> bool:
        """
        Ожидать появления элемента на странице.
        
        Args:
            selector: CSS селектор
            timeout: таймаут в секундах
        
        Returns:
            True если элемент появился, иначе False
        """
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
        result = await self.execute(js)
        return result.get("value", False)
    
    async def wait_for_visible(self, selector: str, timeout: int = 10) -> bool:
        """Ожидать, когда элемент станет видимым"""
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
        result = await self.execute(js)
        return result.get("value", False)
    
    async def wait_for_text(self, selector: str, text: str, timeout: int = 10) -> bool:
        """Ожидать, когда элемент содержит определенный текст"""
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
        result = await self.execute(js)
        return result.get("value", False)
    
    async def wait_for_url(self, url_part: str, timeout: int = 10) -> bool:
        """Ожидать, когда URL станет содержать подстроку"""
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
        result = await self.execute(js)
        return result.get("value", False)
    
    # ========== МАНИПУЛЯЦИИ ==========
    
    async def click_js(self, selector: str) -> bool:
        """Клик через JS (простой, без humanize)"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.click();
                return true;
            }})()
            """
        )
        return result.get("value", False)
    
    async def type_js(self, selector: str, text: str) -> bool:
        """Ввод текста через JS (простой, без humanize)"""
        result = await self.execute(
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
        return result.get("value", False)
    
    async def scroll_to(self, selector: str) -> bool:
        """Скролл к элементу"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return true;
            }})()
            """
        )
        return result.get("value", False)
    
    async def scroll_to_top(self) -> None:
        """Скролл наверх"""
        await self.execute("window.scrollTo({top: 0, behavior: 'smooth'})")
    
    async def scroll_to_bottom(self) -> None:
        """Скролл вниз"""
        await self.execute("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
    
    async def focus(self, selector: str) -> bool:
        """Фокус на элементе"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.focus();
                return true;
            }})()
            """
        )
        return result.get("value", False)
    
    async def blur(self, selector: str) -> bool:
        """Снять фокус с элемента"""
        result = await self.execute(
            f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.blur();
                return true;
            }})()
            """
        )
        return result.get("value", False)
    
    # ========== STORAGE ==========
    
    async def get_local_storage(self, key: str) -> str:
        """Получить значение из localStorage"""
        result = await self.execute(f"localStorage.getItem('{key}') || ''")
        return result.get("value", "")
    
    async def set_local_storage(self, key: str, value: str) -> None:
        """Установить значение в localStorage"""
        await self.execute(f"localStorage.setItem('{key}', '{value}')")
    
    async def get_session_storage(self, key: str) -> str:
        """Получить значение из sessionStorage"""
        result = await self.execute(f"sessionStorage.getItem('{key}') || ''")
        return result.get("value", "")
    
    async def set_session_storage(self, key: str, value: str) -> None:
        """Установить значение в sessionStorage"""
        await self.execute(f"sessionStorage.setItem('{key}', '{value}')")
    
    async def get_cookies(self) -> list:
        """Получить все cookies"""
        result = await self.execute("document.cookie")
        cookies_str = result.get("value", "")
        if not cookies_str:
            return []
        return [c.strip() for c in cookies_str.split(';')]
    
    # ========== ПРОЧЕЕ ==========
    
    async def get_page_info(self) -> dict:
        """Получить всю информацию о странице"""
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
        result = await self.execute(js)
        return result.get("value", {})
    
    async def get_all_links(self) -> list:
        """Получить все ссылки на странице"""
        result = await self.execute(
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
        return result.get("value", [])
    
    async def get_all_images(self) -> list:
        """Получить все изображения на странице"""
        result = await self.execute(
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
        return result.get("value", [])
    
    async def get_all_forms(self) -> list:
        """Получить все формы на странице"""
        result = await self.execute(
            """
            (function() {
                return Array.from(document.querySelectorAll('form')).map(form => ({
                    action: form.action,
                    method: form.method,
                    id: form.id || '',
                    name: form.name || '',
                    inputs: Array.from(form.querySelectorAll('input, textarea, select')).map(el => ({
                        type: el.type || el.tagName,
                        name: el.name || '',
                        id: el.id || '',
                        value: el.value || ''
                    }))
                }));
            })()
            """
        )
        return result.get("value", [])