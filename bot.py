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
                    "content": """Ты - AI-агент для автоматизации браузера. Ты видишь структуру страницы и принимаешь решения.

Правила:
1. Отвечай ТОЛЬКО в формате JSON
2. Если не знаешь что делать - ответь {"action": "done", "reason": "объясни"}
3. Для кнопок используй data-testid если есть, иначе text или class

Формат ответа:
{"action": "click|type|scroll|wait|get|done", "selector": "css_selector", "text": "текст", "reason": "почему"}

Примеры:
{"action": "click", "selector": "[data-testid='tweetButton']", "reason": "Нажать кнопку Написать"}
{"action": "type", "selector": "[data-testid='tweetTextarea_0']", "text": "Привет мир!", "reason": "Написать текст поста"}
{"action": "done", "reason": "Задача выполнена"}"""
                }
            ]
            
            if history:
                for h in history[-5:]:
                    messages.append({"role": "assistant", "content": json.dumps(h)})
            
            if context:
                messages.append({
                    "role": "user",
                    "content": f"Структура страницы:\n{context}\n\nЗадача: {prompt}"
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
                file_logger.log(f"Ошибка AI API: {response.status_code} - {response.text}", "ERROR")
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
            canvas_fingerprint = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]
            webgl_fingerprint = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]
            
            mask_script = f"""
                (function() {{
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined,
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'plugins', {{
                        get: () => {{
                            function Plugin(name, filename, description) {{
                                this.name = name;
                                this.filename = filename;
                                this.description = description;
                            }}
                            Plugin.prototype.item = function(index) {{
                                return this[index] || null;
                            }};
                            Plugin.prototype.namedItem = function(name) {{
                                return this[name] || null;
                            }};
                            
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
                        }},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'languages', {{
                        get: () => ['en-US', 'en', 'ru'],
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'platform', {{
                        get: () => 'Win32',
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => {random.randint(4, 16)},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'deviceMemory', {{
                        get: () => {random.choice([4, 8, 16, 32])},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'userAgentData', {{
                        get: () => {{
                            return {{
                                brands: [
                                    {{ brand: 'Google Chrome', version: '{random.randint(118, 120)}' }},
                                    {{ brand: 'Chromium', version: '{random.randint(118, 120)}' }},
                                    {{ brand: 'Not?A_Brand', version: '99' }}
                                ],
                                platform: 'Windows',
                                mobile: false,
                                getHighEntropyValues: function(hints) {{
                                    return Promise.resolve({{
                                        architecture: 'x86',
                                        bitness: '64',
                                        model: '',
                                        platform: 'Windows',
                                        platformVersion: '10.0',
                                        uaFullVersion: '{random.randint(118, 120)}.0.0.0'
                                    }});
                                }},
                                toJSON: function() {{
                                    return {{
                                        brands: [
                                            {{ brand: 'Google Chrome', version: '{random.randint(118, 120)}' }},
                                            {{ brand: 'Chromium', version: '{random.randint(118, 120)}' }}
                                        ],
                                        platform: 'Windows',
                                        mobile: false
                                    }};
                                }}
                            }};
                        }},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(navigator, 'connection', {{
                        get: () => {{
                            return {{
                                rtt: {random.randint(20, 100)},
                                downlink: {round(random.uniform(5, 20), 1)},
                                effectiveType: '{random.choice(['4g', '3g'])}',
                                saveData: false,
                                type: '{random.choice(['wifi', 'ethernet'])}'
                            }};
                        }},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = function(parameters) {{
                        const permissions = {{
                            'geolocation': 'prompt',
                            'notifications': Notification.permission,
                            'midi': 'prompt',
                            'camera': 'prompt',
                            'microphone': 'prompt',
                            'background-fetch': 'prompt',
                            'background-sync': 'granted',
                            'periodic-background-sync': 'prompt',
                            'persistent-storage': 'prompt',
                            'push': Notification.permission,
                            'speaker-selection': 'prompt'
                        }};
                        return Promise.resolve({{
                            state: permissions[parameters.name] || 'prompt',
                            onchange: null
                        }});
                    }};
                    
                    const originalGetContext = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(contextId, attributes) {{
                        if (contextId === 'webgl' || contextId === 'experimental-webgl') {{
                            const context = originalGetContext.call(this, contextId, attributes);
                            if (context) {{
                                const originalGetParameter = context.getParameter;
                                context.getParameter = function(parameter) {{
                                    if (parameter === 0x1F00) {{
                                        return '{self.webgl_vendor}';
                                    }}
                                    if (parameter === 0x1F01) {{
                                        return '{self.webgl_renderer}';
                                    }}
                                    if (parameter === 0x1F02) {{
                                        return 'WebGL 2.0 (OpenGL ES 3.0)';
                                    }}
                                    if (parameter === 0x8B8C) {{
                                        return 'WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0)';
                                    }}
                                    return originalGetParameter.call(this, parameter);
                                }};
                                
                                const originalGetExtension = context.getExtension;
                                context.getExtension = function(name) {{
                                    const ext = originalGetExtension.call(this, name);
                                    if (ext && name === 'WEBGL_debug_renderer_info') {{
                                        Object.defineProperty(ext, 'UNMASKED_VENDOR_WEBGL', {{
                                            get: () => 0x9245,
                                            configurable: true,
                                            enumerable: true
                                        }});
                                        Object.defineProperty(ext, 'UNMASKED_RENDERER_WEBGL', {{
                                            get: () => 0x9246,
                                            configurable: true,
                                            enumerable: true
                                        }});
                                    }}
                                    return ext;
                                }};
                            }}
                            return context;
                        }}
                        return originalGetContext.call(this, contextId, attributes);
                    }};
                    
                    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
                        if (type === 'image/png' || type === undefined) {{
                            const ctx = this.getContext('2d');
                            const imageData = ctx.getImageData(0, 0, this.width, this.height);
                            const data = imageData.data;
                            
                            const noise = {random.randint(0, 2)};
                            if (noise > 0 && data.length > 100) {{
                                const idx = Math.floor(Math.random() * (data.length - 4));
                                data[idx] = Math.min(255, data[idx] + (Math.random() > 0.5 ? 1 : -1));
                                ctx.putImageData(imageData, 0, 0);
                            }}
                        }}
                        return originalToDataURL.call(this, type, quality);
                    }};
                    
                    const originalAudioCtx = window.AudioContext || window.webkitAudioContext;
                    if (originalAudioCtx) {{
                        const patchedAudioCtx = function() {{
                            const ctx = new originalAudioCtx();
                            const originalGetChannelData = ctx.createBuffer;
                            ctx.createBuffer = function(numChannels, length, sampleRate) {{
                                const buffer = originalGetChannelData.call(this, numChannels, length, sampleRate);
                                for (let i = 0; i < numChannels; i++) {{
                                    const channelData = buffer.getChannelData(i);
                                    for (let j = 0; j < channelData.length; j += 10) {{
                                        channelData[j] += (Math.random() - 0.5) * 0.0001;
                                    }}
                                }}
                                return buffer;
                            }};
                            return ctx;
                        }};
                        patchedAudioCtx.prototype = originalAudioCtx.prototype;
                        window.AudioContext = patchedAudioCtx;
                        window.webkitAudioContext = patchedAudioCtx;
                    }}
                    
                    Object.defineProperty(window, 'screen', {{
                        get: () => {{
                            const availHeight = {random.randint(800, 1080)};
                            const height = availHeight + {random.randint(40, 60)};
                            const availWidth = {random.randint(1200, 1920)};
                            const width = availWidth;
                            return {{
                                width: width,
                                height: height,
                                availWidth: availWidth,
                                availHeight: availHeight,
                                colorDepth: 24,
                                pixelDepth: 24,
                                availLeft: 0,
                                availTop: 0,
                                left: 0,
                                top: 0,
                                orientation: {{
                                    type: 'landscape-primary',
                                    angle: 0
                                }}
                            }};
                        }},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    if (!window.chrome) {{
                        window.chrome = {{}};
                    }}
                    window.chrome.runtime = {{}};
                    window.chrome.loadTimes = function() {{}};
                    window.chrome.csi = function() {{}};
                    window.chrome.app = {{}};
                    
                    const originalPerfNow = performance.now;
                    performance.now = function() {{
                        return originalPerfNow.call(this) + (Math.random() * 0.1);
                    }};
                    
                    const originalDateNow = Date.now;
                    Date.now = function() {{
                        return originalDateNow.call(this) + Math.floor(Math.random() * 5);
                    }};
                    
                    Object.defineProperty(document, 'hidden', {{
                        get: () => false,
                        configurable: true,
                        enumerable: true
                    }});
                    
                    Object.defineProperty(document, 'visibilityState', {{
                        get: () => 'visible',
                        configurable: true,
                        enumerable: true
                    }});
                    
                    window._pydoll_session = {{
                        id: '{hashlib.md5(str(time.time()).encode()).hexdigest()[:16]}',
                        fingerprint: '{canvas_fingerprint}',
                        webgl: '{webgl_fingerprint}'
                    }};
                    
                    console.log('✅ Маскировка применена');
                }})();
            """
            
            await self.send("Runtime.evaluate", {
                "expression": mask_script
            }, session_id=self.session_id)
            
            file_logger.log("Маскировка применена", "INFO")
            
        except Exception as e:
            file_logger.log(f"Ошибка маскировки: {e}", "ERROR")
    
    async def send(self, method, params=None, session_id=None):
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        if session_id:
            msg["sessionId"] = session_id
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            response = await self.ws.recv()
            data = json.loads(response)
            
            if data.get("id") == self.msg_id:
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown CDP error")
                    error_code = data["error"].get("code", 0)
                    raise Exception(f"CDP Error [{error_code}]: {error_msg}")
                return data
    
    async def navigate(self, url):
        """Переход на URL с полным ожиданием загрузки DOM"""
        await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        
        file_logger.log(f"Ожидание загрузки страницы: {url}", "INFO")
        
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": """
                        (function() {
                            if (document.readyState !== 'complete') return false;
                            if (!document.body) return false;
                            if (document.body.children.length === 0) return false;
                            return true;
                        })();
                    """
                }, session_id=self.session_id)
                
                if result.get("result", {}).get("value") == True:
                    file_logger.log("✅ DOM полностью загружен", "INFO")
                    await asyncio.sleep(2)
                    
                    content_check = await self.send("Runtime.evaluate", {
                        "expression": """
                            document.body.innerText.length > 100 || 
                            document.querySelectorAll('button, input, a').length > 0
                        """
                    }, session_id=self.session_id)
                    
                    if content_check.get("result", {}).get("value") == True:
                        file_logger.log("✅ Контент загружен", "INFO")
                        return True
                    else:
                        file_logger.log("⏳ Контент ещё не загружен, ждём...", "INFO")
                        await asyncio.sleep(1)
                        continue
                        
            except Exception as e:
                file_logger.log(f"Ошибка проверки загрузки: {e}", "WARNING")
            
            await asyncio.sleep(0.5)
        
        file_logger.log("⚠️ Таймаут загрузки страницы", "WARNING")
        return False
    
    async def click(self, selector, timeout=10):
        file_logger.log(f"Клик на {selector}", "INFO")
        
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
            file_logger.log(f"Элемент {selector} не найден", "WARNING")
            return False
        
        await self.send("Runtime.evaluate", {
            "expression": f"document.querySelector('{selector}').click();"
        }, session_id=self.session_id)
        
        self.action_history.append({"action": "click", "selector": selector, "success": True})
        return True
    
    async def type_text(self, selector, text, timeout=10):
        file_logger.log(f"Ввод текста в {selector}", "INFO")
        
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
            file_logger.log(f"Элемент {selector} не найден", "WARNING")
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
        return True
    
    async def get_page_context(self):
        """Получает контекст страницы с ожиданием DOM"""
        
        for attempt in range(5):
            try:
                check = await self.send("Runtime.evaluate", {
                    "expression": """
                        (function() {
                            if (document.readyState !== 'complete') return 'loading';
                            if (!document.body) return 'no_body';
                            if (document.body.children.length === 0) return 'empty';
                            return 'ready';
                        })();
                    """
                }, session_id=self.session_id)
                
                status = check.get("result", {}).get("value", "")
                
                if status == 'ready':
                    file_logger.log("✅ DOM готов для сбора контекста", "INFO")
                    break
                elif status == 'loading':
                    file_logger.log(f"⏳ Страница загружается... (попытка {attempt+1})", "INFO")
                    await asyncio.sleep(2)
                    continue
                elif status == 'empty':
                    file_logger.log(f"⏳ DOM пустой, ждём контент... (попытка {attempt+1})", "INFO")
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                file_logger.log(f"Ошибка проверки DOM: {e}", "WARNING")
                await asyncio.sleep(1)
        
        try:
            result = await self.send("Runtime.evaluate", {
                "expression": """
                    (function() {
                        function getSelector(el) {
                            if (el.id) return '#' + el.id;
                            if (el.getAttribute('data-testid')) {
                                return `[data-testid="${el.getAttribute('data-testid')}"]`;
                            }
                            if (el.className && typeof el.className === 'string') {
                                const classes = el.className.split(' ').filter(c => c && c.length > 0);
                                if (classes.length > 0) return '.' + classes.join('.');
                            }
                            return el.tagName.toLowerCase();
                        }
                        
                        const data = {
                            title: document.title || 'No title',
                            url: window.location.href || 'No URL',
                            buttons: [],
                            inputs: [],
                            links: [],
                            text: ''
                        };
                        
                        document.querySelectorAll('button, [role="button"], [data-testid*="button"]').forEach(el => {
                            const text = el.innerText || el.textContent || el.getAttribute('aria-label') || '';
                            if (text.trim()) {
                                data.buttons.push({
                                    text: text.trim().slice(0, 50),
                                    selector: getSelector(el)
                                });
                            }
                        });
                        
                        document.querySelectorAll('input, textarea, [contenteditable="true"]').forEach(el => {
                            const placeholder = el.placeholder || el.getAttribute('aria-label') || '';
                            if (placeholder) {
                                data.inputs.push({
                                    placeholder: placeholder.slice(0, 50),
                                    selector: getSelector(el)
                                });
                            }
                        });
                        
                        document.querySelectorAll('a[href]').forEach(el => {
                            const text = el.innerText || el.textContent || '';
                            if (text.trim() && el.href) {
                                data.links.push({
                                    text: text.trim().slice(0, 30),
                                    href: el.href
                                });
                            }
                        });
                        
                        const bodyText = document.body.innerText || '';
                        data.text = bodyText.slice(0, 1000);
                        data.total_elements = document.querySelectorAll('*').length;
                        
                        return JSON.stringify(data);
                    })();
                """
            }, session_id=self.session_id)
            
            context = result.get("result", {}).get("value", "{}")
            
            try:
                parsed = json.loads(context)
                total = parsed.get('total_elements', 0)
                buttons = len(parsed.get('buttons', []))
                inputs = len(parsed.get('inputs', []))
                
                file_logger.log(f"📊 Контекст: {total} элементов, {buttons} кнопок, {inputs} полей", "INFO")
                
                if total > 10:
                    return context
                else:
                    file_logger.log("⚠️ Мало элементов на странице", "WARNING")
                    return context
                    
            except Exception as e:
                file_logger.log(f"Ошибка парсинга контекста: {e}", "WARNING")
                
        except Exception as e:
            file_logger.log(f"Ошибка получения контекста: {e}", "ERROR")
        
        return json.dumps({
            "title": "Страница загружается...",
            "url": "unknown",
            "buttons": [],
            "inputs": [],
            "links": [],
            "text": "Страница ещё не загружена. Попробуйте позже.",
            "total_elements": 0
        })
    
    async def screenshot(self):
        result = await self.send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 80
        }, session_id=self.session_id)
        
        return base64.b64decode(result["result"]["data"])
    
    async def close(self):
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
        
        await browser.navigate(url)
        
        file_logger.log("Ожидание полной загрузки страницы...", "INFO")
        await asyncio.sleep(5)
        
        context_data = await browser.get_page_context()
        file_logger.log(f"Контекст получен", "INFO")
        
        ai = AgnesAI()
        ai_response = await ai.ask(task, context_data)
        
        results = []
        max_actions = 5
        
        for step in range(max_actions):
            if ai_response.get("action") == "error":
                results.append(f"❌ Ошибка: {ai_response.get('reason')}")
                break
            
            if ai_response.get("action") == "done":
                results.append(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
                break
            
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
            elif action == "wait":
                await asyncio.sleep(3)
                results.append(f"⏳ Ожидание 3 сек - ✅")
            elif action == "scroll":
                results.append(f"📜 Скролл - ✅")
            else:
                results.append(f"❌ Неизвестное действие: {action}")
                break
            
            await asyncio.sleep(2)
            
            context_data = await browser.get_page_context()
            history_text = "\n".join([f"- {h.get('action')} на {h.get('selector', '')}" for h in browser.action_history[-3:]])
            ai_response = await ai.ask(
                f"Задача: {task}\n\nЯ выполнил: {action} на {selector}\nРезультат: {success}\n\nИстория действий:\n{history_text}\n\nЧто дальше?",
                context_data,
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
    
    # Проверяем специальные вопросы про кнопки
    if any(word in text.lower() for word in ['какие кнопки', 'кнопки видишь', 'что видишь', 'что на странице', 'есть ли']):
        context_data = await browser.get_page_context()
        try:
            data = json.loads(context_data)
            response = "🔍 **Что я вижу на странице:**\n\n"
            
            if data.get('buttons'):
                response += "🖱️ **Кнопки:**\n"
                for i, btn in enumerate(data['buttons'][:20], 1):
                    response += f"  {i}. {btn['text']} → `{btn['selector']}`\n"
                if len(data['buttons']) > 20:
                    response += f"  ... и ещё {len(data['buttons']) - 20} кнопок\n"
            else:
                response += "❌ Кнопки не найдены\n"
            
            if data.get('inputs'):
                response += "\n⌨️ **Поля ввода:**\n"
                for inp in data['inputs'][:10]:
                    response += f"  • {inp['placeholder']} → `{inp['selector']}`\n"
            
            if data.get('links'):
                response += "\n🔗 **Ссылки:**\n"
                for link in data['links'][:5]:
                    response += f"  • {link['text']} → {link['href']}\n"
            
            if data.get('text'):
                response += f"\n📝 **Текст:**\n{data['text'][:300]}..."
            
            await update.message.reply_text(response[:4000])
            return
        except:
            pass
    
    file_logger.log(f"Продолжение сессии агента для {user}: {text}", "INFO")
    
    try:
        context_data = await browser.get_page_context()
        
        ai = AgnesAI()
        prompt = f"""
        Ты уже на странице {session['url']}
        Задача: {session['task']}
        История действий: {browser.action_history[-3:]}
        
        Пользователь говорит: {text}
        
        Что мне сделать?
        Ответь в формате JSON.
        """
        
        ai_response = await ai.ask(prompt, context_data, browser.action_history)
        
        if ai_response.get("action") == "error":
            await update.message.reply_text(f"❌ Ошибка AI: {ai_response.get('reason')}")
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
        reason = ai_response.get("reason", "")
        
        file_logger.log(f"Продолжение: {action} на {selector} ({reason})", "INFO")
        
        if action == "click":
            success = await browser.click(selector)
            await update.message.reply_text(f"🖱️ Клик на {selector} - {'✅' if success else '❌'}")
        elif action == "type":
            success = await browser.type_text(selector, text)
            await update.message.reply_text(f"⌨️ Ввод '{text}' - {'✅' if success else '❌'}")
        elif action == "wait":
            await asyncio.sleep(3)
            await update.message.reply_text(f"⏳ Ожидание 3 сек - ✅")
        elif action == "scroll":
            await update.message.reply_text(f"📜 Скролл - ✅")
        else:
            await update.message.reply_text(f"❌ Неизвестное действие: {action}")
            return
        
        screenshot = await browser.screenshot()
        await update.message.reply_photo(screenshot, caption=f"📸 После действия: {action}")
        
        context_data = await browser.get_page_context()
        next_prompt = f"""
        Я выполнил: {action} на {selector}
        Результат: {success}
        Задача: {session['task']}
        
        Что дальше?
        """
        
        next_response = await ai.ask(next_prompt, context_data, browser.action_history)
        
        if next_response.get("action") == "done":
            await update.message.reply_text(f"✅ {next_response.get('reason', 'Задача выполнена!')}")
            screenshot = await browser.screenshot()
            await update.message.reply_photo(screenshot, caption="📸 Финальный скриншот")
            session['active'] = False
        else:
            await update.message.reply_text(
                f"💡 Продолжаю работу. Просто напиши что дальше.\n"
                f"📝 Текущая задача: {session['task']}\n\n"
                f"💡 Спроси: какие кнопки видишь?\n"
                f"⏹️ /end — завершить сессию"
            )
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка продолжения сессии для {user}: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}\n💡 Сессия завершена. Начни заново: /agent")
        session['active'] = False

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('agent_session') and context.user_data['agent_session'].get('active', False):
        session = context.user_data['agent_session']
        
        if session.get('user_id') != user_id:
            await update.message.reply_text("🤖 Нет активной сессии для тебя.")
            return
        
        browser = session['browser']
        await update.message.reply_text(
            f"🤖 **Активная сессия:**\n"
            f"📍 {session['url']}\n"
            f"📝 {session['task']}\n"
            f"📊 Действий выполнено: {len(browser.action_history)}\n\n"
            f"💡 Просто напиши что сделать дальше!\n"
            f"💡 Спроси: какие кнопки видишь?\n"
            f"⏹️ /end — завершить сессию"
        )
    else:
        await update.message.reply_text(
            "🤖 Нет активной сессии.\n"
            "Начни с команды:\n"
            "/agent https://x.com задача"
        )

async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.user_data.get('agent_session'):
        await update.message.reply_text("🤖 Нет активной сессии для завершения")
        return
    
    session = context.user_data['agent_session']
    
    if session.get('user_id') != user_id:
        await update.message.reply_text("⛔ У тебя нет активной сессии для завершения.")
        return
    
    browser = session.get('browser')
    
    if browser:
        try:
            await browser.close()
        except:
            pass
    
    context.user_data['agent_session'] = None
    file_logger.log(f"Пользователь {user} завершил сессию", "INFO")
    
    await update.message.reply_text(
        "✅ **Сессия завершена!**\n\n"
        "Чтобы начать новую:\n"
        "/agent https://x.com задача"
    )

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Логов нет")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt"
            )
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
    print("⏹️ Завершить сессию: /end")
    print("💡 Спроси у агента: какие кнопки видишь?")
    
    app.run_polling()

if __name__ == "__main__":
    main()