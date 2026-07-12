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

# ==================== Pillow для обработки изображений ====================
try:
    from PIL import Image, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("⚠️ Pillow не установлен. Установите: pip install pillow>=11.0.0")

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHROME_PATH = "/usr/bin/google-chrome"
CHROME_PORT = 9222

# ==================== КУКИ ДЛЯ X/TWITTER ====================
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
                print(f"✅ Найден Chrome: {path}")
                return path
        
        try:
            result = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip()
                print(f"✅ Найден Chrome через which: {path}")
                return path
        except:
            pass
        
        return None
    
    def _prepare_cookies_file(self):
        self.user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        print(f"📁 Профиль Chrome: {self.user_data_dir}")
        return self.user_data_dir
    
    def start(self):
        if self.is_running():
            print("✅ Chrome уже запущен")
            self.ws_endpoint = self.get_ws_endpoint()
            return True
        
        print("🚀 Запускаю Chrome...")
        
        chrome_path = self._find_chrome()
        if not chrome_path:
            print("❌ Chrome не найден!")
            return False
        
        self._prepare_cookies_file()
        
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
                        print(f"✅ Chrome запущен: {self.ws_endpoint}")
                        return True
                print(f"⏳ Жду запуск Chrome... {_+1}/10")
            
            print("❌ Chrome не запустился за 10 секунд")
            return False
                
        except Exception as e:
            print(f"❌ Ошибка запуска Chrome: {e}")
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
    
    async def set_cookies_after_start(self):
        try:
            print("🍪 Начинаю установку кук...")
            cdp_temp = CDPClient(self.ws_endpoint)
            await cdp_temp.connect()
            
            session_id, _ = await cdp_temp.create_tab()
            
            cdp_cookies = []
            for cookie in X_COOKIES:
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
            
            result = await cdp_temp.send("Network.setCookies", {
                "cookies": cdp_cookies
            }, session_id=session_id)
            
            if "error" not in result:
                print(f"✅ Установлено {len(X_COOKIES)} кук")
            else:
                print(f"❌ Ошибка: {result.get('error')}")
            
            await cdp_temp.close_tab(session_id)
            await cdp_temp.close()
            print("✅ Все куки установлены")
            
        except Exception as e:
            print(f"⚠️ Ошибка установки кук: {e}")
    
    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None
            print("🛑 Chrome остановлен")
        
        if self.user_data_dir and os.path.exists(self.user_data_dir):
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
            print(f"🗑️ Профиль удалён: {self.user_data_dir}")

