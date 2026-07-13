import os
import json
import time
import subprocess
import base64
import requests
import asyncio
import websockets
import random
import hashlib
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- КОНФИГ ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222

# ---------- AGNES AI API ----------
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "ваш_api_ключ")
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"

# ---------- КУКИ ----------
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"name": "lang", "value": "ru"},
    {"name": "dnt", "value": "1"},
    {"name": "guest_id", "value": "v1%3A178267838599411411"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411"},
    {"name": "personalization_id", "value": '"v1_DKrxLZAC902dMFdd1QrVYg=="'},
    {"name": "twid", "value": "u%3D2067347503503052800"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"name": "__cf_bm", "value": "DKjbDyjx2QirHfmkqVMEiM2Q9FZWkmQRWl7QI8XLKjs-1783962953.1855185-1.0.1.1-CjA58gOnYa62PucjDc.DLVoFW4q7encZTCVGJqwLMENwM3pLXQ2rLX6DdDuE_SFFjQRrFSk3LLEigrhGTLwrLN8RPyfLPBPiIGZZui7lAFIYEAd90bQLkdzLfWy827.2"}
]

# ---------- ЛОГИРОВАНИЕ ----------
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- AI АГЕНТ ----------
class AgnesAI:
    def __init__(self, api_key=AGNES_API_KEY):
        self.api_key = api_key
        self.api_url = AGNES_API_URL
    
    async def ask(self, prompt, context=None, history=None):
        try:
            messages = [
                {
                    "role": "system",
                    "content": """Ты - AI-агент для автоматизации браузера.

Ты получаешь полный snapshot DOM-дерева страницы. Анализируй его и принимай решения.

Правила:
1. Если страница пустая (мало элементов) - ответь {"action": "wait", "reason": "жду загрузки"}
2. Если видишь кнопку с текстом "Обзор", "Войти", "Написать" - нажми её
3. Если есть поле ввода - напиши в него
4. Отвечай ТОЛЬКО в формате JSON

Формат ответа:
{"action": "click|type|scroll|wait|get|done", "selector": "css_selector", "text": "текст", "reason": "почему"}"""
                }
            ]
            
            if history:
                for h in history[-5:]:
                    messages.append({"role": "assistant", "content": json.dumps(h)})
            
            if context:
                messages.append({
                    "role": "user",
                    "content": f"Вот полный snapshot DOM-дерева страницы. Проанализируй его и выполни задачу.\n\nЗадача: {prompt}\n\nSnapshot:\n{context}"
                })
            else:
                messages.append({
                    "role": "user",
                    "content": prompt
                })
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "agnes-2.0-flash",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                file_logger.log(f"AI ответ: {content[:100]}...", "INFO")
                
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    return {"action": "done", "reason": "Задача выполнена"}
            else:
                file_logger.log(f"Ошибка AI API: {response.status_code}", "ERROR")
                return {"action": "error", "reason": f"Ошибка API: {response.status_code}"}
                
        except Exception as e:
            file_logger.log(f"Ошибка AI: {e}", "ERROR")
            return {"action": "error", "reason": str(e)}

# ---------- МАСКИРОВКА ----------
def get_random_window_position():
    return {
        "left": random.randint(50, 300),
        "top": random.randint(50, 200),
        "width": random.randint(1200, 1920),
        "height": random.randint(800, 1080)
    }

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    ]
    return random.choice(user_agents)

def get_random_webgl_vendor():
    vendors = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (AMD)",
        "Google Inc. (Intel)",
        "NVIDIA Corporation",
        "Advanced Micro Devices, Inc.",
        "Intel Corporation"
    ]
    return random.choice(vendors)

def get_random_webgl_renderer():
    renderers = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ]
    return random.choice(renderers)

