# stealth.py - Полная маскировка + CDP клиент (как в Pydoll)

import os
import json
import logging
import asyncio
import subprocess
import requests
import base64
import websockets
import random
import math
import time
from typing import Optional, List, Dict, Any, Callable, Tuple, Union
from dataclasses import dataclass, field

# ============================================================
# 1. КОНФИГУРАЦИИ
# ============================================================

@dataclass
class TimingConfig:
    keystroke_min: float = 0.04
    keystroke_max: float = 0.15
    punctuation_delay: float = 0.08
    thinking_probability: float = 0.03
    thinking_delay_min: float = 0.3
    thinking_delay_max: float = 0.7
    error_probability: float = 0.02
    mouse_speed_min: float = 0.005
    mouse_speed_max: float = 0.015
    click_delay_min: float = 0.05
    click_delay_max: float = 0.15


@dataclass
class StealthConfig:
    browser: str = 'chrome'
    os: str = 'windows'
    headless: bool = True
    proxy: str = None
    user_agent: str = None


# ============================================================
# 2. МАСКИРОВКА (Stealth)
# ============================================================

class Stealth:
    """Полная маскировка как в Pydoll"""
    
    SCRIPTS = [
        # navigator.webdriver
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        """,
        # navigator.plugins
        """
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ];
                plugins.__proto__ = PluginArray.prototype;
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                plugins.refresh = () => {};
                return plugins;
            },
            configurable: true
        });
        """,
        # navigator.languages
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en', 'ru'],
            configurable: true
        });
        """,
        # window.chrome
        """
        if (!window.chrome) {
            window.chrome = {
                runtime: {
                    onStartup: { addListener: () => {} },
                    onInstalled: { addListener: () => {} },
                    getManifest: () => ({ version: '120.0.0.0' })
                },
                loadTimes: () => ({
                    requestTime: Date.now() / 1000,
                    startLoadTime: Date.now() / 1000,
                    commitLoadTime: Date.now() / 1000,
                    finishDocumentLoadTime: Date.now() / 1000,
                    finishLoadTime: Date.now() / 1000,
                    firstPaintTime: Date.now() / 1000,
                    firstPaintAfterLoadTime: Date.now() / 1000,
                    navigationType: 'Reload',
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated: true,
                    npnNegotiatedProtocol: 'h2',
                    wasAlternateProtocolAvailable: true,
                    connectionInfo: 'h2'
                }),
                csi: () => ({ startE: Date.now(), onloadT: Date.now(), pageT: Date.now() }),
                app: { isInstalled: false }
            };
        }
        """,
        # WebGL
        """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            const params = {
                37445: 'Intel Inc.',
                37446: 'Intel Iris OpenGL Engine',
                37447: 'WebGL 2.0',
                37448: 'WebGL 2.0 (OpenGL ES 3.0 Intel)',
                37449: 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 3.0)'
            };
            if (params[parameter]) return params[parameter];
            return getParameter.call(this, parameter);
        };
        """,
        # screen
        """
        Object.defineProperty(screen, 'availWidth', { get: () => 1280, configurable: true });
        Object.defineProperty(screen, 'availHeight', { get: () => 720, configurable: true });
        Object.defineProperty(screen, 'width', { get: () => 1280, configurable: true });
        Object.defineProperty(screen, 'height', { get: () => 720, configurable: true });
        """,
        # navigator.platform
        """
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
            configurable: true
        });
        """,
        # navigator.hardwareConcurrency
        """
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
            configurable: true
        });
        """,
        # navigator.deviceMemory
        """
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: true
        });
        """,
        # window.outerWidth/Height (для headless)
        """
        Object.defineProperty(window, 'outerWidth', {
            get: () => window.innerWidth + 16,
            configurable: true
        });
        Object.defineProperty(window, 'outerHeight', {
            get: () => window.innerHeight + 39,
            configurable: true
        });
        """,
        # canvas fingerprint
        """
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
            if (this.width === 256 && this.height === 256) {
                return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
            }
            return originalToDataURL.call(this, type, quality);
        };
        """,
        # console.log suppression
        """
        if (window.console) {
            const originalLog = console.log;
            console.log = function() {
                const args = Array.from(arguments);
                const blocked = ['headless', 'webdriver', 'automation', 'puppeteer'];
                if (args.some(arg => typeof arg === 'string' && 
                    blocked.some(b => arg.toLowerCase().includes(b)))) {
                    return;
                }
                originalLog.apply(console, args);
            };
        }
        """,
        # WebRTC
        """
        if (window.RTCPeerConnection) {
            const originalCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
            RTCPeerConnection.prototype.createDataChannel = function(label, options) {
                return originalCreateDataChannel.call(this, label, options);
            };
        }
        """,
        # navigator.permissions
        """
        if (window.navigator.permissions) {
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => {
                const denied = ['notifications', 'geolocation', 'camera', 'microphone'];
                if (denied.includes(params.name)) {
                    return Promise.resolve({ state: 'prompt', onchange: null });
                }
                return originalQuery.call(this, params);
            };
        }
        """,
    ]
    
    @classmethod
    def get_scripts_for_cdp(cls) -> List[Dict]:
        return [{'source': script} for script in cls.SCRIPTS]
    
    @classmethod
    def get_chrome_flags(cls, headless: bool = True) -> List[str]:
        flags = [
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-setuid-sandbox',
            '--no-sandbox',
            '--window-size=1280,720',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process,TranslateUI',
            '--disable-web-security',
            '--allow-running-insecure-content',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-breakpad',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--disable-domain-reliability',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--force-color-profile=srgb',
            '--ignore-certificate-errors',
            '--ignore-ssl-errors',
            '--mute-audio',
            '--password-store=basic',
            '--use-fake-device-for-media-stream',
            '--use-fake-ui-for-media-stream',
            '--enable-features=NetworkService,NetworkServiceInProcess',
            '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
            '--enable-webrtc-srtp-aes-gcm',
            '--disable-accelerated-2d-canvas',
            '--disable-accelerated-video-decode',
            '--disable-application-cache',
            '--disable-cache',
            '--disable-databases',
            '--disable-file-system',
            '--disable-java',
            '--disable-local-storage',
            '--disable-session-storage',
            '--disk-cache-size=0',
            '--media-cache-size=0',
        ]
        if headless:
            flags.append('--headless=new')
        return flags
    
    @classmethod
    def get_preferences(cls) -> Dict:
        return {
            'default_content_setting_values': {
                'cookies': 1, 'images': 1, 'javascript': 1, 'plugins': 1,
                'popups': 2, 'geolocation': 1, 'notifications': 2,
                'media_stream': 2, 'media_stream_mic': 2, 'media_stream_camera': 2,
            },
            'password_manager_enabled': False,
            'autofill_enabled': False,
            'translate_enabled': False,
            'safe_browsing_enabled': True,
            'spellcheck_enabled': True,
        }
    
    @classmethod
    def get_user_agent(cls) -> str:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ============================================================
