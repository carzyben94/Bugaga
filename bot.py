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
WEBSOCKET_MAX_SIZE = 50 * 1024 * 1024  # 50 МБ
PAGE_LOAD_TIMEOUT = 45
MAX_HISTORY = 20

# ---------- AI КОНФИГ ----------
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

# ---------- СПИСОК ID GOOGLE ----------
GOOGLE_SEARCH_IDS = ['APjFqb', 'gbqfq', 'lst-ib', 'searchbox', 'q']

# ---------- КУКИ ДЛЯ X.COM ----------
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
    {"domain": ".x.com", "hostOnly": False, "httpOnly": False, "name": "__cf_bm", "path": "/", "sameSite": "unspecified", "secure": False, "session": True, "value": "KFaKAqD6gO1ZhCG6Eng0A2oPJccRx5Yjs2LnNaZIUDs-1784022753.029898-1.0.1.1-NIpFLkCP7hAPgu0V_JbWmriYyaVYe7B5rrbuxMtSTicUxDV0MYrhlTiAdVxPlMbIKnf4TLZNw53wRWfRpoodX0Ys6UaRcP2oXJjXWiYMwXp2i4tTOSYKYcLnRL41ius7"}
]

SITE_COOKIES = {"x.com": X_COOKIES, "twitter.com": X_COOKIES}

def get_cookies_for_url(url):
    for domain, cookies in SITE_COOKIES.items():
        if domain in url.lower():
            return cookies
    return []

# ---------- ПЕРЕВОДЫ И СИНОНИМЫ ----------
TRANSLATIONS = {
    'обзор': 'Explore', 'главная': 'Home', 'уведомления': 'Notifications',
    'сообщения': 'Messages', 'профиль': 'Profile', 'закладки': 'Bookmarks',
    'настройки': 'Settings', 'помощь': 'Help', 'выход': 'Logout',
    'пост': 'Post', 'чат': 'Chat', 'лента': 'Feed', 'популярное': 'Trending',
    'для вас': 'For you', 'читаю': 'Following', 'опубликовать': 'Post',
    'ещё': 'More', 'поиск': 'Search', 'войти': 'Login', 'регистрация': 'Register',
    'отправить': 'Send', 'закрыть': 'Close', 'назад': 'Back', 'далее': 'Next',
    'предыдущий': 'Previous',
}

SYNONYMS = {
    'search': ['search', 'поиск', 'find', 'query', 'lookup'],
    'login': ['login', 'sign in', 'log in', 'войти', 'вход'],
    'register': ['register', 'sign up', 'зарегистрироваться', 'регистрация'],
    'submit': ['submit', 'send', 'отправить', 'послать'],
    'close': ['close', 'закрыть', 'exit'],
    'home': ['home', 'главная', 'main'],
    'explore': ['explore', 'обзор', 'discover'],
    'notifications': ['notifications', 'уведомления', 'alerts'],
    'messages': ['messages', 'сообщения', 'chat'],
    'profile': ['profile', 'профиль', 'account'],
    'bookmarks': ['bookmarks', 'закладки', 'saved'],
    'settings': ['settings', 'настройки', 'preferences'],
    'help': ['help', 'помощь', 'support'],
    'logout': ['logout', 'sign out', 'выход', 'выйти'],
    'post': ['post', 'tweet', 'пост', 'опубликовать', 'publish'],
    'chat': ['chat', 'чат', 'messaging'],
    'feed': ['feed', 'лента', 'timeline'],
    'trending': ['trending', 'популярное', 'popular'],
    'for you': ['for you', 'для вас', 'recommended'],
    'following': ['following', 'читаю', 'подписки', 'follow'],
    'more': ['more', 'ещё', 'additional'],
}

def translate_to_english(text):
    text_lower = text.lower().strip()
    for ru, en in TRANSLATIONS.items():
        if ru in text_lower or text_lower in ru:
            return en
    return text

def get_meaning(text):
    text_lower = text.lower().strip()
    for meaning, synonyms in SYNONYMS.items():
        if any(synonym in text_lower for synonym in synonyms):
            return meaning
    return None

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
        self.last_fields = None
    
    def add_action(self, action_type, data=None):
        entry = {"timestamp": datetime.now().isoformat(), "type": action_type, "data": data}
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
    
    def get_element_names(self):
        if not self.current_snapshot:
            return []
        elements = self.current_snapshot.get('interactive', [])
        names = []
        for el in elements[:50]:
            text = el.get('text', '').strip()
            if text:
                names.append(text)
            elif el.get('selector'):
                names.append(el.get('selector'))
        return names
    
    def get_context_for_ai(self):
        context = []
        if self.current_title:
            context.append(f"Current page: {self.current_title} ({self.current_url})")
        
        element_names = self.get_element_names()
        if element_names:
            context.append("\nAvailable interactive elements:")
            for name in element_names[:30]:
                context.append(f"• {name}")
        
        if self.history:
            context.append("\nRecent actions:")
            for action in self.history[-5:]:
                action_type = action.get('type', 'unknown')
                timestamp = action.get('timestamp', '')[:16]
                if action_type == 'snapshot':
                    url = action.get('data', {}).get('url', '')
                    context.append(f"- {timestamp}: Navigated to {url[:50]}")
                elif action_type == 'question':
                    question = action.get('data', {}).get('question', '')
                    context.append(f"- {timestamp}: Question: {question[:50]}")
                elif action_type == 'click':
                    target = action.get('data', {}).get('target', '')
                    context.append(f"- {timestamp}: Clicked {target}")
                elif action_type == 'type':
                    text = action.get('data', {}).get('text', '')
                    context.append(f"- {timestamp}: Typed '{text}'")
        
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
                lines.append(f"{i}. 📸 [{timestamp}] Screenshot")
            elif action_type == 'click':
                lines.append(f"{i}. 🔘 [{timestamp}] Clicked {data.get('target', '')}")
            elif action_type == 'type':
                lines.append(f"{i}. ✏️ [{timestamp}] Typed '{data.get('text', '')}'")
        return "\n".join(lines)

