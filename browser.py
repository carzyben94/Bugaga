import os
import time
import json
import random
import asyncio
import subprocess
import base64
import requests
import websockets
from config import *

# ==================== ЛОГИРОВАНИЕ ====================
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

# ==================== МАСКИРОВКА ====================
def get_random_window_position():
    return {"left": random.randint(50, 300), "top": random.randint(50, 200),
            "width": random.randint(1200, 1920), "height": random.randint(800, 1080)}

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return random.choice(user_agents)

def get_launch_args():
    window = get_random_window_position()
    user_agent = get_random_user_agent()
    return [
        CHROME_PATH, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled", "--disable-automation",
        "--use-gl=egl", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
        "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials", "--disable-default-apps", "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-client-side-phishing-detection", "--disable-crash-reporter",
        "--disable-component-update", "--disable-logging", "--disable-prompt-on-repost",
        "--disable-sync", "--disable-background-networking",
        "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
        "--disable-breakpad", "--disable-ipc-flooding-protection",
        "--disable-renderer-backgrounding",
        f"--window-position={window['left']},{window['top']}",
        f"--window-size={window['width']},{window['height']}",
        "--no-default-browser-check", "--no-first-run", "--force-color-profile=srgb",
        "--metrics-recording-only", "--password-store=basic", "--use-mock-keychain",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        f"--user-agent={user_agent}", f"--remote-debugging-port={CDP_PORT}"
    ]

def get_mask_js():
    return """
    (function() {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true, enumerable: true });
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                function Plugin(name, filename, description) {
                    this.name = name; this.filename = filename; this.description = description;
                }
                Plugin.prototype.item = function(index) { return this[index] || null; };
                Plugin.prototype.namedItem = function(name) { return this[name] || null; };
                const plugins = new Array();
                Object.setPrototypeOf(plugins, Plugin.prototype);
                plugins.push(new Plugin('Chrome PDF Plugin', 'internal-pdf-viewer', 'Portable Document Format'));
                plugins.push(new Plugin('Chrome PDF Viewer', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', ''));
                plugins.push(new Plugin('Native Client', 'internal-nacl-plugin', ''));
                plugins.length = 3;
                return plugins;
            },
            configurable: true,
            enumerable: true
        });
        console.log('✅ 100% маскировка применена');
    })()
    """

# ==================== УПРАВЛЕНИЕ CHROME ====================
def find_chrome():
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