# 3. BEZIER CURVE (для человеческого движения)
# ============================================================

class BezierCurve:
    @staticmethod
    def cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
        return (1-t)**3 * p0 + 3*(1-t)**2*t * p1 + 3*(1-t)*t**2 * p2 + t**3 * p3
    
    @staticmethod
    def generate_points(start: Tuple[float, float], end: Tuple[float, float],
                        num_points: int = 30, spread: float = 20) -> List[Tuple[float, float]]:
        points = []
        cx1 = start[0] + (end[0] - start[0]) * random.uniform(0.3, 0.7)
        cy1 = start[1] + (end[1] - start[1]) * random.uniform(0.3, 0.7)
        cx2 = start[0] + (end[0] - start[0]) * random.uniform(0.3, 0.7)
        cy2 = start[1] + (end[1] - start[1]) * random.uniform(0.3, 0.7)
        for i in range(num_points):
            t = i / (num_points - 1)
            x = BezierCurve.cubic_bezier(t, start[0], cx1, cx2, end[0])
            y = BezierCurve.cubic_bezier(t, start[1], cy1, cy2, end[1])
            if i > 0 and i < num_points - 1:
                x += random.gauss(0, spread / 20)
                y += random.gauss(0, spread / 20)
            points.append((int(x), int(y)))
        return points


# ============================================================
# 4. HUMAN BEHAVIOR
# ============================================================

