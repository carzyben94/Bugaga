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
        self.accessibility_enabled = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
    
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
                close_timeout=10
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            await self.send("Network.enable", {})
            
            # Включаем Accessibility
            await self.enable_accessibility()
            
            file_logger.log("✅ Page, Runtime, DOM, Network, Accessibility включены")
            
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
    
    async def enable_accessibility(self):
        """Включение Accessibility domain"""
        try:
            await self.send("Accessibility.enable", {})
            self.accessibility_enabled = True
            file_logger.log("✅ Accessibility включен")
            return True
        except Exception as e:
            file_logger.log(f"⚠️ Ошибка включения Accessibility: {e}", "WARNING")
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
    
    # ---------- ACCESSIBILITY API METHODS ----------
    
    async def get_accessibility_tree(self, node_id=None):
        """Получение полного accessibility tree"""
        try:
            params = {}
            if node_id:
                params["nodeId"] = node_id
            
            result = await self.send_safe("Accessibility.getFullAXTree", params)
            
            if result and "nodes" in result:
                file_logger.log(f"✅ Получено {len(result['nodes'])} accessibility узлов")
                return result["nodes"]
            return []
        except Exception as e:
            file_logger.log(f"❌ Ошибка получения accessibility tree: {e}", "ERROR")
            return []
    
    async def query_accessibility(self, role=None, name=None, description=None):
        """Поиск элементов по accessibility свойствам"""
        try:
            params = {}
            if role:
                params["role"] = role
            if name:
                params["name"] = name
            if description:
                params["description"] = description
            
            result = await self.send_safe("Accessibility.queryAXTree", params)
            
            if result and "nodes" in result:
                file_logger.log(f"✅ Найдено {len(result['nodes'])} accessibility элементов")
                return result["nodes"]
            return []
        except Exception as e:
            file_logger.log(f"❌ Ошибка queryAccessibility: {e}", "ERROR")
            return []
    
    async def get_accessible_name(self, node_id):
        """Получение доступного имени элемента"""
        try:
            result = await self.send("Accessibility.getPartialAXTree", {
                "nodeId": node_id
            })
            if result and "nodes" in result and result["nodes"]:
                node = result["nodes"][0]
                if "name" in node:
                    return node["name"].get("value", "")
            return ""
        except Exception as e:
            file_logger.log(f"❌ Ошибка получения имени: {e}", "ERROR")
            return ""
    
    async def find_interactive_elements(self):
        """Поиск всех интерактивных элементов через Accessibility API"""
        try:
            interactive_roles = [
                "button", "link", "checkbox", "radio", "menuitem",
                "option", "tab", "treeitem", "combobox", "listbox",
                "spinbutton", "slider", "textbox", "searchbox",
                "menuitemcheckbox", "menuitemradio",
                "switch", "tabpanel", "treegrid"
            ]
            
            all_elements = []
            for role in interactive_roles:
                elements = await self.query_accessibility(role=role)
                if elements:
                    all_elements.extend(elements)
                    file_logger.log(f"🔍 Найдено {len(elements)} элементов с ролью {role}")
            
            return all_elements
        except Exception as e:
            file_logger.log(f"❌ Ошибка findInteractiveElements: {e}", "ERROR")
            return []
    
    async def get_page_accessibility_info(self):
        """Получение полной информации о странице через Accessibility API"""
        try:
            if not self.accessibility_enabled:
                await self.enable_accessibility()
            
            all_nodes = await self.get_accessibility_tree()
            
            roles = {}
            interactive = []
            headings = []
            links = []
            fields = []
            buttons = []
            
            for node in all_nodes:
                role = node.get("role", {}).get("value", "unknown")
                name = node.get("name", {}).get("value", "")
                
                roles[role] = roles.get(role, 0) + 1
                
                if role in ["button", "link", "checkbox", "radio", "menuitem"]:
                    interactive.append({
                        "role": role,
                        "name": name,
                        "nodeId": node.get("nodeId"),
                        "properties": node.get("properties", [])
                    })
                
                if role == "button":
                    buttons.append({
                        "name": name,
                        "nodeId": node.get("nodeId"),
                        "properties": node.get("properties", [])
                    })
                
                if role in ["heading"]:
                    level = 1
                    for prop in node.get("properties", []):
                        if prop.get("name") == "level":
                            level = prop.get("value", {}).get("value", 1)
                            break
                    headings.append({
                        "level": level,
                        "name": name
                    })
                
                if role == "link":
                    url = ""
                    for prop in node.get("properties", []):
                        if prop.get("name") == "url":
                            url = prop.get("value", {}).get("value", "")
                            break
                    links.append({
                        "name": name,
                        "url": url
                    })
                
                if role in ["textbox", "searchbox", "combobox", "spinbutton"]:
                    value = ""
                    for prop in node.get("properties", []):
                        if prop.get("name") == "value":
                            value = prop.get("value", {}).get("value", "")
                            break
                    fields.append({
                        "role": role,
                        "name": name,
                        "value": value,
                        "nodeId": node.get("nodeId")
                    })
            
            return {
                "total": len(all_nodes),
                "roles": roles,
                "interactive": interactive,
                "buttons": buttons,
                "headings": headings,
                "links": links,
                "fields": fields,
                "all_nodes": all_nodes
            }
        except Exception as e:
            file_logger.log(f"❌ Ошибка getPageAccessibilityInfo: {e}", "ERROR")
            return {}
    
    async def get_maximum_snapshot(self):
        """Получение снапшота ТОЛЬКО через Accessibility API"""
        try:
            file_logger.log("📸 Делаю accessibility снапшот...")
            
            if not self.accessibility_enabled:
                await self.enable_accessibility()
            
            # Получаем данные только из Accessibility API
            ax_info = await self.get_page_accessibility_info()
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "total": ax_info.get("total", 0),
                "buttons": ax_info.get("buttons", []),
                "fields": ax_info.get("fields", []),
                "headings": ax_info.get("headings", []),
                "links": ax_info.get("links", []),
                "interactive": ax_info.get("interactive", []),
                "roles": ax_info.get("roles", {}),
                "all_nodes": ax_info.get("all_nodes", []),
                "masked": self.masked,
                "accessibility_enabled": self.accessibility_enabled
            }
            
            file_logger.log(f"✅ Accessibility снапшот готов: {ax_info.get('total', 0)} узлов, {len(ax_info.get('buttons', []))} кнопок")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            return False
    
    async def get_page_description(self):
        """Описание страницы ТОЛЬКО из Accessibility"""
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        
        # Кнопки
        buttons_text = ""
        for btn in info.get('buttons', [])[:30]:
            name = btn.get('name', '')
            if name:
                properties = btn.get('properties', [])
                props = []
                for p in properties[:3]:
                    p_name = p.get('name', '')
                    p_value = p.get('value', {}).get('value', '')
                    if p_name and p_value:
                        props.append(f"{p_name}={p_value}")
                props_str = f" [{', '.join(props)}]" if props else ""
                buttons_text += f"  🔘 {name[:50]}{props_str}\n"
        
        # Поля ввода
        fields_text = ""
        for field in info.get('fields', [])[:10]:
            name = field.get('name', 'без имени')
            role = field.get('role', '')
            value = field.get('value', '')
            value_str = f" = '{value[:20]}'" if value else ""
            fields_text += f"  📝 {role}: {name[:30]}{value_str}\n"
        
        # Заголовки
        headings_text = ""
        for h in info.get('headings', [])[:5]:
            level = h.get('level', 1)
            name = h.get('name', '')
            if name:
                headings_text += f"  📌 H{level}: {name[:40]}\n"
        
        # Интерактивные элементы
        interactive_text = ""
        for el in info.get('interactive', [])[:10]:
            role = el.get('role', '')
            name = el.get('name', '')
            if name:
                interactive_text += f"  🎯 {role}: {name[:40]}\n"
        
        # Роли
        roles_text = ""
        for role, count in sorted(info.get('roles', {}).items(), key=lambda x: x[1], reverse=True)[:10]:
            roles_text += f"  • {role}: {count}\n"
        
        desc = f"""
♿ **ACCESSIBILITY СНАПШОТ**

📄 **СТРАНИЦА:** {info.get('title', 'Нет заголовка')}
🔗 **URL:** {info.get('url', 'Нет URL')}
📊 **ВСЕГО УЗЛОВ:** {info.get('total', 0)}
♿ **ACCESSIBILITY:** ✅ Включен
🍪 **КУКИ:** {'✅ Да' if self.cookies_set else '❌ Нет'}
🕵️ **МАСКИРОВКА:** {'✅ Активна' if self.masked else '❌ Не активна'}

📊 **РОЛИ:**
{roles_text}

📌 **ЗАГОЛОВКИ:**
{headings_text}

🔘 **КНОПКИ ({len(info.get('buttons', []))}):**
{buttons_text}

📝 **ПОЛЯ ВВОДА ({len(info.get('fields', []))}):**
{fields_text}

🎯 **ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ:**
{interactive_text}
"""
        
        return desc
    
    async def click_element(self, selector):
        """Клик по элементу через Accessibility"""
        # Ищем элемент через Accessibility
        elements = await self.query_accessibility(name=selector)
        
        if not elements:
            # Если не нашли по имени, пробуем через DOM как fallback
            js_code = f"""
            (function() {{
                let el = document.querySelector('{selector}');
                if (!el) {{
                    const all = document.querySelectorAll('[role="button"], button, a');
                    for (const elem of all) {{
                        const text = elem.textContent?.trim() || elem.getAttribute('aria-label') || '';
                        if (text.toLowerCase().includes('{selector}'.toLowerCase())) {{
                            el = elem;
                            break;
                        }}
                    }}
                }}
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    setTimeout(function() {{ el.click(); }}, 300);
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
            """
            result = await self.eval_js(js_code)
            
            if result and result.get('success'):
                await asyncio.sleep(1)
                await self.get_maximum_snapshot()
                return result
            return {"success": False, "error": "Element not found"}
        
        # Кликаем через CDP если нашли в Accessibility
        node_id = elements[0].get("nodeId")
        if node_id:
            try:
                # Получаем DOM nodeId из accessibility nodeId
                dom_result = await self.send("DOM.getNodeForLocation", {
                    "x": 0, "y": 0  # Это не точно, лучше использовать другой метод
                })
                # Или используем JS для клика по элементу
                js_code = f"""
                (function() {{
                    const elements = document.querySelectorAll('[role="button"], button, a');
                    for (const el of elements) {{
                        const text = el.textContent?.trim() || el.getAttribute('aria-label') || '';
                        if (text === '{selector}') {{
                            el.click();
                            return {{ success: true }};
                        }}
                    }}
                    return {{ success: false }};
                }})()
                """
                result = await self.eval_js(js_code)
                
                if result and result.get('success'):
                    await asyncio.sleep(1)
                    await self.get_maximum_snapshot()
                    return result
            except Exception as e:
                file_logger.log(f"❌ Клик через Accessibility ошибка: {e}", "ERROR")
        
        return {"success": False, "error": "Cannot click element"}
    
    async def fill_element(self, selector, value):
        """Заполнение поля через Accessibility"""
        # Ищем поле через Accessibility
        elements = await self.query_accessibility(role="textbox", name=selector)
        if not elements:
            elements = await self.query_accessibility(role="searchbox", name=selector)
        
        if not elements:
            # Fallback через DOM
            js_code = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{value}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
            """
            result = await self.eval_js(js_code)
            if result and result.get('success'):
                await self.get_maximum_snapshot()
                return result
            return {"success": False}
        
        # Используем DOM для заполнения
        node_id = elements[0].get("nodeId")
        if node_id:
            js_code = f"""
            (function() {{
                const elements = document.querySelectorAll('input, textarea, [role="textbox"], [role="searchbox"]');
                for (const el of elements) {{
                    const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
                    if (label === '{selector}') {{
                        el.value = '{value}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }));
                        return {{ success: true }};
                    }}
                }}
                return {{ success: false }};
            }})()
            """
            result = await self.eval_js(js_code)
            if result and result.get('success'):
                await self.get_maximum_snapshot()
                return result
        
        return {"success": False}
    
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

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate(url) - открыть сайт
2. click(selector) - кликнуть
3. fill(selector, value) - заполнить поле
4. press_enter() - нажать Enter
5. screenshot() - скриншот
6. answer(text) - ответить

♿ ВСЕ ЭЛЕМЕНТЫ БЕРУТСЯ ИЗ ACCESSIBILITY API!
- Кнопки (role="button")
- Поля ввода (role="textbox", "searchbox")  
- Ссылки (role="link")
- Заголовки (role="heading")
- Интерактивные элементы

📝 СЕЛЕКТОРЫ:
- По имени: используй текст кнопки
- По aria-label: [aria-label="Explore"]
- По data-testid: [data-testid="obst"]

⚠️ ВАЖНО: 
- "Обзор" → "Explore"
- Все селекторы на АНГЛИЙСКОМ!
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

📄 СТРАНИЦА (ТОЛЬКО ACCESSIBILITY):
{page_desc}

📝 ОТВЕЧАЙ ТОЛЬКО JSON!

⚠️ ВАЖНО:
- Пользователь может писать по-русски, но ты должен использовать АНГЛИЙСКИЕ названия
- "Обзор" → "Explore"
- "Главная" → "Home"
- "Уведомления" → "Notifications"
- "Сообщения" → "Messages"
- "Закладки" → "Bookmarks"
- "Профиль" → "Profile"
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
        "🧠 **АГЕНТ НА ACCESSIBILITY API**\n\n"
        "♿ **ТОЛЬКО ACCESSIBILITY!**\n"
        "🕵️ **Маскировка активна**\n"
        "🍪 **Куки X.com установлены**\n"
        "🔄 **Автовосстановление**\n\n"
        "💡 **Команды:**\n"
        "• Что видишь?\n"
        "• Сделай скриншот\n"
        "• Зайди на x.com\n"
        "• Нажми на кнопку Обзор\n"
        "• Найди все кнопки\n\n"
        "📊 **Служебные:**\n"
        "/logs - логи\n"
        "/clear_logs - очистить логи\n"
        "/cdp - статус браузера"
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
    print("🚀 Запуск бота ТОЛЬКО с Accessibility API...")
    file_logger.log("🚀 Запуск бота ТОЛЬКО с Accessibility API...")
    
    ensure_chrome_running()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен на Accessibility API!")
    file_logger.log("🚀 Бот запущен на Accessibility API!")
    app.run_polling()

if __name__ == "__main__":
    main()