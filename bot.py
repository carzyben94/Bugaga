import os
import logging
import json
import subprocess
import time
import requests
import re
import base64
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets
from io import BytesIO

# Пытаемся импортировать PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("⚠️ PIL не установлен, скриншоты могут не работать")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"

# ---------- Куки для X.com (Twitter) ----------
X_COOKIES = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "dnt",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "1"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "u%3D2067347503503052800"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "auth_token",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "Eb4nVvazwJ5mDp0c.6Ye5ub0rukgdQkcFzPf8.wdbIQ-1783798267.7075489-1.0.1.1-59IptPdWY9w0zyKvebR59I.8iB4M1DWfNNZQW0.c.E4lDCU3wTfEcds69RVBkOeQ9LUDZNLGRv6z8InGbCsH1RaTCKaqehL94yq0FgvU7QB9cbE8BO4.2Y8BMRnN_Nks"
    }
]

# ---------- Логирование ----------

LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи бота ===\n")
            f.write(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- Chrome ----------

def start_chrome_with_mask():
    """Запуск Chrome с маскировкой"""
    try:
        file_logger.log("Запуск Chrome с маскировкой...")
        
        # Проверяем, запущен ли уже Chrome
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
            return True
        
        # Запускаем Chrome с маскировкой
        subprocess.Popen([
            CHROME_PATH,
            "--headless=new",
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--user-data-dir=/tmp/chrome-profile",
            "--window-size=1920,1080",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-web-security",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-notifications"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        
        time.sleep(5)
        file_logger.log("✅ Chrome с маскировкой запущен")
        return True
        
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return False

def get_page_ws_url():
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        for page in pages:
            if page.get("type") == "page":
                ws_url = page.get("webSocketDebuggerUrl")
                file_logger.log(f"✅ WebSocket: {ws_url}")
                return ws_url
        return None
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

def create_page():
    try:
        response = requests.get("http://localhost:9222/json/new?about:blank")
        data = response.json()
        ws_url = data.get("webSocketDebuggerUrl")
        file_logger.log(f"✅ Создана страница: {ws_url}")
        return ws_url
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

# ---------- CDP Client ----------

class CDPClient:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.user_id = None
        self.full_snapshot = None
        self.history = []
        self.cookies_set = False
        self.masked = False
    
    async def connect(self):
        if self.connected:
            return True
        
        file_logger.log(f"Подключение для пользователя {self.user_id}")
        
        ws_url = get_page_ws_url()
        if not ws_url:
            ws_url = create_page()
        
        if not ws_url:
            file_logger.log("❌ Не удалось получить WebSocket URL", "ERROR")
            return False
        
        try:
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=10
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            await self.send("Network.enable", {})
            file_logger.log("✅ Page, Runtime, DOM, Network включены")
            
            # Применяем маскировку
            await self.apply_mask()
            
            # Устанавливаем куки
            await self.set_cookies(X_COOKIES)
            
            await self.navigate("https://google.com")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            return False
    
    async def reconnect(self):
        """Переподключение при разрыве"""
        file_logger.log("🔄 Переподключение...")
        self.connected = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        return await self.connect()
    
    async def apply_mask(self):
        """Применение маскировки через JS"""
        try:
            file_logger.log("🕵️ Применяю маскировку браузера...")
            
            mask_js = """
            (function() {
                // Маскировка navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Маскировка chrome
                if (!window.chrome) {
                    window.chrome = {
                        runtime: {}
                    };
                }
                
                // Маскировка plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Маскировка languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en']
                });
                
                // Маскировка permissions
                if (window.navigator.permissions) {
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                }
                
                return { success: true };
            })()
            """
            
            result = await self.eval_js(mask_js)
            if result and result.get('success'):
                self.masked = True
                file_logger.log("✅ Маскировка применена")
                return True
            else:
                file_logger.log("⚠️ Маскировка применена частично", "WARNING")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка маскировки: {e}", "ERROR")
            return False
    
    async def set_cookies(self, cookies):
        """Установка кук в браузере"""
        try:
            file_logger.log(f"🍪 Установка {len(cookies)} кук...")
            
            # Форматируем куки для CDP
            cdp_cookies = []
            for cookie in cookies:
                cdp_cookie = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain"),
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": cookie.get("sameSite", "unspecified"),
                    "session": cookie.get("session", True)
                }
                cdp_cookies.append(cdp_cookie)
            
            # Отправляем куки через CDP
            result = await self.send("Network.setCookies", {
                "cookies": cdp_cookies
            })
            
            if "error" not in result:
                self.cookies_set = True
                file_logger.log(f"✅ Установлено {len(cookies)} кук")
                return True
            else:
                file_logger.log(f"❌ Ошибка установки кук: {result.get('error')}", "ERROR")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка установки кук: {e}", "ERROR")
            return False
    
    async def send(self, method, params=None):
        if not self.connected:
            await self.connect()
        
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            await self.ws.send(json.dumps(msg))
            
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(response)
                
                if data.get("id") == msg_id:
                    if "error" in data:
                        file_logger.log(f"❌ {method}: {data['error']}", "ERROR")
                    return data
                
                if "method" in data:
                    continue
                
        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError, Exception) as e:
            file_logger.log(f"❌ {method} ошибка: {e}", "ERROR")
            # Пробуем переподключиться
            await self.reconnect()
            # Повторяем запрос
            return await self.send(method, params)
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        result = await self.send("Page.navigate", {"url": url})
        
        if result and "error" in result:
            file_logger.log(f"❌ Ошибка навигации: {result['error']}", "ERROR")
            return False
        
        for i in range(10):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}")
                await self.get_maximum_snapshot()
                return True
        
        return False
    
    async def eval_js(self, code):
        try:
            resp = await self.send("Runtime.evaluate", {
                "expression": code,
                "returnByValue": True,
                "awaitPromise": True
            })
            
            if "result" in resp:
                result_obj = resp["result"]
                
                if "exceptionDetails" in result_obj:
                    file_logger.log(f"❌ JS ошибка: {result_obj['exceptionDetails']}", "ERROR")
                    return None
                
                if "result" in result_obj:
                    remote = result_obj["result"]
                    if remote.get("type") == "undefined":
                        return None
                    if "value" in remote:
                        return remote["value"]
                    if "objectId" in remote:
                        return remote
                
                if "value" in result_obj:
                    return result_obj["value"]
            
            return None
        except Exception as e:
            file_logger.log(f"❌ eval_js error: {e}", "ERROR")
            return None
    
    async def get_maximum_snapshot(self):
        try:
            file_logger.log("📸 Делаю максимальный слепок...")
            
            elements = await self.eval_js("""
                (function() {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    
                    all.forEach(el => {
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && 
                                       style.visibility !== 'hidden';
                        
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        
                        const important = ['a', 'button', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li',
                                          'label', 'option', 'legend', 'fieldset', 'dialog'];
                        
                        if (important.includes(tag)) {
                            result.push({
                                tag: tag,
                                text: (el.textContent || '').trim().slice(0, 100),
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                style: {
                                    display: style.display,
                                    visibility: style.visibility,
                                    position: style.position,
                                    color: style.color,
                                    fontSize: style.fontSize,
                                    backgroundColor: style.backgroundColor,
                                    cursor: style.cursor
                                },
                                parent: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                                children: el.children.length
                            });
                        }
                    });
                    
                    return result;
                })()
            """)
            
            if elements is None:
                elements = []
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            all_fields = []
            
            inputs = [e for e in elements if e.get('tag') == 'input']
            for inp in inputs:
                attrs = inp.get('attrs', {})
                inp['field_type'] = 'input'
                inp['field_selector'] = f"input[name='{attrs.get('name', '')}']" if attrs.get('name') else f"input[type='{attrs.get('type', 'text')}']"
                all_fields.append(inp)
            
            textareas = [e for e in elements if e.get('tag') == 'textarea']
            for ta in textareas:
                attrs = ta.get('attrs', {})
                ta['field_type'] = 'textarea'
                ta['field_selector'] = f"textarea[name='{attrs.get('name', '')}']" if attrs.get('name') else "textarea"
                all_fields.append(ta)
            
            selects = [e for e in elements if e.get('tag') == 'select']
            for sel in selects:
                attrs = sel.get('attrs', {})
                sel['field_type'] = 'select'
                sel['field_selector'] = f"select[name='{attrs.get('name', '')}']" if attrs.get('name') else "select"
                all_fields.append(sel)
            
            contenteditables = [e for e in elements if e.get('attrs', {}).get('contenteditable') == 'true']
            for ce in contenteditables:
                ce['field_type'] = 'contenteditable'
                class_name = ce.get('class', '')
                if isinstance(class_name, list):
                    class_name = ' '.join(class_name)
                ce['field_selector'] = ce.get('id') and f"#{ce.get('id')}" or (class_name and f".{class_name.replace(' ', '.')}" or "div[contenteditable='true']")
                all_fields.append(ce)
            
            roles = [e for e in elements if e.get('attrs', {}).get('role') in ['textbox', 'searchbox', 'combobox']]
            for role in roles:
                role['field_type'] = 'role'
                role['field_selector'] = role.get('id') and f"#{role.get('id')}" or f"[role='{role.get('attrs', {}).get('role')}']"
                all_fields.append(role)
            
            buttons = []
            for el in elements:
                tag = el.get('tag', '')
                attrs = el.get('attrs', {})
                if tag == 'button' or (tag == 'input' and attrs.get('type') in ['submit', 'button']):
                    buttons.append(el)
            
            links = [e for e in elements if e.get('tag') == 'a' and e.get('attrs', {}).get('href')]
            forms = [e for e in elements if e.get('tag') == 'form']
            headings = [e for e in elements if e.get('tag') in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']]
            visible = [e for e in elements if e.get('visible')]
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "all_elements": elements[:500],
                "buttons": buttons,
                "fields": all_fields,
                "inputs": inputs,
                "textareas": textareas,
                "selects": selects,
                "contenteditables": contenteditables,
                "roles": roles,
                "links": links,
                "forms": forms,
                "headings": headings,
                "visible": visible,
                "masked": self.masked
            }
            
            file_logger.log(f"✅ Максимальный слепок: {len(elements)} элементов, {len(buttons)} кнопок, {len(all_fields)} полей")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            return False
    
    async def get_page_description(self):
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        
        desc = f"""
📄 **СТРАНИЦА:** {info.get('title', 'Нет заголовка')}
🔗 **URL:** {info.get('url', 'Нет URL')}
📊 **ВСЕГО ЭЛЕМЕНТОВ:** {info.get('total', 0)}
🍪 **КУКИ УСТАНОВЛЕНЫ:** {'✅ Да' if self.cookies_set else '❌ Нет'}
🕵️ **МАСКИРОВКА:** {'✅ Активна' if self.masked else '❌ Не активна'}

🔘 **КНОПКИ ({len(info.get('buttons', []))}):**
"""
        for el in info.get('buttons', [])[:10]:
            text = el.get('text', '') or el.get('attrs', {}).get('value', '')
            if text:
                desc += f"  • {text[:30]}\n"
        
        desc += f"\n📝 **ПОЛЯ ВВОДА ({len(info.get('fields', []))}):**\n"
        for el in info.get('fields', [])[:15]:
            attrs = el.get('attrs', {})
            field_type = el.get('field_type', 'unknown')
            name = attrs.get('name', '')
            placeholder = attrs.get('placeholder', '')
            field_name = name or placeholder or f"{field_type}"
            selector = el.get('field_selector', '')
            desc += f"  • {field_name[:30]} → {selector}\n"
        
        return desc
    
    async def click_element(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def fill_element(self, selector, value):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def press_enter(self):
        js_code = """
        (function() {
            const active = document.activeElement;
            if (active) {
                const event = new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                });
                active.dispatchEvent(event);
                return { success: true };
            }
            return { success: false };
        })()
        """
        return await self.eval_js(js_code)
    
    async def reload(self):
        await self.send("Page.reload", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def screenshot(self):
        try:
            if not self.connected:
                await self.connect()
            
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Текущий заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                await asyncio.sleep(2)
            
            file_logger.log("📸 Делаю скриншот...")
            
            # Пробуем сделать скриншот в PNG
            resp = await self.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True,
                "fromSurface": True
            })
            
            if "result" in resp and "data" in resp["result"]:
                img_data = base64.b64decode(resp["result"]["data"])
                
                if len(img_data) < 100:
                    file_logger.log("❌ Скриншот слишком маленький", "ERROR")
                    return None
                
                file_logger.log(f"✅ Скриншот сделан ({len(img_data)} байт)")
                
                # Если есть PIL - обрабатываем изображение
                if PIL_AVAILABLE:
                    try:
                        # Открываем изображение
                        img = Image.open(BytesIO(img_data))
                        width, height = img.size
                        file_logger.log(f"📐 Размер изображения: {width}x{height}")
                        
                        # Если изображение слишком большое - уменьшаем
                        max_width = 1920
                        max_height = 1080
                        
                        if width > max_width or height > max_height:
                            # Вычисляем новые размеры
                            ratio = min(max_width/width, max_height/height)
                            new_width = int(width * ratio)
                            new_height = int(height * ratio)
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            file_logger.log(f"📐 Изменен размер: {new_width}x{new_height}")
                            
                            # Сохраняем в JPEG с качеством 85
                            output = BytesIO()
                            img.convert('RGB').save(output, format='JPEG', quality=85, optimize=True)
                            img_data = output.getvalue()
                            file_logger.log(f"📦 Новый размер: {len(img_data)} байт")
                        else:
                            # Если размер нормальный - конвертируем в JPEG
                            output = BytesIO()
                            img.convert('RGB').save(output, format='JPEG', quality=90, optimize=True)
                            img_data = output.getvalue()
                            file_logger.log(f"📦 Сжат до: {len(img_data)} байт")
                        
                        return img_data
                        
                    except Exception as e:
                        file_logger.log(f"⚠️ Ошибка обработки изображения: {e}", "WARNING")
                        # Если обработка не удалась - возвращаем как есть
                        return img_data
                else:
                    # Если PIL нет - возвращаем как есть
                    return img_data
            
            file_logger.log("❌ Не удалось получить скриншот", "ERROR")
            return None
                
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- Хранилище ----------

