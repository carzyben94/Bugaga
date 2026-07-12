import os
import asyncio
import json
import websockets
import requests
import subprocess
import time
import base64
import tempfile
import shutil
import signal
import sys
import re
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== ЛОГИРОВАНИЕ ====================
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

# ==================== Pillow ====================
try:
    from PIL import Image, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    file_logger.log("⚠️ Pillow не установлен. Установите: pip install pillow>=11.0.0", "WARNING")

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    file_logger.log("❌ TELEGRAM_BOT_TOKEN не установлен!", "ERROR")
    print("❌ TELEGRAM_BOT_TOKEN не установлен!")
    sys.exit(1)

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"
CHROME_PORT = 9222

# ==================== КУКИ ДЛЯ X/TWITTER ====================
X_COOKIES = [
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "__cuid", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "lang", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "ru"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "dnt", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "1"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id_marketing", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "guest_id_ads", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "personalization_id", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "twid", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "u%3D2067347503503052800"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "auth_token", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "ct0", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "__cf_bm", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "Eb4nVvazwJ5mDp0c.6Ye5ub0rukgdQkcFzPf8.wdbIQ-1783798267.7075489-1.0.1.1-59IptPdWY9w0zyKvebR59I.8iB4M1DWfNNZQW0.c.E4lDCU3wTfEcds69RVBkOeQ9LUDZNLGRv6z8InGbCsH1RaTCKaqehL94yq0FgvU7QB9cbE8BO4.2Y8BMRnN_Nks"}
]

# ==================== КОД АГЕНТА ====================
AGENT_CODE = """
🤖 ТЫ — АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ

📌 ТЫ ВИДИШЬ ВСЕ КНОПКИ И ПОЛЯ НА СТРАНИЦЕ!
Используй ТОЛЬКО названия из списка ниже.

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate(url) - открыть сайт
2. click(text) - кликнуть по кнопке (из списка)
3. fill(selector, value) - заполнить поле
4. screenshot() - скриншот
5. reload() - перезагрузить страницу
6. answer(text) - ответить пользователю

📌 ПРИМЕРЫ:
{"action": "click", "params": {"text": "Чат"}}
{"action": "navigate", "params": {"url": "https://x.com"}}
{"action": "answer", "params": {"text": "Я открыл страницу"}}

⚠️ ВАЖНО:
- Для клика используй ТОЧНО такие названия как в списке кнопок
- На X.com: "Чат", "Главная", "Личные сообщения", "Уведомления", "Закладки", "Профиль"
- Если нужен поиск — используй fill с селектором

📌 ЕСЛИ НУЖНО НЕСКОЛЬКО ДЕЙСТВИЙ - ВОЗВРАЩАЙ МАССИВ:
[{"action": "click", "params": {"text": "Чат"}}, {"action": "screenshot", "params": {}}]
"""

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
app = None
chrome_manager = None
cdp = None
clients = {}