class HumanBehavior:
    @staticmethod
    async def human_click(page, x: float, y: float, button: str = "left",
                          config: TimingConfig = None):
        if config is None:
            config = TimingConfig()
        try:
            result = await page.connection.send_command("Runtime.evaluate", {
                "expression": "window.innerWidth/2, window.innerHeight/2",
                "returnByValue": True
            })
            current_pos = result.get('result', {}).get('value', (200, 200))
            start_x, start_y = current_pos if isinstance(current_pos, tuple) else (200, 200)
        except:
            start_x, start_y = random.randint(100, 500), random.randint(100, 500)
        
        points = BezierCurve.generate_points((start_x, start_y), (x, y),
                                             num_points=random.randint(20, 40), spread=30)
        for px, py in points:
            await page.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": px, "y": py
            })
            await asyncio.sleep(random.uniform(config.mouse_speed_min, config.mouse_speed_max))
        
        await asyncio.sleep(random.uniform(config.click_delay_min, config.click_delay_max))
        await page.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": 1
        })
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await page.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": 1
        })
    
    @staticmethod
    async def human_type(page, text: str, config: TimingConfig = None):
        if config is None:
            config = TimingConfig()
        for i, char in enumerate(text):
            if char in '.!?;:,' and random.random() < 0.4:
                await asyncio.sleep(random.uniform(0.1, 0.25))
            if random.random() < config.error_probability and char.isalpha():
                keyboard_rows = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
                for row in keyboard_rows:
                    if char.lower() in row:
                        idx = row.index(char.lower())
                        wrong_char = row[idx - 1] if idx > 0 and random.random() < 0.5 else \
                                    row[idx + 1] if idx < len(row) - 1 else char
                        break
                else:
                    wrong_char = char
                await page.connection.send_command("Input.insertText", {"text": wrong_char})
                await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.connection.send_command("Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": "Backspace", "code": "Backspace"
                })
                await page.connection.send_command("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": "Backspace", "code": "Backspace"
                })
                await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
            await page.connection.send_command("Input.insertText", {"text": char})
            await asyncio.sleep(random.uniform(config.keystroke_min, config.keystroke_max))
            if random.random() < config.thinking_probability:
                await asyncio.sleep(random.uniform(config.thinking_delay_min, config.thinking_delay_max))


# ============================================================
# 5. CDP CONNECTION
# ============================================================

class CDPConnection:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.websocket = None
        self.message_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._listener_task = None
    
    async def connect(self):
        self.websocket = await websockets.connect(self.ws_url)
        self._listener_task = asyncio.create_task(self._listen())
        return self
    
    async def _listen(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_id = data.get('id')
                if msg_id and msg_id in self._callbacks:
                    future = self._callbacks.pop(msg_id)
                    if 'error' in data:
                        future.set_exception(Exception(data['error'].get('message', 'CDP Error')))
                    else:
                        future.set_result(data)
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def send_command(self, method: str, params: Dict = None) -> Dict:
        self.message_id += 1
        msg_id = self.message_id
        message = {"id": msg_id, "method": method, "params": params or {}}
        future = asyncio.get_event_loop().create_future()
        self._callbacks[msg_id] = future
        await self.websocket.send(json.dumps(message))
        return await future
    
    async def close(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self.websocket:
            await self.websocket.close()


# ============================================================
# 6. CDP PAGE
# ============================================================

class CDPPage:
    def __init__(self, page_id: str, ws_url: str):
        self.id = page_id
        self.ws_url = ws_url
        self.connection = CDPConnection(ws_url)
        self._is_connected = False
    
    async def connect(self):
        await self.connection.connect()
        await self.connection.send_command("Page.enable")
        await self.connection.send_command("DOM.enable")
        await self.connection.send_command("Runtime.enable")
        await self.connection.send_command("Network.enable")
        await self.connection.send_command("Emulation.setDeviceMetricsOverride", {
            "width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False
        })
        # Применяем маскировку
        for script in Stealth.get_scripts_for_cdp():
            await self.connection.send_command("Runtime.evaluate", script)
        self._is_connected = True
        return self
    
    async def goto(self, url: str):
        return await self.connection.send_command("Page.navigate", {"url": url})
    
    async def evaluate(self, expression: str) -> Any:
        result = await self.connection.send_command("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True
        })
        return result.get('result', {}).get('value')
    
    async def screenshot(self) -> bytes:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        result = await self.connection.send_command("Page.captureScreenshot", {
            "format": "png", "quality": 100, "captureBeyondViewport": False, "fromSurface": True
        })
        return base64.b64decode(result.get('result', {}).get('data', ''))
    
    async def click(self, selector: str, humanize: bool = True, config: TimingConfig = None):
        result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
        root = result.get('root', {}).get('nodeId')
        result = await self.connection.send_command("DOM.querySelector", {
            "nodeId": root, "selector": selector
        })
        node_id = result.get('nodeId')
        if not node_id:
            return False
        result = await self.connection.send_command("DOM.getBoxModel", {"nodeId": node_id})
        content = result.get('model', {}).get('content')
        if not content:
            return False
        x = (content[0] + content[4]) / 2 + random.uniform(-10, 10)
        y = (content[1] + content[5]) / 2 + random.uniform(-10, 10)
        if humanize:
            await HumanBehavior.human_click(self, x, y, "left", config)
        else:
            await self.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
            })
            await asyncio.sleep(0.05)
            await self.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
            })
        return True
    
    async def type_text(self, selector: str, text: str, humanize: bool = True,
                        config: TimingConfig = None):
        result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
        root = result.get('root', {}).get('nodeId')
        result = await self.connection.send_command("DOM.querySelector", {
            "nodeId": root, "selector": selector
        })
        node_id = result.get('nodeId')
        if not node_id:
            return False
        await self.connection.send_command("DOM.focus", {"nodeId": node_id})
        await asyncio.sleep(random.uniform(0.1, 0.3))
        if humanize:
            await HumanBehavior.human_type(self, text, config)
        else:
            await self.connection.send_command("Input.insertText", {"text": text})
        return True
    
    async def html(self) -> str:
        return await self.evaluate("document.documentElement.outerHTML")
    
    async def title(self) -> str:
        return await self.evaluate("document.title")
    
    async def url(self) -> str:
        return await self.evaluate("location.href")
    
    async def scroll_to_bottom(self, humanize: bool = True):
        height = await self.evaluate("document.body.scrollHeight")
        vh = await self.evaluate("window.innerHeight")
        if humanize:
            steps = random.randint(15, 25)
            for i in range(steps):
                progress = (i + 1) / steps
                eased = progress * progress * (3 - 2 * progress)
                current = min(height * eased, height - vh)
                await self.evaluate(f"window.scrollTo(0, {current})")
                await asyncio.sleep(random.uniform(0.03, 0.08))
                if random.random() < 0.05:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
        else:
            await self.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    
    async def close(self):
        await self.connection.close()


