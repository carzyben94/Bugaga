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
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== ЛОГИРОВАНИЕ ====================
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
        # Создаём файл с заголовком
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

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
app = None
chrome_manager = None
cdp = None

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
            
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("DOM.enable")
            await self.send("Network.enable")
            
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
        
        await self.send("Page.enable", session_id=session_id)
        await self.send("Runtime.enable", session_id=session_id)
        await self.send("DOM.enable", session_id=session_id)
        await self.send("Network.enable", session_id=session_id)
        
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
    
    async def get_element_by_selector(self, session_id, selector):
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {{
                        id: el.id || '',
                        className: el.className || '',
                        tagName: el.tagName,
                        x: rect.x + rect.width/2,
                        y: rect.y + rect.height/2,
                        width: rect.width,
                        height: rect.height
                    }};
                }})()
            """
        }, session_id=session_id)
        if "error" in result:
            return None
        return result.get("result", {}).get("result", {}).get("value")
    
    async def click_element(self, session_id, selector):
        file_logger.log(f"🖱️ Клик по '{selector}'")
        coords = await self.get_element_by_selector(session_id, selector)
        if not coords:
            raise Exception("Элемент не найден")
        await self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
            "modifiers": 0
        }, session_id=session_id)
        await asyncio.sleep(0.1)
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
            "modifiers": 0
        }, session_id=session_id)
        file_logger.log(f"✅ Клик выполнен ({coords['x']:.0f}, {coords['y']:.0f})")
        return coords
    
    async def fill_input(self, session_id, selector, text):
        file_logger.log(f"✍️ Заполняю '{selector}' = '{text[:20]}...'")
        await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.focus();
                        el.value = '';
                        return true;
                    }}
                    return false;
                }})()
            """
        }, session_id=session_id)
        await asyncio.sleep(0.1)
        for char in text:
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char
            }, session_id=session_id)
            await asyncio.sleep(0.01)
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "text": char
            }, session_id=session_id)
            await asyncio.sleep(0.01)
        file_logger.log("✅ Поле заполнено")
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

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_logger.log(f"📩 /start от {update.message.from_user.id}")
    pillow_status = "✅" if PILLOW_AVAILABLE else "❌"
    await update.message.reply_text(
        f"🤖 Привет! Я бот для автоматизации браузера.\n\n"
        f"📌 Отправь мне URL, и я покажу все элементы.\n"
        f"📌 Используй /click <селектор> для клика.\n"
        f"📌 Используй /fill <селектор> <текст> для заполнения.\n"
        f"📌 Используй /screenshot для скриншота.\n"
        f"🖼️ Pillow: {pillow_status}\n"
        f"🍪 Куки X.com установлены автоматически!\n"
        f"💓 Авто-пинг для стабильного соединения"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cdp
    url = update.message.text.strip()
    user_id = update.message.from_user.id
    file_logger.log(f"📩 URL от {user_id}: {url}")
    
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Отправь корректный URL")
        return
    
    await update.message.reply_text(f"🔄 Анализирую {url}...")
    
    try:
        if not cdp.websocket:
            await cdp.connect()
        else:
            await cdp.start_keep_alive()
        
        session_id, _ = await cdp.create_tab()
        context.user_data['session_id'] = session_id
        await cdp.set_cookies(X_COOKIES)
        await cdp.navigate(session_id, url)
        await update.message.reply_text("⏳ Ожидаю загрузку страницы...")
        await cdp.wait_for_load(session_id)
        
        if "x.com" in url or "twitter.com" in url:
            await update.message.reply_text("⏳ Жду загрузки контента...")
            await cdp.wait_for_content(session_id, timeout=30)
        
        nodes = await cdp.get_accessibility_tree(session_id)
        interactive = []
        for node in nodes:
            role = node.get("role", {}).get("value", "")
            if role in ["button", "link", "textbox", "checkbox", "combobox", "radio"]:
                name = node.get("name", {}).get("value", "")
                interactive.append({"role": role, "name": name[:100]})
        
        context.user_data['elements'] = interactive
        
        if interactive:
            msg = "🔍 Найдены интерактивные элементы:\n\n"
            for i, el in enumerate(interactive[:20], 1):
                name = el['name'] if el['name'] else "(без названия)"
                msg += f"{i}. [{el['role']}] {name}\n"
            if len(interactive) > 20:
                msg += f"\n... и ещё {len(interactive) - 20} элементов"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ Интерактивных элементов не найдено.\n\n💡 Попробуйте /screenshot")
            
    except Exception as e:
        error_msg = str(e)[:200]
        file_logger.log(f"❌ Ошибка в handle_url: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        args = update.message.text.split()
        if len(args) < 2:
            await update.message.reply_text("❌ Использование: /click <селектор>")
            return
        selector = args[1]
        session_id = context.user_data.get('session_id')
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL")
            return
        file_logger.log(f"🖱️ Клик от {user_id}: {selector}")
        await update.message.reply_text(f"🖱️ Кликаю по '{selector}'...")
        coords = await cdp.click_element(session_id, selector)
        await update.message.reply_text(f"✅ Клик выполнен ({coords['x']:.0f}, {coords['y']:.0f})")
    except Exception as e:
        file_logger.log(f"❌ Ошибка click: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def fill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        args = update.message.text.split()
        if len(args) < 3:
            await update.message.reply_text("❌ Использование: /fill <селектор> <текст>")
            return
        selector = args[1]
        text = " ".join(args[2:])
        session_id = context.user_data.get('session_id')
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL")
            return
        file_logger.log(f"✍️ Заполнение от {user_id}: {selector} = {text[:20]}...")
        await update.message.reply_text(f"✍️ Заполняю '{selector}'...")
        await cdp.fill_input(session_id, selector, text)
        await update.message.reply_text("✅ Поле заполнено")
    except Exception as e:
        file_logger.log(f"❌ Ошибка fill: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        file_logger.log(f"📸 Скриншот от {user_id}")
        session_id = context.user_data.get('session_id')
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL")
            return
        await update.message.reply_text("📸 Делаю скриншот...")
        image_data = await cdp.screenshot(session_id)
        if image_data:
            try:
                await update.message.reply_photo(photo=BytesIO(image_data), caption="📸 Скриншот")
            except Exception as e:
                if "Photo_invalid_dimensions" in str(e):
                    await update.message.reply_text("❌ Ошибка размеров. Попробуйте /reload")
                else:
                    await update.message.reply_text(f"❌ Ошибка отправки: {str(e)[:100]}")
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        file_logger.log(f"❌ Ошибка screenshot: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get('session_id')
    if not session_id:
        await update.message.reply_text("❌ Сначала отправь URL")
        return
    await update.message.reply_text("🔄 Перезагружаю страницу...")
    await cdp.send("Page.reload", {}, session_id=session_id)
    await asyncio.sleep(2)
    await update.message.reply_text("✅ Страница перезагружена")

async def set_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🍪 Устанавливаю куки...")
        if not cdp.websocket:
            await update.message.reply_text("❌ Сначала отправь URL")
            return
        result = await cdp.set_cookies(X_COOKIES)
        if result:
            await update.message.reply_text(f"✅ Установлено {len(X_COOKIES)} кук")
        else:
            await update.message.reply_text("❌ Не удалось установить куки")
    except Exception as e:
        file_logger.log(f"❌ Ошибка set_cookies: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл с логами"""
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
    """Очищает файл логов"""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи очищены ===\n")
            f.write(f"Время очистки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
        await update.message.reply_text("✅ Логи очищены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get('session_id')
    if session_id:
        await cdp.close_tab(session_id)
        await cdp.stop_keep_alive()
        context.user_data.clear()
        await update.message.reply_text("🧹 Сессия очищена")
    else:
        await update.message.reply_text("Активной сессии нет")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Доступные команды:\n\n"
        "/start - Начать работу\n"
        "/help - Эта справка\n"
        "/click <селектор> - Кликнуть\n"
        "/fill <селектор> <текст> - Заполнить поле\n"
        "/screenshot - Скриншот\n"
        "/reload - Перезагрузить страницу\n"
        "/set_cookies - Переустановить куки\n"
        "/logs - Получить файл логов\n"
        "/clear_logs - Очистить логи\n"
        "/clear - Очистить сессию\n\n"
        "🔹 Просто отправь URL для анализа"
    )

# ==================== ЗАПУСК ====================
async def shutdown():
    global app, chrome_manager, cdp
    file_logger.log("🛑 Завершение работы...")
    print("\n🛑 Завершение работы...")
    
    if cdp:
        await cdp.close()
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
    print(f"🖼️ Pillow: {'✅ Доступен' if PILLOW_AVAILABLE else '❌ Не установлен'}")
    print("💓 Авто-пинг включён")
    file_logger.log(f"🔗 Chrome: {chrome_manager.ws_endpoint}")
    file_logger.log(f"🍪 Загружено {len(X_COOKIES)} кук")
    file_logger.log(f"🖼️ Pillow: {'✅ Доступен' if PILLOW_AVAILABLE else '❌ Не установлен'}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("click", click_command))
    app.add_handler(CommandHandler("fill", fill_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(CommandHandler("set_cookies", set_cookies_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
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