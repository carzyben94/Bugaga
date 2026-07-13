import os
import json
import time
import subprocess
import base64
import requests
import asyncio
import websockets
import random
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# ---------- КОНФИГ ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222
WEBSOCKET_MAX_SIZE = 20 * 1024 * 1024
PAGE_LOAD_TIMEOUT = 20
MAX_HISTORY = 20

# ---------- AI КОНФИГ ----------
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

# ---------- ЛОГИРОВАНИЕ ----------
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
        print(f"[{timestamp}] [{level}] {message}")

file_logger = FileLogger()

# ---------- ПАМЯТЬ ----------
class Memory:
    def __init__(self, max_items=MAX_HISTORY):
        self.max_items = max_items
        self.history = []
        self.current_snapshot = None
        self.current_url = None
        self.current_title = None
        self.last_action = None
        self.browser = None  # ← Сохраняем браузер
    
    def add_action(self, action_type, data=None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "data": data
        }
        self.history.append(entry)
        self.last_action = entry
        
        if len(self.history) > self.max_items:
            self.history = self.history[-self.max_items:]
        
        file_logger.log(f"📝 Добавлено в память: {action_type}", "DEBUG")
    
    def set_snapshot(self, snapshot, url, title, browser=None):
        self.current_snapshot = snapshot
        self.current_url = url
        self.current_title = title
        if browser:
            self.browser = browser
        self.add_action("snapshot", {"url": url, "title": title, "elements": len(snapshot.get('elements', []))})
    
    def get_last_url(self, index=0):
        snapshots = [a for a in self.history if a['type'] == 'snapshot']
        if snapshots and len(snapshots) > index:
            return snapshots[-(index + 1)].get('data', {}).get('url')
        return None
    
    def get_context_for_ai(self):
        context = []
        
        if self.current_title:
            context.append(f"Текущая страница: {self.current_title} ({self.current_url})")
        
        if self.current_snapshot and self.current_snapshot.get('elements'):
            elements = self.current_snapshot.get('elements', [])[:30]
            if elements:
                context.append("\nСтруктура страницы:")
                for el in elements[:15]:
                    tag = el.get('tag', 'unknown')
                    text = el.get('text', '').strip()[:50]
                    if text:
                        context.append(f"- <{tag}>: {text}")
                    elif el.get('id'):
                        context.append(f"- <{tag}>: id={el['id']}")
                    else:
                        context.append(f"- <{tag}>")
        
        if self.history:
            context.append("\nПоследние действия:")
            for action in self.history[-5:]:
                action_type = action.get('type', 'unknown')
                timestamp = action.get('timestamp', '')[:16]
                if action_type == 'snapshot':
                    url = action.get('data', {}).get('url', '')
                    context.append(f"- {timestamp}: Переход на {url[:50]}")
                elif action_type == 'question':
                    question = action.get('data', {}).get('question', '')
                    context.append(f"- {timestamp}: Вопрос: {question[:50]}")
                elif action_type == 'click':
                    target = action.get('data', {}).get('target', '')
                    context.append(f"- {timestamp}: Клик по {target}")
                elif action_type == 'type':
                    text = action.get('data', {}).get('text', '')
                    field = action.get('data', {}).get('field', '')
                    context.append(f"- {timestamp}: Ввод '{text}' в {field}")
        
        return "\n".join(context)
    
    def get_history_text(self):
        if not self.history:
            return "📭 История пуста"
        
        lines = []
        for i, action in enumerate(self.history, 1):
            timestamp = action.get('timestamp', '')[:16]
            action_type = action.get('type', 'unknown')
            data = action.get('data', {})
            
            if action_type == 'snapshot':
                lines.append(f"{i}. 🔗 [{timestamp}] {data.get('title', '')} ({data.get('url', '')})")
            elif action_type == 'question':
                lines.append(f"{i}. ❓ [{timestamp}] {data.get('question', '')}")
            elif action_type == 'screenshot':
                lines.append(f"{i}. 📸 [{timestamp}] Скриншот")
            elif action_type == 'click':
                lines.append(f"{i}. 🔘 [{timestamp}] Клик по {data.get('target', '')}")
            elif action_type == 'type':
                lines.append(f"{i}. ✏️ [{timestamp}] Ввод '{data.get('text', '')}' в {data.get('field', '')}")
            else:
                lines.append(f"{i}. ⚡ [{timestamp}] {action_type}")
        
        return "\n".join(lines)

