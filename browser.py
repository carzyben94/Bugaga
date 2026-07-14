import asyncio
import json
import websockets
import requests
import re
import random
import time
from typing import Optional, List, Dict, Any

GOOGLE_SEARCH_IDS = ['APjFqb', 'gbqfq', 'lst-ib', 'searchbox', 'q']

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
        self._debug = False
        
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
        
        print(f"📍 Геолокация: {lat}, {lng}")
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
        print(f"🕐 Таймзона: {timezone}")
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
        print(f"🌐 Язык: {lang}")
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
    
    # ========== КУКИ ==========
    
    def get_default_cookies(self) -> List[Dict[str, Any]]:
        """Получить стандартные куки для X/Twitter"""
        return [
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "__cuid",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "lang",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "ru"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "dnt",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "1"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "guest_id",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "v1%3A178267838599411411"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "guest_id_marketing",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "v1%3A178267838599411411"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "guest_id_ads",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "v1%3A178267838599411411"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "personalization_id",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": '"v1_DKrxLZAC902dMFdd1QrVYg=="'
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "twid",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "u%3D2067347503503052800"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "auth_token",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "ct0",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"
            },
            {
                "domain": ".x.com",
                "hostOnly": False,
                "httpOnly": False,
                "name": "__cf_bm",
                "path": "/",
                "sameSite": "unspecified",
                "secure": False,
                "session": True,
                "value": "wj_dszyJY7t.NS3PCGD3fz27cRQXW6tgfO9_TrBoXPk-1784047968.7823458-1.0.1.1-oJnV6LCjpA4HNw4UmXCuwUCnHGdRlOCDFcQoVgBxAMdp35GIZImrhfbf3kRCgjicmLdK5VzMmZQ5Xqwu4ZmH9dv2Y8I1BWwbonY_SeuhqMeJUz4Y8vxdNzRog4InHuwB"
            }
        ]
    
    async def set_cookies(self, cookies: Optional[List[Dict[str, Any]]] = None):
        """Установить куки в браузере (все сразу)"""
        await self.connect()
        
        if cookies is None:
            cookies = self.get_default_cookies()
        
        await self._send_command("Network.setCookies", {
            "cookies": cookies
        })
        
        print(f"🍪 Установлено {len(cookies)} кук")
        return f"🍪 Установлено {len(cookies)} кук"
    
    async def get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Получить все куки из браузера"""
        await self.connect()
        
        params = {}
        if urls:
            params["urls"] = urls
        
        result = await self._send_command("Network.getCookies", params)
        return result.get('cookies', [])
    
    # ========== МАСКИРОВКА JS ==========
    
    async def apply_mask(self):
        if self._masked:
            return True
        
        try:
            print("🕵️ Маскировка...")
            
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
            print("✅ Маскировка OK")
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
    
    # ========== connect() — ИСПРАВЛЕН (ДОБАВЛЕНЫ AWAIT) ==========
    
    async def connect(self, tab_id: Optional[str] = None):
        if self._connected and self.ws:
            return
        
        self.ws_url = self._get_tab_ws_url(tab_id)
        if not self.ws_url:
            raise Exception("❌ Chrome не запущен или нет доступных вкладок")
        
        print(f"🔗 Подключение к Chrome...")
        
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    max_size=50 * 1024 * 1024,
                    ping_interval=20,
                    ping_timeout=60
                ),
                timeout=10
            )
            self._connected = True
            print("✅ WebSocket подключен")
        except asyncio.TimeoutError:
            raise Exception("❌ Таймаут подключения к Chrome")
        
        # ✅ ИСПРАВЛЕНО — ВСЕ С AWAIT!
        await self._send_command("Page.enable")
        await self._send_command("Runtime.enable")
        await self._send_command("DOM.enable")
        await self._send_command("Network.enable")
        
        await self._set_viewport()
        await self.set_cookies()
        await self.apply_mask()
        
        print("✅ Подключение OK")
    
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
        
        important = ['Page.navigate', 'Page.captureScreenshot', 'Page.reload']
        if self._debug or method in important:
            print(f"📤 {method}")
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(response)
                
                if data.get('id') == self._message_id:
                    if 'error' in data:
                        raise Exception(f"CDP Error: {data['error']}")
                    
                    if self._debug or method in important:
                        if method == 'Page.captureScreenshot':
                            print(f"📥 screenshot OK")
                        elif method == 'Page.navigate':
                            print(f"📥 navigate OK")
                        else:
                            print(f"📥 {method} OK")
                    
                    return data.get('result', {})
            except asyncio.TimeoutError:
                raise Exception(f"❌ Таймаут ответа от Chrome на команду {method}")
    
    # ========== open_page() — ДОБАВЛЕНЫ ЛОГИ ==========
    
    async def open_page(self, url: str):
        print(f"🔵 open_page: {url}")
        await self.connect()
        print("🔵 connect OK")
        
        result = await self._send_command("Page.navigate", {"url": url})
        print(f"🔵 Page.navigate отправлен")
        
        self._current_url = url
        print("🔵 Жду 2 секунды...")
        await asyncio.sleep(2)
        
        await self._set_viewport()
        print("🔵 viewport установлен")
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
    
    # ========== GET_PAGE_TEXT (EVAL) ==========
    
    async def get_page_text(self):
        """Получить текст страницы через EVAL"""
        await self.connect()
        
        js = """
        (function() {
            return document.body?.innerText || document.documentElement?.textContent || '';
        })()
        """
        
        text = await self.execute_script(js)
        
        if not text or text.strip() == "":
            return "📭 Страница пустая или не содержит текста"
        
        return text[:10000]
    
    async def get_page_title(self):
        """Получить заголовок страницы через EVAL"""
        await self.connect()
        
        js = "return document.title || ''"
        
        title = await self.execute_script(js)
        
        if not title or title.strip() == "":
            return "Без названия"
        return title
    
    # ========== CLICK_ELEMENT (EVAL + CDP запасной) ==========
    
    async def click_element(self, selector: str):
        """Клик через EVAL (основной) + CDP (запасной)"""
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        safe_selector = selector.replace('"', '\\"').replace("'", "\\'")
        
        # 1. EVAL (основной способ)
        js = f"""
        (function() {{
            const el = document.querySelector('{safe_selector}');
            if (!el) return false;
            
            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            el.click();
            el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
            el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true }}));
            el.focus();
            
            return true;
        }})()
        """
        
        result = await self.execute_script(js)
        if result:
            return f"✅ Кликнул по: {self._shorten_selector(selector)}"
        
        # 2. CDP (запасной способ)
        try:
            doc = await self._send_command("DOM.getDocument")
            root_node_id = doc['root']['nodeId']
            
            find_result = await self._send_command("DOM.querySelector", {
                "nodeId": root_node_id,
                "selector": selector
            })
            node_id = find_result.get('nodeId')
            
            if not node_id or node_id == 0:
                return f"❌ Элемент не найден: {self._shorten_selector(selector)}"
            
            box_result = await self._send_command("DOM.getBoxModel", {
                "nodeId": node_id
            })
            
            if not box_result or 'model' not in box_result:
                return f"❌ Не удалось получить координаты"
            
            content = box_result['model']['content']
            x = (content[0] + content[4]) / 2
            y = (content[1] + content[5]) / 2
            
            await self._send_command("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": x, "y": y,
                "button": "left", "clickCount": 1
            })
            await self._send_command("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": x, "y": y,
                "button": "left", "clickCount": 1
            })
            
            return f"✅ Кликнул по: {self._shorten_selector(selector)} (CDP)"
            
        except Exception as e:
            return f"❌ Ошибка клика: {str(e)[:200]}"
    
    def _shorten_selector(self, selector: str) -> str:
        """Обрезает длинные селекторы"""
        if len(selector) <= 60:
            return selector
        if "data-testid" in selector:
            return selector
        if '.css-' in selector or '.r-' in selector:
            parts = selector.split('.')
            if len(parts) > 3:
                return parts[0] + '.' + parts[1] + '.' + parts[2] + '...'
        return selector[:60] + '...'
    
    # ========== TYPE_TEXT (EVAL) ==========
    
    async def type_text_cdp(self, selector: str, text: str):
        """Ввод текста + Enter (полностью на EVAL)"""
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        safe_selector = selector.replace('"', '\\"').replace("'", "\\'")
        
        js = f"""
        (function() {{
            let el = null;
            let foundBy = 'не найден';
            
            const googleIds = ['APjFqb', 'gbqfq', 'lst-ib', 'searchbox', 'q'];
            for (let id of googleIds) {{
                const found = document.getElementById(id);
                if (found) {{
                    el = found;
                    foundBy = 'ID: ' + id;
                    break;
                }}
            }}
            
            if (!el) {{
                const inputs = document.querySelectorAll('input, textarea');
                for (let inp of inputs) {{
                    const placeholder = (inp.placeholder || '').toLowerCase();
                    const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
                    const name = (inp.name || '').toLowerCase();
                    const type = (inp.type || '').toLowerCase();
                    const id = (inp.id || '').toLowerCase();
                    const cls = (inp.className || '').toLowerCase();
                    
                    const isMatch = (
                        placeholder.includes('поиск') || placeholder.includes('search') ||
                        placeholder.includes('найти') || placeholder.includes('find') ||
                        aria.includes('поиск') || aria.includes('search') ||
                        name === 'q' || name === 'search' ||
                        type === 'search' ||
                        id.includes('search') || id.includes('query') ||
                        cls.includes('search') || cls.includes('query')
                    );
                    
                    if (isMatch) {{
                        el = inp;
                        foundBy = 'атрибуты';
                        break;
                    }}
                }}
            }}
            
            if (!el) {{
                const testIds = ['SearchBox_Search_Input', 'tweetTextarea_0'];
                for (let testId of testIds) {{
                    const found = document.querySelector('[data-testid="' + testId + '"]');
                    if (found) {{
                        el = found;
                        foundBy = 'data-testid: ' + testId;
                        break;
                    }}
                }}
            }}
            
            if (!el) {{
                const inputs = document.querySelectorAll('input, textarea');
                for (let inp of inputs) {{
                    if (inp.type !== 'hidden' && inp.offsetParent !== null) {{
                        el = inp;
                        foundBy = 'первое видимое поле';
                        break;
                    }}
                }}
            }}
            
            if (!el && '{safe_selector}') {{
                el = document.querySelector('{safe_selector}');
                if (el) foundBy = 'селектор';
            }}
            
            if (!el) {{
                const inputs = document.querySelectorAll('input, textarea, [contenteditable="true"]');
                const result = [];
                inputs.forEach(inp => {{
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {{
                        result.push({{
                            tag: inp.tagName.toLowerCase(),
                            id: inp.id || '',
                            class: inp.className || '',
                            placeholder: inp.placeholder || '',
                            ariaLabel: inp.getAttribute('aria-label') || '',
                            name: inp.name || '',
                            type: inp.type || ''
                        }});
                    }}
                }});
                return result;
            }}
            
            el.focus();
            el.value = '';
            el.value = '{text}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            
            const enterEvent = new KeyboardEvent('keydown', {{
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true,
                cancelable: true,
                composed: true
            }});
            el.dispatchEvent(enterEvent);
            
            const form = el.closest('form');
            if (form) {{
                if (form.requestSubmit) {{
                    form.requestSubmit();
                }} else {{
                    form.submit();
                }}
            }}
            
            const buttons = document.querySelectorAll('button[type="submit"], input[type="submit"], button[aria-label*="поиск"], button[aria-label*="search"]');
            for (let btn of buttons) {{
                const text = (btn.textContent || btn.value || '').toLowerCase();
                if (text.includes('поиск') || text.includes('search') || text.includes('найти')) {{
                    btn.click();
                    break;
                }}
            }}
            
            return true;
        }})()
        """
        
        result = await self.execute_script(js)
        
        if isinstance(result, list) and len(result) > 0:
            fields_text = "🔍 **На странице есть поля:**\n\n"
            for i, f in enumerate(result[:10], 1):
                tag = f.get('tag', 'unknown')
                placeholder = f.get('placeholder', '')
                ariaLabel = f.get('ariaLabel', '')
                name = f.get('name', '')
                field_id = f.get('id', '')
                type = f.get('type', '')
                
                desc = f"  {i}. <{tag}>"
                if placeholder:
                    desc += f" placeholder='{placeholder}'"
                elif ariaLabel:
                    desc += f" aria-label='{ariaLabel}'"
                elif name:
                    desc += f" name='{name}'"
                if field_id:
                    desc += f" id='{field_id}'"
                if type:
                    desc += f" type='{type}'"
                fields_text += desc + "\n"
            
            if len(result) > 10:
                fields_text += f"\n... и ещё {len(result) - 10} полей"
            
            return fields_text
        
        if result is True:
            return f"✅ Ввёл '{text}' и отправил поиск"
        
        if result is False:
            return f"⚠️ Ввёл '{text}', но поиск не отправлен"
        
        return f"⚠️ Ввёл '{text}', но результат неизвестен"
    
    # ========== WAIT_FOR_SELECTOR (EVAL С ТАЙМАУТОМ) ==========
    
    async def wait_for_selector(self, selector: str, timeout: int = 30):
        """Ожидание элемента с таймаутом"""
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        print(f"🔵 wait_for_selector: {selector}, timeout={timeout} сек")
        
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                result = await asyncio.wait_for(
                    self.execute_script(f"document.querySelector('{selector}') !== null"),
                    timeout=2
                )
                if result:
                    return f"✅ Элемент найден: {selector}"
            except asyncio.TimeoutError:
                print("⏳ Ждём...")
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
            
            await asyncio.sleep(0.5)
        
        return f"❌ Элемент не найден за {timeout} секунд: {selector}"
    
    # ========== WAIT_FOR_TEXT (EVAL С ТАЙМАУТОМ) ==========
    
    async def wait_for_text(self, text: str, timeout: int = 30):
        """Ожидание текста с таймаутом"""
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу"
        
        print(f"🔵 wait_for_text: {text}, timeout={timeout} сек")
        
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                page_text = await asyncio.wait_for(
                    self.get_page_text(),
                    timeout=2
                )
                if text.lower() in page_text.lower():
                    return f"✅ Текст найден: {text}"
            except asyncio.TimeoutError:
                print("⏳ Ждём...")
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
            
            await asyncio.sleep(0.5)
        
        return f"❌ Текст не найден за {timeout} секунд: {text}"
    
    # ========== EXECUTE_SCRIPT (С ТАЙМАУТОМ) ==========
    
    async def execute_script(self, script: str):
        """Выполнить JavaScript с таймаутом"""
        await self.connect()
        
        if await self.is_page_empty() and script not in ['document.title', 'location.href']:
            return "⚠️ Страница пустая. Сначала откройте страницу"
        
        try:
            result = await asyncio.wait_for(
                self._send_command("Runtime.evaluate", {
                    "expression": script,
                    "returnByValue": True
                }),
                timeout=10
            )
            value = result['result'].get('value')
            return value if value is not None else 'undefined'
        except asyncio.TimeoutError:
            raise Exception("❌ Таймаут выполнения JS")
    
    # ========== НАВИГАЦИЯ (CDP) ==========
    
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
        """Получить ТОЛЬКО полезные интерактивные элементы с data-testid"""
        await self.connect()
        
        if await self.is_page_empty():
            return {"error": "Страница пустая"}
        
        js = """
        (function() {
            function isVisible(el) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                
                if (rect.width === 0 && rect.height === 0) return false;
                if (style.display === 'none') return false;
                if (style.visibility === 'hidden') return false;
                if (style.opacity === '0') return false;
                if (parseFloat(style.width) === 0 && parseFloat(style.height) === 0) return false;
                
                let parent = el.parentElement;
                while (parent) {
                    const parentStyle = window.getComputedStyle(parent);
                    if (parentStyle.display === 'none') return false;
                    if (parentStyle.visibility === 'hidden') return false;
                    parent = parent.parentElement;
                }
                return true;
            }
            
            function getSelector(el) {
                const testId = el.getAttribute('data-testid');
                if (testId) {
                    return '[data-testid="' + testId + '"]';
                }
                const ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel && ariaLabel.length < 50) {
                    return '[aria-label="' + ariaLabel + '"]';
                }
                if (el.id) {
                    return '#' + el.id;
                }
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.split(' ').filter(c => c && !c.startsWith('r-') && !c.startsWith('css-')).join('.');
                    if (classes) return '.' + classes;
                }
                const tag = el.tagName.toLowerCase();
                const parent = el.parentElement;
                if (parent) {
                    const siblings = parent.querySelectorAll(tag);
                    if (siblings.length > 1) {
                        for (let i = 0; i < siblings.length; i++) {
                            if (siblings[i] === el) return tag + ':nth-child(' + (i + 1) + ')';
                        }
                    }
                }
                return tag;
            }
            
            const interactive = [];
            
            document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"], [role="link"], [data-testid*="Button"], [data-testid*="Link"], [data-testid*="Tab"]').forEach(el => {
                if (!isVisible(el)) return;
                const rect = el.getBoundingClientRect();
                const text = el.innerText?.trim() || el.value || el.getAttribute('aria-label') || '';
                const testId = el.getAttribute('data-testid') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const displayText = text || ariaLabel || testId || 'без текста';
                interactive.push({
                    type: 'button',
                    tag: el.tagName.toLowerCase(),
                    text: displayText.slice(0, 50),
                    selector: getSelector(el),
                    visible: true,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    action: 'click',
                    testId: testId,
                    ariaLabel: ariaLabel
                });
            });
            
            document.querySelectorAll('input:not([type="submit"]):not([type="button"]):not([type="hidden"]), textarea, select').forEach(el => {
                if (!isVisible(el)) return;
                const rect = el.getBoundingClientRect();
                const placeholder = el.placeholder || '';
                const value = el.value || '';
                const name = el.name || '';
                const label = placeholder || value || name || '';
                if (!label) return;
                const inputType = el.type || 'text';
                
                interactive.push({
                    type: 'input',
                    tag: el.tagName.toLowerCase(),
                    input_type: inputType,
                    placeholder: placeholder.slice(0, 50),
                    value: value.slice(0, 50),
                    name: name.slice(0, 30),
                    label: label.slice(0, 50),
                    selector: getSelector(el),
                    visible: true,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    action: 'type'
                });
            });
            
            document.querySelectorAll('a[href]:not([href=""]):not([href="#"])').forEach(el => {
                if (!isVisible(el)) return;
                const rect = el.getBoundingClientRect();
                const text = el.innerText?.trim() || el.getAttribute('aria-label') || '';
                if (!text) return;
                interactive.push({
                    type: 'link',
                    tag: 'a',
                    text: text.slice(0, 50),
                    href: el.href || '',
                    selector: getSelector(el),
                    visible: true,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    action: 'click'
                });
            });
            
            interactive.sort((a, b) => {
                if (a.visible !== b.visible) return a.visible ? -1 : 1;
                const order = { button: 0, link: 1, input: 2 };
                return (order[a.type] || 99) - (order[b.type] || 99);
            });
            
            return {
                title: document.title || '',
                url: window.location.href,
                interactive: interactive,
                total_interactive: interactive.length
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
            const xpath = ".//*[contains(text(), '{text}') or contains(@value, '{text}') or contains(@placeholder, '{text}') or contains(@aria-label, '{text}') or contains(@data-testid, '{text}')]";
            
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
                const testId = el.getAttribute('data-testid') || '';
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
                    selector: testId ? '[data-testid="' + testId + '"]' : (el.id ? '#' + el.id : el.tagName.toLowerCase())
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

🖱 ДОСТУПНЫЕ ЭЛЕМЕНТЫ ({data.get('total_interactive', 0)}):
"""
        
        for i, el in enumerate(data.get('interactive', [])[:20]):
            text = el.get('text', '') or el.get('placeholder', '') or el.get('value', '') or ''
            summary += f"  {i+1}. <{el.get('type', '')}>"
            if text:
                summary += f" '{text[:30]}'"
            if el.get('input_type'):
                summary += f" type={el.get('input_type')}"
            if el.get('testId'):
                summary += f" [data-testid={el.get('testId')}]"
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
            label = (el.get('label') or '').lower()
            value = (el.get('value') or '').lower()
            test_id = (el.get('testId') or '').lower()
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
                if kw in label:
                    score += 2
                if kw in value:
                    score += 2
                if kw in test_id:
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
                "candidates": candidates[:3]
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
        
        from ai import AgnesAI
        ai_engine = AgnesAI()
        
        prompt = f"""
Ты эксперт по анализу веб-страниц. Ответь на вопрос пользователя.

{dom_summary}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

ОТВЕТЬ:
1. Кратко опиши что на странице
2. Найди элементы по запросу пользователя
3. Предложи селекторы для найденных элементов
"""
        
        response = ai_engine.ask(prompt, "")
        return response
    
    # ========== ИИ-АГЕНТ ==========
    
    async def ai_agent(self, command: str) -> str:
        """ИИ-агент — использует AgentHandler из ai.py"""
        from ai import AgentHandler
        
        print(f"🧠 Агент: {command[:50]}...")
        
        handler = AgentHandler(self)
        result = await handler.execute(command)
        
        print(f"✅ Агент OK")
        
        return result
    
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