def get_launch_args():
    window = get_random_window_position()
    
    args = [
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-automation",
        "--use-gl=egl",
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-client-side-phishing-detection",
        "--disable-crash-reporter",
        "--disable-component-update",
        "--disable-logging",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-ipc-flooding-protection",
        "--disable-renderer-backgrounding",
        f"--window-position={window['left']},{window['top']}",
        f"--window-size={window['width']},{window['height']}",
        "--no-default-browser-check",
        "--no-first-run",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--password-store=basic",
        "--use-mock-keychain",
        "--export-tagged-pdf",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        f"--user-agent={get_random_user_agent()}",
        f"--remote-debugging-port={CDP_PORT}"
    ]
    
    return args

# ---------- БРАУЗЕР ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.session_id = None
        self.target_id = None
        self.webgl_vendor = get_random_webgl_vendor()
        self.webgl_renderer = get_random_webgl_renderer()
        self.cookies = COOKIES
        self.agent_active = False
        self.current_task = None
        self.current_url = None
        self.action_history = []
        self.snapshot_history = []
        self.load_event = asyncio.Event()
        self._listener_task = None
        self._message_queue = asyncio.Queue()
        self._pending_requests = {}
    
    def ensure_browser(self):
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("Запускаю Chrome...", "INFO")
            try:
                args = get_launch_args()
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(5)
                file_logger.log("Chrome запущен", "INFO")
                return True
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    async def _message_reader(self):
        """Читает сообщения из WebSocket в отдельной корутине"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                await self._message_queue.put(data)
        except websockets.exceptions.ConnectionClosed:
            file_logger.log("WebSocket соединение закрыто", "WARNING")
        except Exception as e:
            file_logger.log(f"Ошибка в reader: {e}", "ERROR")
    
    async def _process_messages(self):
        """Обрабатывает сообщения из очереди"""
        while True:
            try:
                data = await self._message_queue.get()
                
                # Если есть id - это ответ на запрос
                if "id" in data:
                    msg_id = data["id"]
                    if msg_id in self._pending_requests:
                        self._pending_requests[msg_id] = data
                
                # Если это событие
                elif "method" in data:
                    if data["method"] == "Page.loadEventFired":
                        file_logger.log("✅ Событие Page.loadEventFired получено", "INFO")
                        self.load_event.set()
                    elif data["method"].startswith("Page."):
                        file_logger.log(f"📡 Событие: {data['method']}", "DEBUG")
                        
            except Exception as e:
                file_logger.log(f"Ошибка обработки сообщения: {e}", "ERROR")
    
    async def connect(self):
        if not self.ensure_browser():
            raise Exception("Chrome не доступен")
        
        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version")
        ws_url = resp.json()["webSocketDebuggerUrl"]
        
        self.ws = await websockets.connect(ws_url, max_size=15 * 1024 * 1024)
        file_logger.log("Подключен к браузеру", "INFO")
        
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        self.target_id = result["result"]["targetId"]
        
        attach_result = await self.send("Target.attachToTarget", {
            "targetId": self.target_id,
            "flatten": True
        })
        self.session_id = attach_result["result"]["sessionId"]
        file_logger.log("Прикреплен к вкладке", "INFO")
        
        await self.send("Page.enable", session_id=self.session_id)
        await self.send("Runtime.enable", session_id=self.session_id)
        await self.send("Network.enable", session_id=self.session_id)
        
        # Запускаем reader и processor
        self.load_event.clear()
        self._pending_requests = {}
        asyncio.create_task(self._message_reader())
        asyncio.create_task(self._process_messages())
        
        if self.cookies:
            await self.set_cookies_global(self.cookies)
        
        await self.send("Page.navigate", {"url": "https://x.com"}, session_id=self.session_id)
        await asyncio.sleep(2)
        
        await self.apply_full_mask()
    
    async def set_cookies_global(self, cookies):
        try:
            cookies_list = []
            for cookie in cookies:
                cookies_list.append({
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": ".x.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": "Lax"
                })
            
            await self.send("Network.setCookies", {
                "cookies": cookies_list
            }, session_id=self.session_id)
            file_logger.log(f"✅ Установлено {len(cookies)} кук", "INFO")
        except Exception as e:
            file_logger.log(f"Ошибка установки кук: {e}", "ERROR")
    
    async def apply_full_mask(self):
        try:
            mask_script = """
                (function() {
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                        configurable: true,
                        enumerable: true
                    });
                    
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            function Plugin(name, filename, description) {
                                this.name = name;
                                this.filename = filename;
                                this.description = description;
                            }
                            Plugin.prototype.item = function(index) {
                                return this[index] || null;
                            };
                            Plugin.prototype.namedItem = function(name) {
                                return this[name] || null;
                            };
                            
                            const plugins = new Array();
                            Object.setPrototypeOf(plugins, Plugin.prototype);
                            
                            plugins.push(new Plugin(
                                'Chrome PDF Plugin',
                                'internal-pdf-viewer',
                                'Portable Document Format'
                            ));
                            plugins.push(new Plugin(
                                'Chrome PDF Viewer',
                                'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                                ''
                            ));
                            plugins.push(new Plugin(
                                'Native Client',
                                'internal-nacl-plugin',
                                ''
                            ));
                            
                            plugins.length = 3;
                            return plugins;
                        },
                        configurable: true,
                        enumerable: true
                    });
                    
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                        configurable: true,
                        enumerable: true
                    });
                    
                    console.log('✅ Маскировка применена');
                })();
            """
            
            await self.send("Runtime.evaluate", {
                "expression": mask_script
            }, session_id=self.session_id)
            
            file_logger.log("Маскировка применена", "INFO")
            
        except Exception as e:
            file_logger.log(f"Ошибка маскировки: {e}", "ERROR")
    
    async def send(self, method, params=None, session_id=None, timeout=30):
        """Отправка CDP команды и ожидание ответа"""
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        if session_id:
            msg["sessionId"] = session_id
        
        await self.ws.send(json.dumps(msg))
        
        # Ждём ответ с этим id
        start_time = time.time()
        while time.time() - start_time < timeout:
            if msg_id in self._pending_requests:
                data = self._pending_requests.pop(msg_id)
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown CDP error")
                    error_code = data["error"].get("code", 0)
                    raise Exception(f"CDP Error [{error_code}]: {error_msg}")
                return data
            await asyncio.sleep(0.05)
        
        raise Exception(f"Таймаут ожидания ответа на {method}")
    
    async def navigate_and_wait(self, url, timeout=30):
        """Навигация с ожиданием Page.loadEventFired"""
        self.load_event.clear()
        
        await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        
        try:
            await asyncio.wait_for(self.load_event.wait(), timeout=timeout)
            file_logger.log("✅ Страница загружена (Page.loadEventFired)", "INFO")
            await asyncio.sleep(2)
            return True
        except asyncio.TimeoutError:
            file_logger.log(f"⏰ Таймаут ожидания загрузки страницы ({timeout}с)", "WARNING")
            return False
    
    async def get_full_snapshot(self, max_depth=4):
        """Получает полный snapshot DOM-дерева"""
        try:
            result = await self.send("Runtime.evaluate", {
                "expression": f"""
                    (function() {{
                        const maxDepth = {max_depth};
                        
                        function getNodeTree(node, depth) {{
                            if (depth > maxDepth) return {{ tag: '...' }};
                            if (!node || node.nodeType === 8) return null;
                            
                            const data = {{
                                tag: node.tagName ? node.tagName.toLowerCase() : 'text',
                                type: node.nodeType
                            }};
                            
                            if (node.nodeType === 3) {{
                                data.text = node.textContent.trim().slice(0, 100);
                                return data;
                            }}
                            
                            if (node.attributes) {{
                                data.attrs = {{}};
                                for (let attr of node.attributes) {{
                                    if (['id', 'class', 'data-testid', 'role', 'href', 'src', 'type', 'name', 'placeholder', 'aria-label'].includes(attr.name)) {{
                                        data.attrs[attr.name] = attr.value;
                                    }}
                                }}
                            }}
                            
                            if (node.children && node.children.length > 0) {{
                                const textNodes = [];
                                for (let child of node.children) {{
                                    if (child.nodeType === 3) {{
                                        const text = child.textContent.trim();
                                        if (text) textNodes.push(text);
                                    }}
                                }}
                                if (textNodes.length > 0) {{
                                    data.text = textNodes.join(' ').slice(0, 200);
                                }}
                            }}
                            
                            if (node.children && node.children.length > 0) {{
                                data.children = [];
                                for (let child of node.children) {{
                                    const childData = getNodeTree(child, depth + 1);
                                    if (childData) data.children.push(childData);
                                }}
                                if (data.children.length === 0) delete data.children;
                            }}
                            
                            return data;
                        }}
                        
                        const snapshot = getNodeTree(document, 0);
                        return JSON.stringify(snapshot);
                    }})();
                """
            }, session_id=self.session_id, timeout=30)
            
            snapshot = result.get("result", {}).get("value", "{}")
            file_logger.log(f"📸 Snapshot получен: {len(snapshot)} символов", "INFO")
            
            try:
                data = json.loads(snapshot)
                if data.get('children'):
                    file_logger.log(f"📊 В snapshot {len(data['children'])} элементов", "INFO")
                else:
                    file_logger.log("⚠️ Snapshot пустой", "WARNING")
            except:
                pass
            
            self.snapshot_history.append(snapshot)
            return snapshot
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка получения snapshot: {e}", "ERROR")
            return "{}"
    
    async def click(self, selector, timeout=10):
        file_logger.log(f"🖱️ Клик на {selector}", "INFO")
        
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                new Promise((resolve) => {{
                    const start = Date.now();
                    const check = () => {{
                        const el = document.querySelector('{selector}');
                        if (el) {{
                            resolve(true);
                        }} else if (Date.now() - start > {timeout * 1000}) {{
                            resolve(false);
                        }} else {{
                            setTimeout(check, 100);
                        }}
                    }};
                    check();
                }});
            """
        }, session_id=self.session_id)
        
        if result.get("result", {}).get("value") != True:
            file_logger.log(f"❌ Элемент {selector} не найден", "WARNING")
            return False
        
        await self.send("Runtime.evaluate", {
            "expression": f"document.querySelector('{selector}').click();",
            "userGesture": True
        }, session_id=self.session_id)
        
        self.action_history.append({"action": "click", "selector": selector, "success": True})
        file_logger.log(f"✅ Клик на {selector} выполнен", "INFO")
        return True
    
    async def type_text(self, selector, text, timeout=10):
        file_logger.log(f"⌨️ Ввод текста в {selector}", "INFO")
        
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                new Promise((resolve) => {{
                    const start = Date.now();
                    const check = () => {{
                        const el = document.querySelector('{selector}');
                        if (el) {{
                            resolve(true);
                        }} else if (Date.now() - start > {timeout * 1000}) {{
                            resolve(false);
                        }} else {{
                            setTimeout(check, 100);
                        }}
                    }};
                    check();
                }});
            """
        }, session_id=self.session_id)
        
        if result.get("result", {}).get("value") != True:
            file_logger.log(f"❌ Элемент {selector} не найден", "WARNING")
            return False
        
        escaped_text = text.replace("'", "\\'").replace('"', '\\"')
        await self.send("Runtime.evaluate", {
            "expression": f"""
                const el = document.querySelector('{selector}');
                el.value = '{escaped_text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """
        }, session_id=self.session_id)
        
        self.action_history.append({"action": "type", "selector": selector, "text": text, "success": True})
        file_logger.log(f"✅ Текст введён в {selector}", "INFO")
        return True
    
    async def screenshot(self):
        result = await self.send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 80
        }, session_id=self.session_id)
        
        return base64.b64decode(result["result"]["data"])
    
    async def close(self):
        if self._listener_task:
            self._listener_task.cancel()
        try:
            await self.send("Target.closeTarget", {"targetId": self.target_id})
        except:
            pass
        await self.ws.close()
        self.agent_active = False

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    file_logger.log(f"Пользователь {user} запустил бота", "INFO")
    
    await update.message.reply_text(
        "🤖 **AI-агент для автоматизации браузера**\n\n"
        "Просто напиши что нужно сделать:\n"
        "• `/agent https://x.com найди пост про AI`\n"
        "• `/agent https://x.com напиши пост Привет`\n"
        "• `/agent зайди на https://x.com`\n\n"
        "📁 `/log` — получить логи\n"
        "🔍 `/status` — статус агента\n"
        "⏹️ `/end` — завершить сессию"
    )