# ---------- ПАРСЕР КОМАНД ----------
def parse_command(text):
    """Распознает команды на естественном языке"""
    text_lower = text.lower().strip()
    
    # ====== URL напрямую ======
    if text.startswith(('http://', 'https://')):
        return {'action': 'navigate', 'url': text}
    
    # ====== НАВИГАЦИЯ ======
    nav_patterns = [
        (r'зайди на\s+(.+)', 'зайди на'),
        (r'зайди\s+(.+)', 'зайди'),
        (r'открой\s+(.+)', 'открой'),
        (r'перейди на\s+(.+)', 'перейди на'),
        (r'перейди\s+(.+)', 'перейди'),
        (r'покажи\s+(.+)', 'покажи'),
        (r'открой сайт\s+(.+)', 'открой сайт'),
        (r'сходи на\s+(.+)', 'сходи на'),
        (r'дай\s+(.+)', 'дай'),
    ]
    
    for pattern, _ in nav_patterns:
        match = re.search(pattern, text_lower)
        if match:
            url = match.group(1).strip()
            if not url.startswith(('http://', 'https://')):
                url = url.split()[0] if ' ' in url else url
                url = 'https://' + url
            return {'action': 'navigate', 'url': url}
    
    # ====== КЛИК ======
    click_patterns = [
        r'нажми\s+на\s+(.+)',
        r'кликни\s+на\s+(.+)',
        r'нажми\s+(.+)',
        r'кликни\s+(.+)',
        r'тапни\s+(.+)',
        r'нажать\s+(.+)',
    ]
    for pattern in click_patterns:
        match = re.search(pattern, text_lower)
        if match:
            target = match.group(1).strip()
            return {'action': 'click', 'target': target}
    
    # ====== ВВОД ТЕКСТА ======
    type_patterns = [
        r'введи\s+["\']?(.+?)["\']?\s+в\s+(.+)',
        r'напиши\s+["\']?(.+?)["\']?\s+в\s+(.+)',
        r'вставь\s+["\']?(.+?)["\']?\s+в\s+(.+)',
        r'напечатай\s+["\']?(.+?)["\']?\s+в\s+(.+)',
        r'ввести\s+["\']?(.+?)["\']?\s+в\s+(.+)',
    ]
    for pattern in type_patterns:
        match = re.search(pattern, text_lower)
        if match:
            text_input = match.group(1).strip()
            field = match.group(2).strip()
            return {'action': 'type', 'text': text_input, 'field': field}
    
    # ====== ОТПРАВКА ФОРМЫ ======
    submit_keywords = ['отправь форму', 'сабмит', 'отправить', 'submit', 'войти', 'залогиниться']
    if any(keyword in text_lower for keyword in submit_keywords):
        return {'action': 'submit'}
    
    # ====== ВОЗВРАТ НАЗАД ======
    if any(word in text_lower for word in ['назад', 'вернись', 'вернуться', 'предыдущий']):
        return {'action': 'back'}
    
    # ====== СКРИНШОТ ======
    screenshot_keywords = ['скриншот', 'скрин', 'фото', 'сфоткай', 'сделай скрин', 'сними']
    if any(keyword in text_lower for keyword in screenshot_keywords):
        return {'action': 'screenshot'}
    
    # ====== ВОПРОСЫ ======
    question_keywords = [
        'какие', 'что', 'есть ли', 'где', 'когда', 'почему', 'сколько',
        'какой', 'какая', 'какое', 'покажи', 'найди', 'расскажи', 'опиши',
        'поля', 'формы', 'инпуты', 'элементы', 'кнопки', 'ссылки', 'меню',
        'картинки', 'видео', 'заголовки'
    ]
    
    if any(keyword in text_lower for keyword in question_keywords) or '?' in text:
        return {'action': 'ask', 'question': text}
    
    # ====== ИСТОРИЯ ======
    history_keywords = ['история', 'что было', 'помнишь', 'список', 'действия']
    if any(keyword in text_lower for keyword in history_keywords):
        return {'action': 'history'}
    
    # ====== ОЧИСТКА ======
    clear_keywords = ['очисти', 'забудь', 'сбрось', 'удали']
    if any(keyword in text_lower for keyword in clear_keywords):
        return {'action': 'clear'}
    
    # ====== ПРИВЕТСТВИЕ ======
    if any(word in text_lower for word in ['привет', 'здравствуй', 'hello', 'hi']):
        return {'action': 'greeting'}
    
    return {'action': 'unknown'}

