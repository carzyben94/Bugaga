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
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- КОНФИГ ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222

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

# ---------- БРАУЗЕР (АСИНХРОННЫЙ) ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.session_id = None
        self.target_id = None
        self.webgl_vendor = get_random_webgl_vendor()
        self.webgl_renderer = get_random_webgl_renderer()
        self.cookies = COOKIES
    
    def ensure_browser(self):
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("Запускаю Chrome с полной маскировкой...", "INFO")
            try:
                args = get_launch_args()
                
                subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "LANG": "en_US.UTF-8"}
                )
                time.sleep(5)
                file_logger.log("Chrome запущен успешно", "INFO")
                return True
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    async def connect(self):
        if not self.ensure_browser():
            raise Exception("Chrome не доступен")
        
        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version")
        ws_url = resp.json()["webSocketDebuggerUrl"]
        
        self.ws = await websockets.connect(
            ws_url,
            max_size=15 * 1024 * 1024
        )
        file_logger.log("Подключен к браузеру (лимит 15MB)", "INFO")
        
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
            
            file_logger.log(f"✅ Установлено {len(cookies)} кук глобально", "INFO")
        except Exception as e:
            file_logger.log(f"Ошибка при установке кук: {e}", "ERROR")
    
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
                    
                    console.log('✅ 100% маскировка применена');
                }})();
            """
            
            await self.send("Runtime.evaluate", {
                "expression": mask_script
            }, session_id=self.session_id)
            
            file_logger.log("100% маскировка применена", "INFO")
            
        except Exception as e:
            file_logger.log(f"Ошибка при маскировке: {e}", "ERROR")
    
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
    
    # ========== НОВЫЕ МЕТОДЫ ДЛЯ ДЕЙСТВИЙ НА САЙТЕ ==========
    
    async def click(self, selector, timeout=10):
        """Кликает на элемент по CSS-селектору"""
        file_logger.log(f"Клик на {selector}", "INFO")
        
        # Ждём появления элемента
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
        
        # Кликаем
        await self.send("Runtime.evaluate", {
            "expression": f"document.querySelector('{selector}').click();"
        }, session_id=self.session_id)
        
        file_logger.log(f"Клик на {selector} выполнен", "INFO")
        return True
    
    async def type_text(self, selector, text, timeout=10):
        """Вводит текст в поле по CSS-селектору"""
        file_logger.log(f"Ввод текста в {selector}", "INFO")
        
        # Ждём появления элемента
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
        
        # Вводим текст
        escaped_text = text.replace("'", "\\'").replace('"', '\\"')
        await self.send("Runtime.evaluate", {
            "expression": f"""
                const el = document.querySelector('{selector}');
                el.value = '{escaped_text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            """
        }, session_id=self.session_id)
        
        file_logger.log(f"Текст введён в {selector}", "INFO")
        return True
    
    async def get_text(self, selector, timeout=10):
        """Получает текст элемента по CSS-селектору"""
        file_logger.log(f"Получение текста из {selector}", "INFO")
        
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const start = Date.now();
                    while (Date.now() - start < {timeout * 1000}) {{
                        const el = document.querySelector('{selector}');
                        if (el) {{
                            return el.innerText || el.textContent || '';
                        }}
                        // Ждём 100ms
                        const end = Date.now() + 100;
                        while (Date.now() < end) {{}}
                    }}
                    return null;
                }})();
            """
        }, session_id=self.session_id)
        
        text = result.get("result", {}).get("value")
        if text:
            file_logger.log(f"Текст получен: {text[:50]}...", "INFO")
        else:
            file_logger.log(f"Элемент {selector} не найден", "WARNING")
        
        return text
    
    async def scroll_to(self, selector=None, position="bottom"):
        """Скроллит страницу"""
        if selector:
            # Скролл к элементу
            await self.send("Runtime.evaluate", {
                "expression": f"""
                    const el = document.querySelector('{selector}');
                    if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                """
            }, session_id=self.session_id)
            file_logger.log(f"Скролл к {selector}", "INFO")
        else:
            # Скролл вниз или вверх
            if position == "bottom":
                await self.send("Runtime.evaluate", {
                    "expression": "window.scrollTo(0, document.body.scrollHeight);"
                }, session_id=self.session_id)
            else:
                await self.send("Runtime.evaluate", {
                    "expression": "window.scrollTo(0, 0);"
                }, session_id=self.session_id)
            file_logger.log(f"Скролл {position}", "INFO")
    
    async def wait_for_element(self, selector, timeout=10):
        """Ожидает появления элемента"""
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
        
        found = result.get("result", {}).get("value") == True
        if found:
            file_logger.log(f"Элемент {selector} найден", "INFO")
        else:
            file_logger.log(f"Элемент {selector} не найден за {timeout}с", "WARNING")
        
        return found
    
    async def navigate_and_screenshot(self, url):
        """Навигация и создание скриншота с возможностью действий"""
        file_logger.log(f"Навигация на {url}", "INFO")
        await self.connect()
        
        # Устанавливаем разрешение
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "mobile": False,
            "scale": 1
        }, session_id=self.session_id)
        file_logger.log("Установлено разрешение: 1280x720", "INFO")
        
        # Переходим на целевой URL
        if "x.com" not in url and "twitter.com" not in url:
            await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
            file_logger.log("Навигация на целевой URL", "INFO")
        else:
            file_logger.log("Уже на X.com", "INFO")
        
        # Ждём загрузку
        await asyncio.sleep(5)
        
        # Делаем скриншот
        file_logger.log("Делаю скриншот...", "INFO")
        screenshot_data = None
        
        for attempt in range(3):
            try:
                result = await self.send("Page.captureScreenshot", {
                    "format": "jpeg",
                    "quality": 80
                }, session_id=self.session_id)
                
                if "result" in result and "data" in result["result"]:
                    screenshot_data = result["result"]["data"]
                    file_logger.log(f"Скриншот создан (JPEG, 1280x720)", "INFO")
                    break
            except Exception as e:
                file_logger.log(f"Попытка {attempt+1} не удалась: {e}", "WARNING")
                await asyncio.sleep(1)
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот")
        
        try:
            await self.send("Target.closeTarget", {"targetId": self.target_id})
        except:
            pass
        
        await self.ws.close()
        
        return base64.b64decode(screenshot_data)

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запустил бота", "INFO")
    
    await update.message.reply_text(
        "📁 /log — получить файл логов\n\n"
        "🔧 Бот умеет:\n"
        "• Делать скриншоты (отправь URL)\n"
        "• Кликать на элементы\n"
        "• Вводить текст\n"
        "• Парсить данные"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запросил: {url}", "INFO")
    
    if not url.startswith(('http://', 'https://')):
        file_logger.log(f"Неверный URL от {user}: {url}", "WARNING")
        await update.message.reply_text("❌ Добавь http:// или https://")
        return
    
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        browser = BrowserCDP()
        screenshot = await browser.navigate_and_screenshot(url)
        await update.message.reply_photo(screenshot, caption=f"✅ {url}")
        file_logger.log(f"Скриншот отправлен пользователю {user}", "INFO")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка для {user} ({url}): {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

# ========== НОВЫЕ КОМАНДЫ ДЛЯ ДЕЙСТВИЙ ==========

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для клика по селектору: /click selector"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /click button#submit")
        return
    
    selector = " ".join(context.args)
    file_logger.log(f"Пользователь {user} (ID: {user_id}) кликает на {selector}", "INFO")
    
    await update.message.reply_text(f"🔄 Кликаю на {selector}...")
    
    try:
        browser = BrowserCDP()
        await browser.connect()
        result = await browser.click(selector)
        await browser.ws.close()
        
        if result:
            await update.message.reply_text(f"✅ Клик на {selector} выполнен")
        else:
            await update.message.reply_text(f"❌ Элемент {selector} не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для ввода текста: /type selector текст"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажи селектор и текст: /type input#name Привет")
        return
    
    selector = context.args[0]
    text = " ".join(context.args[1:])
    file_logger.log(f"Пользователь {user} (ID: {user_id}) вводит '{text}' в {selector}", "INFO")
    
    await update.message.reply_text(f"🔄 Ввожу текст в {selector}...")
    
    try:
        browser = BrowserCDP()
        await browser.connect()
        result = await browser.type_text(selector, text)
        await browser.ws.close()
        
        if result:
            await update.message.reply_text(f"✅ Текст введён в {selector}")
        else:
            await update.message.reply_text(f"❌ Элемент {selector} не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения текста: /get selector"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /get article")
        return
    
    selector = " ".join(context.args)
    file_logger.log(f"Пользователь {user} (ID: {user_id}) получает текст из {selector}", "INFO")
    
    await update.message.reply_text(f"🔄 Получаю текст из {selector}...")
    
    try:
        browser = BrowserCDP()
        await browser.connect()
        text = await browser.get_text(selector)
        await browser.ws.close()
        
        if text:
            await update.message.reply_text(f"📝 Текст:\n{text[:1000]}")
        else:
            await update.message.reply_text(f"❌ Элемент {selector} не найден или пуст")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запросил лог-файл", "INFO")
    
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Файл логов ещё не создан")
            return
        
        file_size = os.path.getsize(LOG_FILE)
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(f"⚠️ Файл слишком большой ({file_size // 1024 // 1024}MB)")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt",
                caption=f"📋 Логи бота за {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        file_logger.log(f"Лог-файл отправлен пользователю {user}", "INFO")
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка при отправке лога {user}: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

# ---------- ЗАПУСК ----------
def main():
    file_logger.log("="*50, "INFO")
    file_logger.log("БОТ ЗАПУЩЕН (С DOM-ДЕЙСТВИЯМИ)", "INFO")
    file_logger.log(f"Chrome путь: {CHROME_PATH}", "INFO")
    file_logger.log(f"CDP порт: {CDP_PORT}", "INFO")
    file_logger.log("WebSocket лимит: 15 MB", "INFO")
    file_logger.log(f"Загружено кук: {len(COOKIES)}", "INFO")
    file_logger.log("Разрешение скриншотов: 1280x720", "INFO")
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        file_logger.log("TELEGRAM_BOT_TOKEN не указан!", "ERROR")
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(CommandHandler("click", click_command))
    app.add_handler(CommandHandler("type", type_command))
    app.add_handler(CommandHandler("get", get_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("🚀 Бот запущен!")
    print("📁 Команды:")
    print("  /start - меню")
    print("  /log - получить логи")
    print("  /click selector - кликнуть на элемент")
    print("  /type selector текст - ввести текст")
    print("  /get selector - получить текст")
    print("  URL - сделать скриншот")
    print(f"🍪 Куки: {len(COOKIES)} (X.com)")
    
    app.run_polling()

if __name__ == "__main__":
    main()