def ensure_browser():
    file_logger.log("🔍 Проверяю Chrome...", "INFO")
    try:
        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
        if resp.status_code == 200:
            file_logger.log("✅ Chrome уже запущен", "INFO")
            return True
    except:
        pass
    
    chrome_path = find_chrome()
    if not chrome_path:
        file_logger.log("❌ Chrome не найден!", "ERROR")
        return False
    
    global CHROME_PATH
    CHROME_PATH = chrome_path
    
    file_logger.log("🔄 Запускаю Chrome с маскировкой", "INFO")
    try:
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
        time.sleep(2)
        subprocess.Popen(get_launch_args(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        for i in range(5):
            try:
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
                if resp.status_code == 200:
                    file_logger.log("✅ Chrome запущен!", "INFO")
                    return True
            except:
                pass
            time.sleep(1)
        return False
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return False

# ==================== DOM ПАРСЕР ====================
class DOMParser:
    @staticmethod
    async def get_all_interactive(cdp):
        js = """
            (function() {
                const result = [];
                function getSelector(el) {
                    if (el.id) return '#' + el.id;
                    if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
                    const aria = el.getAttribute('aria-label');
                    if (aria && /^[a-zA-Z0-9\\s\\-_\\.]+$/.test(aria)) return '[aria-label="' + aria + '"]';
                    if (el.className) {
                        const classes = el.className.split(' ').filter(c => c);
                        if (classes.length > 0) return '.' + classes.join('.');
                    }
                    return el.tagName.toLowerCase();
                }
                function getAttrs(el) {
                    const attrs = {};
                    for (const attr of el.attributes) attrs[attr.name] = attr.value;
                    return attrs;
                }
                const selectors = [
                    'button', 'input[type="submit"]', 'input[type="button"]', 'input[type="reset"]',
                    'div[role="button"]', 'span[role="button"]', 'a[role="button"]',
                    '[role="button"]', '[role="menuitem"]', '[role="tab"]', '[role="link"]',
                    '[role="checkbox"]', '[role="radio"]', '[role="switch"]', '[role="option"]',
                    '[data-testid="AppTabBar_Home_Link"]', '[data-testid="AppTabBar_Explore_Link"]',
                    '[data-testid="AppTabBar_Notifications_Link"]', '[data-testid="AppTabBar_Messages_Link"]',
                    '[data-testid="SideNav_AccountSwitcher_Button"]', '[data-testid="compose-tweet-button"]',
                    '[data-testid="Search"]',
                    '[aria-label*="Home"]', '[aria-label*="Explore"]', '[aria-label*="Notifications"]',
                    '[aria-label*="Messages"]', '[aria-label*="Profile"]', '[aria-label*="More"]',
                    '[aria-label*="Post"]', '[aria-label*="Tweet"]', '[aria-label*="Search"]'
                ];
                document.querySelectorAll(selectors.join(',')).forEach(el => {
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
                return result;
            })()
        """
        return await cdp.eval_js(js) or []

    @staticmethod
    async def get_page_elements(cdp):
        js = """
            (function() {
                const result = [];
                const important = ['button','a','input','textarea','select','form','h1','h2','h3','h4','h5','h6','p','img','video','iframe','div','span','section','article','nav','header','footer','main','aside','ul','ol','li','table','tr','td','th','label','figure','figcaption','details','summary','dialog','menu','menuitem','time'];
                document.querySelectorAll('*').forEach(el => {
                    const tag = el.tagName.toLowerCase();
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    const attrs = {};
                    for (const attr of el.attributes) attrs[attr.name] = attr.value;
                    const text = (el.textContent || '').trim().slice(0, 200);
                    const isInteractive = tag === 'button' || tag === 'a' || attrs.role === 'button' || attrs.role === 'link' || attrs.role === 'menuitem' || tag === 'input' || tag === 'textarea' || tag === 'select';
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
        """
        return await cdp.eval_js(js) or []

    @staticmethod
    async def get_page_info(cdp):
        title = await cdp.eval_js("document.title") or "Нет заголовка"
        url = await cdp.eval_js("window.location.href") or "Нет URL"
        return title, url

    @staticmethod
    async def open_search_on_x(cdp):
        """Открывает поле поиска на X.com"""
        if await cdp.eval_js('document.querySelector(\'input[placeholder="Search"]\') !== null'):
            return True
        
        if await cdp.eval_js('''
            (function() {
                const btn = document.querySelector('[data-testid="Search"], button[aria-label="Search"]');
                if (btn) { btn.click(); return true; }
                return false;
            })()
        '''):
            for i in range(10):
                await asyncio.sleep(0.5)
                if await cdp.eval_js('document.querySelector(\'input[placeholder="Search"]\') !== null'):
                    return True
        return False

# ==================== CDP КЛИЕНТ ====================
class Browser:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.current_url = None
        self.snapshot = {}

    def _get_or_create_tab(self, url=None):
        try:
            full_url = f"http://localhost:{CDP_PORT}/json/new{('?' + url) if url else ''}"
            resp = requests.put(full_url, timeout=3)
            if resp.status_code == 405:
                resp = requests.post(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            if resp.status_code == 405:
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
            tab = resp.json()
            return tab["webSocketDebuggerUrl"], tab["id"]
        except Exception as e:
            raise Exception(f"Ошибка создания вкладки: {e}")

    async def connect(self):
        if not ensure_browser():
            raise Exception("❌ Chrome не доступен")
        
        ws_url, _ = self._get_or_create_tab()
        self.ws = await websockets.connect(ws_url, max_size=WEBSOCKET_MAX_SIZE, ping_interval=20, ping_timeout=10)
        
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        
        await self.eval_js(get_mask_js())
        file_logger.log("✅ Браузер подключен и замаскирован", "INFO")

    async def send(self, method, params=None):
        self.msg_id += 1
        await self.ws.send(json.dumps({"id": self.msg_id, "method": method, "params": params or {}}))
        while True:
            data = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if data.get("id") == self.msg_id:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data

    async def eval_js(self, script):
        try:
            result = await self.send("Runtime.evaluate", {"expression": script, "returnByValue": True})
            return result.get("result", {}).get("result", {}).get("value")
        except:
            return None

    async def ensure_connection(self):
        try:
            if not self.ws:
                await self.connect()
                if self.current_url:
                    await self.send("Page.navigate", {"url": self.current_url})
                    await self.wait_for_page_load()
                    await self.get_snapshot()
                return True
            await self.ws.ping()
            return True
        except:
            file_logger.log("🔄 Переподключение...", "WARNING")
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
            await self.connect()
            if self.current_url:
                await self.send("Page.navigate", {"url": self.current_url})
                await self.wait_for_page_load()
                await self.get_snapshot()
            return True

    async def set_cookies(self, cookies_list):
        if not cookies_list:
            return True
        cdp_cookies = [{
            "name": c.get("name"), "value": c.get("value"),
            "domain": c.get("domain"), "path": c.get("path", "/"),
            "secure": c.get("secure", False), "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "unspecified"), "session": c.get("session", True)
        } for c in cookies_list]
        await self.send("Network.setCookies", {"cookies": cdp_cookies})
        return True

    async def wait_for_page_load(self):
        start = time.time()
        while time.time() - start < PAGE_LOAD_TIMEOUT:
            try:
                result = await self.send("Runtime.evaluate", {"expression": "document.readyState"})
                state = result.get("result", {}).get("result", {}).get("value", "")
                if state in ["complete", "interactive"]:
                    return True
            except:
                pass
            await asyncio.sleep(0.5)
        return False

    async def get_snapshot(self):
        await asyncio.sleep(5)
        interactive = await DOMParser.get_all_interactive(self)
        elements = await DOMParser.get_page_elements(self) or []
        
        # Объединяем
        for el in interactive:
            if not any(e.get('text') == el.get('text') and e.get('x') == el.get('x') for e in elements):
                elements.append({
                    "tag": el.get('tag', 'unknown'),
                    "text": el.get('text', ''),
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
        
        title, url = await DOMParser.get_page_info(self)
        
        elements.sort(key=lambda x: (
            (x.get('visible', False) and x.get('isInteractive', False)) * 100 +
            (x.get('visible', False)) * 10 +
            (x.get('isInteractive', False)) * 1
        ), reverse=True)
        
        self.snapshot = {
            "title": title, "url": url,
            "total": len(elements),
            "elements": elements,
            "interactive": interactive
        }
        return True

    async def click_element(self, target, memory=None):
        if not await self.ensure_connection():
            return False
        
        # Поиск через память
        if memory:
            found = memory.find_element_by_text(target)
            if found and found.get('selector'):
                js = f"document.querySelector('{found['selector']}')?.click()"
                if await self.eval_js(js):
                    file_logger.log(f"✅ Кликнул по '{target}'", "INFO")
                    return True
        
        # Поиск в DOM
        js = f"""
            (function() {{
                const target = '{target}'.toLowerCase();
                for (let el of document.querySelectorAll('button, a, input, div[role="button"], [role="link"], [role="menuitem"], [role="tab"], input[type="submit"], [data-testid*="Tab"], [data-testid="Search"]')) {{
                    const text = ((el.textContent || el.value || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.id || '') + ' ' + (el.className || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('data-testid') || '')).toLowerCase();
                    if (text.includes(target)) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
        """
        if await self.eval_js(js):
            file_logger.log(f"✅ Кликнул по '{target}'", "INFO")
            return True
        return False

    async def type_text(self, text, field):
        if not await self.ensure_connection():
            return False
        
        # X.com - открываем поиск
        if self.current_url and 'x.com' in self.current_url:
            if 'search' in field.lower() or 'поиск' in field.lower():
                await DOMParser.open_search_on_x(self)
                await asyncio.sleep(1)
        
        # Google search IDs
        for field_id in GOOGLE_SEARCH_IDS:
            js = f"""
                (function() {{
                    const el = document.getElementById('{field_id}');
                    if (el) {{
                        el.focus(); el.value = ''; el.value = '{text}';
                        el.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true, composed:true}}));
                        return true;
                    }}
                    return false;
                }})()
            """
            if await self.eval_js(js):
                file_logger.log(f"✅ Ввел '{text}' в {field_id}", "INFO")
                return True
        
        # Поиск по атрибутам
        js = f"""
            (function() {{
                const field = '{field}'.toLowerCase();
                for (let el of document.querySelectorAll('input, textarea, [contenteditable="true"]')) {{
                    const attrs = ((el.getAttribute('placeholder') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.id || '') + ' ' + (el.className || '') + ' ' + (el.getAttribute('name') || '') + ' ' + (el.getAttribute('type') || '')).toLowerCase();
                    if (attrs.includes(field) || attrs.includes('search')) {{
                        el.focus(); el.value = ''; el.value = '{text}';
                        el.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true, composed:true}}));
                        return true;
                    }}
                }}
                for (let el of document.querySelectorAll('input, textarea')) {{
                    if (el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button') {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            el.focus(); el.value = ''; el.value = '{text}';
                            el.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true, composed:true}}));
                            return true;
                        }}
                    }}
                }}
                return false;
            }})()
        """
        if await self.eval_js(js):
            file_logger.log(f"✅ Ввел '{text}' в поле", "INFO")
            return True
        return False

    async def screenshot(self):
        if not await self.ensure_connection():
            return None
        
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False, "scale": 1
        })
        
        quality = 60 if self.snapshot and self.snapshot.get('total', 0) > 1000 else 80
        result = await self.send("Page.captureScreenshot", {
            "format": "jpeg", "quality": quality, "captureBeyondViewport": False
        })
        
        if "result" in result and "data" in result["result"]:
            return base64.b64decode(result["result"]["data"])
        return None

    async def navigate_and_screenshot(self, url):
        self.current_url = url
        await self.connect()
        
        cookies = get_cookies_for_url(url)
        if cookies:
            await self.set_cookies(cookies)
        
        await self.send("Page.navigate", {"url": url})
        await self.wait_for_page_load()
        await self.get_snapshot()
        
        screenshot = await self.screenshot()
        if not screenshot:
            raise Exception("Не удалось получить скриншот")
        return screenshot