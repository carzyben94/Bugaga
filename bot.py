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
        self.browser = None
    
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

# ---------- AI ДЛЯ РАСПОЗНАВАНИЯ КОМАНД ----------
def ask_ai_for_command(text, memory=None):
    """
    AI сам понимает, что хочет пользователь
    """
    try:
        if not AGNES_API_KEY:
            return {'action': 'error', 'message': 'AGNES_API_KEY не указан'}
        
        messages = []
        
        system_prompt = """Ты — умный AI-помощник, который понимает команды пользователя.

Твоя задача — понять, что хочет пользователь, и вернуть JSON с действием.

ДОСТУПНЫЕ ДЕЙСТВИЯ:
1. navigate — перейти на сайт
2. ask — задать вопрос о странице
3. click — кликнуть на элемент
4. type — ввести текст в поле
5. submit — отправить форму
6. screenshot — сделать скриншот
7. back — вернуться назад
8. history — показать историю
9. clear — очистить память
10. greeting — приветствие
11. help — помощь

ПРИМЕРЫ:
Пользователь: "зайди в гугл"
Ответ: {"action": "navigate", "url": "https://google.com"}

Пользователь: "открой ютуб"
Ответ: {"action": "navigate", "url": "https://youtube.com"}

Пользователь: "перейди на сайт вк"
Ответ: {"action": "navigate", "url": "https://vk.com"}

Пользователь: "зайди на х"
Ответ: {"action": "navigate", "url": "https://x.com"}

Пользователь: "какие кнопки видишь?"
Ответ: {"action": "ask", "question": "какие кнопки видишь?"}

Пользователь: "что есть на странице?"
Ответ: {"action": "ask", "question": "что есть на странице?"}

Пользователь: "нажми на кнопку Войти"
Ответ: {"action": "click", "target": "Войти"}

Пользователь: "кликни по ссылке Регистрация"
Ответ: {"action": "click", "target": "Регистрация"}

Пользователь: "введи погоду в поле поиска"
Ответ: {"action": "type", "text": "погода", "field": "поиска"}

Пользователь: "напиши hello в поле ввода"
Ответ: {"action": "type", "text": "hello", "field": "ввода"}

Пользователь: "отправь форму"
Ответ: {"action": "submit"}

Пользователь: "войти"
Ответ: {"action": "submit"}

Пользователь: "сделай скриншот"
Ответ: {"action": "screenshot"}

Пользователь: "скрин"
Ответ: {"action": "screenshot"}

Пользователь: "вернись назад"
Ответ: {"action": "back"}

Пользователь: "назад"
Ответ: {"action": "back"}

Пользователь: "покажи историю"
Ответ: {"action": "history"}

Пользователь: "что я делал"
Ответ: {"action": "history"}

Пользователь: "очисти память"
Ответ: {"action": "clear"}

Пользователь: "забудь всё"
Ответ: {"action": "clear"}

Пользователь: "привет"
Ответ: {"action": "greeting"}

Пользователь: "помоги"
Ответ: {"action": "help"}

Правила:
1. Всегда возвращай ТОЛЬКО JSON
2. Для navigate — всегда добавляй https:// если нет
3. Если не понял — верни {"action": "unknown"}
4. Для type — всегда указывай text и field
5. Для click — всегда указывай target

Сейчас пользователь написал: """
        
        if memory:
            context = memory.get_context_for_ai()
            if context:
                system_prompt += f"\n\nКонтекст:\n{context}"
        
        messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": AI_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 200
        }
        
        file_logger.log(f"🤖 AI распознает команду...", "INFO")
        
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            try:
                command = json.loads(answer)
                file_logger.log(f"✅ AI распознал: {command}", "INFO")
                return command
            except:
                file_logger.log(f"❌ AI вернул не JSON: {answer}", "ERROR")
                return {'action': 'unknown'}
        else:
            file_logger.log(f"❌ Ошибка AI: {response.status_code}", "ERROR")
            return {'action': 'error', 'message': f"HTTP {response.status_code}"}
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка AI: {e}", "ERROR")
        return {'action': 'error', 'message': str(e)}

