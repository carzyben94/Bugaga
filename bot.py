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

# ---------- МАСКИРОВКА (100% Pydoll style) ----------
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
    """Генерирует реалистичный WebGL vendor"""
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
    """Генерирует реалистичный WebGL renderer"""
    renderers = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ]
    return random.choice(renderers)

def get_launch_args():
    """Возвращает аргументы запуска Chrome с полной маскировкой"""
    window = get_random_window_position()
    
    args = [
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        
        # Отключение автоматизации
        "--disable-blink-features=AutomationControlled",
        "--disable-automation",
        
        # GPU эмуляция (не отключаем!)
        "--use-gl=egl",  # Вместо swiftshader, для лучшей эмуляции
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        
        # Отключаем только проблемные фичи
        "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        
        # Безопасность и скрытие
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
        
        # Настройки окна
        f"--window-position={window['left']},{window['top']}",
        f"--window-size={window['width']},{window['height']}",
        
        # Дополнительно
        "--no-default-browser-check",
        "--no-first-run",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--password-store=basic",
        "--use-mock-keychain",
        "--export-tagged-pdf",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        
        # User-Agent подмена
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
        
        self.ws = await websockets.connect(ws_url)
        file_logger.log("Подключен к браузеру", "INFO")
        
        # Создаём новую вкладку
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        self.target_id = result["result"]["targetId"]
        
        # Прикрепляемся к вкладке
        attach_result = await self.send("Target.attachToTarget", {
            "targetId": self.target_id,
            "flatten": True
        })
        self.session_id = attach_result["result"]["sessionId"]
        file_logger.log("Прикреплен к вкладке", "INFO")
        
        # Активируем домены
        await self.send("Page.enable", session_id=self.session_id)
        await self.send("Runtime.enable", session_id=self.session_id)
        await self.send("Network.enable", session_id=self.session_id)
        
        # 100% маскировка
        await self.apply_full_mask()
    
    async def apply_full_mask(self):
        """100% маскировка в стиле Pydoll"""
        try:
            # Генерируем случайные отпечатки
            canvas_fingerprint = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]
            webgl_fingerprint = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]
            
            mask_script = f"""
                (function() {{
                    // ============================================
                    // 1. БАЗОВАЯ МАСКИРОВКА
                    // ============================================
                    
                    // Скрываем webdriver (основной флаг)
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined,
                        configurable: true,
                        enumerable: true
                    }});
                    
                    // ============================================
                    // 2. ПОДМЕНА NAVIGATOR
                    // ============================================
                    
                    // Подмена plugins с реальными объектами
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
                    
                    // Подмена languages
                    Object.defineProperty(navigator, 'languages', {{
                        get: () => ['en-US', 'en', 'ru'],
                        configurable: true,
                        enumerable: true
                    }});
                    
                    // Подмена platform
                    Object.defineProperty(navigator, 'platform', {{
                        get: () => 'Win32',
                        configurable: true,
                        enumerable: true
                    }});
                    
                    // Подмена hardwareConcurrency
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => {random.randint(4, 16)},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    // Подмена deviceMemory
                    Object.defineProperty(navigator, 'deviceMemory', {{
                        get: () => {random.choice([4, 8, 16, 32])},
                        configurable: true,
                        enumerable: true
                    }});
                    
                    // Подмена userAgentData
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
                    
                    // Подмена connection
                    Object.defineProperty(navigator, 'connection', {{
                        get: () => {{
                            const types = ['4g', '3g', '2g'];
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
                    
                    // Подмена permissions
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
                    
                    // ============================================
                    // 3. ПОДМЕНА WEBGL (ключевая часть!)
                    // ============================================
                    
                    // Подменяем WebGL контекст
                    const originalGetContext = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(contextId, attributes) {{
                        if (contextId === 'webgl' || contextId === 'experimental-webgl') {{
                            const context = originalGetContext.call(this, contextId, attributes);
                            if (context) {{
                                // Подмена getParameter для WebGL
                                const originalGetParameter = context.getParameter;
                                context.getParameter = function(parameter) {{
                                    const vendor = context.getParameter(0x1F00);
                                    const renderer = context.getParameter(0x1F01);
                                    
                                    // Подмена vendor
                                    if (parameter === 0x1F00) {{
                                        return '{self.webgl_vendor}';
                                    }}
                                    // Подмена renderer
                                    if (parameter === 0x1F01) {{
                                        return '{self.webgl_renderer}';
                                    }}
                                    // Подмена версии
                                    if (parameter === 0x1F02) {{
                                        return 'WebGL 2.0 (OpenGL ES 3.0)';
                                    }}
                                    // Подмена shading language
                                    if (parameter === 0x8B8C) {{
                                        return 'WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0)';
                                    }}
                                    return originalGetParameter.call(this, parameter);
                                }};
                                
                                // Подмена getExtension для WebGL
                                const originalGetExtension = context.getExtension;
                                context.getExtension = function(name) {{
                                    const ext = originalGetExtension.call(this, name);
                                    if (ext && name === 'WEBGL_debug_renderer_info') {{
                                        // Подмена UNMASKED_VENDOR_WEBGL и UNMASKED_RENDERER_WEBGL
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
                    
                    // ============================================
                    // 4. ПОДМЕНА CANVAS (отпечаток)
                    // ============================================
                    
                    // Добавляем небольшой шум в Canvas
                    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
                        if (type === 'image/png' || type === undefined) {{
                            const ctx = this.getContext('2d');
                            const imageData = ctx.getImageData(0, 0, this.width, this.height);
                            const data = imageData.data;
                            
                            // Добавляем небольшой случайный шум
                            const noise = {random.randint(0, 2)};
                            if (noise > 0 && data.length > 100) {{
                                const idx = Math.floor(Math.random() * (data.length - 4));
                                data[idx] = Math.min(255, data[idx] + (Math.random() > 0.5 ? 1 : -1));
                                ctx.putImageData(imageData, 0, 0);
                            }}
                        }}
                        return originalToDataURL.call(this, type, quality);
                    }};
                    
                    // ============================================
                    // 5. ПОДМЕНА AUDIO
                    // ============================================
                    
                    // Подмена AudioContext
                    const originalAudioCtx = window.AudioContext || window.webkitAudioContext;
                    if (originalAudioCtx) {{
                        const patchedAudioCtx = function() {{
                            const ctx = new originalAudioCtx();
                            const originalGetChannelData = ctx.createBuffer;
                            ctx.createBuffer = function(numChannels, length, sampleRate) {{
                                const buffer = originalGetChannelData.call(this, numChannels, length, sampleRate);
                                // Добавляем небольшой шум в аудиоотпечаток
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
                    
                    // ============================================
                    // 6. ПОДМЕНА SCREEN
                    // ============================================
                    
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
                    
                    // ============================================
                    // 7. СКРЫТИЕ CHROME
                    // ============================================
                    
                    // Скрываем chrome.runtime
                    if (!window.chrome) {{
                        window.chrome = {{}};
                    }}
                    window.chrome.runtime = {{}};
                    window.chrome.loadTimes = function() {{}};
                    window.chrome.csi = function() {{}};
                    window.chrome.app = {{}};
                    
                    // ============================================
                    // 8. ПОДМЕНА ТАЙМИНГОВ
                    // ============================================
                    
                    // Подмена performance.now()
                    const originalPerfNow = performance.now;
                    performance.now = function() {{
                        return originalPerfNow.call(this) + (Math.random() * 0.1);
                    }};
                    
                    // Подмена Date.now()
                    const originalDateNow = Date.now;
                    Date.now = function() {{
                        return originalDateNow.call(this) + Math.floor(Math.random() * 5);
                    }};
                    
                    // ============================================
                    // 9. ПОДМЕНА DOCUMENT
                    // ============================================
                    
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
                    
                    // ============================================
                    // 10. УНИКАЛЬНЫЙ ОТПЕЧАТОК
                    // ============================================
                    
                    // Добавляем уникальный идентификатор сессии
                    window._pydoll_session = {{
                        id: '{hashlib.md5(str(time.time()).encode()).hexdigest()[:16]}',
                        fingerprint: '{canvas_fingerprint}',
                        webgl: '{webgl_fingerprint}'
                    }};
                    
                    console.log('✅ 100% маскировка применена (Pydoll full stealth)');
                }})();
            """
            
            await self.send("Runtime.evaluate", {
                "expression": mask_script
            }, session_id=self.session_id)
            
            file_logger.log("100% маскировка применена", "INFO")
            file_logger.log(f"WebGL Vendor: {self.webgl_vendor}", "DEBUG")
            file_logger.log(f"WebGL Renderer: {self.webgl_renderer}", "DEBUG")
            
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
    
    async def wait_for_page_load(self, timeout=30):
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState === 'complete'"
                }, session_id=self.session_id)
                
                if result.get("result", {}).get("result", {}).get("value") == True:
                    file_logger.log("Страница загружена", "INFO")
                    return True
                    
            except Exception as e:
                file_logger.log(f"Ошибка при проверке загрузки: {e}", "DEBUG")
            
            await asyncio.sleep(0.5)
        
        file_logger.log("Таймаут ожидания загрузки страницы", "WARNING")
        return False
    
    async def navigate_and_screenshot(self, url):
        file_logger.log(f"Навигация на {url}", "INFO")
        await self.connect()
        
        await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        file_logger.log("Навигация инициирована", "INFO")
        
        loaded = await self.wait_for_page_load(timeout=30)
        
        if not loaded:
            await asyncio.sleep(2)
        
        screenshot_data = None
        for attempt in range(3):
            try:
                result = await self.send("Page.captureScreenshot", {
                    "format": "png",
                    "captureBeyondViewport": True
                }, session_id=self.session_id)
                
                if "result" in result and "data" in result["result"]:
                    screenshot_data = result["result"]["data"]
                    file_logger.log(f"Скриншот создан для {url}", "INFO")
                    break
            except Exception as e:
                file_logger.log(f"Попытка {attempt+1} скриншота не удалась: {e}", "WARNING")
                await asyncio.sleep(1)
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот после 3 попыток")
        
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
        "👋 Отправь URL и я сделаю скриншот\n"
        "Пример: https://google.com\n\n"
        "📁 /log — получить файл логов\n"
        "🕵️ 100% маскировка (Pydoll full stealth)"
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
    
    await update.message.reply_text(f"🔄 Загружаю {url} (full stealth)...")
    
    try:
        browser = BrowserCDP()
        screenshot = await browser.navigate_and_screenshot(url)
        await update.message.reply_photo(screenshot, caption=f"✅ {url}")
        file_logger.log(f"Скриншот отправлен пользователю {user}", "INFO")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка для {user} ({url}): {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

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
    file_logger.log("БОТ ЗАПУЩЕН (100% STEALTH MODE)", "INFO")
    file_logger.log(f"Chrome путь: {CHROME_PATH}", "INFO")
    file_logger.log(f"CDP порт: {CDP_PORT}", "INFO")
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        file_logger.log("TELEGRAM_BOT_TOKEN не указан!", "ERROR")
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("🚀 Бот запущен в 100% STEALTH режиме!")
    print("🕵️ Полная маскировка: WebGL, Canvas, Audio, Navigator, Screen, Timing")
    print("📁 Команды: /start, /log")
    
    app.run_polling()

if __name__ == "__main__":
    main()