# ---------- AI ФУНКЦИИ ----------
def ask_ai(prompt, context=None, memory=None):
    """Запрос к Agnes AI с памятью"""
    try:
        if not AGNES_API_KEY:
            return "❌ AGNES_API_KEY не указан. Получите ключ на https://platform.agnes-ai.com/"
        
        messages = []
        
        system_prompt = "Ты - умный AI-ассистент для анализа веб-страниц. Отвечай кратко, понятно и по делу."
        
        if memory:
            memory_context = memory.get_context_for_ai()
            if memory_context:
                system_prompt += f"\n\nКонтекст из памяти:\n{memory_context}"
        
        messages.append({"role": "system", "content": system_prompt})
        
        if context:
            messages.append({"role": "user", "content": f"Контекст страницы:\n{context}"})
        
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": AI_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 800
        }
        
        file_logger.log(f"🤖 Отправляю запрос к Agnes AI...", "INFO")
        
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
            file_logger.log(f"✅ AI ответил ({len(answer)} символов)", "INFO")
            return answer
        elif response.status_code == 401:
            return "❌ Ошибка: неверный API ключ"
        elif response.status_code == 429:
            return "❌ Превышен лимит запросов. Подождите минуту"
        else:
            return f"❌ Ошибка: HTTP {response.status_code}"
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка запроса к AI: {e}", "ERROR")
        return f"❌ Ошибка: {e}"

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
    user_agent = get_random_user_agent()
    
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
        f"--user-agent={user_agent}",
        f"--remote-debugging-port={CDP_PORT}"
    ]
    
    return args

def get_mask_js():
    webgl_vendor = get_random_webgl_vendor()
    webgl_renderer = get_random_webgl_renderer()
    chrome_version = random.randint(118, 120)
    cpu_cores = random.randint(4, 16)
    memory_gb = random.choice([4, 8, 16, 32])
    rtt = random.randint(20, 100)
    downlink = round(random.uniform(5, 20), 1)
    connection_type = random.choice(['4g', '3g'])
    network_type = random.choice(['wifi', 'ethernet'])
    screen_height = random.randint(800, 1080)
    screen_width = random.randint(1200, 1920)
    noise = random.randint(0, 2)
    extra_height = random.randint(40, 60)
    
    return f"""
    (function() {{
        // ========== NAVIGATOR ==========
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
                
                plugins.push(new Plugin('Chrome PDF Plugin', 'internal-pdf-viewer', 'Portable Document Format'));
                plugins.push(new Plugin('Chrome PDF Viewer', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', ''));
                plugins.push(new Plugin('Native Client', 'internal-nacl-plugin', ''));
                
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
            get: () => {cpu_cores},
            configurable: true,
            enumerable: true
        }});
        
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {memory_gb},
            configurable: true,
            enumerable: true
        }});
        
        Object.defineProperty(navigator, 'userAgentData', {{
            get: () => {{
                return {{
                    brands: [
                        {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                        {{ brand: 'Chromium', version: '{chrome_version}' }},
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
                            uaFullVersion: '{chrome_version}.0.0.0'
                        }});
                    }},
                    toJSON: function() {{
                        return {{
                            brands: [
                                {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                                {{ brand: 'Chromium', version: '{chrome_version}' }}
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
                    rtt: {rtt},
                    downlink: {downlink},
                    effectiveType: '{connection_type}',
                    saveData: false,
                    type: '{network_type}'
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
        
        // ========== WEBGL ==========
        const originalGetContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(contextId, attributes) {{
            if (contextId === 'webgl' || contextId === 'experimental-webgl') {{
                const context = originalGetContext.call(this, contextId, attributes);
                if (context) {{
                    const originalGetParameter = context.getParameter;
                    context.getParameter = function(parameter) {{
                        if (parameter === 0x1F00) return '{webgl_vendor}';
                        if (parameter === 0x1F01) return '{webgl_renderer}';
                        if (parameter === 0x1F02) return 'WebGL 2.0 (OpenGL ES 3.0)';
                        if (parameter === 0x8B8C) return 'WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0)';
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
        
        // ========== CANVAS ==========
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
            if (type === 'image/png' || type === undefined) {{
                const ctx = this.getContext('2d');
                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                const data = imageData.data;
                const noise = {noise};
                if (noise > 0 && data.length > 100) {{
                    const idx = Math.floor(Math.random() * (data.length - 4));
                    data[idx] = Math.min(255, data[idx] + (Math.random() > 0.5 ? 1 : -1));
                    ctx.putImageData(imageData, 0, 0);
                }}
            }}
            return originalToDataURL.call(this, type, quality);
        }};
        
        // ========== AUDIO ==========
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
        
        // ========== SCREEN ==========
        Object.defineProperty(window, 'screen', {{
            get: () => {{
                const availHeight = {screen_height};
                const height = availHeight + {extra_height};
                const availWidth = {screen_width};
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
        
        // ========== CHROME ==========
        if (!window.chrome) {{
            window.chrome = {{}};
        }}
        window.chrome.runtime = {{}};
        window.chrome.loadTimes = function() {{}};
        window.chrome.csi = function() {{}};
        window.chrome.app = {{}};
        
        // ========== TIMING ==========
        const originalPerfNow = performance.now;
        performance.now = function() {{
            return originalPerfNow.call(this) + (Math.random() * 0.1);
        }};
        
        const originalDateNow = Date.now;
        Date.now = function() {{
            return originalDateNow.call(this) + Math.floor(Math.random() * 5);
        }};
        
        // ========== DOCUMENT ==========
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
        
        console.log('✅ 100% маскировка применена');
    }})()
    """