# ---------- AI ДЛЯ ОТВЕТОВ НА ВОПРОСЫ ----------
def ask_ai_for_answer(prompt, context=None, memory=None):
    """Запрос к Agnes AI для ответов на вопросы"""
    try:
        if not AGNES_API_KEY:
            return "❌ AGNES_API_KEY не указан"
        
        messages = []
        
        system_prompt = """Ты — AI-ассистент для анализа веб-страниц.

ТВОЯ РОЛЬ:
- Помогаешь пользователю понимать структуру страницы
- Отвечаешь на вопросы об элементах
- Даешь рекомендации по действиям

ПРАВИЛА:
1. Отвечай кратко (3-5 предложений)
2. Перечисляй элементы с пояснениями
3. Если не нашел — скажи честно
4. Используй эмодзи: 🔘 кнопка, 📄 текст, 🔗 ссылка, ✏️ поле
5. Не выдумывай то, чего нет

ФОРМАТ:
- Списки: • или 1.
- Элементы: тип + текст + местоположение
- Если можно кликнуть — скажи"""
        
        if memory:
            memory_context = memory.get_context_for_ai()
            if memory_context:
                system_prompt += f"\n\nКОНТЕКСТ ИЗ ПАМЯТИ:\n{memory_context}"
        
        messages.append({"role": "system", "content": system_prompt})
        
        if context:
            messages.append({"role": "user", "content": f"СТРУКТУРА СТРАНИЦЫ:\n{context}"})
        
        messages.append({"role": "user", "content": f"ВОПРОС: {prompt}"})
        
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
        
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
            return answer
        else:
            return f"❌ Ошибка: HTTP {response.status_code}"
            
    except Exception as e:
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
    
    # ========== ДЕЙСТВИЯ ==========
    
    async def click_element(self, target):
        try:
            js = f"""
                (function() {{
                    const target = '{target}'.toLowerCase();
                    const elements = document.querySelectorAll('button, a, input, div[role="button"]');
                    
                    for (let el of elements) {{
                        const text = (el.textContent || '').trim().toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        
                        if (text.includes(target) || aria.includes(target) || placeholder.includes(target) ||
                            id.includes(target) || cls.includes(target)) {{
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
        try:
            js = f"""
                (function() {{
                    const field = '{field}'.toLowerCase();
                    const elements = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                    
                    for (let el of elements) {{
                        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const name = (el.getAttribute('name') || '').toLowerCase();
                        
                        if (placeholder.includes(field) || aria.includes(field) || id.includes(field) ||
                            cls.includes(field) || name.includes(field)) {{
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

# ---------- ОСНОВНОЙ ОБРАБОТЧИК ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    
    await update.message.reply_text(
        "👋 Привет! Я бот с ИИ-пониманием.\n\n"
        "🗣️ Говори как хочешь — я пойму:\n"
        "• зайди в гугл\n"
        "• открой ютуб\n"
        "• какие кнопки?\n"
        "• нажми на Войти\n"
        "• введи погоду в поиск\n"
        "• сделай скрин\n"
        "• вернись назад\n\n"
        "🧠 Всё понимает ИИ, говори свободно!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user.first_name
    
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    
    memory = context.user_data['memory']
    
    # ====== ПРИВЕТСТВИЕ ======
    if text.lower() in ['привет', 'здравствуй', 'hello', 'hi', 'хай']:
        await update.message.reply_text(
            "👋 Привет! Спрашивай что хочешь.\n"
            "Можешь сказать 'зайди в гугл' или 'какие кнопки?'"
        )
        return
    
    # ====== ПОМОЩЬ ======
    if text.lower() in ['помоги', 'что умеешь', 'help', '/help']:
        await update.message.reply_text(
            "🤖 Я умею:\n"
            "• зайди на сайт\n"
            "• показать кнопки/поля/ссылки\n"
            "• кликнуть на элемент\n"
            "• ввести текст в поле\n"
            "• отправить форму\n"
            "• сделать скриншот\n"
            "• вернуться назад\n"
            "• показать историю\n\n"
            "Говори как с человеком!"
        )
        return
    
    # ====== ОТПРАВЛЯЕМ ВСЁ В AI ======
    thinking_msg = await update.message.reply_text("🤔 Думаю...")
    
    command = ask_ai_for_command(text, memory)
    
    action = command.get('action', 'unknown')
    
    # ====== НАВИГАЦИЯ ======
    if action == 'navigate':
        url = command.get('url')
        if not url:
            await thinking_msg.edit_text("❌ Не понял, на какой сайт перейти")
            return
        
        memory.add_action("url", {"url": url})
        
        await thinking_msg.edit_text(f"🔄 Загружаю {url}...")
        
        try:
            browser = BrowserCDP()
            screenshot = await browser.navigate_and_screenshot(url)
            
            await thinking_msg.delete()
            await update.message.reply_photo(
                screenshot,
                caption=f"✅ {url}"
            )
            
            memory.set_snapshot(browser.snapshot, url, browser.snapshot.get('title', 'Без названия'), browser)
            context.user_data['browser'] = browser
            
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВОПРОС ======
    if action == 'ask':
        question = command.get('question', text)
        
        if not memory.current_snapshot:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу (скажи 'зайди на сайт')")
            return
        
        memory.add_action("question", {"question": question})
        
        await thinking_msg.edit_text("🤖 Анализирую страницу...")
        
        try:
            snapshot = memory.current_snapshot
            elements = snapshot.get('elements', [])[:50]
            
            elements_text = []
            for el in elements[:30]:
                tag = el.get('tag', 'unknown')
                text_el = el.get('text', '').strip()[:100]
                attrs = el.get('attrs', {})
                is_interactive = '🔘' if el.get('isInteractive') else '📄'
                visible = '👁️' if el.get('visible') else '👻'
                
                desc = f"{is_interactive} <{tag}> {visible}"
                if text_el:
                    desc += f" — «{text_el}»"
                if attrs.get('id'):
                    desc += f" (id: {attrs['id']})"
                if attrs.get('type'):
                    desc += f" (type: {attrs['type']})"
                if attrs.get('placeholder'):
                    desc += f" (placeholder: {attrs['placeholder']})"
                
                elements_text.append(desc)
            
            context_text = f"""
📄 СТРАНИЦА: {snapshot.get('title', 'Без названия')}
🔗 URL: {snapshot.get('url', 'Нет URL')}
📊 ВСЕГО ЭЛЕМЕНТОВ: {snapshot.get('total', 0)}

🔍 ОСНОВНЫЕ ЭЛЕМЕНТЫ:
{chr(10).join(elements_text)}
"""
            
            answer = ask_ai_for_answer(question, context_text, memory)
            await thinking_msg.edit_text(f"🤖 **Ответ:**\n\n{answer}", parse_mode='Markdown')
            
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== КЛИК ======
    if action == 'click':
        target = command.get('target')
        if not target:
            await thinking_msg.edit_text("❌ Не понял, на что кликнуть")
            return
        
        if not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        
        await thinking_msg.edit_text(f"🔘 Ищу и кликаю по '{target}'...")
        
        try:
            result = await memory.browser.click_element(target)
            if result:
                memory.add_action("click", {"target": target})
                await thinking_msg.edit_text(f"✅ Кликнул по '{target}'")
                
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        screenshot,
                        caption=f"✅ После клика на '{target}'"
                    )
            else:
                await thinking_msg.edit_text(f"❌ Элемент '{target}' не найден")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВВОД ТЕКСТА ======
    if action == 'type':
        text_input = command.get('text')
        field = command.get('field')
        if not text_input or not field:
            await thinking_msg.edit_text("❌ Не понял, что и куда вводить")
            return
        
        if not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        
        await thinking_msg.edit_text(f"✏️ Ввожу '{text_input}' в поле '{field}'...")
        
        try:
            result = await memory.browser.type_text(text_input, field)
            if result:
                memory.add_action("type", {"text": text_input, "field": field})
                await thinking_msg.edit_text(f"✅ Ввел '{text_input}' в поле '{field}'")
                
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
            else:
                await thinking_msg.edit_text(f"❌ Поле '{field}' не найдено")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ОТПРАВКА ФОРМЫ ======
    if action == 'submit':
        if not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        
        await thinking_msg.edit_text("📤 Отправляю форму...")
        
        try:
            result = await memory.browser.submit_form()
            if result:
                memory.add_action("submit", {})
                await thinking_msg.edit_text("✅ Форма отправлена")
                
                await memory.browser.wait_for_page_load()
                await memory.browser.get_snapshot()
                memory.set_snapshot(
                    memory.browser.snapshot,
                    memory.current_url,
                    memory.browser.snapshot.get('title', 'Без названия'),
                    memory.browser
                )
                
                screenshot = await memory.browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(
                        screenshot,
                        caption="✅ После отправки формы"
                    )
            else:
                await thinking_msg.edit_text("❌ Форма не найдена")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== СКРИНШОТ ======
    if action == 'screenshot':
        if not memory.current_url or not memory.browser:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        
        await thinking_msg.edit_text("📸 Делаю скриншот...")
        
        try:
            screenshot = await memory.browser.screenshot()
            if screenshot:
                await thinking_msg.delete()
                await update.message.reply_photo(
                    screenshot,
                    caption=f"✅ {memory.current_url}"
                )
                memory.add_action("screenshot", {"url": memory.current_url})
            else:
                await thinking_msg.edit_text("❌ Не удалось сделать скриншот")
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВОЗВРАТ НАЗАД ======
    if action == 'back':
        last_url = memory.get_last_url(1)
        if last_url:
            await thinking_msg.edit_text(f"🔄 Возвращаюсь на {last_url}...")
            
            try:
                browser = BrowserCDP()
                screenshot = await browser.navigate_and_screenshot(last_url)
                
                await thinking_msg.delete()
                await update.message.reply_photo(
                    screenshot,
                    caption=f"✅ {last_url}"
                )
                
                memory.set_snapshot(browser.snapshot, last_url, browser.snapshot.get('title', 'Без названия'), browser)
                context.user_data['browser'] = browser
                
            except Exception as e:
                await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        else:
            await thinking_msg.edit_text("📭 Нет предыдущей страницы")
        return
    
    # ====== ИСТОРИЯ ======
    if action == 'history':
        history_text = memory.get_history_text()
        await thinking_msg.delete()
        
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
    if action == 'clear':
        context.user_data['memory'] = Memory()
        await thinking_msg.edit_text("🧹 Память очищена!")
        return
    
    # ====== ПРИВЕТСТВИЕ (если AI вернул) ======
    if action == 'greeting':
        await thinking_msg.edit_text(
            "👋 Привет! Говори что хочешь:\n"
            "• зайди на сайт\n"
            "• покажи кнопки\n"
            "• кликни на элемент"
        )
        return
    
    # ====== ПОМОЩЬ ======
    if action == 'help':
        await thinking_msg.edit_text(
            "🤖 Что я умею:\n"
            "• зайди на сайт\n"
            "• какие кнопки?\n"
            "• нажми на Войти\n"
            "• введи текст в поле\n"
            "• отправь форму\n"
            "• сделай скриншот\n"
            "• вернись назад\n"
            "• покажи историю"
        )
        return
    
    # ====== НЕИЗВЕСТНО ======
    if action == 'unknown':
        await thinking_msg.edit_text(
            "❌ Не понял команду\n\n"
            "Примеры:\n"
            "• зайди в гугл\n"
            "• какие кнопки?\n"
            "• нажми на Войти\n"
            "• введи погоду в поиск"
        )
        return
    
    # ====== ОШИБКА ======
    if action == 'error':
        await thinking_msg.edit_text(f"❌ Ошибка: {command.get('message', 'Неизвестная ошибка')}")
        return
    
    # ====== НА ВСЯКИЙ СЛУЧАЙ ======
    await thinking_msg.edit_text("❌ Что-то пошло не так. Попробуй еще раз.")

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
    print("🚀 ЗАПУСК БОТА С AI-ПОНИМАНИЕМ")
    print("="*50)
    print(f"📌 Chrome путь: {CHROME_PATH}")
    print("🕵️ Маскировка: ВСЕГДА ВКЛЮЧЕНА")
    print("🧠 Память: ВКЛЮЧЕНА")
    print("🤖 AI-понимание: ВКЛЮЧЕНО")
    print(f"🤖 AI модель: {AI_MODEL}")
    print("="*50)
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    if not AGNES_API_KEY:
        print("⚠️ AGNES_API_KEY не указан! Бот не будет работать!")
        print("📌 Получи ключ на https://platform.agnes-ai.com/")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот готов!")
    print("🗣️ Говори как с человеком:")
    print("   • зайди в гугл")
    print("   • какие кнопки?")
    print("   • нажми на Войти")
    print("   • введи погоду в поиск")
    app.run_polling()

if __name__ == "__main__":
    main()