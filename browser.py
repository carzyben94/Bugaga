import asyncio
import json
import websockets
import requests
import re
import random
import time
from typing import Optional, List, Dict, Any

class BrowserManager:
    def __init__(self, host='localhost', port=9222):
        self.host = host
        self.port = port
        self.ws = None
        self.ws_url = None
        self._message_id = 0
        self._connected = False
        self._page_id = None
        self._current_url = ""
        self._masked = False
        
        self.viewport_width = 1280
        self.viewport_height = 720
        self.timeout = 60
    
    # ========== МАСКИРОВКА ==========
    
    def get_random_window_position(self):
        return {
            "left": random.randint(50, 300),
            "top": random.randint(50, 200),
            "width": random.randint(1200, 1920),
            "height": random.randint(800, 1080)
        }
    
    def get_random_user_agent(self):
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]
        return random.choice(user_agents)
    
    def get_random_webgl_vendor(self):
        vendors = [
            "Google Inc. (NVIDIA)",
            "Google Inc. (AMD)",
            "Google Inc. (Intel)",
            "NVIDIA Corporation",
            "Advanced Micro Devices, Inc.",
            "Intel Corporation"
        ]
        return random.choice(vendors)
    
    def get_random_webgl_renderer(self):
        renderers = [
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ]
        return random.choice(renderers)
    
    def get_random_location(self):
        cities = [
            {"name": "New York", "lat": 40.7128, "lng": -74.0060, "timezone": "America/New_York", "lang": "en-US"},
            {"name": "London", "lat": 51.5074, "lng": -0.1278, "timezone": "Europe/London", "lang": "en-GB"},
            {"name": "Paris", "lat": 48.8566, "lng": 2.3522, "timezone": "Europe/Paris", "lang": "fr-FR"},
            {"name": "Berlin", "lat": 52.5200, "lng": 13.4050, "timezone": "Europe/Berlin", "lang": "de-DE"},
            {"name": "Tokyo", "lat": 35.6762, "lng": 139.6503, "timezone": "Asia/Tokyo", "lang": "ja-JP"},
            {"name": "Sydney", "lat": -33.8688, "lng": 151.2093, "timezone": "Australia/Sydney", "lang": "en-AU"},
            {"name": "Moscow", "lat": 55.7558, "lng": 37.6173, "timezone": "Europe/Moscow", "lang": "ru-RU"},
            {"name": "Dubai", "lat": 25.2048, "lng": 55.2708, "timezone": "Asia/Dubai", "lang": "ar-AE"},
            {"name": "Singapore", "lat": 1.3521, "lng": 103.8198, "timezone": "Asia/Singapore", "lang": "en-SG"},
            {"name": "Los Angeles", "lat": 34.0522, "lng": -118.2437, "timezone": "America/Los_Angeles", "lang": "en-US"},
        ]
        return random.choice(cities)
    
    def get_launch_args(self, chrome_path):
        window = self.get_random_window_position()
        user_agent = self.get_random_user_agent()
        
        args = [
            chrome_path,
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
            f"--remote-debugging-port={self.port}"
        ]
        
        return args
    
    # ========== ГЕОЛОКАЦИЯ ==========
    
    async def set_geolocation(self, lat: float = None, lng: float = None):
        await self.connect()
        
        if lat is None or lng is None:
            location = self.get_random_location()
            lat = location["lat"]
            lng = location["lng"]
        
        await self._send_command("Emulation.setGeolocationOverride", {
            "latitude": lat,
            "longitude": lng,
            "accuracy": random.randint(10, 100)
        })
        
        print(f"📍 Геолокация установлена: {lat}, {lng}")
        return f"📍 Геолокация: {lat}, {lng}"
    
    async def set_timezone(self, timezone: str = None):
        await self.connect()
        
        if timezone is None:
            location = self.get_random_location()
            timezone = location["timezone"]
        
        js = f"""
        (function() {{
            const originalDateTimeFormat = Intl.DateTimeFormat;
            Intl.DateTimeFormat = function(locales, options) {{
                if (!options) options = {{}};
                options.timeZone = '{timezone}';
                return new originalDateTimeFormat(locales, options);
            }};
            Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;
            
            const originalDateToString = Date.prototype.toString;
            Date.prototype.toString = function() {{
                return originalDateToString.call(this).replace(/\\(.*?\\)/, '({timezone})');
            }};
            
            const lang = '{timezone.split('/')[0]}';
            Object.defineProperty(navigator, 'language', {{
                get: () => lang,
                configurable: true
            }});
            
            console.log('🕐 Таймзона установлена: {timezone}');
        }})()
        """
        
        await self.execute_script(js)
        print(f"🕐 Таймзона установлена: {timezone}")
        return f"🕐 Таймзона: {timezone}"
    
    async def set_language(self, lang: str = None):
        await self.connect()
        
        if lang is None:
            location = self.get_random_location()
            lang = location["lang"]
        
        js = f"""
        (function() {{
            const languages = ['{lang}', '{lang.split('-')[0]}', 'en-US', 'en'];
            
            Object.defineProperty(navigator, 'language', {{
                get: () => '{lang}',
                configurable: true
            }});
            
            Object.defineProperty(navigator, 'languages', {{
                get: () => languages,
                configurable: true
            }});
            
            console.log('🌐 Язык установлен: {lang}');
        }})()
        """
        
        await self.execute_script(js)
        print(f"🌐 Язык установлен: {lang}")
        return f"🌐 Язык: {lang}"
    
    async def setup_location_by_ip(self, ip: str = None):
        if ip:
            try:
                response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,timezone,isp", timeout=10)
                data = response.json()
                
                if data.get('status') == 'success':
                    lat = data.get('lat')
                    lng = data.get('lon')
                    timezone = data.get('timezone', 'Europe/London')
                    
                    country = data.get('country', 'US')
                    lang_map = {
                        'Russia': 'ru-RU',
                        'United States': 'en-US',
                        'United Kingdom': 'en-GB',
                        'France': 'fr-FR',
                        'Germany': 'de-DE',
                        'Japan': 'ja-JP',
                        'Australia': 'en-AU',
                        'China': 'zh-CN',
                        'Brazil': 'pt-BR',
                        'India': 'hi-IN',
                        'UAE': 'ar-AE',
                        'Singapore': 'en-SG',
                        'Italy': 'it-IT',
                        'Spain': 'es-ES',
                        'Canada': 'en-CA',
                    }
                    lang = lang_map.get(country, 'en-US')
                    
                    await self.set_geolocation(lat, lng)
                    await self.set_timezone(timezone)
                    await self.set_language(lang)
                    
                    return f"✅ Гео по IP {ip}:\n📍 {lat}, {lng}\n🕐 {timezone}\n🌐 {lang}"
            except Exception as e:
                print(f"❌ Ошибка определения гео по IP: {e}")
        
        location = self.get_random_location()
        await self.set_geolocation(location["lat"], location["lng"])
        await self.set_timezone(location["timezone"])
        await self.set_language(location["lang"])
        
        return f"✅ Случайная геолокация:\n📍 {location['name']}\n🕐 {location['timezone']}\n🌐 {location['lang']}"
    
    # ========== МАСКИРОВКА JS ==========
    
    async def apply_mask(self):
        if self._masked:
            return True
        
        try:
            print("🕵️ Применяю 100% маскировку...")
            
            location = self.get_random_location()
            await self.set_geolocation(location["lat"], location["lng"])
            await self.set_timezone(location["timezone"])
            await self.set_language(location["lang"])
            
            webgl_vendor = self.get_random_webgl_vendor()
            webgl_renderer = self.get_random_webgl_renderer()
            hardware_concurrency = random.randint(4, 16)
            device_memory = random.choice([4, 8, 16, 32])
            chrome_version = random.randint(118, 120)
            rtt = random.randint(20, 100)
            downlink = round(random.uniform(5, 20), 1)
            effective_type = random.choice(['4g', '3g'])
            connection_type = random.choice(['wifi', 'ethernet'])
            screen_height = random.randint(800, 1080)
            screen_width = random.randint(1200, 1920)
            platform = random.choice(['Win32', 'MacIntel', 'Linux x86_64'])
            
            mask_js = f"""
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
                    get: () => '{platform}',
                    configurable: true,
                    enumerable: true
                }});
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {{
                    get: () => {hardware_concurrency},
                    configurable: true,
                    enumerable: true
                }});
                
                Object.defineProperty(navigator, 'deviceMemory', {{
                    get: () => {device_memory},
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
                            platform: '{platform.replace('Win32', 'Windows').replace('MacIntel', 'macOS').replace('Linux x86_64', 'Linux')}',
                            mobile: false,
                            getHighEntropyValues: function(hints) {{
                                return Promise.resolve({{
                                    architecture: '{random.choice(['x86', 'arm'])}',
                                    bitness: '{random.choice(['32', '64'])}',
                                    model: '',
                                    platform: '{platform}',
                                    platformVersion: '{random.choice(['10.0', '11.0', '12.0'])}',
                                    uaFullVersion: '{chrome_version}.0.0.0'
                                }});
                            }},
                            toJSON: function() {{
                                return {{
                                    brands: [
                                        {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                                        {{ brand: 'Chromium', version: '{chrome_version}' }}
                                    ],
                                    platform: '{platform}',
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
                            effectiveType: '{effective_type}',
                            saveData: false,
                            type: '{connection_type}'
                        }};
                    }},
                    configurable: true,
                    enumerable: true
                }});
                
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(contextId, attributes) {{
                    if (contextId === 'webgl' || contextId === 'experimental-webgl') {{
                        const context = originalGetContext.call(this, contextId, attributes);
                        if (context) {{
                            const originalGetParameter = context.getParameter;
                            context.getParameter = function(parameter) {{
                                if (parameter === 0x1F00) {{
                                    return '{webgl_vendor}';
                                }}
                                if (parameter === 0x1F01) {{
                                    return '{webgl_renderer}';
                                }}
                                return originalGetParameter.call(this, parameter);
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
                        if (ctx) {{
                            const imageData = ctx.getImageData(0, 0, this.width, this.height);
                            const data = imageData.data;
                            for (let i = 0; i < data.length && i < 100; i += 4) {{
                                if (Math.random() < 0.01) {{
                                    data[i] = Math.min(255, data[i] + (Math.random() > 0.5 ? 1 : -1));
                                    data[i+1] = Math.min(255, data[i+1] + (Math.random() > 0.5 ? 1 : -1));
                                    data[i+2] = Math.min(255, data[i+2] + (Math.random() > 0.5 ? 1 : -1));
                                }}
                            }}
                            ctx.putImageData(imageData, 0, 0);
                        }}
                    }}
                    return originalToDataURL.call(this, type, quality);
                }};
                
                const originalAudioCtx = window.AudioContext || window.webkitAudioContext;
                if (originalAudioCtx) {{
                    const patchedAudioCtx = function() {{
                        const ctx = new originalAudioCtx();
                        const originalCreateBuffer = ctx.createBuffer;
                        ctx.createBuffer = function(numChannels, length, sampleRate) {{
                            const buffer = originalCreateBuffer.call(this, numChannels, length, sampleRate);
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
                        const height = availHeight + {random.randint(40, 60)};
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
                
                if (!window.chrome) {{
                    window.chrome = {{}};
                }}
                window.chrome.runtime = {{}};
                window.chrome.loadTimes = function() {{
                    return {{
                        requestTime: Date.now() / 1000,
                        startLoadTime: Date.now() / 1000 - {random.uniform(0.5, 2)},
                        commitLoadTime: Date.now() / 1000 - {random.uniform(0.2, 1)},
                        finishDocumentLoadTime: Date.now() / 1000 - {random.uniform(0.1, 0.5)},
                        finishLoadTime: Date.now() / 1000 - {random.uniform(0.05, 0.3)},
                        firstPaintTime: Date.now() / 1000 - {random.uniform(0.1, 0.8)},
                        firstPaintAfterLoadTime: 0,
                        navigationType: 'Other',
                        wasFetchedViaSpdy: false,
                        wasNpnNegotiated: false,
                        npnNegotiatedProtocol: 'unknown',
                        wasAlternateProtocolAvailable: false,
                        connectionInfo: 'http/1.1'
                    }};
                }};
                window.chrome.csi = function() {{
                    return {{
                        startE: Date.now() - {random.randint(500, 2000)},
                        onloadT: Date.now() - {random.randint(100, 500)},
                        pageT: {random.randint(100, 500)},
                        tran: '15'
                    }};
                }};
                window.chrome.app = {{}};
                window.chrome.app.isInstalled = false;
                
                Object.defineProperty(navigator, 'mimeTypes', {{
                    get: () => {{
                        return {{
                            0: {{
                                type: 'application/pdf',
                                suffixes: 'pdf',
                                description: 'Portable Document Format',
                                enabledPlugin: {{
                                    name: 'Chrome PDF Plugin',
                                    filename: 'internal-pdf-viewer',
                                    description: 'Portable Document Format'
                                }}
                            }},
                            length: 1
                        }};
                    }},
                    configurable: true,
                    enumerable: true
                }});
                
                const originalPerfNow = performance.now;
                performance.now = function() {{
                    return originalPerfNow.call(this) + (Math.random() * 0.5);
                }};
                
                const originalDateNow = Date.now;
                Date.now = function() {{
                    return originalDateNow.call(this) + Math.floor(Math.random() * 10);
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
                
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = function(parameters) {{
                    const permissions = {{
                        'geolocation': '{random.choice(['prompt', 'denied'])}',
                        'notifications': Notification.permission || 'default',
                        'midi': 'prompt',
                        'camera': 'prompt',
                        'microphone': 'prompt',
                        'background-fetch': 'prompt',
                        'background-sync': 'granted',
                        'periodic-background-sync': 'prompt',
                        'persistent-storage': 'prompt',
                        'push': Notification.permission || 'default',
                        'speaker-selection': 'prompt',
                        'clipboard-read': 'prompt',
                        'clipboard-write': 'granted'
                    }};
                    return Promise.resolve({{
                        state: permissions[parameters.name] || 'prompt',
                        onchange: null,
                        name: parameters.name
                    }});
                }};
                
                console.log('✅ 100% маскировка применена');
            }})()
            """
            
            await self.execute_script(mask_js)
            self._masked = True
            print("✅ 100% маскировка применена")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка маскировки: {e}")
            return False
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ==========
    
    def _get_tab_ws_url(self, tab_id: Optional[str] = None) -> Optional[str]:
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/list', timeout=5)
            if resp.status_code != 200:
                return None
            
            pages = resp.json()
            
            if not pages:
                resp = requests.get(f'http://{self.host}:{self.port}/json/new', timeout=5)
                new_page = resp.json()
                self._page_id = new_page.get('id')
                self._current_url = new_page.get('url', '')
                return new_page['webSocketDebuggerUrl']
            
            if tab_id:
                for page in pages:
                    if page.get('id') == tab_id:
                        self._page_id = page['id']
                        self._current_url = page.get('url', '')
                        return page['webSocketDebuggerUrl']
            
            first_page = pages[0]
            self._page_id = first_page.get('id')
            self._current_url = first_page.get('url', '')
            return first_page['webSocketDebuggerUrl']
            
        except Exception as e:
            print(f"❌ Ошибка подключения к Chrome: {e}")
            return None
    
    async def connect(self, tab_id: Optional[str] = None):
        if self._connected and self.ws:
            return
        
        self.ws_url = self._get_tab_ws_url(tab_id)
        if not self.ws_url:
            raise Exception("❌ Chrome не запущен или нет доступных вкладок")
        
        print(f"🔗 Подключаюсь к: {self.ws_url}")
        self.ws = await websockets.connect(
            self.ws_url,
            max_size=50 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=60
        )
        self._connected = True
        
        await self._send_command("Page.enable")
        await self._send_command("Runtime.enable")
        await self._send_command("DOM.enable")
        await self._send_command("Network.enable")
        
        await self._set_viewport()
        await self.apply_mask()
        
        print("✅ Подключение к CDP установлено")
    
    async def _set_viewport(self):
        await self._send_command("Emulation.setDeviceMetricsOverride", {
            "width": self.viewport_width,
            "height": self.viewport_height,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    
    async def _send_command(self, method: str, params: dict = None):
        if not self._connected:
            await self.connect()
        
        self._message_id += 1
        message = {
            "id": self._message_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(message))
        print(f"📤 Отправлена команда: {method} (id: {self._message_id})")
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=self.timeout)
                data = json.loads(response)
                
                if data.get('id') == self._message_id:
                    if 'error' in data:
                        raise Exception(f"CDP Error: {data['error']}")
                    print(f"📥 Получен ответ на {method}")
                    return data.get('result', {})
            except asyncio.TimeoutError:
                raise Exception(f"❌ Таймаут ответа от Chrome на команду {method}")
    
    async def open_page(self, url: str):
        await self.connect()
        result = await self._send_command("Page.navigate", {"url": url})
        self._current_url = url
        await asyncio.sleep(2)
        await self._set_viewport()
        return result
    
    async def is_page_empty(self) -> bool:
        try:
            if not self._current_url or self._current_url in ['about:blank', 'chrome://newtab/', '']:
                return True
            
            text = await self.get_page_text()
            if not text or text.strip() == "" or text == "📭 Страница пустая или не содержит текста":
                return True
            
            title = await self.get_page_title()
            if not title or title.strip() == "" or title == "Без названия":
                return True
            
            return False
        except:
            return True
    
    async def screenshot(self):
        await self.connect()
        
        if await self.is_page_empty():
            raise Exception("📭 Страница пустая или не загружена. Сначала откройте страницу")
        
        await self._set_viewport()
        
        result = await self._send_command("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": False
        })
        
        screenshot_data = result['data']
        screenshot_data = screenshot_data.strip()
        
        if 'base64,' in screenshot_data:
            screenshot_data = screenshot_data.split('base64,')[-1]
        elif ',' in screenshot_data:
            screenshot_data = screenshot_data.split(',')[-1]
        
        screenshot_data = ''.join(screenshot_data.split())
        screenshot_data = re.sub(r'[^A-Za-z0-9+/=]', '', screenshot_data)
        
        return screenshot_data
    
    async def get_page_text(self):
        await self.connect()
        
        try:
            result = await self._send_command("Runtime.evaluate", {
                "expression": "document.body?.innerText || document.documentElement?.textContent || ''"
            })
            text = result['result'].get('value', '')
            
            if not text or text.strip() == "":
                return "📭 Страница пустая или не содержит текста"
            
            return text[:10000]
        except Exception as e:
            return f"⚠️ Не удалось получить текст: {str(e)[:100]}"
    
    async def get_page_title(self):
        await self.connect()
        try:
            result = await self._send_command("Runtime.evaluate", {
                "expression": "document.title || ''"
            })
            title = result['result'].get('value', '')
            if not title or title.strip() == "":
                return "Без названия"
            return title
        except:
            return "Без названия"
    
    async def click_element(self, selector: str):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        find_result = await self._send_command("DOM.querySelector", {
            "selector": selector
        })
        node_id = find_result.get('nodeId')
        
        if not node_id or node_id == 0:
            return "❌ Элемент не найден"
        
        box_result = await self._send_command("DOM.getBoxModel", {
            "nodeId": node_id
        })
        
        if not box_result or 'model' not in box_result:
            return "❌ Не удалось получить координаты"
        
        content = box_result['model']['content']
        x = (content[0] + content[4]) / 2
        y = (content[1] + content[5]) / 2
        
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        
        return f"✅ Кликнул по: {selector}"
    
    async def execute_script(self, script: str):
        await self.connect()
        
        if await self.is_page_empty() and script not in ['document.title', 'location.href']:
            return "⚠️ Страница пустая. Сначала откройте страницу"
        
        result = await self._send_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
        
        value = result['result'].get('value')
        return value if value is not None else 'undefined'
    
    async def go_back(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, некуда возвращаться"
        
        await self._send_command("Page.navigateBack")
        await asyncio.sleep(1)
        return "⬅️ Назад"
    
    async def go_forward(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, некуда идти вперёд"
        
        await self._send_command("Page.navigateForward")
        await asyncio.sleep(1)
        return "➡️ Вперёд"
    
    async def refresh(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, нечего обновлять"
        
        await self._send_command("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(1)
        return "🔄 Обновлено"
    
    # ========== ОЖИДАНИЕ ЭЛЕМЕНТОВ ==========
    
    async def wait_for_selector(self, selector: str, timeout: int = 30):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = await self._send_command("Runtime.evaluate", {
                    "expression": f"document.querySelector('{selector}') !== null"
                })
                
                if result['result'].get('value', False):
                    return f"✅ Элемент найден: {selector}"
                
                await asyncio.sleep(0.5)
            except Exception as e:
                pass
        
        return f"❌ Элемент не найден за {timeout} секунд: {selector}"
    
    async def wait_for_text(self, text: str, timeout: int = 30):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                page_text = await self.get_page_text()
                if text.lower() in page_text.lower():
                    return f"✅ Текст найден: {text}"
                await asyncio.sleep(0.5)
            except Exception as e:
                pass
        
        return f"❌ Текст не найден за {timeout} секунд: {text}"
    
    # ========== DOM МЕТОДЫ ==========
    
    async def get_full_dom(self) -> str:
        await self.connect()
        
        if await self.is_page_empty():
            return "📭 Страница пустая или не загружена"
        
        result = await self._send_command("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML"
        })
        
        return result['result'].get('value', '')
    
    async def get_dom_with_metadata(self) -> Dict[str, Any]:
        await self.connect()
        
        if await self.is_page_empty():
            return {"error": "Страница пустая"}
        
        js = """
        (function() {
            const interactive = [];
            const selectors = ['button', 'a', 'input', 'textarea', 'select', '[role="button"]', '[onclick]'];
            
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    const rect = el.getBoundingClientRect();
                    interactive.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        class: el.className || null,
                        text: el.innerText ? el.innerText.trim().slice(0, 100) : null,
                        placeholder: el.placeholder || null,
                        value: el.value || null,
                        type: el.type || null,
                        href: el.href || null,
                        name: el.name || null,
                        role: el.getAttribute('role') || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        data_attr: el.getAttribute('data-testid') || el.getAttribute('data-id') || null,
                        visible: rect.width > 0 && rect.height > 0,
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        selector: el.id ? '#' + el.id : 
                                  el.className ? '.' + el.className.split(' ')[0] : 
                                  el.tagName.toLowerCase()
                    });
                });
            });
            
            return {
                title: document.title || '',
                url: window.location.href,
                interactive: interactive,
                total_elements: document.querySelectorAll('*').length,
                forms: document.forms.length,
                links: document.links.length,
                images: document.images.length,
                scripts: document.scripts.length
            };
        })()
        """
        
        result = await self._send_command("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        
        return result['result'].get('value', {})
    
    async def find_elements_by_text(self, text: str) -> List[Dict[str, Any]]:
        await self.connect()
        
        if await self.is_page_empty():
            return []
        
        js = f"""
        (function() {{
            const results = [];
            const xpath = ".//*[contains(text(), '{text}') or contains(@value, '{text}') or contains(@placeholder, '{text}') or contains(@aria-label, '{text}')]";
            
            const elements = document.evaluate(
                xpath,
                document,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );
            
            for (let i = 0; i < elements.snapshotLength; i++) {{
                const el = elements.snapshotItem(i);
                const rect = el.getBoundingClientRect();
                results.push({{
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    class: el.className || null,
                    text: el.innerText ? el.innerText.trim().slice(0, 100) : null,
                    value: el.value || null,
                    placeholder: el.placeholder || null,
                    href: el.href || null,
                    type: el.type || null,
                    visible: rect.width > 0 && rect.height > 0,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    selector: el.id ? '#' + el.id : el.tagName.toLowerCase()
                }});
            }}
            
            return results;
        }})()
        """
        
        result = await self._send_command("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        
        return result['result'].get('value', [])
    
    async def get_interactive_elements(self) -> List[Dict[str, Any]]:
        data = await self.get_dom_with_metadata()
        return data.get('interactive', [])
    
    async def get_dom_summary(self) -> str:
        data = await self.get_dom_with_metadata()
        
        if 'error' in data:
            return data['error']
        
        summary = f"""
📄 СТРАНИЦА:
• Заголовок: {data.get('title', 'Нет')}
• URL: {data.get('url', 'Нет')}

📊 СТАТИСТИКА:
• Всего элементов: {data.get('total_elements', 0)}
• Форм: {data.get('forms', 0)}
• Ссылок: {data.get('links', 0)}
• Изображений: {data.get('images', 0)}
• Скриптов: {data.get('scripts', 0)}

🖱 ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ ({len(data.get('interactive', []))}):
"""
        
        for i, el in enumerate(data.get('interactive', [])[:20]):
            text = el.get('text', '') or el.get('placeholder', '') or el.get('value', '') or ''
            summary += f"  {i+1}. <{el.get('tag', '')}>"
            if text:
                summary += f" '{text[:30]}'"
            if el.get('type'):
                summary += f" type={el.get('type')}"
            if el.get('visible'):
                summary += " ✅"
            else:
                summary += " ⛔"
            summary += f"\n     Селектор: {el.get('selector', '')}\n"
        
        if len(data.get('interactive', [])) > 20:
            summary += f"  ... и ещё {len(data.get('interactive', [])) - 20} элементов\n"
        
        return summary
    
    async def ai_find_element(self, description: str) -> Dict[str, Any]:
        await self.connect()
        
        if await self.is_page_empty():
            return {"error": "Страница пустая"}
        
        elements = await self.get_interactive_elements()
        
        if not elements:
            return {"error": "Нет интерактивных элементов"}
        
        desc_lower = description.lower()
        candidates = []
        
        for el in elements:
            score = 0
            text = (el.get('text') or '').lower()
            placeholder = (el.get('placeholder') or '').lower()
            aria_label = (el.get('aria_label') or '').lower()
            value = (el.get('value') or '').lower()
            tag = el.get('tag', '').lower()
            el_type = (el.get('type') or '').lower()
            
            keywords = desc_lower.split()
            for kw in keywords:
                if len(kw) < 3:
                    continue
                if kw in text:
                    score += 3
                if kw in placeholder:
                    score += 2
                if kw in aria_label:
                    score += 2
                if kw in value:
                    score += 2
            
            if tag in ['button', 'a'] and 'кнопк' in desc_lower:
                score += 1
            if tag == 'input' and 'пол' in desc_lower:
                score += 1
            if el_type == 'submit' and 'отправ' in desc_lower:
                score += 1
            
            if el.get('visible', False):
                score += 1
            
            if score > 0:
                candidates.append({**el, 'score': score})
        
        candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        if candidates:
            return {
                "found": True,
                "best": candidates[0],
                "candidates": candidates[:5]
            }
        
        return {
            "found": False,
            "message": f"Не найден элемент по описанию: {description}"
        }
    
    async def ai_interact(self, description: str, action: str = "click") -> str:
        result = await self.ai_find_element(description)
        
        if not result.get('found', False):
            return f"❌ {result.get('message', 'Элемент не найден')}"
        
        el = result['best']
        selector = el.get('selector', '')
        
        if action == "click":
            if not selector:
                return "❌ Нет селектора для клика"
            return await self.click_element(selector)
        
        elif action == "get_text":
            return f"📝 Текст: {el.get('text', 'Нет текста')}"
        
        elif action == "focus":
            await self.execute_script(f"document.querySelector('{selector}')?.focus()")
            return f"✅ Фокус на: {description}"
        
        elif action == "hover":
            await self.execute_script(f"""
                const el = document.querySelector('{selector}');
                if (el) {{
                    const event = new MouseEvent('mouseover', {{
                        view: window,
                        bubbles: true,
                        cancelable: true
                    }});
                    el.dispatchEvent(event);
                }}
            """)
            return f"🖱 Наведение на: {description}"
        
        return f"✅ Действие '{action}' выполнено на: {description}"
    
    async def ai_analyze_page(self, question: str) -> str:
        await self.connect()
        
        if await self.is_page_empty():
            return "📭 Страница пустая"
        
        dom_summary = await self.get_dom_summary()
        full_dom = await self.get_full_dom()
        dom_preview = full_dom[:3000] + "..." if len(full_dom) > 3000 else full_dom
        
        from ai import AgnesAI
        ai_engine = AgnesAI()
        
        prompt = f"""
Ты эксперт по анализу веб-страниц. Ответь на вопрос пользователя.

{dom_summary}

Фрагмент DOM страницы (первые 3000 символов):
{dom_preview}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

ОТВЕТЬ:
1. Кратко опиши что на странице
2. Найди элементы по запросу пользователя
3. Предложи селекторы для найденных элементов
4. Если есть кнопки - предложи их найти и нажать
"""
        
        response = ai_engine.ask(prompt, "")
        return response
    
    # ========== ИИ-АГЕНТ (ГЛАВНАЯ ФИЧА) ==========
    
    def _format_interactive_for_ai(self, elements: List[Dict]) -> str:
        if not elements:
            return "Нет интерактивных элементов"
        
        result = ""
        for i, el in enumerate(elements[:30]):
            text = el.get('text', '') or el.get('placeholder', '') or el.get('value', '') or ''
            if text:
                result += f"  {i+1}. <{el.get('tag', '')}> '{text[:40]}'"
            else:
                result += f"  {i+1}. <{el.get('tag', '')}>"
            
            if el.get('type'):
                result += f" type={el.get('type')}"
            
            result += f" → {el.get('selector', '')}"
            
            if not el.get('visible', False):
                result += " ⛔"
            result += "\n"
        
        if len(elements) > 30:
            result += f"  ... и ещё {len(elements) - 30} элементов\n"
        
        return result
    
    async def ai_agent(self, command: str) -> str:
        """ИИ-агент: читает DOM и выполняет команды"""
        await self.connect()
        
        if await self.is_page_empty():
            return "📭 Страница пустая. Сначала откройте страницу"
        
        # Получаем DOM
        dom_data = await self.get_dom_with_metadata()
        full_dom = await self.get_full_dom()
        dom_preview = full_dom[:5000] + "..." if len(full_dom) > 5000 else full_dom
        
        # Формируем промпт для ИИ
        from ai import AgnesAI
        ai_engine = AgnesAI()
        
        prompt = f"""
Ты ИИ-агент, который управляет браузером. Твоя задача — выполнить команду пользователя.

📄 ТЕКУЩАЯ СТРАНИЦА:
Заголовок: {dom_data.get('title', 'Нет')}
URL: {dom_data.get('url', 'Нет')}
Всего элементов: {dom_data.get('total_elements', 0)}
Форм: {dom_data.get('forms', 0)}
Ссылок: {dom_data.get('links', 0)}

🖱 ДОСТУПНЫЕ ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ:
{self._format_interactive_for_ai(dom_data.get('interactive', []))}

📄 ФРАГМЕНТ DOM (первые 5000 символов):
{dom_preview}

КОМАНДА ПОЛЬЗОВАТЕЛЯ:
{command}

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "action": "click | type | find | analyze | wait | none | screenshot | open",
    "selector": "CSS селектор элемента",
    "text": "текст для ввода (если action=type)",
    "url": "URL для открытия (если action=open)",
    "message": "понятный ответ пользователю"
}}

ПРИМЕРЫ:
1. Команда: "нажми на кнопку войти"
   {{"action": "click", "selector": "#login-btn", "message": "✅ Кликнул по кнопке 'Войти'"}}

2. Команда: "введи test@gmail.com в поле email"
   {{"action": "type", "selector": "input[type='email']", "text": "test@gmail.com", "message": "✅ Ввёл email в поле"}}

3. Команда: "какие кнопки есть?"
   {{"action": "analyze", "selector": "", "message": "На странице есть кнопки: 'Войти', 'Зарегистрироваться'"}}

4. Команда: "подожди загрузки"
   {{"action": "wait", "selector": ".loading", "message": "⏳ Ожидание загрузки..."}}

5. Команда: "что здесь написано?"
   {{"action": "none", "selector": "", "message": "На странице написано: ..."}}

6. Команда: "открой google.com"
   {{"action": "open", "url": "https://google.com", "message": "✅ Открыл Google"}}

7. Команда: "сделай скриншот"
   {{"action": "screenshot", "selector": "", "message": "📸 Скриншот готов"}}
"""
        
        # Получаем ответ от ИИ
        response = ai_engine.ask(prompt, "")
        
        # Парсим JSON
        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return f"❌ ИИ не смог распарсить команду: {response[:200]}"
        except Exception as e:
            return f"❌ Ошибка парсинга JSON: {e}\nОтвет ИИ: {response[:200]}"
        
        action = data.get('action', 'none')
        selector = data.get('selector', '')
        text = data.get('text', '')
        url = data.get('url', '')
        message = data.get('message', '')
        
        # Выполняем действие
        try:
            if action == 'open':
                if not url:
                    return "❌ Не указан URL для открытия"
                await self.open_page(url)
                title = await self.get_page_title()
                return f"{message}\n✅ Открыто: {title}"
            
            elif action == 'screenshot':
                screenshot_base64 = await self.screenshot()
                # Возвращаем base64 для отправки в Telegram
                return f"{message}\n📸 screenshot_data:{screenshot_base64}"
            
            elif action == 'click':
                if not selector:
                    return "❌ Не найден селектор для клика"
                result = await self.click_element(selector)
                return f"{message}\n{result}"
            
            elif action == 'type':
                if not selector:
                    return "❌ Не найден селектор для ввода"
                js = f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.value = '{text}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
                """
                result = await self.execute_script(js)
                if result:
                    return f"{message}\n✅ Текст введён в поле: {selector}"
                else:
                    return f"❌ Не удалось ввести текст в поле: {selector}"
            
            elif action == 'find':
                results = await self.find_elements_by_text(text or selector)
                if results:
                    return f"{message}\n🔍 Найдено {len(results)} элементов"
                else:
                    return f"❌ Элементы не найдены: {message}"
            
            elif action == 'wait':
                if not selector:
                    return "❌ Не указан селектор для ожидания"
                result = await self.wait_for_selector(selector)
                return f"{message}\n{result}"
            
            elif action == 'analyze':
                return message
            
            else:
                return message or response
        
        except Exception as e:
            return f"❌ Ошибка выполнения команды: {str(e)}"
    
    # ========== УПРАВЛЕНИЕ ВКЛАДКАМИ ==========
    
    async def list_tabs(self):
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/list', timeout=5)
            pages = resp.json()
            
            if not pages:
                return "📭 Нет открытых вкладок"
            
            result = "📑 Список вкладок:\n\n"
            for i, page in enumerate(pages):
                title = page.get('title', 'Без названия')[:40]
                url = page.get('url', '')[:40]
                active = "🔵" if page.get('id') == self._page_id else "⚪"
                result += f"{active} {i+1}. {title}\n   {url}\n\n"
            return result
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def create_tab(self, url: str = ""):
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/new', timeout=5)
            page = resp.json()
            
            await self.close()
            
            self._page_id = page.get('id')
            self._current_url = page.get('url', '')
            await self.connect(self._page_id)
            
            if url:
                await self.open_page(url)
            
            return f"✅ Создана вкладка: {page.get('title', 'Новая вкладка')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def close_tab(self):
        if not self._page_id:
            return "❌ Нет активной вкладки"
        
        try:
            requests.get(f'http://{self.host}:{self.port}/json/close/{self._page_id}', timeout=5)
            await self.close()
            
            await self.connect()
            return "✅ Вкладка закрыта"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def close(self):
        if self.ws and self._connected:
            try:
                await self.ws.close()
            except:
                pass
            self._connected = False
            self.ws = None