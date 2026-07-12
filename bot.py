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

# ---------- Управление Chrome ----------

def is_chrome_alive():
    """Проверка, жив ли Chrome"""
    try:
        response = requests.get("http://localhost:9222/json", timeout=2)
        return response.status_code == 200
    except:
        return False

def start_chrome_with_mask():
    """Запуск Chrome с маскировкой"""
    try:
        file_logger.log("Запуск Chrome с маскировкой...")
        
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
            return True
        
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

def restart_chrome():
    """Перезапуск Chrome"""
    file_logger.log("🔄 Перезапуск Chrome...")
    
    try:
        subprocess.run(["pkill", "-f", "google-chrome"], capture_output=True)
        time.sleep(2)
    except:
        pass
    
    return start_chrome_with_mask()

def ensure_chrome_running():
    """Гарантирует, что Chrome работает"""
    if not is_chrome_alive():
        file_logger.log("⚠️ Chrome не отвечает, перезапускаю...")
        return restart_chrome()
    return True

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
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.last_url = ""
    
    async def connect_with_retry(self):
        """Подключение с повторными попытками"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                if not is_chrome_alive():
                    file_logger.log("🔄 Chrome не отвечает, перезапускаю...")
                    restart_chrome()
                    await asyncio.sleep(3)
                
                return await self.connect()
                
            except Exception as e:
                file_logger.log(f"⚠️ Попытка {attempt+1}/{self.max_reconnect_attempts}: {e}")
                await asyncio.sleep(2 ** attempt)
        
        file_logger.log("❌ Не удалось подключиться после всех попыток", "ERROR")
        return False
    
    async def ensure_connection(self):
        """Гарантирует активное соединение"""
        if not self.connected or not self.ws:
            return await self.connect_with_retry()
        
        try:
            await asyncio.wait_for(
                self.send("Runtime.evaluate", {"expression": "1"}),
                timeout=5
            )
            return True
        except:
            file_logger.log("⚠️ Соединение потеряно, переподключаюсь...")
            return await self.connect_with_retry()
    
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
                close_timeout=10,
                max_size=50 * 1024 * 1024
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            await self.send("Network.enable", {})
            file_logger.log("✅ Page, Runtime, DOM, Network включены")
            
            await self.apply_mask()
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
        return await self.connect_with_retry()
    
    async def apply_mask(self):
        """Применение маскировки через JS"""
        try:
            file_logger.log("🕵️ Применяю маскировку браузера...")
            
            mask_js = """
            (function() {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                if (!window.chrome) {
                    window.chrome = { runtime: {} };
                }
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en']
                });
                
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
            await self.reconnect()
            return await self.send(method, params)
    
    async def send_safe(self, method, params=None, retries=3):
        """Безопасная отправка с автоматическим восстановлением"""
        for attempt in range(retries):
            try:
                if not await self.ensure_connection():
                    return {"error": "Connection failed"}
                
                return await self.send(method, params)
                
            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.WebSocketException,
                    BrokenPipeError,
                    ConnectionResetError) as e:
                
                file_logger.log(f"⚠️ Ошибка {method}, попытка {attempt+1}/{retries}: {e}")
                
                if attempt < retries - 1:
                    await self.reconnect()
                    await asyncio.sleep(1)
                else:
                    file_logger.log("🔄 Перезапуск Chrome...")
                    restart_chrome()
                    await asyncio.sleep(3)
                    await self.connect_with_retry()
                    return await self.send(method, params)
        
        return {"error": "Max retries exceeded"}
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        self.last_url = url
        result = await self.send_safe("Page.navigate", {"url": url})
        
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
            resp = await self.send_safe("Runtime.evaluate", {
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
        """Оптимизированный сбор информации о странице (только полезные элементы)"""
        try:
            file_logger.log("📸 Делаю максимальный слепок...")
            
            elements = await self.eval_js("""
                (function() {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    
                    for (const el of all) {
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        // Только первые 100 символов
                        const text = (el.textContent || '').trim().slice(0, 100);
                        const hasText = text.length > 0;
                        
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && 
                                       style.visibility !== 'hidden';
                        
                        const attrs = {};
                        // Берем ТОЛЬКО важные атрибуты
                        const importantAttrs = ['id', 'class', 'role', 'aria-label', 'data-testid', 
                                               'name', 'type', 'placeholder', 'href', 'title'];
                        for (const attr of el.attributes) {
                            if (importantAttrs.includes(attr.name)) {
                                attrs[attr.name] = attr.value;
                            }
                        }
                        
                        // Проверка на полезность
                        const isInteractive = (
                            tag === 'button' ||
                            tag === 'a' ||
                            attrs.role === 'button' ||
                            attrs['data-testid'] ||
                            attrs['aria-label']
                        );
                        
                        const isField = (
                            tag === 'input' ||
                            tag === 'textarea' ||
                            tag === 'select'
                        );
                        
                        const isHeading = (
                            tag === 'h1' || tag === 'h2' || tag === 'h3' ||
                            tag === 'h4' || tag === 'h5' || tag === 'h6'
                        );
                        
                        const isTextElement = (
                            tag === 'p' || tag === 'span' || tag === 'div' || 
                            tag === 'li' || tag === 'label'
                        );
                        
                        const isUseful = (
                            isInteractive || isField ||
                            (isHeading && hasText) ||
                            ((isTextElement) && hasText) ||
                            attrs['aria-label'] || attrs['title'] || attrs['data-testid']
                        );
                        
                        // Отсеиваем мусор
                        if (!isUseful) continue;
                        if (!hasText && !attrs['aria-label'] && !attrs['title']) continue;
                        if (!visible && !isInteractive) continue;
                        
                        // МИНИМАЛЬНЫЙ набор данных
                        result.push({
                            t: tag,                    // tag
                            x: text.slice(0, 50),      // текст (50 символов)
                            a: attrs,                  // только важные атрибуты
                            v: visible,                // видимость
                            i: isInteractive           // интерактивность
                        });
                        
                        // Ограничиваем количество элементов
                        if (result.length >= 300) break;
                    }
                    
                    return result;
                })()
            """)
            
            if elements is None:
                elements = []
            
            # Получаем заголовок и URL (отдельно, один раз)
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            self.last_url = url
            
            # Собираем кнопки и поля из уже полученных элементов
            buttons = [e for e in elements if e.get('i') or e.get('t') == 'button' or e.get('t') == 'a']
            fields = [e for e in elements if e.get('t') in ['input', 'textarea', 'select']]
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "all_elements": elements,
                "buttons": buttons,
                "fields": fields,
                "masked": self.masked
            }
            
            file_logger.log(f"✅ Слепок: {len(elements)} элементов, {len(buttons)} кнопок, {len(fields)} полей")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            return False
    
    async def find_clickable_elements(self):
        """Поиск всех кликабельных элементов на странице"""
        try:
            result = await self.eval_js("""
                (function() {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    
                    all.forEach(el => {
                        const style = window.getComputedStyle(el);
                        const cursor = style.cursor;
                        const isClickable = (
                            el.tagName === 'BUTTON' ||
                            el.tagName === 'A' ||
                            el.getAttribute('role') === 'button' ||
                            cursor === 'pointer' ||
                            el.onclick !== null ||
                            el.getAttribute('data-testid') === 'obst' ||
                            (el.getAttribute('aria-label') && 
                             (el.getAttribute('aria-label').toLowerCase().includes('обзор') ||
                              el.getAttribute('aria-label').toLowerCase().includes('explore') ||
                              el.getAttribute('aria-label').toLowerCase().includes('review')))
                        );
                        
                        if (isClickable) {
                            const item = {
                                tag: el.tagName.toLowerCase(),
                                text: el.textContent?.trim() || el.getAttribute('aria-label') || el.getAttribute('title') || '',
                                id: el.id || '',
                                class: el.className || '',
                                attrs: {}
                            };
                            for (const attr of el.attributes) {
                                item.attrs[attr.name] = attr.value;
                            }
                            result.push(item);
                        }
                    });
                    
                    return result;
                })()
            """)
            
            return result if result else []
            
        except Exception as e:
            file_logger.log(f"❌ find_clickable_elements error: {e}", "ERROR")
            return []
    
    async def get_page_description(self):
        """Полное описание страницы со всеми кнопками (оптимизированное)"""
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        
        buttons_text = ""
        for el in info.get('buttons', [])[:20]:
            attrs = el.get('a', {})
            text = el.get('x', '') or attrs.get('aria-label', '') or attrs.get('data-testid', '')
            if text:
                visible_mark = "👁️" if el.get('v') else "👻"
                selector = ""
                if attrs.get('data-testid'):
                    selector = f" [data-testid='{attrs.get('data-testid')}']"
                elif attrs.get('aria-label'):
                    selector = f" [aria-label='{attrs.get('aria-label')}']"
                buttons_text += f"  {visible_mark} {text[:30]}{selector}\n"
        
        fields_text = ""
        for el in info.get('fields', [])[:5]:
            attrs = el.get('a', {})
            name = attrs.get('name', '') or attrs.get('placeholder', '') or attrs.get('aria-label', '')
            selector = ""
            if attrs.get('aria-label'):
                selector = f" [aria-label='{attrs.get('aria-label')}']"
            elif attrs.get('data-testid'):
                selector = f" [data-testid='{attrs.get('data-testid')}']"
            elif attrs.get('name'):
                selector = f" [name='{attrs.get('name')}']"
            if name:
                fields_text += f"  • {name[:30]}{selector}\n"
        
        desc = f"""
📄 **СТРАНИЦА:** {info.get('title', 'Нет заголовка')}
🔗 **URL:** {info.get('url', 'Нет URL')}
📊 **ЭЛЕМЕНТОВ:** {info.get('total', 0)}
🍪 **КУКИ:** {'✅ Да' if self.cookies_set else '❌ Нет'}
🕵️ **МАСКИРОВКА:** {'✅ Активна' if self.masked else '❌ Не активна'}

🔘 **КНОПКИ ({len(info.get('buttons', []))}):**
{buttons_text}

📝 **ПОЛЯ ({len(info.get('fields', []))}):**
{fields_text}
"""
        return desc
    
    async def click_element(self, selector):
        """Клик по элементу с поддержкой разных селекторов и языков"""
        selector_escaped = selector.replace("'", "\\'").replace('"', '\\"')
        
        js_code = f"""
        (function() {{
            let el = null;
            
            try {{
                el = document.querySelector("{selector_escaped}");
            }} catch(e) {{
            }}
            
            if (!el) {{
                const allElements = document.querySelectorAll('[aria-label]');
                for (const elem of allElements) {{
                    const label = elem.getAttribute('aria-label') || '';
                    const lowerLabel = label.toLowerCase();
                    if (lowerLabel.includes('обзор') || 
                        lowerLabel.includes('explore') ||
                        lowerLabel.includes('review')) {{
                        el = elem;
                        break;
                    }}
                }}
            }}
            
            if (!el) {{
                const allButtons = document.querySelectorAll('button, a, [role="button"], [data-testid="obst"]');
                for (const btn of allButtons) {{
                    const text = btn.textContent?.trim() || btn.getAttribute('aria-label') || btn.getAttribute('title') || '';
                    const lowerText = text.toLowerCase();
                    if (lowerText.includes('обзор') || 
                        lowerText.includes('explore') ||
                        lowerText.includes('review')) {{
                        el = btn;
                        break;
                    }}
                }}
            }}
            
            if (!el) {{
                el = document.querySelector('[data-testid="obst"]');
            }}
            
            if (!el) {{
                const svgs = document.querySelectorAll('svg');
                for (const svg of svgs) {{
                    const parent = svg.closest('button, a, [role="button"], div[class*="explore"]');
                    if (parent) {{
                        el = parent;
                        break;
                    }}
                }}
            }}
            
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                setTimeout(function() {{
                    el.click();
                    el.dispatchEvent(new Event('click', {{ bubbles: true }}));
                }}, 300);
                return {{ success: true }};
            }}
            return {{ success: false, error: 'Element not found' }};
        }})()
        """
        result = await self.eval_js(js_code)
        
        if result and result.get('success'):
            await asyncio.sleep(1)
            await self.get_maximum_snapshot()
        
        return result
    
    async def fill_element(self, selector, value):
        """Заполнение поля с правильным экранированием и запасным поиском"""
        # Экранируем все опасные символы
        value_escaped = value.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
        selector_escaped = selector.replace("'", "\\'").replace('"', '\\"')
        
        js_code = f"""
        (function() {{
            let el = null;
            
            // 1. Пробуем найти по селектору (если он есть)
            if ("{selector_escaped}" && "{selector_escaped}" !== "") {{
                try {{
                    el = document.querySelector("{selector_escaped}");
                }} catch(e) {{
                    // Если селектор невалидный - игнорируем
                }}
            }}
            
            // 2. Если не нашли - ищем по атрибутам
            if (!el) {{
                const allInputs = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                const searchTerms = [
                    "Search Twitter",
                    "Поиск",
                    "Search",
                    "search",
                    "q",
                    "query"
                ];
                
                for (const input of allInputs) {{
                    const attrs = {{
                        name: input.getAttribute('name') || '',
                        placeholder: input.getAttribute('placeholder') || '',
                        ariaLabel: input.getAttribute('aria-label') || '',
                        testId: input.getAttribute('data-testid') || '',
                        id: input.id || ''
                    }};
                    
                    // Проверяем все атрибуты
                    const allAttrs = Object.values(attrs);
                    let found = false;
                    for (const term of searchTerms) {{
                        for (const attr of allAttrs) {{
                            if (attr.toLowerCase().includes(term.toLowerCase())) {{
                                found = true;
                                break;
                            }}
                        }}
                        if (found) break;
                    }}
                    
                    if (found) {{
                        el = input;
                        break;
                    }}
                }}
            }}
            
            // 3. Если всё равно не нашли - ищем видимое поле ввода
            if (!el) {{
                const allInputs = document.querySelectorAll('input[type="text"], input:not([type]), textarea');
                for (const input of allInputs) {{
                    const rect = input.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {{
                        el = input;
                        break;
                    }}
                }}
            }}
            
            if (el) {{
                el.focus();
                el.value = '';
                const text = "{value_escaped}";
                el.value = text;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false, error: 'Element not found' }};
        }})()
        """
        result = await self.eval_js(js_code)
        
        if result and result.get('success'):
            await self.get_maximum_snapshot()
        
        return result
    
    async def press_enter(self):
        """Обычный Enter (через JS) - НЕ НАДЕЖНЫЙ!"""
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
    
    # ========== CDP МЕТОДЫ (САМЫЕ НАДЕЖНЫЕ) ==========
    
    async def press_enter_cdp(self):
        """Настоящий Enter через CDP (обходит все блокировки)"""
        try:
            file_logger.log("⌨️ Нажимаю Enter через CDP...")
            
            # KeyDown
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "keyCode": 13,
                "modifiers": 0,
                "autoRepeat": False,
                "isKeypad": False,
                "text": "\r",
                "unmodifiedText": "\r",
                "location": 0,
                "nativeVirtualKeyCode": 13,
                "windowsVirtualKeyCode": 13
            })
            
            await asyncio.sleep(0.05)
            
            # KeyUp
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "keyCode": 13,
                "modifiers": 0
            })
            
            file_logger.log("✅ Enter нажат через CDP")
            return {"success": True, "method": "cdp_enter"}
            
        except Exception as e:
            file_logger.log(f"❌ CDP Enter error: {e}", "ERROR")
            return {"success": False, "error": str(e)}
    
    def _get_key_code(self, char):
        """Получить код клавиши для CDP"""
        if char.isalpha():
            return f"Key{char.upper()}"
        elif char.isdigit():
            return f"Digit{char}"
        elif char == " ":
            return "Space"
        elif char == "@":
            return "Digit2"
        elif char == ".":
            return "Period"
        elif char == ",":
            return "Comma"
        elif char == "!":
            return "Digit1"
        elif char == "?":
            return "Slash"
        else:
            return "Unknown"
    
    async def type_text_cdp(self, text):
        """Настоящий ввод текста через CDP (имитация клавиатуры)"""
        try:
            file_logger.log(f"⌨️ Ввожу текст через CDP: {text[:20]}...")
            
            # Сначала кликаем в поле для фокуса
            await self.eval_js("""
                (function() {
                    const field = document.activeElement || 
                                  document.querySelector('[aria-label="Search Twitter"], [placeholder="Поиск"], input[type="text"]');
                    if (field) field.focus();
                })()
            """)
            await asyncio.sleep(0.3)
            
            # Очищаем поле (Ctrl+A + Delete)
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": "a",
                "code": "KeyA",
                "modifiers": 2  # Ctrl
            })
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": "a",
                "code": "KeyA",
                "modifiers": 2
            })
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": "Delete",
                "code": "Delete"
            })
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": "Delete",
                "code": "Delete"
            })
            
            # Вводим текст посимвольно
            for char in text:
                await self.send("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": char,
                    "code": self._get_key_code(char),
                    "text": char,
                    "unmodifiedText": char,
                    "modifiers": 0
                })
                await self.send("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": char,
                    "code": self._get_key_code(char),
                    "text": char,
                    "unmodifiedText": char,
                    "modifiers": 0
                })
                await asyncio.sleep(0.03)
            
            file_logger.log(f"✅ Текст введен через CDP: {text[:20]}...")
            return {"success": True, "method": "cdp_type"}
            
        except Exception as e:
            file_logger.log(f"❌ CDP type error: {e}", "ERROR")
            return {"success": False, "error": str(e)}
    
    async def find_search_field_selector(self):
        """Найти СЕЛЕКТОР (строку) для поля поиска"""
        selector = await self.eval_js("""
            (function() {
                const fields = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                const searchTerms = ['search', 'поиск', 'query', 'q', 'find'];
                
                for (const field of fields) {
                    const ariaLabel = field.getAttribute('aria-label') || '';
                    const placeholder = field.getAttribute('placeholder') || '';
                    const name = field.getAttribute('name') || '';
                    const testId = field.getAttribute('data-testid') || '';
                    const id = field.id || '';
                    
                    const allAttrs = [ariaLabel, placeholder, name, testId, id];
                    
                    for (const term of searchTerms) {
                        for (const attr of allAttrs) {
                            if (attr.toLowerCase().includes(term.toLowerCase())) {
                                // Возвращаем СЕЛЕКТОР (строку), а не элемент!
                                if (id) return '#' + id;
                                if (name) return '[name="' + name + '"]';
                                if (ariaLabel) return '[aria-label="' + ariaLabel + '"]';
                                if (testId) return '[data-testid="' + testId + '"]';
                                if (placeholder) return '[placeholder="' + placeholder + '"]';
                                return 'input[type="text"]';
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        return selector
    
    async def set_value_cdp(self, selector, value):
        """Нативный ввод через CDP (устанавливает значение напрямую)"""
        try:
            file_logger.log(f"📝 Устанавливаю значение через CDP: {value[:20]}...")
            
            value_escaped = value.replace("'", "\\'").replace('"', '\\"')
            selector_escaped = selector.replace("'", "\\'").replace('"', '\\"')
            
            js_code = f"""
            (function() {{
                let el = null;
                try {{
                    el = document.querySelector("{selector_escaped}");
                }} catch(e) {{}}
                
                if (!el) {{
                    // Пробуем найти по атрибутам
                    const inputs = document.querySelectorAll('input, textarea');
                    for (const input of inputs) {{
                        const attrs = {{
                            ariaLabel: input.getAttribute('aria-label') || '',
                            placeholder: input.getAttribute('placeholder') || '',
                            name: input.getAttribute('name') || '',
                            testId: input.getAttribute('data-testid') || ''
                        }};
                        if (attrs.ariaLabel.toLowerCase().includes('search') || 
                            attrs.placeholder.toLowerCase().includes('поиск') ||
                            attrs.name === 'q' ||
                            attrs.name === 'search' ||
                            attrs.testId.toLowerCase().includes('search')) {{
                            el = input;
                            break;
                        }}
                    }}
                }}
                
                if (el) {{
                    el.focus();
                    el.value = '{value_escaped}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return {{ success: true }};
                }}
                return {{ success: false, error: 'Element not found' }};
            }})()
            """
            
            result = await self.eval_js(js_code)
            if result and result.get('success'):
                file_logger.log(f"✅ Значение установлено через CDP")
                return {"success": True, "method": "cdp_native"}
            else:
                return {"success": False, "error": result.get('error', 'Unknown error')}
                
        except Exception as e:
            file_logger.log(f"❌ CDP set value error: {e}", "ERROR")
            return {"success": False, "error": str(e)}
    
    async def smart_search_cdp(self, text, selector=None):
        """УМНЫЙ ПОИСК — только по точному селектору лупы!"""
        
        file_logger.log(f"🔍 Умный поиск CDP: {text[:20]}...")
        
        # 1. Находим поле
        if not selector:
            selector = await self.find_search_field_selector()
        
        if selector:
            # 2. Активируем поле (кликаем в него)
            file_logger.log(f"🖱️ Активирую поле: {selector}")
            await self.click_element(selector)
            await asyncio.sleep(0.5)  # Ждем появления лупы
            
            # 3. Вводим текст
            result = await self.set_value_cdp(selector, text)
            if result.get('success'):
                await asyncio.sleep(0.5)
                
                # 4. Ищем ТОЛЬКО по точному селектору!
                file_logger.log("🔍 Ищу лупу...")
                
                btn_selector = await self.eval_js("""
                    (function() {
                        const btn = document.querySelector('[data-testid="SearchBox_Search_Button"]');
                        if (btn) return '[data-testid="SearchBox_Search_Button"]';
                        return null;
                    })()
                """)
                
                if btn_selector:
                    file_logger.log(f"🔍 Найдена лупа: {btn_selector}")
                    await self.click_element(btn_selector)
                    return {"success": True, "method": "click_search_button"}
                else:
                    file_logger.log("⚠️ Лупа не найдена")
        
        return {"success": False, "error": "Лупа не найдена"}
    
    async def reload(self):
        await self.send_safe("Page.reload", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def screenshot(self):
        try:
            if not await self.ensure_connection():
                return None
            
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Текущий заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                await asyncio.sleep(2)
            
            file_logger.log("📸 Делаю скриншот...")
            
            resp = await self.send_safe("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 70,
                "captureBeyondViewport": False,
                "fromSurface": True,
                "optimizeForSpeed": True
            })
            
            if "result" in resp and "data" in resp["result"]:
                img_data = base64.b64decode(resp["result"]["data"])
                
                if len(img_data) < 100:
                    file_logger.log("❌ Скриншот слишком маленький", "ERROR")
                    return None
                
                file_logger.log(f"✅ Скриншот сделан ({len(img_data)} байт)")
                
                if img_data[:2] == b'\xff\xd8':
                    return img_data
                else:
                    file_logger.log("❌ Невалидный формат изображения", "ERROR")
                    return None
            
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

⚠️ ГЛАВНОЕ ПРАВИЛО: ДЛЯ ПОИСКА ИСПОЛЬЗУЙ ТОЛЬКО search_cdp!

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ:

1. search_cdp(value) - ЕДИНСТВЕННЫЙ ПРАВИЛЬНЫЙ СПОСОБ ПОИСКА!
   Пример: {"action": "search_cdp", "params": {"value": "вова"}}
   
2. navigate(url) - открыть сайт
   Пример: {"action": "navigate", "params": {"url": "https://x.com"}}

3. click(selector) - кликнуть по кнопке
   Пример: {"action": "click", "params": {"selector": "[data-testid='obst']"}}

4. screenshot() - скриншот
   Пример: {"action": "screenshot", "params": {}}

5. answer(text) - ответить
   Пример: {"action": "answer", "params": {"text": "твой ответ"}}

❌ НЕ ИСПОЛЬЗУЙ для поиска:
- fill + press_enter
- fill + click
- Только fill без поиска

✅ ВСЕГДА ИСПОЛЬЗУЙ:
- search_cdp - он сам найдет поле, введет текст и кликнет по лупе!

📝 КАК ВЫБИРАТЬ СЕЛЕКТОРЫ:

🔹 X.com (Twitter):
   - Поле поиска: [aria-label="Поисковый запрос"] или [data-testid="SearchBox_Search_Input"]
   - Кнопка поиска (ЛУПА): [data-testid="SearchBox_Search_Button"]
   - Кнопка "Обзор": [data-testid="obst"] или [data-testid="AppTabBar_Explore_Link"]

🔹 Google:
   - Поле поиска: input[name='q'] или [aria-label="Найти"]

🔹 YouTube:
   - Поле поиска: input[name='search_query'] или [aria-label="Поиск"]

📝 ФОРМАТ ОТВЕТА:
- Одно действие: {"action": "search_cdp", "params": {"value": "@elonmusk"}}
- Несколько действий: [{"action": "navigate", "params": {"url": "https://x.com"}}, {"action": "search_cdp", "params": {"value": "@elonmusk"}}]
- Ответ текстом: {"action": "answer", "params": {"text": "твой ответ"}}

⚠️ ВАЖНО:
- Пользователь может писать по-русски, но селекторы используй АНГЛИЙСКИЕ!
- "Обзор" → "Explore"
- "Главная" → "Home"
- "Уведомления" → "Notifications"
- "Сообщения" → "Messages"
- "Закладки" → "Bookmarks"
- "Профиль" → "Profile"
- ДЛЯ ПОИСКА ВСЕГДА ИСПОЛЬЗУЙ search_cdp!
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

⚠️ ВАЖНО:
- Пользователь может писать по-русски, но ты должен использовать АНГЛИЙСКИЕ названия в селекторах
- "Обзор" → "Explore"
- "Главная" → "Home"
- "Уведомления" → "Notifications"
- "Сообщения" → "Messages"
- "Закладки" → "Bookmarks"
- "Профиль" → "Profile"
- Все атрибуты в селекторах пиши на английском!
- ВСЕГДА используй aria-label или data-testid если они есть в описании!
- ДЛЯ ПОИСКА ВСЕГДА ИСПОЛЬЗУЙ search_cdp!
"""

    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
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
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector", "")
            value = params.get("value", "")
            result = await client.fill_element(selector, value)
            if result and result.get("success"):
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "press_enter":
            result = await client.press_enter()
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return "✅ Нажал Enter"
            return "❌ Не удалось нажать Enter"
        
        elif action_type == "search_cdp":
            value = params.get("value", "")
            selector = params.get("selector", "")
            result = await client.smart_search_cdp(value, selector)
            if result and result.get("success"):
                method = result.get("method", "")
                return f"✅ Поиск выполнен ({method}): {value}"
            return f"❌ Не удалось выполнить поиск: {result.get('error', '')}"
        
        elif action_type == "answer":
            text = params.get('text', 'Нет ответа')
            return f"📝 {text}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Команды ----------

async def find_button_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск кнопки на странице"""
    user_id = update.message.from_user.id
    button_name = ' '.join(context.args) if context.args else 'Обзор'
    
    if user_id not in clients:
        await update.message.reply_text("❌ Сначала откройте страницу (например, 'Зайди на x.com')")
        return
    
    client = clients[user_id]
    
    try:
        await update.message.reply_text(f"🔍 Ищу кнопку '{button_name}'...")
        
        elements = await client.find_clickable_elements()
        
        if not elements:
            await update.message.reply_text("❌ Не удалось найти элементы на странице")
            return
        
        found = []
        for el in elements:
            text = el.get('text', '').lower()
            attrs = el.get('attrs', {})
            aria_label = attrs.get('aria-label', '').lower()
            data_testid = attrs.get('data-testid', '').lower()
            title_attr = attrs.get('title', '').lower()
            
            search_term = button_name.lower()
            if (search_term in text or 
                search_term in aria_label or 
                search_term in data_testid or
                search_term in title_attr or
                ('обзор' in text and 'explore' in search_term) or
                ('explore' in text and 'обзор' in search_term)):
                found.append(el)
        
        if found:
            msg = f"✅ Найдено {len(found)} элементов с '{button_name}':\n\n"
            for el in found[:20]:
                attrs = el.get('attrs', {})
                text = el.get('text', '') or attrs.get('aria-label', '') or attrs.get('title', '') or el.get('tag', '')
                selector = el.get('id') and f"#{el.get('id')}" or (el.get('class') and f".{el.get('class', '').split()[0] if el.get('class') else ''}")
                data_testid = attrs.get('data-testid', '')
                aria_label = attrs.get('aria-label', '')
                
                msg += f"  • {text[:50]}\n"
                if selector:
                    msg += f"    Селектор: {selector}\n"
                if data_testid:
                    msg += f"    data-testid: {data_testid}\n"
                if aria_label:
                    msg += f"    aria-label: {aria_label}\n"
                msg += "\n"
            
            if len(found) > 20:
                msg += f"... и еще {len(found) - 20} элементов"
                
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(
                f"❌ Кнопка '{button_name}' не найдена\n\n"
                f"💡 Попробуйте:\n"
                f"• Проверить написание (Обзор, обзор, explore)\n"
                f"• Использовать /find_button [название]\n"
                f"• Сделать скриншот и посмотреть визуально\n"
                f"• На X.com кнопка 'Обзор' → 'Explore'"
            )
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

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

async def get_snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачать полный слепок страницы в JSON"""
    user_id = update.message.from_user.id
    
    if user_id not in clients:
        await update.message.reply_text("❌ Сначала откройте страницу (например, 'Зайди на x.com')")
        return
    
    client = clients[user_id]
    
    try:
        await update.message.reply_text("📸 Делаю полный слепок страницы...")
        
        await client.get_maximum_snapshot()
        
        if not client.full_snapshot:
            await update.message.reply_text("❌ Не удалось получить слепок страницы")
            return
        
        snapshot = client.full_snapshot.copy()
        snapshot["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        snapshot["user_id"] = user_id
        
        filename = f"snapshot_{user_id}_{int(time.time())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 Слепок страницы\n\n"
                        f"📄 {snapshot.get('title', 'Нет заголовка')}\n"
                        f"🔗 {snapshot.get('url', 'Нет URL')}\n"
                        f"📊 Элементов: {snapshot.get('total', 0)}\n"
                        f"🔘 Кнопок: {len(snapshot.get('buttons', []))}\n"
                        f"📝 Полей: {len(snapshot.get('fields', []))}\n"
                        f"🕐 {snapshot['timestamp']}"
            )
        
        os.remove(filename)
        
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
        ensure_chrome_running()
        
        if user_id not in clients:
            client = CDPClient()
            client.user_id = user_id
            await client.connect_with_retry()
            clients[user_id] = client
        
        client = clients[user_id]
        
        if not await client.ensure_connection():
            await update.message.reply_text("❌ Не удалось подключиться к браузеру. Попробуйте позже.")
            return
        
        await client.get_maximum_snapshot()
        
        if AGNES_API_KEY:
            response = await ask_agnes(prompt, client)
            if "error" not in response:
                result = await execute_action(client, response)
                if result == "screenshot":
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
        "🔍 **Команды:**\n"
        "/cdp - статус браузера\n"
        "/logs - логи\n"
        "/set_cookies - установить куки\n"
        "/mask - применить маскировку\n"
        "/find_button - найти кнопку\n"
        "/get_snapshot - скачать слепок страницы"
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
        if not is_chrome_alive():
            await update.message.reply_text("❌ Браузер не активен. Перезапускаю...")
            restart_chrome()
            await asyncio.sleep(3)
        
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
    
    ensure_chrome_running()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(CommandHandler("set_cookies", set_cookies_command))
    app.add_handler(CommandHandler("mask", mask_command))
    app.add_handler(CommandHandler("find_button", find_button_command))
    app.add_handler(CommandHandler("get_snapshot", get_snapshot_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()