async def handle_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи URL и задачу:\n"
            "/agent https://x.com найди пост про AI"
        )
        return
    
    url = None
    task_parts = []
    
    for arg in context.args:
        if arg.startswith(('http://', 'https://')):
            url = arg
        elif '.' in arg and ' ' not in arg and len(arg) > 3 and not arg.startswith('/'):
            url = 'https://' + arg
        else:
            task_parts.append(arg)
    
    if not url:
        full_text = " ".join(context.args)
        url_match = re.search(r'(https?://[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*)', full_text)
        if url_match:
            url = url_match.group(1)
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            task_parts = full_text.replace(url_match.group(0), '').strip().split()
    
    if not url:
        await update.message.reply_text(
            "❌ Не найден URL.\n"
            "Примеры:\n"
            "/agent https://x.com найди пост\n"
            "/agent зайди на https://x.com"
        )
        return
    
    task = " ".join(task_parts) if task_parts else "проанализируй страницу"
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запустил агента: {url} - {task}", "INFO")
    
    await update.message.reply_text(f"🤖 Запускаю агента на {url}...\n📝 Задача: {task}")
    
    try:
        browser = BrowserCDP()
        await browser.connect()
        
        browser.agent_active = True
        browser.current_task = task
        browser.current_url = url
        browser.action_history = []
        
        # Навигация с ожиданием
        loaded = await browser.navigate_and_wait(url, timeout=45)
        
        if not loaded:
            file_logger.log("⚠️ Страница не загрузилась", "WARNING")
        
        # Получаем snapshot
        snapshot = await browser.get_full_snapshot(max_depth=4)
        
        # Отправляем в AI
        ai = AgnesAI()
        prompt = f"""
        Задача: {task}
        URL: {url}
        
        Вот полная структура страницы (snapshot DOM-дерева):
        {snapshot if snapshot else "{}"}
        
        Проанализируй структуру и скажи, что мне сделать, чтобы выполнить задачу.
        """
        
        ai_response = await ai.ask(prompt, snapshot if snapshot else "{}")
        
        results = []
        max_actions = 5
        
        for step in range(max_actions):
            if ai_response.get("action") == "error":
                results.append(f"❌ Ошибка: {ai_response.get('reason')}")
                break
            
            if ai_response.get("action") == "done":
                results.append(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
                break
            
            if ai_response.get("action") == "wait":
                results.append("⏳ Ожидание 3 секунды...")
                await asyncio.sleep(3)
                snapshot = await browser.get_full_snapshot(max_depth=4)
                ai_response = await ai.ask(
                    f"Задача: {task}\n\nСтраница после ожидания:\n{snapshot}\n\nЧто дальше?",
                    snapshot
                )
                continue
            
            action = ai_response.get("action")
            selector = ai_response.get("selector")
            text = ai_response.get("text", "")
            reason = ai_response.get("reason", "")
            
            file_logger.log(f"Шаг {step+1}: {action} на {selector} ({reason})", "INFO")
            
            if action == "click":
                success = await browser.click(selector)
                results.append(f"🖱️ Клик на {selector} - {'✅' if success else '❌'}")
            elif action == "type":
                success = await browser.type_text(selector, text)
                results.append(f"⌨️ Ввод '{text}' - {'✅' if success else '❌'}")
            elif action == "scroll":
                await browser.send("Runtime.evaluate", {
                    "expression": "window.scrollTo(0, document.body.scrollHeight);"
                }, session_id=browser.session_id)
                results.append("📜 Скролл вниз - ✅")
            else:
                results.append(f"❌ Неизвестное действие: {action}")
                break
            
            await asyncio.sleep(2)
            
            snapshot = await browser.get_full_snapshot(max_depth=4)
            history_text = "\n".join([f"- {h.get('action')} на {h.get('selector', '')}" for h in browser.action_history[-3:]])
            
            ai_response = await ai.ask(
                f"Задача: {task}\n\nЯ выполнил: {action} на {selector}\nРезультат: {success}\n\nИстория:\n{history_text}\n\nОбновлённый snapshot:\n{snapshot}\n\nЧто дальше?",
                snapshot,
                browser.action_history
            )
        
        context.user_data['agent_session'] = {
            'browser': browser,
            'url': url,
            'task': task,
            'active': True,
            'user_id': user_id
        }
        
        screenshot = await browser.screenshot()
        
        caption = f"🤖 **Задача выполнена!**\n📍 {url}\n📝 {task}\n\n📋 **Действия:**\n" + "\n".join(results)
        
        await update.message.reply_photo(screenshot, caption=caption[:1024])
        file_logger.log(f"Агент завершил задачу для {user}", "INFO")
        
        await update.message.reply_text(
            "💡 Теперь ты можешь просто писать команды, и агент продолжит работу:\n"
            "• Нажми на кнопку Обзор\n"
            "• Напиши привет\n"
            "• Сделай скриншот\n"
            "• Какие кнопки видишь?\n\n"
            "⏹️ /end — завершить сессию"
        )
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка агента для {user}: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not context.user_data.get('agent_session'):
        if text.startswith(('http://', 'https://')) or '.' in text:
            context.args = text.split()
            await handle_agent(update, context)
            return
        else:
            await update.message.reply_text(
                "🤖 Нет активной сессии.\n"
                "Начни с команды:\n"
                "/agent https://x.com задача"
            )
            return
    
    session = context.user_data['agent_session']
    browser = session['browser']
    
    if not session.get('active', False):
        await update.message.reply_text("❌ Сессия не активна. Начни заново: /agent")
        return
    
    if session.get('user_id') != user_id:
        await update.message.reply_text("❌ У тебя нет активной сессии. Начни заново: /agent")
        return
    
    if any(word in text.lower() for word in ['какие кнопки', 'кнопки видишь', 'что видишь', 'что на странице', 'есть ли']):
        snapshot = await browser.get_full_snapshot(max_depth=4)
        try:
            data = json.loads(snapshot)
            response = "🔍 **Что я вижу на странице:**\n\n"
            
            buttons = []
            inputs = []
            
            def find_elements(node, depth=0):
                if depth > 5 or not node:
                    return
                
                if isinstance(node, dict):
                    if node.get('tag') in ['button', 'a'] and node.get('attrs', {}).get('role') == 'button':
                        text = node.get('text', '')[:30]
                        if text:
                            buttons.append({'text': text, 'selector': node.get('attrs', {}).get('data-testid')})
                    elif node.get('tag') in ['input', 'textarea']:
                        placeholder = node.get('attrs', {}).get('placeholder', '') or node.get('attrs', {}).get('aria-label', '')
                        if placeholder:
                            inputs.append({'placeholder': placeholder[:30], 'selector': node.get('attrs', {}).get('data-testid')})
                    
                    if node.get('children'):
                        for child in node['children']:
                            find_elements(child, depth + 1)
            
            find_elements(data)
            
            if buttons:
                response += "🖱️ **Кнопки:**\n"
                for i, btn in enumerate(buttons[:15], 1):
                    response += f"  {i}. {btn['text']} → `{btn['selector'] or 'не найден'}`\n"
            else:
                response += "❌ Кнопки не найдены\n"
            
            if inputs:
                response += "\n⌨️ **Поля ввода:**\n"
                for inp in inputs[:10]:
                    response += f"  • {inp['placeholder']} → `{inp['selector'] or 'не найден'}`\n"
            
            await update.message.reply_text(response[:4000])
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа: {e}")
            return
    
    file_logger.log(f"Продолжение сессии для {user}: {text}", "INFO")
    
    try:
        snapshot = await browser.get_full_snapshot(max_depth=4)
        
        ai = AgnesAI()
        prompt = f"""
        Ты уже на странице {session['url']}
        Задача: {session['task']}
        История: {browser.action_history[-3:]}
        
        Пользователь говорит: {text}
        
        Что мне сделать? Ответь в формате JSON.
        """
        
        ai_response = await ai.ask(prompt, snapshot, browser.action_history)
        
        if ai_response.get("action") == "error":
            await update.message.reply_text(f"❌ Ошибка: {ai_response.get('reason')}")
            return
        
        if ai_response.get("action") == "done":
            await update.message.reply_text(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
            screenshot = await browser.screenshot()
            await update.message.reply_photo(screenshot, caption="📸 Финальный скриншот")
            session['active'] = False
            return
        
        action = ai_response.get("action")
        selector = ai_response.get("selector")
        text = ai_response.get("text", "")
        
        if action == "click":
            success = await browser.click(selector)
            await update.message.reply_text(f"🖱️ Клик на {selector} - {'✅' if success else '❌'}")
        elif action == "type":
            success = await browser.type_text(selector, text)
            await update.message.reply_text(f"⌨️ Ввод '{text}' - {'✅' if success else '❌'}")
        elif action == "wait":
            await asyncio.sleep(3)
            await update.message.reply_text("⏳ Ожидание 3 сек - ✅")
        else:
            await update.message.reply_text(f"❌ Неизвестное действие: {action}")
            return
        
        screenshot = await browser.screenshot()
        await update.message.reply_photo(screenshot, caption=f"📸 После действия")
        
        next_response = await ai.ask(
            f"Задача: {session['task']}\n\nЧто дальше?",
            await browser.get_full_snapshot(max_depth=4)
        )
        
        if next_response.get("action") == "done":
            await update.message.reply_text(f"✅ {next_response.get('reason', 'Задача выполнена!')}")
            session['active'] = False
        else:
            await update.message.reply_text("💡 Продолжаю. Напиши что дальше.")
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('agent_session') and context.user_data['agent_session'].get('active', False):
        session = context.user_data['agent_session']
        if session.get('user_id') != user_id:
            await update.message.reply_text("🤖 Нет активной сессии")
            return
        
        browser = session['browser']
        await update.message.reply_text(
            f"🤖 **Активная сессия:**\n"
            f"📍 {session['url']}\n"
            f"📝 {session['task']}\n"
            f"📊 Действий: {len(browser.action_history)}\n\n"
            f"⏹️ /end — завершить"
        )
    else:
        await update.message.reply_text("🤖 Нет активной сессии.\n/agent https://x.com задача")

async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.user_data.get('agent_session'):
        await update.message.reply_text("🤖 Нет активной сессии")
        return
    
    session = context.user_data['agent_session']
    if session.get('user_id') != user_id:
        await update.message.reply_text("⛔ Не твоя сессия")
        return
    
    browser = session.get('browser')
    if browser:
        try:
            await browser.close()
        except:
            pass
    
    context.user_data['agent_session'] = None
    await update.message.reply_text("✅ **Сессия завершена!**")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Логов нет")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(document=f, filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- ЗАПУСК ----------
def main():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("end", end_session))
    app.add_handler(CommandHandler("agent", handle_agent))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    print("🤖 AI-агент: /agent https://x.com задача")
    print("📁 Логи: /log")
    print("🔍 Статус: /status")
    print("⏹️ /end - завершить")
    
    app.run_polling()

if __name__ == "__main__":
    main()