clients = {}

# ---------- КОД АГЕНТА ----------

AGENT_CODE = """
🤖 ТЫ — АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate(url) - открыть сайт
2. click(selector) - кликнуть
3. fill(selector, value) - заполнить поле
4. press_enter() - нажать Enter
5. screenshot() - скриншот
6. answer(text) - ответить

📝 СЕЛЕКТОРЫ:
- По ID: #APjFqb
- По классу: .gLFyf
- По имени: input[name='q']

⚠️ ЕСЛИ НУЖНО НЕСКОЛЬКО ДЕЙСТВИЙ - ВОЗВРАЩАЙ МАССИВ:
[{"action": "fill", "params": {"selector": "#APjFqb", "value": "текст"}}, {"action": "press_enter", "params": {}}]

⚠️ ЕСЛИ ПРОСТО ОТВЕТИТЬ - ИСПОЛЬЗУЙ ФОРМАТ:
{"action": "answer", "params": {"text": "твой ответ"}}
"""

# ---------- Агент ----------

async def ask_agnes(prompt: str, client: CDPClient) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    page_desc = await client.get_page_description()
    
    system_prompt = f"""
{AGENT_CODE}

📄 СТРАНИЦА:
{page_desc}

📝 ОТВЕЧАЙ ТОЛЬКО JSON!
"""

    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }
    
    for attempt in range(3):
        try:
            response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            file_logger.log(f"Agnes ответ: {content[:200]}...")
            
            if not content or not content.strip():
                return {"action": "answer", "params": {"text": "⚠️ Получен пустой ответ от AI"}}
            
            json_match = re.search(r'\[.*\]|\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    
                    if isinstance(parsed, list):
                        if len(parsed) == 0:
                            return {"action": "answer", "params": {"text": "⚠️ AI вернул пустой массив"}}
                        if len(parsed) == 1:
                            parsed = parsed[0]
                        else:
                            return parsed
                    
                    if isinstance(parsed, dict):
                        if "answer" in parsed and "action" not in parsed:
                            return {"action": "answer", "params": {"text": parsed["answer"]}}
                        
                        if "action" in parsed and "text" in parsed and "params" not in parsed:
                            parsed["params"] = {"text": parsed.pop("text")}
                            return parsed
                        
                        if "action" in parsed and "answer" in parsed and "params" not in parsed:
                            parsed["params"] = {"text": parsed.pop("answer")}
                            return parsed
                        
                        if "text" in parsed and "action" not in parsed:
                            return {"action": "answer", "params": {"text": parsed["text"]}}
                        
                        if "action" not in parsed:
                            return {"action": "answer", "params": {"text": json.dumps(parsed, ensure_ascii=False)}}
                        
                        return parsed
                    
                except json.JSONDecodeError:
                    if content.strip():
                        return {"action": "answer", "params": {"text": content}}
            
            if content.strip():
                return {"action": "answer", "params": {"text": content}}
            else:
                return {"action": "answer", "params": {"text": "⚠️ Получен пустой ответ от AI"}}
                
        except requests.exceptions.Timeout:
            file_logger.log(f"⚠️ Попытка {attempt + 1} таймаут, повтор...")
            if attempt == 2:
                return {"action": "answer", "params": {"text": "⏳ Превышено время ожидания ответа от AI. Попробуйте ещё раз."}}
            await asyncio.sleep(2)
        except Exception as e:
            file_logger.log(f"Agnes error: {e}", "ERROR")
            return {"action": "answer", "params": {"text": f"❌ Ошибка: {str(e)}"}}
    
    return {"action": "answer", "params": {"text": "❌ Не удалось получить ответ от AI"}}

# ---------- Выполнение действий ----------

async def execute_action(client: CDPClient, action) -> str:
    if isinstance(action, list):
        results = []
        for a in action:
            result = await execute_single_action(client, a)
            results.append(result)
        return "\n".join(results)
    return await execute_single_action(client, action)

async def execute_single_action(client: CDPClient, action: dict) -> str:
    if "text" in action and "params" not in action:
        action["params"] = {"text": action.pop("text")}
    
    if "answer" in action and "action" not in action:
        action = {"action": "answer", "params": {"text": action.pop("answer")}}
    
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await client.navigate(url)
            title = await client.eval_js("document.title")
            return f"✅ Открыл: {url}\n📄 {title}"
        
        elif action_type == "screenshot":
            img_data = await client.screenshot()
            if img_data:
                with open("screenshot.jpg", "wb") as f:
                    f.write(img_data)
                return "screenshot"
            return "❌ Не удалось сделать скриншот"
        
        elif action_type == "click":
            selector = params.get("selector")
            if not selector:
                return "❌ Нет селектора"
            result = await client.click_element(selector)
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            if not selector:
                return "❌ Нет селектора"
            result = await client.fill_element(selector, value)
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "press_enter":
            result = await client.press_enter()
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return "✅ Нажал Enter"
            return "❌ Не удалось нажать Enter"
        
        elif action_type == "answer":
            text = params.get('text', 'Нет ответа')
            return f"📝 {text}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Команды ----------

async def set_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in clients:
        await update.message.reply_text("❌ Сначала отправьте команду чтобы инициализировать браузер")
        return
    
    client = clients[user_id]
    
    try:
        await update.message.reply_text("🍪 Устанавливаю куки для X.com...")
        result = await client.set_cookies(X_COOKIES)
        
        if result:
            await update.message.reply_text(f"✅ Установлено {len(X_COOKIES)} кук для X.com")
        else:
            await update.message.reply_text("❌ Не удалось установить куки")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def mask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in clients:
        await update.message.reply_text("❌ Сначала отправьте команду чтобы инициализировать браузер")
        return
    
    client = clients[user_id]
    
    try:
        await update.message.reply_text("🕵️ Применяю маскировку...")
        result = await client.apply_mask()
        
        if result:
            await update.message.reply_text("✅ Маскировка успешно применена!")
        else:
            await update.message.reply_text("⚠️ Маскировка применена частично")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Обработчик ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        if user_id not in clients:
            client = CDPClient()
            client.user_id = user_id
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        await client.get_maximum_snapshot()
        
        if AGNES_API_KEY:
            response = await ask_agnes(prompt, client)
            if "error" not in response:
                result = await execute_action(client, response)
                if result == "screenshot":
                    # Проверяем наличие файла
                    screenshot_files = ["screenshot.jpg", "screenshot.png"]
                    sent = False
                    for file in screenshot_files:
                        if os.path.exists(file) and os.path.getsize(file) > 0:
                            try:
                                with open(file, "rb") as photo:
                                    await update.message.reply_photo(photo=photo)
                                sent = True
                                break
                            except Exception as e:
                                file_logger.log(f"❌ Ошибка отправки {file}: {e}", "ERROR")
                    
                    if not sent:
                        await update.message.reply_text("❌ Не удалось отправить скриншот")
                else:
                    await update.message.reply_text(result)
                return
        
        await update.message.reply_text("❌ Не понял команду. Попробуйте переформулировать.")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 **МАКСИМАЛЬНЫЙ АГЕНТ**\n\n"
        "🕵️ **Маскировка браузера активна!**\n"
        "🍪 **Куки X.com установлены автоматически**\n\n"
        "💡 **Примеры команд:**\n"
        "• Открой Google\n"
        "• Что видишь?\n"
        "• Сделай скриншот\n"
        "• Зайди на x.com\n\n"
        "/cdp - статус браузера\n"
        "/logs - логи\n"
        "/set_cookies - установить куки\n"
        "/mask - применить маскировку"
    )

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"bot_logs_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt",
                    caption="📋 Логи бота"
                )
        else:
            await update.message.reply_text("❌ Файл логов не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def clear_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи очищены ===\n")
            f.write(f"Время очистки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
        await update.message.reply_text("✅ Логи очищены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        
        status_text = f"✅ **Браузер активен**\n\n"
        status_text += f"📄 Страниц: {len(pages)}\n\n"
        
        for page in pages[:3]:
            title = page.get('title', 'без названия')[:30]
            url = page.get('url', '')[:40]
            status_text += f"• {title}\n  {url}\n\n"
        
        await update.message.reply_text(status_text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def main():
    print("🚀 Запуск бота...")
    file_logger.log("🚀 Запуск бота...")
    
    if PIL_AVAILABLE:
        print("✅ PIL доступен для обработки изображений")
        file_logger.log("✅ PIL доступен для обработки изображений")
    else:
        print("⚠️ PIL не установлен! Установите: pip install Pillow")
        file_logger.log("⚠️ PIL не установлен! Установите: pip install Pillow")
    
    start_chrome_with_mask()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(CommandHandler("set_cookies", set_cookies_command))
    app.add_handler(CommandHandler("mask", mask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен с маскировкой и обработкой скриншотов!")
    file_logger.log("🚀 Бот запущен с маскировкой и обработкой скриншотов!")
    app.run_polling()

if __name__ == "__main__":
    main()