# ---------- БРАУЗЕР ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.target_id = None
        self.snapshot = {}
    
    def find_chrome(self):
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "google-chrome",
            "chromium-browser",
            "chromium"
        ]
        
        for path in chrome_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=2)
                if result.returncode == 0:
                    file_logger.log(f"✅ Найден Chrome: {path}", "INFO")
                    return path
            except:
                continue
        return None
    
    def ensure_browser(self):
        file_logger.log("🔍 Проверяю Chrome...", "INFO")
        
        try:
            resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            if resp.status_code == 200:
                file_logger.log("✅ Chrome уже запущен и отвечает", "INFO")
                return True
        except Exception as e:
            file_logger.log(f"⚠️ Chrome не отвечает: {e}", "WARNING")
        
        chrome_path = self.find_chrome()
        if not chrome_path:
            file_logger.log("❌ Chrome не найден в системе!", "ERROR")
            return False
        
        global CHROME_PATH
        CHROME_PATH = chrome_path
        
        file_logger.log(f"🔄 Запускаю Chrome с маскировкой", "INFO")
        
        try:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
            time.sleep(2)
            
            launch_args = get_launch_args()
            
            subprocess.Popen(launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            file_logger.log("⏳ Жду запуска Chrome (5 сек)...", "INFO")
            time.sleep(5)
            
            for i in range(5):
                try:
                    resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
                    if resp.status_code == 200:
                        file_logger.log("✅ Chrome запущен успешно!", "INFO")
                        return True
                except:
                    pass
                time.sleep(1)
            
            file_logger.log("❌ Chrome не отвечает после запуска", "ERROR")
            return False
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            return False
    
    def get_or_create_tab(self, url=None):
        try:
            version_resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=3)
            file_logger.log(f"✅ Chrome version: {version_resp.json().get('Browser', 'unknown')}", "INFO")
            
            if url:
                full_url = f"http://localhost:{CDP_PORT}/json/new?{url}"
            else:
                full_url = f"http://localhost:{CDP_PORT}/json/new"
            
            resp = requests.put(full_url, timeout=3)
            
            if resp.status_code == 405:
                resp = requests.post(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            
            if resp.status_code == 405:
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
            
            tab = resp.json()
            file_logger.log(f"✅ Вкладка создана: {tab.get('id', 'unknown')}", "INFO")
            return tab["webSocketDebuggerUrl"], tab["id"]
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка создания вкладки: {e}", "ERROR")
            raise
    
    async def connect(self):
        if not self.ensure_browser():
            raise Exception("❌ Chrome не доступен")
        
        ws_url, self.target_id = self.get_or_create_tab()
        file_logger.log(f"🔗 Подключаюсь к WebSocket...", "INFO")
        
        try:
            self.ws = await websockets.connect(ws_url, max_size=WEBSOCKET_MAX_SIZE)
            file_logger.log(f"✅ WebSocket подключен", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка WebSocket: {e}", "ERROR")
            raise
        
        try:
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            file_logger.log("✅ Домены активированы", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка активации доменов: {e}", "ERROR")
            raise
    
    async def send(self, method, params=None):
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("id") == self.msg_id:
                    if "error" in data:
                        error_msg = data["error"].get("message", "Unknown CDP error")
                        error_code = data["error"].get("code", 0)
                        raise Exception(f"CDP Error [{error_code}]: {error_msg}")
                    return data
            except asyncio.TimeoutError:
                raise Exception("Таймаут ожидания ответа")
    
    async def eval_js(self, script):
        try:
            result = await self.send("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True
            })
            return result.get("result", {}).get("result", {}).get("value")
        except Exception as e:
            file_logger.log(f"❌ Ошибка выполнения JS: {e}", "ERROR")
            return None
    
    async def apply_mask(self):
        try:
            file_logger.log("🕵️ Применяю 100% маскировку...", "INFO")
            mask_js = get_mask_js()
            await self.eval_js(mask_js)
            file_logger.log("✅ 100% маскировка применена", "INFO")
            return True
        except Exception as e:
            file_logger.log(f"❌ Ошибка маскировки: {e}", "ERROR")
            return False
    
    # ========== НОВЫЕ ФУНКЦИИ ДЛЯ ДЕЙСТВИЙ ==========
    
    async def click_element(self, target):
        """Кликает по элементу"""
        try:
            # Ищем элемент по тексту или селектору
            selectors = [
                f"button:contains('{target}')",
                f"a:contains('{target}')",
                f"[aria-label*='{target}']",
                f"[placeholder*='{target}']",
                f"[class*='{target}']",
                f"#{target}"
            ]
            
            # Пробуем найти через JS
            js = f"""
                (function() {{
                    const targets = ['{target}'];
                    const elements = document.querySelectorAll('button, a, input, div[role="button"]');
                    
                    for (let el of elements) {{
                        const text = (el.textContent || '').trim().toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        
                        const target_lower = '{target}'.toLowerCase();
                        
                        if (text.includes(target_lower) || 
                            aria.includes(target_lower) || 
                            placeholder.includes(target_lower) ||
                            id.includes(target_lower) ||
                            cls.includes(target_lower)) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }})()
            """
            
            result = await self.eval_js(js)
            
            if result:
                file_logger.log(f"✅ Кликнул по {target}", "INFO")
                return True
            else:
                file_logger.log(f"❌ Элемент {target} не найден", "WARNING")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка клика: {e}", "ERROR")
            return False
    
    async def type_text(self, text, field):
        """Вводит текст в поле"""
        try:
            js = f"""
                (function() {{
                    const field_lower = '{field}'.toLowerCase();
                    const elements = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                    
                    for (let el of elements) {{
                        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const name = (el.getAttribute('name') || '').toLowerCase();
                        
                        if (placeholder.includes(field_lower) || 
                            aria.includes(field_lower) || 
                            id.includes(field_lower) ||
                            cls.includes(field_lower) ||
                            name.includes(field_lower)) {{
                            el.focus();
                            el.value = '';
                            el.value = '{text}';
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }})()
            """
            
            result = await self.eval_js(js)
            
            if result:
                file_logger.log(f"✅ Ввел '{text}' в поле {field}", "INFO")
                return True
            else:
                file_logger.log(f"❌ Поле {field} не найдено", "WARNING")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка ввода: {e}", "ERROR")
            return False
    
    async def submit_form(self):
        """Отправляет форму (находит первую форму и сабмитит)"""
        try:
            js = """
                (function() {
                    const form = document.querySelector('form');
                    if (form) {
                        form.submit();
                        return true;
                    }
                    return false;
                })()
            """
            
            result = await self.eval_js(js)
            
            if result:
                file_logger.log("✅ Форма отправлена", "INFO")
                return True
            else:
                file_logger.log("❌ Форма не найдена", "WARNING")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка отправки формы: {e}", "ERROR")
            return False
    
    async def get_snapshot(self):
        try:
            file_logger.log("📸 Делаю слепок страницы...", "INFO")
            
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
                        
                        const text = (el.textContent || '').trim().slice(0, 200);
                        
                        const isInteractive = (
                            tag === 'button' ||
                            tag === 'a' ||
                            attrs.role === 'button' ||
                            tag === 'input' ||
                            tag === 'textarea' ||
                            tag === 'select'
                        );
                        
                        const important = ['button', 'a', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li'];
                        
                        if (important.includes(tag) || isInteractive || attrs['data-testid'] || attrs['aria-label']) {
                            result.push({
                                tag: tag,
                                text: text,
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                isInteractive: isInteractive
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
            
            elements.sort(key=lambda x: x.get('visible', False), reverse=True)
            
            self.snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "elements": elements[:500]
            }
            
            file_logger.log(f"✅ Слепок: {len(elements)} элементов", "INFO")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка слепка: {e}", "ERROR")
            self.snapshot = {"title": "Ошибка", "url": "Ошибка", "total": 0, "elements": []}
            return False
    
    async def navigate_and_screenshot(self, url):
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        await self.connect()
        
        await self.apply_mask()
        
        try:
            await self.send("Page.navigate", {"url": url})
            file_logger.log(f"✅ Навигация отправлена", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка навигации: {e}", "ERROR")
            raise
        
        await self.wait_for_page_load()
        await self.get_snapshot()
        
        screenshot_data = await self.screenshot()
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот")
        
        return screenshot_data
    
    async def wait_for_page_load(self):
        file_logger.log("⏳ Ожидаю загрузку...", "INFO")
        start_time = time.time()
        
        while time.time() - start_time < PAGE_LOAD_TIMEOUT:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                
                ready_state = result.get("result", {}).get("result", {}).get("value", "")
                
                if ready_state in ["complete", "interactive"]:
                    file_logger.log(f"✅ Страница загружена ({ready_state})", "INFO")
                    return True
                
            except Exception as e:
                file_logger.log(f"⚠️ Ошибка проверки: {e}", "WARNING")
            
            await asyncio.sleep(0.5)
        
        file_logger.log("⏰ Таймаут загрузки", "WARNING")
        return False
    
    async def screenshot(self):
        try:
            file_logger.log("📸 Делаю скриншот...", "INFO")
            
            await self.send("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False,
                "scale": 1
            })
            
            result = await self.send("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 80,
                "captureBeyondViewport": False
            })
            
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                file_logger.log(f"✅ Скриншот {len(img_data)//1024} KB", "INFO")
                return img_data
            
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    
    await update.message.reply_text(
        "👋 Привет! Я бот для скриншотов, анализа и действий на сайтах.\n\n"
        "🗣️ Говори со мной как с человеком:\n"
        "• зайди на google.com\n"
        "• какие кнопки видишь?\n"
        "• нажми на кнопку 'Поиск'\n"
        "• введи 'погода' в поле поиска\n"
        "• отправь форму\n"
        "• сделай скриншот\n"
        "• вернись назад\n"
        "• покажи историю\n\n"
        "📁 Команды: /log\n"
        "🕵️ Маскировка: ВСЕГДА ВКЛЮЧЕНА"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user.first_name
    
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    
    memory = context.user_data['memory']
    
    # Парсим команду
    command = parse_command(text)
    file_logger.log(f"📝 Распознано: {command}", "DEBUG")
    
    # ====== ПРИВЕТСТВИЕ ======
    if command['action'] == 'greeting':
        await update.message.reply_text(
            "👋 Привет! Я бот для скриншотов, анализа и действий на сайтах.\n\n"
            "Скажи что-то вроде:\n"
            "• зайди на google.com\n"
            "• какие кнопки видишь?\n"
            "• нажми на кнопку 'Поиск'\n"
            "• введи 'погода' в поле поиска"
        )
        return
    
    # ====== НАВИГАЦИЯ ======
    if command['action'] == 'navigate':
        url = command['url']
        memory.add_action("url", {"url": url})
        
        await update.message.reply_text(f"🔄 Загружаю {url}...")
        
        try:
            browser = BrowserCDP()
            screenshot = await browser.navigate_and_screenshot(url)
            
            await update.message.reply_photo(
                screenshot,
                caption=f"✅ {url}"
            )
            file_logger.log(f"✅ Скриншот отправлен {user}", "INFO")
            
            memory.set_snapshot(browser.snapshot, url, browser.snapshot.get('title', 'Без названия'), browser)
            context.user_data['browser'] = browser
            
        except Exception as e:
            error_msg = str(e)
            file_logger.log(f"❌ Ошибка: {error_msg}", "ERROR")
            await update.message.reply_text(f"❌ Ошибка: {error_msg}")
        return
    
    # ====== КЛИК ======
    if command['action'] == 'click':
        target = command['target']
        
        if not memory.browser:
            await update.message.reply_text("📭 Нет загруженной страницы. Сначала отправь URL")
            return
        
        await update.message.reply_text(f"🔘 Ищу и кликаю по '{target}'...")
        
        try:
            result = await memory.browser.click_element(target)
            if result:
                memory.add_action("click", {"target": target})
                await update.message.reply_text(f"✅ Кликнул по '{target}'")
                
                # Обновляем snapshot после клика
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                
                # Делаем скриншот после клика
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        screenshot,
                        caption=f"✅ После клика на '{target}'"
                    )
            else:
                await update.message.reply_text(f"❌ Элемент '{target}' не найден")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВВОД ТЕКСТА ======
    if command['action'] == 'type':
        text_input = command['text']
        field = command['field']
        
        if not memory.browser:
            await update.message.reply_text("📭 Нет загруженной страницы. Сначала отправь URL")
            return
        
        await update.message.reply_text(f"✏️ Ввожу '{text_input}' в поле '{field}'...")
        
        try:
            result = await memory.browser.type_text(text_input, field)
            if result:
                memory.add_action("type", {"text": text_input, "field": field})
                await update.message.reply_text(f"✅ Ввел '{text_input}' в поле '{field}'")
                
                # Обновляем snapshot
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
            else:
                await update.message.reply_text(f"❌ Поле '{field}' не найдено")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ОТПРАВКА ФОРМЫ ======
    if command['action'] == 'submit':
        if not memory.browser:
            await update.message.reply_text("📭 Нет загруженной страницы. Сначала отправь URL")
            return
        
        await update.message.reply_text("📤 Отправляю форму...")
        
        try:
            result = await memory.browser.submit_form()
            if result:
                memory.add_action("submit", {})
                await update.message.reply_text("✅ Форма отправлена")
                
                # Ждем загрузки
                await memory.browser.wait_for_page_load()
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                
                # Делаем скриншот
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        screenshot,
                        caption="✅ После отправки формы"
                    )
            else:
                await update.message.reply_text("❌ Форма не найдена")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВОЗВРАТ НАЗАД ======
    if command['action'] == 'back':
        last_url = memory.get_last_url(1)
        if last_url:
            await update.message.reply_text(f"🔄 Возвращаюсь на {last_url}...")
            
            try:
                browser = BrowserCDP()
                screenshot = await browser.navigate_and_screenshot(last_url)
                
                await update.message.reply_photo(
                    screenshot,
                    caption=f"✅ {last_url}"
                )
                
                memory.set_snapshot(browser.snapshot, last_url, browser.snapshot.get('title', 'Без названия'), browser)
                context.user_data['browser'] = browser
                
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        else:
            await update.message.reply_text("📭 Нет предыдущей страницы")
        return
    
    # ====== СКРИНШОТ ======
    if command['action'] == 'screenshot':
        if memory.current_url and memory.browser:
            await update.message.reply_text("📸 Делаю скриншот текущей страницы...")
            
            try:
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        screenshot,
                        caption=f"✅ {memory.current_url}"
                    )
                    memory.add_action("screenshot", {"url": memory.current_url})
                else:
                    await update.message.reply_text("❌ Не удалось сделать скриншот")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        else:
            await update.message.reply_text("📭 Нет загруженной страницы. Сначала отправь URL")
        return
    
    # ====== ВОПРОСЫ AI ======
    if command['action'] == 'ask':
        question = command['question']
        
        if not memory.current_snapshot:
            await update.message.reply_text("📭 Сначала загрузи страницу (отправь URL)")
            return
        
        memory.add_action("question", {"question": question})
        
        await update.message.reply_text("🤖 Анализирую страницу...")
        
        try:
            snapshot = memory.current_snapshot
            elements = snapshot.get('elements', [])[:50]
            
            elements_text = []
            for el in elements[:30]:
                tag = el.get('tag', 'unknown')
                text = el.get('text', '').strip()[:100]
                attrs = el.get('attrs', {})
                is_interactive = '🔘' if el.get('isInteractive') else '📄'
                visible = '👁️' if el.get('visible') else '👻'
                
                element_desc = f"{is_interactive} <{tag}> {visible}"
                if text:
                    element_desc += f" — «{text}»"
                if attrs.get('id'):
                    element_desc += f" (id: {attrs['id']})"
                if attrs.get('type'):
                    element_desc += f" (type: {attrs['type']})"
                if attrs.get('placeholder'):
                    element_desc += f" (placeholder: {attrs['placeholder']})"
                
                elements_text.append(element_desc)
            
            context_text = f"""
📄 СТРАНИЦА: {snapshot.get('title', 'Без названия')}
🔗 URL: {snapshot.get('url', 'Нет URL')}
📊 ВСЕГО ЭЛЕМЕНТОВ: {snapshot.get('total', 0)}

🔍 ОСНОВНЫЕ ЭЛЕМЕНТЫ:
{chr(10).join(elements_text)}
"""
            
            prompt = f"""
На основе структуры страницы ответь на вопрос пользователя.

Вопрос: {question}

Инструкции:
1. Отвечай кратко и по делу
2. Ссылайся на конкретные элементы
3. Если элемент не найден — скажи об этом
"""
            
            answer = ask_ai(prompt, context_text, memory)
            await update.message.reply_text(f"🤖 **Ответ:**\n\n{answer}", parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ИСТОРИЯ ======
    if command['action'] == 'history':
        history_text = memory.get_history_text()
        
        if len(history_text) > 4000:
            with open('history_temp.txt', 'w', encoding='utf-8') as f:
                f.write(history_text)
            
            with open('history_temp.txt', 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"history_{datetime.now().strftime('%Y-%m-%d')}.txt",
                    caption="📜 История действий"
                )
            os.remove('history_temp.txt')
        else:
            await update.message.reply_text(f"📜 **История действий:**\n\n{history_text}", parse_mode='Markdown')
        return
    
    # ====== ОЧИСТКА ======
    if command['action'] == 'clear':
        context.user_data['memory'] = Memory()
        await update.message.reply_text("🧹 Память очищена!")
        return
    
    # ====== НЕИЗВЕСТНО ======
    await update.message.reply_text(
        "❌ Не понял команду\n\n"
        "Вот что я умею:\n"
        "• зайди на google.com\n"
        "• какие кнопки видишь?\n"
        "• нажми на кнопку 'Поиск'\n"
        "• введи 'погода' в поле поиска\n"
        "• отправь форму\n"
        "• сделай скриншот\n"
        "• вернись назад\n"
        "• покажи историю"
    )

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Файл логов ещё не создан")
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
    print("="*50)
    print("🚀 ЗАПУСК БОТА С ДЕЙСТВИЯМИ")
    print("="*50)
    print(f"📌 Chrome путь: {CHROME_PATH}")
    print("🕵️ Маскировка: ВСЕГДА ВКЛЮЧЕНА")
    print("🧠 Память: ВКЛЮЧЕНА")
    print("🗣️ Естественный язык: ВКЛЮЧЕН")
    print("🔘 Клики: ВКЛЮЧЕНЫ")
    print("✏️ Ввод текста: ВКЛЮЧЕН")
    print("📤 Отправка форм: ВКЛЮЧЕНА")
    print(f"🤖 AI модель: {AI_MODEL}")
    print("="*50)
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    if not AGNES_API_KEY:
        print("⚠️ AGNES_API_KEY не указан! AI-функции не будут работать")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот готов!")
    print("📁 Команды: /start, /log")
    print("🗣️ Говори как с человеком:")
    print("   • зайди на google.com")
    print("   • нажми на кнопку 'Поиск'")
    print("   • введи 'погода' в поле поиска")
    print("   • отправь форму")
    app.run_polling()

if __name__ == "__main__":
    main()