# ---------- AI ФУНКЦИИ ----------
SYSTEM_PROMPT = """You are a smart AI assistant that understands user commands.

🔥 IMPORTANT: ALWAYS use ENGLISH names for elements!

RECOGNIZE THESE COMMANDS (in ANY language):
1. Questions about page:
   - "what buttons do you see?" → {"action": "ask", "question": "what buttons are on the page?"}
   - "what links are there?" → {"action": "ask", "question": "what links are on the page?"}
   - "what fields are there?" → {"action": "ask", "question": "what input fields are on the page?"}
   - "what do you see?" → {"action": "ask", "question": "what do you see on the page?"}
   - "какие кнопки есть?" → {"action": "ask", "question": "what buttons are on the page?"}
   - "что видишь?" → {"action": "ask", "question": "what do you see on the page?"}

2. Actions:
   - "нажми Обзор" → {"action": "click", "target": "Explore"}
   - "click Explore" → {"action": "click", "target": "Explore"}
   - "введи текст в поиск" → {"action": "type", "text": "текст", "field": "search"}
   - "type hello in search" → {"action": "type", "text": "hello", "field": "search"}
   - "отправь форму" → {"action": "submit"}
   - "submit form" → {"action": "submit"}
   - "сделай скриншот" → {"action": "screenshot"}
   - "take screenshot" → {"action": "screenshot"}

3. Navigation:
   - "зайди на x.com" → {"action": "navigate", "url": "https://x.com"}
   - "go to google" → {"action": "navigate", "url": "https://google.com"}

🔥 RULES:
- ALWAYS respond with JSON only
- If user asks about elements → use "ask"
- If user wants to click → use "click"
- If user wants to type → use "type"
- If user asks in English → respond in English

Current user said: """

def ask_ai_for_command(text, memory=None):
    try:
        if not AGNES_API_KEY:
            return {'action': 'error', 'message': 'AGNES_API_KEY не указан'}
        
        messages = []
        system_prompt = SYSTEM_PROMPT
        
        if memory:
            context = memory.get_context_for_ai()
            if context:
                system_prompt += f"\n\nCONTEXT:\n{context}"
        
        messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})
        
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": AI_MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 200}
        
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
                return {'action': 'unknown'}
        else:
            return {'action': 'error', 'message': f"HTTP {response.status_code}"}
    except Exception as e:
        return {'action': 'error', 'message': str(e)}

def ask_ai_for_answer(prompt, context=None, memory=None):
    try:
        if not AGNES_API_KEY:
            return "❌ AGNES_API_KEY is not set"
        
        messages = []
        system_prompt = SYSTEM_PROMPT + """
        
🔥 LANGUAGE RULES:
- If user asked in English → answer in English
- If user asked in Russian → answer in Russian
- Always use emojis: 🔘 button, 🔗 link, ✏️ input field, 👁️ visible, 👻 hidden
- List elements with their types and selectors"""
        
        if memory:
            memory_context = memory.get_context_for_ai()
            if memory_context:
                system_prompt += f"\n\nCONTEXT:\n{memory_context}"
        
        messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.append({"role": "user", "content": f"PAGE STRUCTURE:\n{context}"})
        messages.append({"role": "user", "content": f"QUESTION: {prompt}"})
        
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": AI_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 600}
        
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
        else:
            return f"❌ Ошибка: HTTP {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ---------- МАСКИРОВКА ----------
def get_random_window_position():
    return {"left": random.randint(50, 300), "top": random.randint(50, 200),
            "width": random.randint(1200, 1920), "height": random.randint(800, 1080)}

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
    return random.choice(["Google Inc. (NVIDIA)", "Google Inc. (AMD)", "Google Inc. (Intel)", "NVIDIA Corporation", "Advanced Micro Devices, Inc.", "Intel Corporation"])

def get_random_webgl_renderer():
    return random.choice([
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ])