# ==================== CDP КЛИЕНТ ====================
class CDPClient:
    def __init__(self, ws_endpoint):
        self.ws_endpoint = ws_endpoint
        self.websocket = None
        self.msg_id = 0
        self.targets = {}
        self.session_id = None
        self.cookies_set = False
    
    async def connect(self):
        if not self.ws_endpoint:
            raise Exception("WebSocket endpoint не указан")
        self.websocket = await websockets.connect(
            self.ws_endpoint,
            ping_interval=20,
            ping_timeout=30,
            close_timeout=10,
            max_size=50 * 1024 * 1024
        )
        print(f"✅ Подключено к Chrome: {self.ws_endpoint}")
    
    async def send(self, method, params=None, session_id=None):
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        
        await self.websocket.send(json.dumps(msg))
        
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            if data.get("id") == self.msg_id:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data
    
    async def eval_js(self, code, session_id=None):
        """Выполняет JavaScript и возвращает результат"""
        try:
            result = await self.send("Runtime.evaluate", {
                "expression": code,
                "returnByValue": True,
                "awaitPromise": True
            }, session_id=session_id or self.session_id)
            
            if "result" in result:
                obj = result["result"]
                if "value" in obj:
                    return obj["value"]
                if "result" in obj and "value" in obj["result"]:
                    return obj["result"]["value"]
            return None
        except Exception as e:
            print(f"❌ eval_js error: {e}")
            return None
    
    async def create_tab(self):
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        target_id = result["result"]["targetId"]
        
        result = await self.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = result["result"]["sessionId"]
        
        await self.send("Page.enable", session_id=session_id)
        await self.send("Runtime.enable", session_id=session_id)
        await self.send("DOM.enable", session_id=session_id)
        await self.send("Network.enable", session_id=session_id)
        
        self.targets[session_id] = target_id
        self.session_id = session_id
        return session_id, target_id
    
    async def set_cookies(self, cookies):
        try:
            print(f"🍪 Установка {len(cookies)} кук...")
            
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
            }, session_id=self.session_id)
            
            if "error" not in result:
                self.cookies_set = True
                print(f"✅ Установлено {len(cookies)} кук")
                return True
            else:
                print(f"❌ Ошибка: {result.get('error')}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка установки кук: {e}")
            return False
    
    async def navigate(self, session_id, url):
        return await self.send("Page.navigate", {"url": url}, session_id=session_id)
    
    async def wait_for_load(self, session_id, timeout=30):
        for _ in range(timeout):
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=1)
                data = json.loads(response)
                if data.get("method") == "Page.loadEventFired":
                    return True
                if data.get("method") == "Page.frameStoppedLoading":
                    return True
                if data.get("id") and data.get("error"):
                    return False
            except asyncio.TimeoutError:
                continue
        return False
    
    async def wait_for_content(self, session_id, timeout=30):
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
            
            if result.get("result", {}).get("result", {}).get("value"):
                return True
            await asyncio.sleep(1)
        return False
    
    async def get_accessibility_tree(self, session_id):
        result = await self.send("Accessibility.getFullAXTree", session_id=session_id)
        return result["result"]["nodes"]
    
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
        
        if result.get("result", {}).get("result", {}).get("value"):
            return result["result"]["result"]["value"]
        return None
    
    async def click_element(self, session_id, selector):
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
        
        return coords
    
    async def fill_input(self, session_id, selector, text):
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
        
        return True
    
    async def screenshot_with_pillow(self, session_id):
        """Скриншот с обработкой через Pillow"""
        try:
            # 1. Проверяем размеры страницы через JS
            dims = await self.eval_js("""
                (function() {
                    const d = document.documentElement;
                    const b = document.body;
                    return {
                        w: Math.max(d.scrollWidth, b.scrollWidth, window.innerWidth) || 1920,
                        h: Math.max(d.scrollHeight, b.scrollHeight, window.innerHeight) || 1080
                    };
                })()
            """, session_id)
            
            width = dims.get('w', 1920) if dims else 1920
            height = dims.get('h', 1080) if dims else 1080
            
            print(f"📐 Размеры страницы: {width}x{height}")
            
            # 2. Делаем скриншот
            result = await self.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True,
                "fromSurface": True
            }, session_id=session_id)
            
            if "result" not in result or "data" not in result["result"]:
                return None
            
            img_data = base64.b64decode(result["result"]["data"])
            
            if len(img_data) < 100:
                print("❌ Скриншот слишком маленький")
                return None
            
            # 3. Обрабатываем через Pillow
            if PILLOW_AVAILABLE:
                try:
                    img = Image.open(BytesIO(img_data))
                    w, h = img.size
                    print(f"📐 Реальный размер: {w}x{h}")
                    
                    # Если изображение слишком маленькое - пробуем с clip
                    if w < 100 or h < 100:
                        print("⚠️ Изображение слишком маленькое, пробую с clip...")
                        
                        result = await self.send("Page.captureScreenshot", {
                            "format": "png",
                            "clip": {
                                "x": 0,
                                "y": 0,
                                "width": min(width, 1920),
                                "height": min(height, 1080),
                                "scale": 1
                            }
                        }, session_id=session_id)
                        
                        if "result" in result and "data" in result["result"]:
                            img_data = base64.b64decode(result["result"]["data"])
                            img = Image.open(BytesIO(img_data))
                            w, h = img.size
                            print(f"📐 Новый размер: {w}x{h}")
                    
                    # Сохраняем как JPEG для уменьшения размера
                    output = BytesIO()
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    img.save(output, format='JPEG', quality=85)
                    output.seek(0)
                    
                    print(f"✅ Скриншот обработан через Pillow: {w}x{h}")
                    return output.getvalue()
                    
                except Exception as e:
                    print(f"⚠️ Pillow ошибка: {e}")
                    # Возвращаем оригинал
                    return img_data
            else:
                # Если Pillow нет - возвращаем оригинал
                return img_data
                
        except Exception as e:
            print(f"❌ Screenshot error: {e}")
            return None
    
    async def close_tab(self, session_id):
        if session_id in self.targets:
            target_id = self.targets[session_id]
            await self.send("Target.closeTarget", {"targetId": target_id})
            del self.targets[session_id]
    
    async def close(self):
        if self.websocket:
            await self.websocket.close()

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pillow_status = "✅" if PILLOW_AVAILABLE else "❌"
    await update.message.reply_text(
        f"🤖 Привет! Я бот для автоматизации браузера.\n\n"
        f"📌 Отправь мне URL, и я покажу все элементы.\n"
        f"📌 Используй /click <селектор> для клика.\n"
        f"📌 Используй /fill <селектор> <текст> для заполнения.\n"
        f"📌 Используй /screenshot для скриншота.\n"
        f"🖼️ Pillow: {pillow_status}\n"
        f"🍪 Куки X.com установлены автоматически!"
    )