# ============================================================
# 7. CDP BROWSER
# ============================================================

class CDPBrowser:
    def __init__(self):
        self.chrome_process = None
        self.pages: List[CDPPage] = []
        self.current_page: Optional[CDPPage] = None
    
    def get_debugger_url(self) -> Optional[str]:
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=2)
            return resp.json().get("webSocketDebuggerUrl")
        except:
            return None
    
    def get_pages_list(self) -> List[Dict]:
        try:
            resp = requests.get("http://localhost:9222/json/list")
            return resp.json()
        except:
            return []
    
    async def launch(self, headless: bool = True):
        chrome_cmd = '/usr/bin/chromium'
        if not os.path.exists(chrome_cmd):
            return False, f"❌ Chromium не найден: {chrome_cmd}"
        if self.get_debugger_url():
            return True, "✅ Chrome уже запущен"
        
        cmd = [chrome_cmd] + Stealth.get_chrome_flags(headless)
        self.chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        for _ in range(15):
            await asyncio.sleep(1)
            if self.get_debugger_url():
                return True, f"✅ Chrome запущен (headless={headless})"
        return False, "❌ Не удалось запустить Chrome"
    
    async def new_page(self, url: str = "about:blank") -> Optional[CDPPage]:
        try:
            await asyncio.sleep(random.uniform(0.1, 0.5))
            resp = requests.get(f"http://localhost:9222/json/new?{url}")
            if resp.status_code == 200:
                data = resp.json()
                page = CDPPage(data.get('id'), data.get('webSocketDebuggerUrl'))
                await page.connect()
                self.pages.append(page)
                self.current_page = page
                return page
        except Exception as e:
            logging.error(f"Ошибка создания страницы: {e}")
        return None
    
    def get_first_page(self) -> Optional[CDPPage]:
        pages = self.get_pages_list()
        if pages:
            page_id = pages[0].get('id')
            ws_url = pages[0].get('webSocketDebuggerUrl')
            return CDPPage(page_id, ws_url)
        return None
    
    async def close(self):
        for page in self.pages:
            await page.close()
        if self.chrome_process:
            self.chrome_process.terminate()


# ============================================================
# 8. ГЛОБАЛЬНЫЙ КЛИЕНТ (для использования в bot.py)
# ============================================================

browser = CDPBrowser()
current_page: Optional[CDPPage] = None
timing_config = TimingConfig()

async def ensure_browser():
    global current_page
    if current_page and current_page._is_connected:
        try:
            await current_page.evaluate("1")
            return True, "✅ Уже подключен"
        except:
            current_page = None
    
    success, msg = await browser.launch(headless=True)
    if not success:
        return False, msg
    
    page = browser.get_first_page()
    if page:
        await page.connect()
        current_page = page
        browser.current_page = page
        return True, "✅ Подключен"
    
    page = await browser.new_page()
    if page:
        current_page = page
        return True, "✅ Создана новая страница"
    
    return False, "❌ Не удалось получить страницу"