def get_launch_args():
    window = get_random_window_position()
    user_agent = get_random_user_agent()
    return [
        CHROME_PATH, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled", "--disable-automation",
        "--use-gl=egl", "--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--enable-zero-copy",
        "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials", "--disable-default-apps", "--disable-extensions",
        "--disable-component-extensions-with-background-pages", "--disable-client-side-phishing-detection",
        "--disable-crash-reporter", "--disable-component-update", "--disable-logging",
        "--disable-prompt-on-repost", "--disable-sync", "--disable-background-networking",
        "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
        "--disable-breakpad", "--disable-ipc-flooding-protection", "--disable-renderer-backgrounding",
        f"--window-position={window['left']},{window['top']}", f"--window-size={window['width']},{window['height']}",
        "--no-default-browser-check", "--no-first-run", "--force-color-profile=srgb",
        "--metrics-recording-only", "--password-store=basic", "--use-mock-keychain", "--export-tagged-pdf",
        "--enable-features=NetworkService,NetworkServiceInProcess", f"--user-agent={user_agent}",
        f"--remote-debugging-port={CDP_PORT}"
    ]

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
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined, configurable: true, enumerable: true }});
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                function Plugin(name, filename, description) {{
                    this.name = name; this.filename = filename; this.description = description;
                }}
                Plugin.prototype.item = function(index) {{ return this[index] || null; }};
                Plugin.prototype.namedItem = function(name) {{ return this[name] || null; }};
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
        Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en', 'ru'], configurable: true, enumerable: true }});
        Object.defineProperty(navigator, 'platform', {{ get: () => 'Win32', configurable: true, enumerable: true }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {cpu_cores}, configurable: true, enumerable: true }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {memory_gb}, configurable: true, enumerable: true }});
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
                            architecture: 'x86', bitness: '64', model: '', platform: 'Windows',
                            platformVersion: '10.0', uaFullVersion: '{chrome_version}.0.0.0'
                        }});
                    }},
                    toJSON: function() {{
                        return {{
                            brands: [
                                {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                                {{ brand: 'Chromium', version: '{chrome_version}' }}
                            ],
                            platform: 'Windows', mobile: false
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
                    rtt: {rtt}, downlink: {downlink}, effectiveType: '{connection_type}',
                    saveData: false, type: '{network_type}'
                }};
            }},
            configurable: true,
            enumerable: true
        }});
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = function(parameters) {{
            const permissions = {{
                'geolocation': 'prompt', 'notifications': Notification.permission,
                'midi': 'prompt', 'camera': 'prompt', 'microphone': 'prompt',
                'background-fetch': 'prompt', 'background-sync': 'granted',
                'periodic-background-sync': 'prompt', 'persistent-storage': 'prompt',
                'push': Notification.permission, 'speaker-selection': 'prompt'
            }};
            return Promise.resolve({{ state: permissions[parameters.name] || 'prompt', onchange: null }});
        }};
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
                                get: () => 0x9245, configurable: true, enumerable: true
                            }});
                            Object.defineProperty(ext, 'UNMASKED_RENDERER_WEBGL', {{
                                get: () => 0x9246, configurable: true, enumerable: true
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
                const noise = {noise};
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
                const availHeight = {screen_height};
                const height = availHeight + {extra_height};
                const availWidth = {screen_width};
                const width = availWidth;
                return {{
                    width: width, height: height, availWidth: availWidth, availHeight: availHeight,
                    colorDepth: 24, pixelDepth: 24, availLeft: 0, availTop: 0, left: 0, top: 0,
                    orientation: {{ type: 'landscape-primary', angle: 0 }}
                }};
            }},
            configurable: true,
            enumerable: true
        }});
        if (!window.chrome) {{ window.chrome = {{}}; }}
        window.chrome.runtime = {{}};
        window.chrome.loadTimes = function() {{}};
        window.chrome.csi = function() {{}};
        window.chrome.app = {{}};
        const originalPerfNow = performance.now;
        performance.now = function() {{ return originalPerfNow.call(this) + (Math.random() * 0.1); }};
        const originalDateNow = Date.now;
        Date.now = function() {{ return originalDateNow.call(this) + Math.floor(Math.random() * 5); }};
        Object.defineProperty(document, 'hidden', {{ get: () => false, configurable: true, enumerable: true }});
        Object.defineProperty(document, 'visibilityState', {{ get: () => 'visible', configurable: true, enumerable: true }});
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
        self.last_fields = None
        self.current_url = None
    
    def find_chrome(self):
        chrome_paths = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium", "/snap/bin/chromium", "google-chrome", "chromium-browser", "chromium"]
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
            subprocess.Popen(get_launch_args(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            full_url = f"http://localhost:{CDP_PORT}/json/new{('?' + url) if url else ''}"
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
            self.ws = await websockets.connect(
                ws_url,
                max_size=WEBSOCKET_MAX_SIZE,
                ping_interval=20,
                ping_timeout=10
            )
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
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
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
            result = await self.send("Runtime.evaluate", {"expression": script, "returnByValue": True})
            return result.get("result", {}).get("result", {}).get("value")
        except Exception as e:
            file_logger.log(f"❌ Ошибка выполнения JS: {e}", "ERROR")
            return None
    
    async def apply_mask(self):
        try:
            file_logger.log("🕵️ Применяю 100% маскировку...", "INFO")
            await self.eval_js(get_mask_js())
            file_logger.log("✅ 100% маскировка применена", "INFO")
            return True
        except Exception as e:
            file_logger.log(f"❌ Ошибка маскировки: {e}", "ERROR")
            return False
    
    async def ensure_connection(self):
        try:
            if not self.ws:
                file_logger.log("⚠️ Нет WebSocket соединения", "WARNING")
                await self.connect()
                await self.apply_mask()
                if self.current_url:
                    await self.send("Page.navigate", {"url": self.current_url})
                    await self.wait_for_page_load()
                    await self.get_snapshot()
                return True
            
            try:
                await self.ws.ping()
                return True
            except:
                raise Exception("WebSocket dead")
                
        except Exception as e:
            file_logger.log(f"🔄 WebSocket отвалился, переподключаюсь... ({e})", "WARNING")
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
            await self.connect()
            await self.apply_mask()
            if self.current_url:
                file_logger.log(f"🌐 Восстанавливаю страницу: {self.current_url}", "INFO")
                await self.send("Page.navigate", {"url": self.current_url})
                await self.wait_for_page_load()
                await self.get_snapshot()
            return True
    
    async def set_cookies(self, cookies_list):
        try:
            if not cookies_list:
                return True
            cdp_cookies = []
            for cookie in cookies_list:
                cdp_cookies.append({
                    "name": cookie.get("name"), "value": cookie.get("value"),
                    "domain": cookie.get("domain"), "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False), "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": cookie.get("sameSite", "unspecified"), "session": cookie.get("session", True)
                })
            await self.send("Network.setCookies", {"cookies": cdp_cookies})
            file_logger.log(f"✅ Установлено {len(cdp_cookies)} кук", "INFO")
            return True
        except Exception as e:
            file_logger.log(f"❌ Ошибка установки кук: {e}", "ERROR")
            return False

    # ========== СБОР ВСЕХ ИНТЕРАКТИВНЫХ ЭЛЕМЕНТОВ ==========
    async def get_all_interactive_elements(self):
        try:
            js = """
                (function() {
                    const result = [];
                    
                    function getSelector(el) {
                        if (el.id) return '#' + el.id;
                        if (el.getAttribute('data-testid')) {
                            return '[data-testid="' + el.getAttribute('data-testid') + '"]';
                        }
                        const aria = el.getAttribute('aria-label');
                        if (aria && /^[a-zA-Z0-9\\s\\-_\\.]+$/.test(aria)) {
                            return '[aria-label="' + aria + '"]';
                        }
                        if (el.getAttribute('aria-labelledby')) {
                            return '[aria-labelledby="' + el.getAttribute('aria-labelledby') + '"]';
                        }
                        if (el.getAttribute('name')) {
                            return 'input[name="' + el.getAttribute('name') + '"]';
                        }
                        if (el.className) {
                            const classes = el.className.split(' ').filter(c => c);
                            if (classes.length > 0) return '.' + classes.join('.');
                        }
                        return el.tagName.toLowerCase();
                    }
                    
                    function getAttrs(el) {
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        return attrs;
                    }
                    
                    const interactiveSelectors = [
                        'button', 'input[type="submit"]', 'input[type="button"]', 'input[type="reset"]',
                        'div[role="button"]', 'span[role="button"]', 'a[role="button"]',
                        '[role="button"]', '[role="menuitem"]', '[role="tab"]', '[role="link"]',
                        '[role="checkbox"]', '[role="radio"]', '[role="switch"]', '[role="option"]',
                        '[data-testid="AppTabBar_Home_Link"]', '[data-testid="AppTabBar_Explore_Link"]',
                        '[data-testid="AppTabBar_Notifications_Link"]', '[data-testid="AppTabBar_Messages_Link"]',
                        '[data-testid="SideNav_AccountSwitcher_Button"]', '[data-testid="compose-tweet-button"]',
                        '[aria-label*="Home"]', '[aria-label*="Explore"]', '[aria-label*="Notifications"]',
                        '[aria-label*="Messages"]', '[aria-label*="Profile"]', '[aria-label*="More"]',
                        '[aria-label*="Post"]', '[aria-label*="Tweet"]'
                    ];
                    
                    const interactiveElements = document.querySelectorAll(interactiveSelectors.join(','));
                    interactiveElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const text = (el.textContent || el.value || '').trim().slice(0, 200);
                        const aria = el.getAttribute('aria-label') || '';
                        const dataTestId = el.getAttribute('data-testid') || '';
                        result.push({
                            type: 'interactive',
                            tag: el.tagName.toLowerCase(),
                            text: text || aria || dataTestId,
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el),
                            dataTestId: dataTestId,
                            ariaLabel: aria
                        });
                    });
                    
                    const links = document.querySelectorAll('a[href]:not([role="button"])');
                    links.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const text = (el.textContent || '').trim().slice(0, 200);
                        result.push({
                            type: 'link',
                            tag: 'a',
                            text: text,
                            href: el.getAttribute('href') || '',
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el)
                        });
                    });
                    
                    const inputSelectors = [
                        'input:not([type="hidden"]):not([type="submit"]):not([type="button"])',
                        'textarea', 'select', '[contenteditable="true"]',
                        '[role="textbox"]', '[role="searchbox"]', '[role="combobox"]'
                    ];
                    const inputs = document.querySelectorAll(inputSelectors.join(','));
                    inputs.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const placeholder = el.getAttribute('placeholder') || '';
                        const aria = el.getAttribute('aria-label') || '';
                        result.push({
                            type: 'input',
                            tag: el.tagName.toLowerCase(),
                            inputType: el.getAttribute('type') || '',
                            placeholder: placeholder || aria,
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el)
                        });
                    });
                    
                    const menuItems = document.querySelectorAll('li, [role="menuitem"], [role="listitem"]');
                    menuItems.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const text = (el.textContent || '').trim().slice(0, 200);
                        const isInMenu = el.closest('nav, ul, ol, [role="menu"], [role="listbox"], [role="tablist"]');
                        if (isInMenu && text) {
                            result.push({
                                type: 'menu',
                                tag: el.tagName.toLowerCase(),
                                text: text,
                                id: el.id || '',
                                class: el.className || '',
                                attrs: getAttrs(el),
                                visible: visible,
                                x: Math.round(rect.x), y: Math.round(rect.y),
                                width: Math.round(rect.width), height: Math.round(rect.height),
                                interactive: true,
                                selector: getSelector(el)
                            });
                        }
                    });
                    
                    const checkboxes = document.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
                    checkboxes.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const label = el.getAttribute('aria-label') || '';
                        const checked = el.checked || false;
                        result.push({
                            type: 'checkbox',
                            tag: el.tagName.toLowerCase(),
                            text: label,
                            checked: checked,
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el)
                        });
                    });
                    
                    const radios = document.querySelectorAll('input[type="radio"], [role="radio"]');
                    radios.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const label = el.getAttribute('aria-label') || '';
                        result.push({
                            type: 'radio',
                            tag: el.tagName.toLowerCase(),
                            text: label,
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el)
                        });
                    });
                    
                    const tabs = document.querySelectorAll('[role="tab"], [role="tabpanel"]');
                    tabs.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const text = (el.textContent || '').trim().slice(0, 200);
                        result.push({
                            type: 'tab',
                            tag: el.tagName.toLowerCase(),
                            text: text,
                            id: el.id || '',
                            class: el.className || '',
                            attrs: getAttrs(el),
                            visible: visible,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            width: Math.round(rect.width), height: Math.round(rect.height),
                            interactive: true,
                            selector: getSelector(el)
                        });
                    });
                    
                    return result;
                })()
            """
            result = await self.eval_js(js)
            if result:
                file_logger.log(f"✅ Найдено {len(result)} интерактивных элементов", "INFO")
                return result
            return []
        except Exception as e:
            file_logger.log(f"❌ Ошибка сбора элементов: {e}", "ERROR")
            return []

    # ========== SNAPSHOT ==========
    async def get_snapshot(self):
        try:
            file_logger.log("📸 Делаю слепок страницы...", "INFO")
            await asyncio.sleep(5)
            
            interactive_elements = await self.get_all_interactive_elements()
            
            elements = await self.eval_js("""
                (function() {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    const important = [
                        'button', 'a', 'input', 'textarea', 'select', 'form',
                        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                        'iframe', 'div', 'span', 'section', 'article', 'nav',
                        'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li',
                        'table', 'tr', 'td', 'th', 'label', 'figure', 'figcaption',
                        'details', 'summary', 'dialog', 'menu', 'menuitem', 'time'
                    ];
                    
                    all.forEach(el => {
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && style.visibility !== 'hidden';
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        const text = (el.textContent || '').trim().slice(0, 200);
                        const isInteractive = (
                            tag === 'button' || tag === 'a' || attrs.role === 'button' ||
                            attrs.role === 'link' || attrs.role === 'menuitem' ||
                            tag === 'input' || tag === 'textarea' || tag === 'select'
                        );
                        if (important.includes(tag) || isInteractive || attrs['data-testid'] || attrs['aria-label']) {
                            result.push({
                                tag: tag, text: text, id: el.id || '', class: el.className || '',
                                attrs: attrs, visible: visible, x: Math.round(rect.x), y: Math.round(rect.y),
                                width: Math.round(rect.width), height: Math.round(rect.height),
                                isInteractive: isInteractive
                            });
                        }
                    });
                    return result;
                })()
            """)
            
            if elements is None:
                elements = []
            
            if interactive_elements:
                for el in interactive_elements:
                    exists = any(e.get('text') == el.get('text') and e.get('x') == el.get('x') for e in elements)
                    if not exists:
                        elements.append({
                            "tag": el.get('tag', 'unknown'),
                            "text": el.get('text', ''),
                            "type": el.get('type', 'unknown'),
                            "id": el.get('id', ''),
                            "class": el.get('class', ''),
                            "attrs": el.get('attrs', {}),
                            "visible": el.get('visible', True),
                            "x": el.get('x', 0), "y": el.get('y', 0),
                            "width": el.get('width', 0), "height": el.get('height', 0),
                            "isInteractive": True,
                            "selector": el.get('selector', ''),
                            "dataTestId": el.get('dataTestId', ''),
                            "ariaLabel": el.get('ariaLabel', '')
                        })
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            elements.sort(key=lambda x: x.get('visible', False), reverse=True)
            
            self.snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "elements": elements,
                "interactive": interactive_elements
            }
            
            file_logger.log(f"✅ Слепок: {len(elements)} элементов ({len(interactive_elements)} интерактивных)", "INFO")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка слепка: {e}", "ERROR")
            self.snapshot = {"title": "Ошибка", "url": "Ошибка", "total": 0, "elements": [], "interactive": []}
            return False

    # ========== КЛИК ==========
    async def click_element(self, target):
        try:
            if not await self.ensure_connection():
                return False
            
            english_target = translate_to_english(target)
            meaning = get_meaning(english_target)
            file_logger.log(f"🔍 Ищем '{target}' → '{english_target}'", "INFO")
            
            js = f"""
                (function() {{
                    const target = '{english_target}'.toLowerCase();
                    const meaning = '{meaning}' if '{meaning}' else '';
                    const elements = document.querySelectorAll('button, a, input, div[role="button"], [role="link"], [role="menuitem"], [role="tab"], input[type="submit"], [data-testid*="Tab"], [aria-label*="Home"], [aria-label*="Explore"]');
                    for (let el of elements) {{
                        const text = (el.textContent || el.value || '').trim().toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const title = (el.getAttribute('title') || '').toLowerCase();
                        const dataTestId = (el.getAttribute('data-testid') || '').toLowerCase();
                        const allText = text + ' ' + aria + ' ' + id + ' ' + cls + ' ' + title + ' ' + dataTestId;
                        if (allText.includes(target) || (meaning && allText.includes(meaning)) || text === target || aria === target) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }})()
            """
            result = await self.eval_js(js)
            if result:
                file_logger.log(f"✅ Кликнул по '{target}'", "INFO")
                return True
            else:
                file_logger.log(f"❌ Элемент '{target}' не найден", "WARNING")
                return False
        except Exception as e:
            file_logger.log(f"❌ Ошибка клика: {e}", "ERROR")
            return False

    # ========== ВВОД ТЕКСТА ==========
    async def type_text(self, text, field):
        try:
            if not await self.ensure_connection():
                return False
            
            english_field = translate_to_english(field)
            file_logger.log(f"🔍 Ищем поле '{field}' → '{english_field}'", "INFO")
            
            for field_id in GOOGLE_SEARCH_IDS:
                js = f"""
                    (function() {{
                        const el = document.getElementById('{field_id}');
                        if (el) {{
                            el.focus();
                            el.value = '';
                            el.value = '{text}';
                            const enterEvent = new KeyboardEvent('keydown', {{
                                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                                bubbles: true, cancelable: true, composed: true
                            }});
                            el.dispatchEvent(enterEvent);
                            return true;
                        }}
                        return false;
                    }})()
                """
                result = await self.eval_js(js)
                if result:
                    file_logger.log(f"✅ Ввел '{text}' в поле по ID: {field_id} + Enter", "INFO")
                    return True
            
            meaning = get_meaning(english_field)
            
            js = f"""
                (function() {{
                    const field = '{english_field}'.toLowerCase();
                    const meaning = '{meaning}' if '{meaning}' else '';
                    const elements = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                    for (let el of elements) {{
                        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const name = (el.getAttribute('name') || '').toLowerCase();
                        const type = (el.getAttribute('type') || '').toLowerCase();
                        const isMatch = (
                            placeholder.includes(field) || aria.includes(field) || id.includes(field) ||
                            cls.includes(field) || name.includes(field) || type === 'search' ||
                            name === 'q' || (meaning && (placeholder.includes(meaning) || aria.includes(meaning))) ||
                            placeholder.includes('search') || aria.includes('search')
                        );
                        if (isMatch) {{
                            el.focus();
                            el.value = '';
                            el.value = '{text}';
                            const enterEvent = new KeyboardEvent('keydown', {{
                                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                                bubbles: true, cancelable: true, composed: true
                            }});
                            el.dispatchEvent(enterEvent);
                            return true;
                        }}
                    }}
                    for (let el of elements) {{
                        if (el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button') {{
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                el.focus();
                                el.value = '';
                                el.value = '{text}';
                                const enterEvent = new KeyboardEvent('keydown', {{
                                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                                    bubbles: true, cancelable: true, composed: true
                                }});
                                el.dispatchEvent(enterEvent);
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }})()
            """
            result = await self.eval_js(js)
            if result:
                file_logger.log(f"✅ Ввел '{text}' в поле + Enter", "INFO")
                return True
            
            file_logger.log(f"❌ Поле '{field}' не найдено", "WARNING")
            return False
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка ввода: {e}", "ERROR")
            return False

    # ========== ОТПРАВКА ФОРМЫ ==========
    async def submit_form(self):
        try:
            if not await self.ensure_connection():
                return False
            
            js = """
                (function() {
                    const form = document.querySelector('form');
                    if (form) { form.submit(); return true; }
                    const submitBtn = document.querySelector('button[type="submit"], input[type="submit"]');
                    if (submitBtn) { submitBtn.click(); return true; }
                    const buttons = document.querySelectorAll('button, input[type="button"]');
                    for (let btn of buttons) {
                        const text = (btn.textContent || btn.value || '').toLowerCase();
                        if (text.includes('submit') || text.includes('search') || 
                            text.includes('login') || text.includes('sign in')) {
                            btn.click();
                            return true;
                        }
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

    # ========== СКРИНШОТ ==========
    async def screenshot(self):
        try:
            if not await self.ensure_connection():
                return None
            
            file_logger.log("📸 Делаю скриншот...", "INFO")
            
            await self.send("Emulation.setDeviceMetricsOverride", {
                "width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False, "scale": 1
            })
            
            quality = 80
            if self.snapshot and self.snapshot.get('total', 0) > 1000:
                quality = 60
            
            result = await self.send("Page.captureScreenshot", {
                "format": "jpeg", "quality": quality, "captureBeyondViewport": False
            })
            
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                size_kb = len(img_data) // 1024
                
                if size_kb > 500:
                    file_logger.log(f"⚠️ Скриншот {size_kb} KB, уменьшаю качество", "WARNING")
                    result = await self.send("Page.captureScreenshot", {
                        "format": "jpeg", "quality": 50, "captureBeyondViewport": False
                    })
                    if "result" in result and "data" in result["result"]:
                        img_data = base64.b64decode(result["result"]["data"])
                        file_logger.log(f"✅ Скриншот {len(img_data)//1024} KB (сжатый)", "INFO")
                        return img_data
                
                file_logger.log(f"✅ Скриншот {size_kb} KB", "INFO")
                return img_data
            
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

    async def wait_for_page_load(self):
        file_logger.log("⏳ Ожидаю загрузку...", "INFO")
        start_time = time.time()
        while time.time() - start_time < PAGE_LOAD_TIMEOUT:
            try:
                result = await self.send("Runtime.evaluate", {"expression": "document.readyState"})
                ready_state = result.get("result", {}).get("result", {}).get("value", "")
                if ready_state in ["complete", "interactive"]:
                    file_logger.log(f"✅ Страница загружена ({ready_state})", "INFO")
                    return True
            except Exception as e:
                file_logger.log(f"⚠️ Ошибка проверки: {e}", "WARNING")
            await asyncio.sleep(0.5)
        file_logger.log("⏰ Таймаут загрузки", "WARNING")
        return False

    async def navigate_and_screenshot(self, url):
        self.current_url = url
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        await self.connect()
        await self.apply_mask()
        
        cookies = get_cookies_for_url(url)
        if cookies:
            file_logger.log(f"🍪 Устанавливаю {len(cookies)} кук для {url}", "INFO")
            await self.set_cookies(cookies)
        
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

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    await update.message.reply_text(
        "👋 Привет! Я бот с ИИ-пониманием.\n\n"
        "🗣️ Говори как хочешь:\n"
        "• зайди на x.com\n"
        "• what buttons do you see?\n"
        "• нажми Обзор\n"
        "• введи текст в поиск\n\n"
        "🌐 Понимаю русский и английский!\n"
        "🍪 Авторизация на X.com!\n"
        "🔍 Находит все интерактивные элементы!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if 'memory' not in context.user_data:
        context.user_data['memory'] = Memory()
    memory = context.user_data['memory']
    
    # Приветствие
    if text.lower() in ['привет', 'здравствуй', 'hello', 'hi']:
        await update.message.reply_text("👋 Привет! Спрашивай что хочешь.")
        return
    
    # Помощь
    if text.lower() in ['помоги', 'что умеешь', 'help']:
        await update.message.reply_text(
            "🤖 Я умею:\n"
            "• зайди на сайт (с куками для X.com)\n"
            "• нажми на элемент (понимаю русский и английский)\n"
            "• показать все кнопки, ссылки, поля\n"
            "• ввести текст (автоматически Enter)\n"
            "• сделать скриншот\n\n"
            "🌐 Понимаю русский и английский!"
        )
        return
    
    thinking_msg = await update.message.reply_text("🤔 Думаю...")
    command = ask_ai_for_command(text, memory)
    action = command.get('action', 'unknown')
    
    # ====== FALLBACK ДЛЯ НЕИЗВЕСТНЫХ КОМАНД ======
    if action == 'unknown':
        text_lower = text.lower()
        if any(word in text_lower for word in ['кнопк', 'button', 'buttons', 'кнопки', 'кнопок']):
            action = 'ask'
            question = text
            command = {'action': 'ask', 'question': question}
            file_logger.log("🔄 Fallback: вопрос о кнопках", "INFO")
        elif any(word in text_lower for word in ['ссылк', 'link', 'links', 'ссылки', 'ссылок']):
            action = 'ask'
            question = text
            command = {'action': 'ask', 'question': question}
            file_logger.log("🔄 Fallback: вопрос о ссылках", "INFO")
        elif any(word in text_lower for word in ['пол', 'field', 'fields', 'input', 'поля', 'поле']):
            action = 'ask'
            question = text
            command = {'action': 'ask', 'question': question}
            file_logger.log("🔄 Fallback: вопрос о полях", "INFO")
        elif any(word in text_lower for word in ['what', 'where', 'how', 'why', 'when', 'which', 'who']):
            action = 'ask'
            question = text
            command = {'action': 'ask', 'question': question}
            file_logger.log("🔄 Fallback: английский вопрос", "INFO")
        elif any(word in text_lower for word in ['что', 'какие', 'какая', 'какой', 'где', 'когда', 'почему', 'сколько']):
            action = 'ask'
            question = text
            command = {'action': 'ask', 'question': question}
            file_logger.log("🔄 Fallback: русский вопрос", "INFO")
        else:
            await thinking_msg.edit_text(
                "❌ I didn't understand the command\n\n"
                "Examples:\n"
                "• go to x.com\n"
                "• what buttons do you see?\n"
                "• click Explore\n"
                "• type hello in search\n\n"
                "🌐 I understand both English and Russian!"
            )
            return
    
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
            await update.message.reply_photo(screenshot, caption=f"✅ {url}")
            memory.set_snapshot(browser.snapshot, url, browser.snapshot.get('title', 'Без названия'), browser)
            context.user_data['browser'] = browser
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Ошибка: {e}")
        return
    
    # ====== ВОПРОС ======
    if action == 'ask':
        question = command.get('question', text)
        if not memory.current_snapshot:
            await thinking_msg.edit_text("📭 Сначала загрузи страницу")
            return
        
        memory.add_action("question", {"question": question})
        await thinking_msg.edit_text("🤖 Анализирую страницу...")
        
        try:
            snapshot = memory.current_snapshot
            interactive = snapshot.get('interactive', [])[:50]
            
            context_text = "Interactive elements:\n"
            for el in interactive[:30]:
                text_el = el.get('text', '').strip()[:50]
                if text_el:
                    context_text += f"• {text_el}\n"
            
            answer = ask_ai_for_answer(question, context_text, memory)
            await thinking_msg.edit_text(f"🤖 Answer:\n\n{answer}")
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
        await thinking_msg.edit_text(f"🔘 Ищу '{target}'...")
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
                    await update.message.reply_photo(screenshot, caption=f"✅ После клика на '{target}'")
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
        await thinking_msg.edit_text(f"✏️ Ищу поле '{field}'...")
        try:
            result = await memory.browser.type_text(text_input, field)
            if result:
                memory.add_action("type", {"text": text_input, "field": field})
                await thinking_msg.edit_text(f"✅ Ввел '{text_input}' + Enter")
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
                    await update.message.reply_photo(screenshot, caption=f"✅ Результаты поиска '{text_input}'")
            else:
                await thinking_msg.edit_text("❌ Не нашел поле ввода")
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
                    await update.message.reply_photo(screenshot, caption="✅ После отправки формы")
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
                await update.message.reply_photo(screenshot, caption=f"✅ {memory.current_url}")
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
                await update.message.reply_photo(screenshot, caption=f"✅ {last_url}")
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
                    caption="📜 История"
                )
            os.remove('history_temp.txt')
        else:
            await update.message.reply_text(f"📜 **История:**\n\n{history_text}", parse_mode='Markdown')
        return
    
    # ====== ОЧИСТКА ======
    if action == 'clear':
        context.user_data['memory'] = Memory()
        await thinking_msg.edit_text("🧹 Память очищена!")
        return
    
    # ====== НЕИЗВЕСТНО ======
    if action == 'unknown':
        await thinking_msg.edit_text(
            "❌ Не понял команду\n\n"
            "Примеры:\n"
            "• зайди на x.com\n"
            "• what buttons do you see?\n"
            "• нажми Обзор\n"
            "• введи текст в поиск\n\n"
            "🌐 Я понимаю и русский, и английский!"
        )
        return
    
    # ====== ОШИБКА ======
    if action == 'error':
        await thinking_msg.edit_text(f"❌ Ошибка: {command.get('message', 'Неизвестная ошибка')}")
        return
    
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
    print("🚀 ЗАПУСК БОТА (ФИНАЛЬНАЯ ВЕРСИЯ)")
    print("="*50)
    print(f"📌 Chrome путь: {CHROME_PATH}")
    print("📦 WebSocket max_size: 50 МБ")
    print("🕵️ Маскировка: ВКЛЮЧЕНА")
    print("🍪 Куки: ВКЛЮЧЕНЫ (X.com)")
    print("🌐 AI перевод: ВКЛЮЧЕН")
    print("🔍 Поиск по data-testid, aria-label, role: ВКЛЮЧЕН")
    print("📊 Snapshot: ВСЕ ЭЛЕМЕНТЫ (без ограничений)")
    print("🔄 Auto-reconnect: ВКЛЮЧЕН")
    print("="*50)
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    if not AGNES_API_KEY:
        print("⚠️ AGNES_API_KEY не указан!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот готов!")
    print("🗣️ Говори как с человеком:")
    print("   • зайди на x.com")
    print("   • what buttons do you see?")
    print("   • нажми Обзор (AI переведет в Explore)")
    print("🔍 Находит все интерактивные элементы!")
    print("🔄 Автоматически восстанавливает WebSocket!")
    app.run_polling()

if __name__ == "__main__":
    main()