async def set_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cdp
    
    try:
        await update.message.reply_text("🍪 Устанавливаю куки для X.com...")
        
        if not cdp.websocket or not cdp.session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        result = await cdp.set_cookies(X_COOKIES)
        
        if result:
            await update.message.reply_text(f"✅ Установлено {len(X_COOKIES)} кук для X.com")
        else:
            await update.message.reply_text("❌ Не удалось установить куки")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cdp
    
    url = update.message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Отправь корректный URL")
        return
    
    await update.message.reply_text(f"🔄 Анализирую {url}...")
    
    try:
        if not cdp.websocket:
            await cdp.connect()
        
        session_id, target_id = await cdp.create_tab()
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
                node_id = node.get("nodeId")
                interactive.append({
                    "id": node_id,
                    "role": role,
                    "name": name[:100]
                })
        
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
            await update.message.reply_text(
                "❌ Интерактивных элементов не найдено.\n\n"
                "💡 Попробуйте:\n"
                "• /screenshot - посмотреть страницу\n"
                "• /set_cookies - переустановить куки"
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        print(f"Error: {e}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.split()
        if len(args) < 2:
            await update.message.reply_text("❌ Использование: /click <селектор>")
            return
        
        selector = args[1]
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text(f"🖱️ Кликаю по '{selector}'...")
        coords = await cdp.click_element(session_id, selector)
        await update.message.reply_text(f"✅ Клик выполнен по координатам ({coords['x']:.0f}, {coords['y']:.0f})")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def fill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.split()
        if len(args) < 3:
            await update.message.reply_text("❌ Использование: /fill <селектор> <текст>")
            return
        
        selector = args[1]
        text = " ".join(args[2:])
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text(f"✍️ Заполняю '{selector}' текстом: {text}")
        await cdp.fill_input(session_id, selector, text)
        await update.message.reply_text("✅ Поле заполнено")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        # Используем скриншот с Pillow
        image_data = await cdp.screenshot_with_pillow(session_id)
        
        if image_data:
            try:
                # Отправляем как JPEG
                await update.message.reply_photo(
                    photo=BytesIO(image_data),
                    caption="📸 Скриншот страницы"
                )
            except Exception as e:
                if "Photo_invalid_dimensions" in str(e):
                    await update.message.reply_text(
                        "❌ Ошибка размеров изображения. Попробуйте:\n"
                        "1. /reload - перезагрузить страницу\n"
                        "2. Открыть другую страницу\n"
                        "3. Проверить что страница загружена"
                    )
                else:
                    await update.message.reply_text(f"❌ Ошибка отправки: {str(e)}")
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        print(f"Error: {e}")

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезагрузка страницы"""
    session_id = context.user_data.get('session_id')
    if not session_id:
        await update.message.reply_text("❌ Сначала отправь URL для анализа")
        return
    
    await update.message.reply_text("🔄 Перезагружаю страницу...")
    await cdp.send("Page.reload", {}, session_id=session_id)
    await asyncio.sleep(2)
    await update.message.reply_text("✅ Страница перезагружена")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get('session_id')
    if session_id:
        await cdp.close_tab(session_id)
        context.user_data.clear()
        await update.message.reply_text("🧹 Сессия очищена")
    else:
        await update.message.reply_text("Активной сессии нет")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Доступные команды:\n\n"
        "/start - Начать работу\n"
        "/help - Эта справка\n"
        "/click <селектор> - Кликнуть по элементу\n"
        "/fill <селектор> <текст> - Заполнить поле\n"
        "/screenshot - Сделать скриншот\n"
        "/reload - Перезагрузить страницу\n"
        "/set_cookies - Переустановить куки X.com\n"
        "/clear - Очистить сессию\n\n"
        "🔹 Просто отправь URL для анализа страницы"
    )

# ==================== ЗАПУСК БОТА ====================
async def shutdown():
    global app, chrome_manager, cdp
    
    print("\n🛑 Завершение работы...")
    
    if app:
        try:
            await app.stop()
            await app.shutdown()
            print("✅ Бот остановлен")
        except:
            pass
    
    if cdp and cdp.websocket:
        try:
            await cdp.close()
            print("✅ WebSocket закрыт")
        except:
            pass
    
    if chrome_manager:
        chrome_manager.stop()
    
    print("👋 Завершено")

async def main_async():
    global app, chrome_manager, cdp
    
    print("🚀 Запуск бота...")
    print(f"🔗 Chrome: {chrome_manager.ws_endpoint}")
    print(f"🍪 Загружено {len(X_COOKIES)} кук для X.com")
    print(f"🖼️ Pillow: {'✅ Доступен' if PILLOW_AVAILABLE else '❌ Не установлен'}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("click", click_command))
    app.add_handler(CommandHandler("fill", fill_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(CommandHandler("set_cookies", set_cookies_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    loop = asyncio.get_event_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    print("✅ Бот запущен и готов к работе!")
    
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
        print("❌ Не удалось запустить Chrome")
        sys.exit(1)
    
    cdp = CDPClient(chrome_manager.ws_endpoint)
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n👋 Прервано пользователем")
    finally:
        if chrome_manager:
            chrome_manager.stop()

if __name__ == "__main__":
    main()