# ==================== УПРАВЛЕНИЕ БРАУЗЕРОМ ====================
class ChromeManager:
    def __init__(self, chrome_path=CHROME_PATH, port=CHROME_PORT):
        self.chrome_path = chrome_path
        self.port = port
        self.process = None
        self.ws_endpoint = None
        self.user_data_dir = None
    
    def _find_chrome(self):
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/local/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/app/.apt/usr/bin/google-chrome"
        ]
        for path in paths:
            if os.path.exists(path):
                file_logger.log(f"✅ Найден Chrome: {path}")
                return path
        try:
            result = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip()
                file_logger.log(f"✅ Найден Chrome через which: {path}")
                return path
        except:
            pass
        file_logger.log("❌ Chrome не найден!", "ERROR")
        return None
    
    def _prepare_profile(self):
        self.user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        file_logger.log(f"📁 Профиль Chrome: {self.user_data_dir}")
        return self.user_data_dir
    
    def start(self):
        if self.is_running():
            file_logger.log("✅ Chrome уже запущен")
            self.ws_endpoint = self.get_ws_endpoint()
            return True
        
        file_logger.log("🚀 Запускаю Chrome...")
        chrome_path = self._find_chrome()
        if not chrome_path:
            file_logger.log("❌ Chrome не найден!", "ERROR")
            return False
        
        self._prepare_profile()
        
        cmd = [
            chrome_path,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--window-size=1920,1080",
            "--disable-blink-features=AutomationControlled"
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            for _ in range(10):
                time.sleep(1)
                if self.is_running():
                    self.ws_endpoint = self.get_ws_endpoint()
                    if self.ws_endpoint:
                        file_logger.log(f"✅ Chrome запущен: {self.ws_endpoint}")
                        return True
                file_logger.log(f"⏳ Жду запуск Chrome... {_+1}/10")
            
            file_logger.log("❌ Chrome не запустился за 10 секунд", "ERROR")
            return False
        except Exception as e:
            file_logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            return False
    
    def is_running(self):
        try:
            response = requests.get(f"http://localhost:{self.port}/json/version", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_ws_endpoint(self):
        try:
            response = requests.get(f"http://localhost:{self.port}/json/version", timeout=2)
            return response.json()["webSocketDebuggerUrl"]
        except:
            return None
    
    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None
            file_logger.log("🛑 Chrome остановлен")
        
        if self.user_data_dir and os.path.exists(self.user_data_dir):
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
            file_logger.log(f"🗑️ Профиль удалён: {self.user_data_dir}")

# ==================== CDP КЛИЕНТ ====================
class CDPClient:
    def __init__(self, ws_endpoint):
        self.ws_endpoint = ws_endpoint
        self.websocket = None
        self.msg_id = 0
        self.targets = {}
        self.session_id = None
        self.cookies_set = False
        self.ping_task = None
        self._keep_alive = True
        self._message_queue = asyncio.Queue()
        self._receiver_task = None
        self._pending_requests = {}
        self.user_id = None
        self.full_snapshot = None
    
    async def _receiver(self):
        file_logger.log("📡 Запущен приёмник сообщений")
        while True:
            try:
                if not self.websocket:
                    await asyncio.sleep(0.5)
                    continue
                
                message = await self.websocket.recv()
                data = json.loads(message)
                
                msg_id = data.get("id")
                if msg_id and msg_id in self._pending_requests:
                    future = self._pending_requests.pop(msg_id)
                    if not future.done():
                        future.set_result(data)
                else:
                    await self._message_queue.put(data)
                    
            except websockets.exceptions.ConnectionClosed:
                file_logger.log("⚠️ WebSocket закрыт, останавливаю приёмник", "WARNING")
                break
            except Exception as e:
                file_logger.log(f"⚠️ Ошибка приёмника: {e}", "WARNING")
                await asyncio.sleep(0.5)
    
    async def connect(self):
        if not self.ws_endpoint:
            raise Exception("WebSocket endpoint не указан")
        
        try:
            self.websocket = await websockets.connect(
                self.ws_endpoint,
                ping_interval=20,
                ping_timeout=30,
                close_timeout=15,
                max_size=50 * 1024 * 1024
            )
            file_logger.log(f"✅ Подключено к Chrome: {self.ws_endpoint}")
            
            if self._receiver_task is None or self._receiver_task.done():
                self._receiver_task = asyncio.create_task(self._receiver())
                file_logger.log("📡 Приёмник запущен")
            
            await self.start_keep_alive()
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка подключения: {e}", "ERROR")
            return False
    
    async def keep_alive(self):
        file_logger.log("💓 Запущен пинг для поддержания соединения")
        while self._keep_alive:
            try:
                if self.websocket and not self.websocket.closed:
                    self.msg_id += 1
                    ping_msg = {
                        "id": self.msg_id,
                        "method": "Runtime.evaluate",
                        "params": {"expression": "1"}
                    }
                    await self.websocket.send(json.dumps(ping_msg))
                    file_logger.log("💓 Пинг отправлен")
                else:
                    file_logger.log("⚠️ WebSocket закрыт, останавливаю пинг", "WARNING")
                    break
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                file_logger.log("🛑 Пинг остановлен")
                break
            except Exception as e:
                file_logger.log(f"⚠️ Ошибка пинга: {e}", "WARNING")
                await asyncio.sleep(5)
    
    async def start_keep_alive(self):
        if self.ping_task is None or self.ping_task.done():
            self._keep_alive = True
            self.ping_task = asyncio.create_task(self.keep_alive())
            file_logger.log("✅ Пинг запущен")
    
    async def stop_keep_alive(self):
        self._keep_alive = False
        if self.ping_task and not self.ping_task.done():
            self.ping_task.cancel()
            try:
                await self.ping_task
            except:
                pass
            self.ping_task = None
            file_logger.log("🛑 Пинг остановлен")
    
    async def send(self, method, params=None, session_id=None, timeout=60):
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        
        future = asyncio.Future()
        self._pending_requests[msg_id] = future
        
        try:
            await self.websocket.send(json.dumps(msg))
            response = await asyncio.wait_for(future, timeout=timeout)
            if "error" in response:
                file_logger.log(f"❌ CDP Error: {response['error']}", "ERROR")
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            file_logger.log(f"⏰ Таймаут {method}", "WARNING")
            return {"error": "timeout"}
        except Exception as e:
            self._pending_requests.pop(msg_id, None)
            file_logger.log(f"❌ Ошибка {method}: {e}", "ERROR")
            return {"error": str(e)}
    
    async def eval_js(self, code, session_id=None):
        try:
            result = await self.send("Runtime.evaluate", {
                "expression": code,
                "returnByValue": True,
                "awaitPromise": True
            }, session_id=session_id or self.session_id)
            
            if not result or "error" in result:
                return None
            if "result" in result:
                obj = result["result"]
                if "exceptionDetails" in obj:
                    file_logger.log(f"❌ JS исключение: {obj['exceptionDetails']}", "ERROR")
                    return None
                if "result" in obj:
                    if "value" in obj["result"]:
                        return obj["result"]["value"]
                    if obj["result"].get("type") == "undefined":
                        return None
                if "value" in obj:
                    return obj["value"]
            return None
        except Exception as e:
            file_logger.log(f"❌ eval_js error: {e}", "ERROR")
            return None
    
    async def create_tab(self):
        file_logger.log("📑 Создаю вкладку...")
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        if "error" in result:
            raise Exception(f"Create tab error: {result['error']}")
        target_id = result["result"]["targetId"]
        
        result = await self.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        if "error" in result:
            raise Exception(f"Attach error: {result['error']}")
        session_id = result["result"]["sessionId"]
        
        self.targets[session_id] = target_id
        self.session_id = session_id
        file_logger.log(f"✅ Вкладка создана: {session_id}")
        return session_id, target_id
    
    async def set_cookies(self, cookies):
        try:
            file_logger.log(f"🍪 Установка {len(cookies)} кук...")
            cdp_cookies = []
            for cookie in cookies:
                cdp_cookies.append({
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain"),
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": cookie.get("sameSite", "unspecified"),
                    "session": cookie.get("session", True)
                })
            result = await self.send("Network.setCookies", {
                "cookies": cdp_cookies
            }, session_id=self.session_id)
            if "error" not in result:
                self.cookies_set = True
                file_logger.log(f"✅ Установлено {len(cookies)} кук")
                return True
            file_logger.log(f"❌ Ошибка установки кук: {result.get('error')}", "ERROR")
            return False
        except Exception as e:
            file_logger.log(f"❌ Ошибка установки кук: {e}", "ERROR")
            return False
    
    async def navigate(self, session_id, url):
        file_logger.log(f"🌐 Навигация на {url}")
        result = await self.send("Page.navigate", {"url": url}, session_id=session_id)
        if "error" in result:
            file_logger.log(f"❌ Ошибка навигации: {result['error']}", "ERROR")
            return False
        file_logger.log(f"✅ Навигация выполнена")
        return True
    
    async def wait_for_load(self, session_id, timeout=30):
        file_logger.log("⏳ Ожидаю загрузку страницы...")
        for _ in range(timeout):
            try:
                if not self._message_queue.empty():
                    data = await asyncio.wait_for(self._message_queue.get(), timeout=0.1)
                    if data.get("method") in ["Page.loadEventFired", "Page.frameStoppedLoading"]:
                        file_logger.log("✅ Страница загружена")
                        return True
                await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                file_logger.log(f"⚠️ wait_for_load error: {e}", "WARNING")
                continue
        file_logger.log("⚠️ Таймаут загрузки страницы", "WARNING")
        return False
    
    async def wait_for_content(self, session_id, timeout=30):
        file_logger.log("⏳ Жду загрузки контента...")
        for _ in range(timeout):
            result = await self.send("Runtime.evaluate", {
                "expression": """
                    (function() {
                        const body = document.body;
                        if (!body) return false;
                        const text = body.innerText || '';
                        const hasText = text.length > 200;
                        const hasElements = document.querySelectorAll('article, div, p').length > 10;
                        return hasText || hasElements;
                    })()
                """
            }, session_id=session_id)
            if result and "error" not in result:
                if result.get("result", {}).get("result", {}).get("value", False):
                    file_logger.log("✅ Контент загружен")
                    return True
            await asyncio.sleep(1)
        file_logger.log("⚠️ Таймаут загрузки контента", "WARNING")
        return False
    
    async def get_accessibility_tree(self, session_id):
        file_logger.log("🌳 Получаю дерево доступности...")
        result = await self.send("Accessibility.getFullAXTree", session_id=session_id)
        if "error" in result:
            file_logger.log(f"❌ Ошибка: {result['error']}", "ERROR")
            return []
        nodes = result.get("result", {}).get("nodes", [])
        file_logger.log(f"✅ Найдено {len(nodes)} элементов")
        return nodes
    
    async def get_page_description(self):
        """Получение описания страницы для AI"""
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        nodes = info.get('elements', [])
        
        # Собираем кнопки
        buttons = [el for el in nodes if el.get('role') in ['button', 'link']]
        
        # Собираем поля
        fields = [el for el in nodes if el.get('role') in ['textbox', 'searchbox', 'combobox']]
        
        desc = f"""
📄 СТРАНИЦА: {info.get('title', 'Нет заголовка')}
🔗 URL: {info.get('url', 'Нет URL')}
📊 ВСЕГО ЭЛЕМЕНТОВ: {info.get('total', 0)}

🔘 КНОПКИ И ССЫЛКИ ({len(buttons)}):
"""
        for el in buttons[:30]:
            name = el.get('name', '') or el.get('text', '')
            if name:
                desc += f"  • {name}\n"
        
        desc += f"\n📝 ПОЛЯ ВВОДА ({len(fields)}):\n"
        for el in fields[:10]:
            name = el.get('name', '') or el.get('text', '')
            if name:
                desc += f"  • {name}\n"
        
        return desc
    
    async def get_maximum_snapshot(self):
        try:
            file_logger.log("📸 Делаю максимальный слепок...")
            
            nodes = await self.get_accessibility_tree(self.session_id)
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            elements = []
            for node in nodes:
                role = node.get("role", {}).get("value", "")
                name = node.get("name", {}).get("value", "")
                if name:
                    elements.append({
                        "role": role,
                        "name": name[:100],
                        "text": name[:100],
                        "description": node.get("description", {}).get("value", "")[:100]
                    })
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "elements": elements
            }
            
            file_logger.log(f"✅ Слепок: {len(elements)} элементов")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            return False
    
    async def click_element(self, session_id, selector):
        """Клик по элементу с поддержкой текста, атрибутов и селекторов"""
        file_logger.log(f"🖱️ Клик по '{selector}'")
        
        selector_escaped = selector.replace("'", "\\'").replace('"', '\\"')
        
        js_code = f"""
        (function() {{
            let el = null;
            const search = '{selector_escaped}';
            const searchLower = search.toLowerCase();
            
            // 1. CSS-селектор
            try {{
                el = document.querySelector(search);
            }} catch(e) {{}}
            
            // 2. По тексту
            if (!el) {{
                const all = document.querySelectorAll('*');
                for (const elem of all) {{
                    const text = elem.textContent?.trim() || '';
                    if (text === search || text.toLowerCase().includes(searchLower)) {{
                        el = elem;
                        break;
                    }}
                }}
            }}
            
            // 3. По aria-label
            if (!el) {{
                const all = document.querySelectorAll('[aria-label]');
                for (const elem of all) {{
                    const label = elem.getAttribute('aria-label') || '';
                    if (label === search || label.toLowerCase().includes(searchLower)) {{
                        el = elem;
                        break;
                    }}
                }}
            }}
            
            // 4. По data-testid
            if (!el) {{
                const all = document.querySelectorAll('[data-testid]');
                for (const elem of all) {{
                    const testid = elem.getAttribute('data-testid') || '';
                    if (testid.toLowerCase().includes(searchLower)) {{
                        el = elem;
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
                
                return {{
                    success: true,
                    tag: el.tagName,
                    text: el.textContent?.trim()?.slice(0, 50) || ''
                }};
            }}
            
            return {{ success: false, error: 'Element not found' }};
        }})()
        """
        
        result = await self.eval_js(js_code, session_id)
        
        if result and result.get('success'):
            file_logger.log(f"✅ Клик выполнен: {result.get('tag')} '{result.get('text')}'")
            await asyncio.sleep(1)
            await self.get_maximum_snapshot()
            return result
        
        file_logger.log(f"❌ Элемент не найден: {selector}", "ERROR")
        raise Exception(f"Элемент не найден: {selector}")
    
    async def fill_input(self, session_id, selector, text):
        file_logger.log(f"✍️ Заполняю '{selector}' = '{text[:20]}...'")
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.focus();
                        el.value = '{text}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
            """
        }, session_id=session_id)
        
        if "error" in result:
            file_logger.log(f"❌ Ошибка заполнения: {result['error']}", "ERROR")
            return False
        
        file_logger.log("✅ Поле заполнено")
        await self.get_maximum_snapshot()
        return True
    
    async def screenshot(self, session_id):
        try:
            file_logger.log("📸 Делаю скриншот...")
            title = await self.eval_js("document.title", session_id)
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate(session_id, "https://google.com")
                await asyncio.sleep(2)
                title = await self.eval_js("document.title", session_id)
                if not title:
                    file_logger.log("❌ Не удалось загрузить страницу", "ERROR")
                    return None
            file_logger.log(f"📄 Заголовок: {title}")
            
            resp = await self.send("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 70,
                "captureBeyondViewport": False,
                "fromSurface": True,
                "optimizeForSpeed": True
            }, session_id=session_id)
            
            if "error" in resp:
                file_logger.log(f"❌ Ошибка скриншота: {resp['error']}", "ERROR")
                return None
            
            if "result" in resp and "data" in resp["result"]:
                img_data = base64.b64decode(resp["result"]["data"])
                if len(img_data) > 100 and img_data[:2] == b'\xff\xd8':
                    file_logger.log(f"✅ Скриншот сделан ({len(img_data)} байт)")
                    return img_data
            file_logger.log("❌ Не удалось получить скриншот", "ERROR")
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None
    
    async def reload(self, session_id):
        await self.send("Page.reload", {}, session_id=session_id)
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def close_tab(self, session_id):
        if session_id in self.targets:
            target_id = self.targets[session_id]
            await self.send("Target.closeTarget", {"targetId": target_id})
            del self.targets[session_id]
            file_logger.log(f"📑 Вкладка закрыта: {session_id}")
    
    async def close(self):
        file_logger.log("🔌 Закрываю соединение...")
        await self.stop_keep_alive()
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except:
                pass
            self._receiver_task = None
        if self.websocket:
            try:
                await self.websocket.close()
                file_logger.log("🔌 WebSocket закрыт")
            except:
                pass
            self.websocket = None

# ==================== AI АГЕНТ ====================
async def ask_agnes(prompt: str, client: CDPClient) -> dict:
    """Запрос к Agnes AI"""
    if not AGNES_API_KEY:
        return {"action": "answer", "params": {"text": "❌ AGNES_API_KEY не установлен"}}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Получаем описание страницы
    page_desc = await client.get_page_description()
    
    system_prompt = f"""
{AGENT_CODE}

📄 ТЕКУЩАЯ СТРАНИЦА:
{page_desc}

⚠️ ВАЖНО:
- Используй ТОЛЬКО названия из списка кнопок
- На X.com: "Чат", "Главная", "Личные сообщения", "Уведомления", "Закладки", "Профиль"
- Отвечай ТОЛЬКО JSON!
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
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        file_logger.log(f"Agnes ответ: {content[:200]}...")
        
        if not content or not content.strip():
            return {"action": "answer", "params": {"text": "⚠️ Получен пустой ответ от AI"}}
        
        # Парсим JSON
        json_match = re.search(r'\[.*\]|\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                
                # Если массив с одним элементом
                if isinstance(parsed, list):
                    if len(parsed) == 0:
                        return {"action": "answer", "params": {"text": "⚠️ AI вернул пустой массив"}}
                    if len(parsed) == 1:
                        parsed = parsed[0]
                    else:
                        return parsed
                
                # Если словарь
                if isinstance(parsed, dict):
                    # Преобразуем answer в action
                    if "answer" in parsed and "action" not in parsed:
                        return {"action": "answer", "params": {"text": parsed["answer"]}}
                    
                    # Преобразуем text в params
                    if "action" in parsed and "text" in parsed and "params" not in parsed:
                        parsed["params"] = {"text": parsed.pop("text")}
                        return parsed
                    
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
        file_logger.log("⏳ Таймаут Agnes API", "WARNING")
        return {"action": "answer", "params": {"text": "⏳ Превышено время ожидания ответа от AI. Попробуйте ещё раз."}}
    except Exception as e:
        file_logger.log(f"❌ Agnes error: {e}", "ERROR")
        return {"action": "answer", "params": {"text": f"❌ Ошибка: {str(e)}"}}

# ==================== ВЫПОЛНЕНИЕ ДЕЙСТВИЙ ====================
async def execute_action(client: CDPClient, action, user_id) -> str:
    """Выполнение действия от AI"""
    if isinstance(action, list):
        results = []
        for a in action:
            result = await execute_single_action(client, a, user_id)
            results.append(result)
        return "\n".join(results)
    return await execute_single_action(client, action, user_id)

async def execute_single_action(client: CDPClient, action: dict, user_id) -> str:
    """Выполнение одного действия"""
    if "text" in action and "params" not in action:
        action["params"] = {"text": action.pop("text")}
    
    if "answer" in action and "action" not in action:
        action = {"action": "answer", "params": {"text": action.pop("answer")}}
    
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение действия: {action_type}")
    
    try:
        session_id = client.session_id
        
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await client.navigate(session_id, url)
            await client.wait_for_load(session_id)
            await client.wait_for_content(session_id, timeout=30)
            await client.get_maximum_snapshot()
            title = await client.eval_js("document.title", session_id)
            return f"✅ Открыл: {url}\n📄 {title}"
        
        elif action_type == "click":
            text = params.get("text") or params.get("selector")
            if not text:
                return "❌ Нет текста для клика"
            result = await client.click_element(session_id, text)
            if result and result.get('success'):
                await client.get_maximum_snapshot()
                return f"✅ Кликнул: {text}"
            return f"❌ Элемент не найден: {text}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            if not selector:
                return "❌ Нет селектора"
            result = await client.fill_input(session_id, selector, value)
            if result:
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "screenshot":
            img_data = await client.screenshot(session_id)
            if img_data:
                filename = f"screenshot_{user_id}_{int(time.time())}.jpg"
                with open(filename, "wb") as f:
                    f.write(img_data)
                return "screenshot"
            return "❌ Не удалось сделать скриншот"
        
        elif action_type == "reload":
            await client.reload(session_id)
            return "✅ Страница перезагружена"
        
        elif action_type == "answer":
            text = params.get('text', 'Нет ответа')
            return f"📝 {text}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"❌ Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_logger.log(f"📩 /start от {update.message.from_user.id}")
    agnes_status = "✅" if AGNES_API_KEY else "❌"
    pillow_status = "✅" if PILLOW_AVAILABLE else "❌"
    
    await update.message.reply_text(
        f"🧠 **AI АГЕНТ ДЛЯ БРАУЗЕРА**\n\n"
        f"🤖 Управляй браузером через AI!\n\n"
        f"📌 **Просто напиши что хочешь сделать:**\n"
        f"• Открой x.com\n"
        f"• Нажми на кнопку Чат\n"
        f"• Сделай скриншот\n"
        f"• Что видишь на странице?\n\n"
        f"🖼️ Pillow: {pillow_status}\n"
        f"🧠 Agnes AI: {agnes_status}\n"
        f"🍪 Куки X.com: ✅ установлены\n"
        f"💓 Авто-пинг: ✅ активен\n\n"
        f"📌 Доступные команды:\n"
        f"/start - Начать\n"
        f"/help - Справка\n"
        f"/click <название> - Кликнуть\n"
        f"/screenshot - Скриншот\n"
        f"/logs - Логи\n"
        f"/clear - Очистить сессию"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений через AI"""
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"💬 Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Получаем или создаём клиент
        if user_id not in clients:
            file_logger.log(f"🆕 Создаю клиент для {user_id}")
            client = CDPClient(chrome_manager.ws_endpoint)
            client.user_id = user_id
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        # Проверяем соединение
        if not client.websocket or client.websocket.closed:
            file_logger.log(f"🔄 Переподключение для {user_id}")
            await client.connect()
        
        # Если нет вкладки - создаём
        if not client.session_id:
            await client.create_tab()
            await client.set_cookies(X_COOKIES)
            await client.navigate(client.session_id, "https://x.com")
            await client.wait_for_load(client.session_id)
            await client.wait_for_content(client.session_id)
        
        # Обновляем слепок
        await client.get_maximum_snapshot()
        
        # Запрашиваем AI
        if AGNES_API_KEY:
            response = await ask_agnes(prompt, client)
            if "error" not in response:
                result = await execute_action(client, response, user_id)
                
                if result == "screenshot":
                    # Ищем файл скриншота
                    import glob
                    files = glob.glob(f"screenshot_{user_id}_*.jpg")
                    if files:
                        latest = max(files, key=os.path.getctime)
                        with open(latest, "rb") as f:
                            await update.message.reply_photo(photo=f, caption="📸 Скриншот")
                        os.remove(latest)
                    else:
                        await update.message.reply_text("❌ Не удалось найти скриншот")
                else:
                    await update.message.reply_text(result)
                return
            else:
                await update.message.reply_text(f"❌ Ошибка AI: {response.get('error', 'Неизвестная ошибка')}")
                return
        
        # Если нет API ключа - обычный режим
        await update.message.reply_text(
            "❌ AGNES_API_KEY не установлен.\n"
            "Используйте команды напрямую:\n"
            "/click Чат\n"
            "/screenshot"
        )
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка в handle_message: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        args = update.message.text.split()
        if len(args) < 2:
            await update.message.reply_text("❌ Использование: /click <название>")
            return
        
        selector = " ".join(args[1:])
        
        if user_id not in clients:
            await update.message.reply_text("❌ Сначала отправь сообщение")
            return
        
        client = clients[user_id]
        if not client.session_id:
            await update.message.reply_text("❌ Нет активной вкладки")
            return
        
        await update.message.reply_text(f"🖱️ Кликаю по '{selector}'...")
        result = await client.click_element(client.session_id, selector)
        
        if result and result.get('success'):
            await update.message.reply_text(f"✅ Клик выполнен")
        else:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка click: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        
        if user_id not in clients:
            await update.message.reply_text("❌ Сначала отправь сообщение")
            return
        
        client = clients[user_id]
        if not client.session_id:
            await update.message.reply_text("❌ Нет активной вкладки")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        img_data = await client.screenshot(client.session_id)
        
        if img_data:
            await update.message.reply_photo(photo=BytesIO(img_data), caption="📸 Скриншот")
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка screenshot: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 **AI АГЕНТ**\n\n"
        "📌 **Просто напиши что хочешь сделать:**\n"
        "• Открой x.com\n"
        "• Нажми на Чат\n"
        "• Сделай скриншот\n"
        "• Что видишь на странице?\n\n"
        "📌 **Команды:**\n"
        "/click <название> - Кликнуть\n"
        "/screenshot - Скриншот\n"
        "/logs - Логи\n"
        "/clear - Очистить сессию\n\n"
        "💡 На X.com доступны кнопки:\n"
        "Главная, Чат, Личные сообщения, Уведомления, Закладки, Профиль"
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in clients:
        await clients[user_id].close()
        del clients[user_id]
        await update.message.reply_text("🧹 Сессия очищена")
    else:
        await update.message.reply_text("Активной сессии нет")

# ==================== ЗАПУСК ====================
async def shutdown():
    global app, chrome_manager, cdp, clients
    file_logger.log("🛑 Завершение работы...")
    print("\n🛑 Завершение работы...")
    
    # Закрываем все клиенты
    for user_id, client in clients.items():
        try:
            await client.close()
        except:
            pass
    
    if app:
        try:
            await app.stop()
            await app.shutdown()
            file_logger.log("✅ Бот остановлен")
        except:
            pass
    
    if chrome_manager:
        chrome_manager.stop()
    
    file_logger.log("👋 Завершено")
    print("👋 Завершено")

async def main_async():
    global app, chrome_manager, cdp
    file_logger.log("🚀 Запуск бота...")
    print("🚀 Запуск бота...")
    print(f"🔗 Chrome: {chrome_manager.ws_endpoint}")
    print(f"🍪 Загружено {len(X_COOKIES)} кук")
    print(f"🧠 Agnes AI: {'✅ Доступен' if AGNES_API_KEY else '❌ Не установлен'}")
    print("💓 Авто-пинг включён")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("click", click_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    # Обработчик сообщений (AI)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    loop = asyncio.get_event_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    file_logger.log("✅ Бот запущен!")
    print("✅ Бот запущен!")
    
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown()

def main():
    global chrome_manager, cdp
    chrome_manager = ChromeManager()
    if not chrome_manager.start():
        file_logger.log("❌ Не удалось запустить Chrome", "ERROR")
        print("❌ Не удалось запустить Chrome")
        sys.exit(1)
    cdp = CDPClient(chrome_manager.ws_endpoint)
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        file_logger.log("👋 Прервано пользователем")
        print("\n👋 Прервано пользователем")
    finally:
        if chrome_manager:
            chrome_manager.stop()

if __name__ == "__main__":
    main()