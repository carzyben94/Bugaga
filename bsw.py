# ============================================
# bsw.py - Browser Stealth Wrapper
# Полная маскировка браузера как в Pydoll
# ============================================

import random
import asyncio
import subprocess
import json
import base64
import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import websockets
import aiohttp

logger = logging.getLogger(__name__)


# ============================================
# БЛОК 1: ПАРСЕР USER-AGENT
# ============================================

class UserAgentParser:
    """
    Полный парсер User-Agent как в Pydoll.
    Извлекает метаданные из UA строки для согласованности всех слоёв.
    """

    @staticmethod
    def parse(user_agent: str) -> Dict[str, Any]:
        """
        Парсит User-Agent строку и возвращает все метаданные
        для Emulation.setUserAgentOverride и navigator-свойств.
        """
        result = {
            "user_agent": user_agent,
            "platform": "Win32",
            "platform_for_js": "Win32",
            "vendor": "Google Inc.",
            "app_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "brands": [
                {"brand": "Google Chrome", "version": "120"},
                {"brand": "Chromium", "version": "120"},
                {"brand": "Not?A_Brand", "version": "99"}
            ],
            "full_version_list": [
                {"brand": "Google Chrome", "version": "120.0.6099.109"},
                {"brand": "Chromium", "version": "120.0.6099.109"},
                {"brand": "Not?A_Brand", "version": "99.0.0.0"}
            ],
            "platform_version": "10.0",
            "architecture": "x86",
            "bitness": "64",
            "mobile": False,
            "model": ""
        }

        # Определяем платформу
        if "Windows NT 10.0" in user_agent:
            result["platform"] = "Win32"
            result["platform_for_js"] = "Windows"
        elif "Mac OS X" in user_agent:
            result["platform"] = "MacIntel"
            result["platform_for_js"] = "macOS"
        elif "Linux" in user_agent and "Android" not in user_agent:
            result["platform"] = "Linux x86_64"
            result["platform_for_js"] = "Linux"
        elif "Android" in user_agent:
            result["platform"] = "Linux armv8l"
            result["platform_for_js"] = "Android"
            result["mobile"] = True
        elif "iPhone" in user_agent or "iPad" in user_agent:
            result["platform"] = "iPhone"
            result["platform_for_js"] = "iOS"
            result["mobile"] = True

        # Извлекаем версию Chrome
        import re
        chrome_match = re.search(r'Chrome/(\d+)\.', user_agent)
        if chrome_match:
            chrome_version = chrome_match.group(1)
            result["brands"][0]["version"] = chrome_version
            result["brands"][1]["version"] = chrome_version
            result["full_version_list"][0]["version"] = f"{chrome_version}.0.6099.109"
            result["full_version_list"][1]["version"] = f"{chrome_version}.0.6099.109"

        return result

    @staticmethod
    def generate_ua_metadata(parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Генерирует userAgentMetadata для CDP"""
        return {
            "brands": parsed["brands"],
            "fullVersionList": parsed["full_version_list"],
            "platform": parsed["platform_for_js"],
            "platformVersion": parsed["platform_version"],
            "architecture": parsed["architecture"],
            "bitness": parsed["bitness"],
            "mobile": parsed["mobile"],
            "model": parsed["model"]
        }


# ============================================
# БЛОК 2: ОСНОВНОЙ КЛАСС МАСКИРОВКИ
# ============================================

class StealthBrowser:
    """
    100% маскировка браузера — полная копия Pydoll.
    Все 24+ техники маскировки.
    """
    
    # Список User-Agent
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    
    # WebGL вендоры
    WEBGL_VENDORS = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (AMD)",
        "Google Inc. (Intel)",
        "NVIDIA Corporation",
        "Advanced Micro Devices, Inc.",
        "Intel Corporation"
    ]
    
    # WebGL рендеры
    WEBGL_RENDERERS = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6900 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ]
    
    # Путь к браузеру по умолчанию
    CHROME_PATH = "/usr/bin/chromium"
    
    # ============================================
    # 2.1: ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================
    
    @staticmethod
    def random_window_position() -> Dict[str, int]:
        return {
            "left": random.randint(50, 300),
            "top": random.randint(50, 200),
            "width": random.randint(1200, 1920),
            "height": random.randint(800, 1080)
        }
    
    @staticmethod
    def random_user_agent() -> str:
        return random.choice(StealthBrowser.USER_AGENTS)
    
    @staticmethod
    def random_webgl_vendor() -> str:
        return random.choice(StealthBrowser.WEBGL_VENDORS)
    
    @staticmethod
    def random_webgl_renderer() -> str:
        return random.choice(StealthBrowser.WEBGL_RENDERERS)
    
    @staticmethod
    def _find_chrome() -> Optional[str]:
        """Ищет Chrome/Chromium в системе."""
        import shutil
        import sys
        
        paths = [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "chrome",
            "chrome.exe",
        ]
        
        if sys.platform == "win32":
            paths.extend([
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Chromium\Application\chrome.exe",
            ])
        elif sys.platform == "darwin":
            paths.extend([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ])
        else:
            paths.extend([
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ])
        
        for path in paths:
            found = shutil.which(path) if not path.startswith(("/", "C:")) else path
            if found and shutil.which(found):
                return found
            elif found and os.path.exists(found):
                return found
        
        return None
    
    @staticmethod
    async def _wait_for_cdp(port: int, timeout: int = 30) -> Optional[str]:
        """Ожидает запуска CDP и возвращает URL."""
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://localhost:{port}/json/version", timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get("webSocketDebuggerUrl")
            except:
                await asyncio.sleep(0.5)
                continue
        
        return None
    
    # ============================================
    # 2.2: ФЛАГИ ЗАПУСКА
    # ============================================
    
    @staticmethod
    def get_launch_args(
        chrome_path: str,
        debug_port: int,
        headless: bool = False,
        proxy: str = None,
        user_data_dir: str = None
    ) -> List[str]:
        """Флаги запуска Chrome (как в Pydoll)"""
        window = StealthBrowser.random_window_position()
        user_agent = StealthBrowser.random_user_agent()
        
        args = [
            chrome_path,
            "--no-sandbox",
            "--disable-dev-shm-usage",
            
            # Скрываем автоматизацию
            "--disable-blink-features=AutomationControlled",
            "--disable-automation",
            
            # GPU и WebGL
            "--use-gl=egl",
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-zero-copy",
            "--use-cmd-decoder=passthrough",
            "--enable-features=WebGLDeveloperExtensions",
            
            # WebRTC защита от утечки IP
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--enable-webrtc-hide-local-ips-with-mdns",
            
            # Отключаем всё лишнее
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
            "--disable-gpu",  # Для Linux
            "--disable-setuid-sandbox",  # Для Linux
            
            # User-Agent (только HTTP-заголовок)
            f"--user-agent={user_agent}",
            
            f"--remote-debugging-port={debug_port}",
            "about:blank"
        ]
        
        if headless:
            args.append("--headless=new")
        
        if proxy:
            args.append(f"--proxy-server={proxy}")
        
        if user_data_dir:
            args.append(f"--user-data-dir={user_data_dir}")
        
        return args
    
    # ============================================
    # 2.3: JS МАСКИРОВКА (ВСЕ 24+ ТЕХНИК)
    # ============================================
    
    @staticmethod
    def get_js_mask() -> str:
        """
        JS-маскировка 100% как в Pydoll.
        Выполняется через Page.addScriptToEvaluateOnNewDocument.
        Включает все 24+ техники маскировки.
        """
        webgl_vendor = StealthBrowser.random_webgl_vendor()
        webgl_renderer = StealthBrowser.random_webgl_renderer()
        chrome_version = random.randint(118, 121)
        hardware_concurrency = random.randint(4, 16)
        device_memory = random.choice([4, 8, 16, 32])
        rtt = random.randint(20, 100)
        downlink = round(random.uniform(5, 20), 1)
        effective_type = random.choice(['4g', '3g'])
        connection_type = random.choice(['wifi', 'ethernet'])
        screen_height = random.randint(800, 1080)
        screen_width = random.randint(1200, 1920)
        platform = random.choice(['Win32', 'MacIntel', 'Linux x86_64'])
        lang = random.choice(['en-US', 'en-GB', 'fr-FR', 'de-DE', 'ru-RU', 'ja-JP', 'zh-CN'])
        timezone = random.choice([
            'America/New_York', 'Europe/London', 'Europe/Paris',
            'Europe/Berlin', 'Europe/Moscow', 'Asia/Tokyo',
            'America/Los_Angeles', 'Australia/Sydney'
        ])
        
        return f"""
        (function() {{
            console.log('🕵️ Pydoll маскировка 100%...');
            
            // ========== 1. NAVIGATOR ==========
            
            // webdriver → undefined
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
                configurable: true,
                enumerable: true
            }});
            
            // Плагины (стандартные Chrome плагины)
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
            
            // Languages
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{lang}', '{lang.split('-')[0]}', 'en-US', 'en'],
                configurable: true,
                enumerable: true
            }});
            
            // Platform
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}',
                configurable: true,
                enumerable: true
            }});
            
            // Hardware
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
            
            // ========== 2. CLIENT HINTS (userAgentData) ==========
            
            if (!navigator.userAgentData) {{
                Object.defineProperty(navigator, 'userAgentData', {{
                    get: () => {{
                        const platformMap = {{
                            'Win32': 'Windows',
                            'MacIntel': 'macOS',
                            'Linux x86_64': 'Linux'
                        }};
                        return {{
                            brands: [
                                {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                                {{ brand: 'Chromium', version: '{chrome_version}' }},
                                {{ brand: 'Not?A_Brand', version: '99' }}
                            ],
                            platform: platformMap['{platform}'] || '{platform}',
                            mobile: false,
                            getHighEntropyValues: function(hints) {{
                                return Promise.resolve({{
                                    architecture: 'x86',
                                    bitness: '64',
                                    model: '',
                                    platform: '{platform}',
                                    platformVersion: '10.0',
                                    uaFullVersion: '{chrome_version}.0.0.0',
                                    wow64: false
                                }});
                            }},
                            toJSON: function() {{
                                return {{
                                    brands: [
                                        {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                                        {{ brand: 'Chromium', version: '{chrome_version}' }}
                                    ],
                                    platform: platformMap['{platform}'] || '{platform}',
                                    mobile: false
                                }};
                            }}
                        }};
                    }},
                    configurable: true,
                    enumerable: true
                }});
            }}
            
            // ========== 3. CONNECTION API ==========
            
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
            
            // ========== 4. PERMISSION API ==========
            
            if (navigator.permissions) {{
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = function(descriptor) {{
                    const sensitive = ['notifications', 'geolocation', 'camera', 'microphone', 'midi', 'storage-access'];
                    if (sensitive.includes(descriptor.name)) {{
                        return Promise.resolve({{
                            state: 'prompt',
                            onchange: null
                        }});
                    }}
                    return originalQuery.call(this, descriptor);
                }};
            }}
            
            // ========== 5. BATTERY API ==========
            
            Object.defineProperty(navigator, 'getBattery', {{
                get: () => function() {{
                    return Promise.resolve({{
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1.0,
                        onchargingchange: null,
                        onchargingtimechange: null,
                        ondischargingtimechange: null,
                        onlevelchange: null
                    }});
                }}
            }});
            
            // ========== 6. WEBGL ==========
            
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
                        
                        // Шейдеры с шумом
                        const originalCreateShader = context.createShader;
                        context.createShader = function(type) {{
                            const shader = originalCreateShader.call(this, type);
                            const originalShaderSource = context.shaderSource;
                            context.shaderSource = function(shader, source) {{
                                const noise = `// ${{Math.random().toString(36).substring(2, 8)}}\\n`;
                                return originalShaderSource.call(this, shader, noise + source);
                            }};
                            return shader;
                        }};
                    }}
                    return context;
                }}
                return originalGetContext.call(this, contextId, attributes);
            }};
            
            // ========== 7. CANVAS FINGERPRINTING ЗАЩИТА ==========
            
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
                try {{
                    const ctx = this.getContext('2d');
                    if (ctx && type && type.startsWith('image/')) {{
                        const imageData = ctx.getImageData(0, 0, this.width, this.height);
                        const data = imageData.data;
                        for (let i = 0; i < data.length; i += 4) {{
                            data[i] = Math.min(255, data[i] + Math.floor(Math.random() * 2));
                            data[i+1] = Math.min(255, data[i+1] + Math.floor(Math.random() * 2));
                            data[i+2] = Math.min(255, data[i+2] + Math.floor(Math.random() * 2));
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }}
                }} catch(e) {{}}
                return originalToDataURL.call(this, type, quality);
            }};
            
            // ========== 8. AUDIO FINGERPRINTING ЗАЩИТА ==========
            
            if (window.AudioBuffer) {{
                const originalGetChannelData = AudioBuffer.prototype.getChannelData;
                AudioBuffer.prototype.getChannelData = function(channel) {{
                    const data = originalGetChannelData.call(this, channel);
                    try {{
                        for (let i = 0; i < data.length; i += 100) {{
                            data[i] += (Math.random() - 0.5) * 0.0001;
                        }}
                    }} catch(e) {{}}
                    return data;
                }};
            }}
            
            // ========== 9. FONT FINGERPRINTING ЗАЩИТА ==========
            
            const originalMeasureText = CanvasRenderingContext2D.prototype.measureText;
            CanvasRenderingContext2D.prototype.measureText = function(text) {{
                const metrics = originalMeasureText.call(this, text);
                metrics.width += (Math.random() - 0.5) * 0.01;
                return metrics;
            }};
            
            // ========== 10. SCREEN ==========
            
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
            
            // ========== 11. CHROME ==========
            
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
            
            // ========== 12. TIMING ШУМ ==========
            
            const originalPerfNow = performance.now;
            performance.now = function() {{
                return originalPerfNow.call(this) + (Math.random() * 0.1);
            }};
            
            const originalDateNow = Date.now;
            Date.now = function() {{
                return originalDateNow.call(this) + Math.floor(Math.random() * 5);
            }};
            
            // Performance API шум
            if (performance.getEntries) {{
                const originalGetEntries = performance.getEntries;
                performance.getEntries = function() {{
                    const entries = originalGetEntries.call(this);
                    try {{
                        return entries.map(entry => {{
                            if (entry && entry.entryType === 'navigation') {{
                                entry.domContentLoadedEventEnd = (entry.domContentLoadedEventEnd || 0) + Math.random() * 10;
                                entry.loadEventEnd = (entry.loadEventEnd || 0) + Math.random() * 20;
                            }}
                            return entry;
                        }});
                    }} catch(e) {{
                        return entries;
                    }}
                }};
            }}
            
            // ========== 13. DOCUMENT ==========
            
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
            
            // ========== 14. WEBRTC (дополнительная защита) ==========
            
            if (window.RTCPeerConnection) {{
                const originalCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
                RTCPeerConnection.prototype.createDataChannel = function(label, options) {{
                    if (!options) options = {{}};
                    options.protocol = options.protocol || '';
                    return originalCreateDataChannel.call(this, label, options);
                }};
            }}
            
            console.log('✅ Pydoll маскировка 100% применена');
        }})()
        """
    
    # ============================================
    # 2.4: HUMANIZE (ЧЕЛОВЕЧЕСКОЕ ПОВЕДЕНИЕ)
    # ============================================
    
    @staticmethod
    def get_human_click_js(selector: str) -> str:
        """
        Человеческий клик как в Pydoll:
        - Bezier-кривая
        - Fitts's Law
        - Tremor (шум)
        - Overshoot + correction
        - Микропаузы
        """
        return f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return false;
            
            const rect = el.getBoundingClientRect();
            const targetX = rect.left + rect.width / 2 + (Math.random() - 0.5) * 10;
            const targetY = rect.top + rect.height / 2 + (Math.random() - 0.5) * 10;
            
            // Текущая позиция мыши (или стартовая)
            let startX = window.innerWidth / 2 + (Math.random() - 0.5) * 100;
            let startY = window.innerHeight / 2 + (Math.random() - 0.5) * 100;
            let currentX = startX;
            let currentY = startY;
            
            // Расстояние
            const distance = Math.sqrt(
                Math.pow(targetX - startX, 2) + Math.pow(targetY - startY, 2)
            );
            
            // Fitts's Law: MT = a + b * log2(D/W + 1)
            const a = 50, b = 200;
            const duration = a + b * Math.log2(distance / 20 + 1);
            const totalSteps = Math.max(20, Math.floor(duration / 16));
            
            // Bezier control points (асимметричные)
            const cp1x = startX + (targetX - startX) * 0.3 + (Math.random() - 0.5) * 50;
            const cp1y = startY + (targetY - startY) * 0.1 + (Math.random() - 0.5) * 50;
            const cp2x = startX + (targetX - startX) * 0.7 + (Math.random() - 0.5) * 50;
            const cp2y = startY + (targetY - startY) * 0.9 + (Math.random() - 0.5) * 50;
            
            // Overshoot (70% шанс)
            let overshootX = 0, overshootY = 0;
            if (Math.random() < 0.7 && distance > 100) {{
                const factor = 1.03 + Math.random() * 0.09;
                overshootX = (targetX - startX) * (factor - 1) * (Math.random() > 0.5 ? 1 : -1);
                overshootY = (targetY - startY) * (factor - 1) * (Math.random() > 0.5 ? 1 : -1);
            }}
            
            function bezier(t) {{
                const u = 1 - t;
                const x = u*u*u*startX + 3*u*u*t*cp1x + 3*u*t*t*cp2x + t*t*t*(targetX + overshootX);
                const y = u*u*u*startY + 3*u*u*t*cp1y + 3*u*t*t*cp2y + t*t*t*(targetY + overshootY);
                return {{x, y}};
            }}
            
            // Tremor: физиологический шум
            function tremor(step, total) {{
                const amplitude = 1 + Math.random() * 2;
                return (Math.random() - 0.5) * amplitude * (1 - step / total);
            }}
            
            async function moveMouse() {{
                const totalFrames = 60;
                for (let i = 0; i < totalFrames; i++) {{
                    const t = i / totalFrames;
                    const pos = bezier(t);
                    const tremX = tremor(i, totalFrames);
                    const tremY = tremor(i, totalFrames);
                    
                    currentX = pos.x + tremX;
                    currentY = pos.y + tremY;
                    
                    // Dispatch mousemove
                    const moveEvent = new MouseEvent('mousemove', {{
                        clientX: currentX,
                        clientY: currentY,
                        bubbles: true,
                        cancelable: true
                    }});
                    document.dispatchEvent(moveEvent);
                    
                    // Микропауза (5% шанс)
                    if (Math.random() < 0.05) {{
                        await new Promise(r => setTimeout(r, 20 + Math.random() * 30));
                    }}
                    
                    await new Promise(r => setTimeout(r, 16));
                }}
                
                // Коррекция после overshoot
                if (Math.abs(overshootX) > 1 || Math.abs(overshootY) > 1) {{
                    const correctionSteps = 10;
                    for (let i = 0; i < correctionSteps; i++) {{
                        const t = i / correctionSteps;
                        currentX = (targetX + overshootX) + (targetX - targetX - overshootX) * t;
                        currentY = (targetY + overshootY) + (targetY - targetY - overshootY) * t;
                        
                        const moveEvent = new MouseEvent('mousemove', {{
                            clientX: currentX,
                            clientY: currentY,
                            bubbles: true
                        }});
                        document.dispatchEvent(moveEvent);
                        await new Promise(r => setTimeout(r, 16));
                    }}
                }}
                
                // Click
                const holdTime = 50 + Math.random() * 150;
                const downEvent = new MouseEvent('mousedown', {{
                    clientX: targetX,
                    clientY: targetY,
                    bubbles: true,
                    cancelable: true,
                    button: 0
                }});
                el.dispatchEvent(downEvent);
                
                await new Promise(r => setTimeout(r, holdTime));
                
                const upEvent = new MouseEvent('mouseup', {{
                    clientX: targetX,
                    clientY: targetY,
                    bubbles: true,
                    cancelable: true,
                    button: 0
                }});
                el.dispatchEvent(upEvent);
                
                const clickEvent = new MouseEvent('click', {{
                    clientX: targetX,
                    clientY: targetY,
                    bubbles: true,
                    cancelable: true
                }});
                el.dispatchEvent(clickEvent);
                
                return true;
            }}
            
            return moveMouse();
        }})()
        """
    
    @staticmethod
    def get_human_type_js(selector: str, text: str) -> str:
        """
        Человеческий ввод как в Pydoll:
        - Опечатки 2%
        - Исправление опечаток
        - Переменная скорость
        - Паузы для обдумывания
        """
        return f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return false;
            
            el.focus();
            el.value = '';
            el.click();
            
            const chars = '{text}'.split('');
            let index = 0;
            
            // Типы опечаток: соседняя клавиша, перестановка, пропуск
            function generateTypo(char) {{
                const typoType = Math.random();
                const charsTypo = 'qwertyuiopasdfghjklzxcvbnm';
                
                if (typoType < 0.3) {{ // Соседняя клавиша
                    const idx = charsTypo.indexOf(char.toLowerCase());
                    if (idx > 0) return charsTypo[idx - 1];
                    if (idx < charsTypo.length - 1) return charsTypo[idx + 1];
                    return char;
                }} else if (typoType < 0.6) {{ // Перестановка
                    return '';
                }}
                return char;
            }}
            
            function typeNext() {{
                if (index >= chars.length) {{
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return;
                }}
                
                let char = chars[index];
                
                // 2% опечатка
                if (Math.random() < 0.02 && index < chars.length - 1) {{
                    const typoChar = generateTypo(char);
                    if (typoChar) {{
                        el.value += typoChar;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        
                        // Исправление опечатки (задержка)
                        const fixDelay = {random.randint(100, 300)};
                        setTimeout(() => {{
                            el.value = el.value.slice(0, -1);
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            
                            // Печатаем правильный символ
                            el.value += char;
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            index++;
                            const delay = {random.randint(50, 150)} + Math.random() * {random.randint(50, 100)};
                            setTimeout(typeNext, delay);
                        }}, fixDelay);
                        return;
                    }}
                }}
                
                // Нормальный ввод
                el.value += char;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                index++;
                
                // 10% пауза для обдумывания
                let delay = {random.randint(50, 150)} + Math.random() * {random.randint(50, 100)};
                if (Math.random() < 0.1) {{
                    delay += {random.randint(200, 500)};
                }}
                
                setTimeout(typeNext, delay);
            }}
            
            setTimeout(typeNext, {random.randint(100, 300)});
            return true;
        }})()
        """
    
    @staticmethod
    def get_human_scroll_js(distance: int) -> str:
        """
        Человеческий скролл как в Pydoll:
        - Physics-based (импульс, трение)
        - Overshoot + correction
        - Jitter (шум)
        - Микропаузы
        """
        return f"""
        (function() {{
            const targetDistance = {distance};
            const direction = targetDistance > 0 ? 1 : -1;
            const absTarget = Math.abs(targetDistance);
            
            // Физика: импульс + трение
            const friction = 0.92 + Math.random() * 0.05;
            
            // Fitts's Law для скролла
            const duration = 200 + 300 * Math.log2(absTarget / 50 + 1);
            const totalSteps = Math.max(20, Math.floor(duration / 16));
            
            // Overshoot (15% шанс)
            let overshootFactor = 1;
            if (Math.random() < 0.15) {{
                overshootFactor = 1.02 + Math.random() * 0.06;
            }}
            
            let step = 0;
            let remaining = absTarget * overshootFactor;
            
            function doScroll() {{
                if (step >= totalSteps || remaining < 5) {{
                    // Коррекция при overshoot
                    if (remaining < -10 || remaining > 10) {{
                        window.scrollBy(0, -remaining * direction * 0.1);
                    }}
                    return;
                }}
                
                const progress = step / totalSteps;
                const eased = 1 - Math.pow(1 - progress, 3);
                const targetRemaining = absTarget * (1 - eased) * overshootFactor;
                const delta = (targetRemaining - remaining) * direction;
                
                // Jitter (шум ±3px)
                const jitter = (Math.random() - 0.5) * 6;
                const finalDelta = delta + jitter;
                
                window.scrollBy(0, finalDelta);
                remaining -= finalDelta * direction;
                
                // Микропауза (5% шанс)
                let delay = 12;
                if (Math.random() < 0.05) {{
                    delay += 20 + Math.random() * 30;
                }}
                
                step++;
                setTimeout(doScroll, delay);
            }}
            
            // Импульсный старт
            setTimeout(doScroll, 50 + Math.random() * 50);
            return true;
        }})()
        """
    
    # ============================================
    # 2.5: ЗАПУСК БРАУЗЕРА
    # ============================================
    
    @staticmethod
    async def launch(
        headless: bool = False,
        port: int = 9222,
        proxy: str = None,
        chrome_path: str = None,
        user_data_dir: str = None,
        timeout: int = 30
    ) -> dict:
        """
        Запускает браузер со 100% маскировкой Pydoll.
        
        Args:
            headless: Запуск в headless режиме.
            port: Порт для CDP подключения.
            proxy: Прокси (например, 'http://user:pass@proxy:8080').
            chrome_path: Путь к Chrome/Chromium.
            user_data_dir: Директория для профиля пользователя.
            timeout: Таймаут ожидания запуска.
        
        Returns:
            Dict с полями:
                - process: subprocess.Popen
                - ws: websocket соединение
                - cdp_url: str
                - _id: int (счетчик запросов)
                - port: int
        """
        # Находим Chrome
        if chrome_path is None:
            chrome_path = StealthBrowser._find_chrome()
            if not chrome_path:
                raise RuntimeError("Chrome не найден в системе!")
        
        # Проверяем существование
        if not os.path.exists(chrome_path):
            raise RuntimeError(f"Браузер не найден по пути: {chrome_path}")
        
        logger.info(f"🚀 Запуск браузера с маскировкой...")
        logger.info(f"   Путь: {chrome_path}")
        logger.info(f"   Порт: {port}")
        logger.info(f"   Headless: {headless}")
        if proxy:
            logger.info(f"   Прокси: {proxy}")
        
        # Собираем флаги запуска
        args = StealthBrowser.get_launch_args(
            chrome_path=chrome_path,
            debug_port=port,
            headless=headless,
            proxy=proxy,
            user_data_dir=user_data_dir
        )
        
        # Запускаем процесс
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True
        )
        
        # Ждем CDP
        cdp_url = await StealthBrowser._wait_for_cdp(port, timeout)
        
        if not cdp_url:
            process.terminate()
            raise RuntimeError(f"Не удалось подключиться к CDP на порту {port}")
        
        logger.info(f"✅ CDP готов: {cdp_url}")
        
        # Подключаемся через WebSocket
        ws = await websockets.connect(cdp_url, max_size=10**7)
        
        # Применяем JS-маскировку
        js_mask = StealthBrowser.get_js_mask()
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.addScriptToEvaluateOnNewDocument",
            "params": {"source": js_mask}
        }))
        await ws.recv()
        logger.info("✅ JS-маскировка применена")
        
        return {
            "process": process,
            "ws": ws,
            "cdp_url": cdp_url,
            "_id": 1,
            "port": port
        }
    
    # ============================================
    # 2.6: МЕТОДЫ УПРАВЛЕНИЯ БРАУЗЕРОМ
    # ============================================
    
    @staticmethod
    async def go_to(browser: dict, url: str, wait_time: int = 3):
        """Переход на страницу"""
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Page.navigate",
            "params": {"url": url}
        }))
        await asyncio.sleep(wait_time)
        logger.info(f"🌐 Перешел на {url}")
    
    @staticmethod
    async def click(browser: dict, selector: str, humanize: bool = True):
        """Клик по элементу с человеческим поведением"""
        if humanize:
            js = StealthBrowser.get_human_click_js(selector)
        else:
            js = f"document.querySelector('{selector}')?.click()"
        
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {"expression": js}
        }))
        logger.info(f"🖱️ Клик на {selector}")
    
    @staticmethod
    async def type_text(browser: dict, selector: str, text: str, humanize: bool = True):
        """Ввод текста с человеческим поведением"""
        if humanize:
            js = StealthBrowser.get_human_type_js(selector, text)
        else:
            js = f"document.querySelector('{selector}').value = '{text}'"
        
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {"expression": js}
        }))
        logger.info(f"⌨️ Ввод '{text}' в {selector}")
    
    @staticmethod
    async def scroll(browser: dict, distance: int, humanize: bool = True):
        """Скролл с человеческим поведением"""
        if humanize:
            js = StealthBrowser.get_human_scroll_js(distance)
        else:
            js = f"window.scrollBy(0, {distance})"
        
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {"expression": js}
        }))
        logger.info(f"📜 Скролл на {distance}px")
    
    @staticmethod
    async def get_text(browser: dict, selector: str) -> str:
        """Получение текста элемента"""
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {
                "expression": f"document.querySelector('{selector}')?.textContent || ''",
                "returnByValue": True
            }
        }))
        response = await browser["ws"].recv()
        data = json.loads(response)
        result = data.get("result", {}).get("result", {}).get("value", "")
        logger.info(f"📝 Получен текст: {result[:50]}...")
        return result
    
    @staticmethod
    async def get_html(browser: dict) -> str:
        """Получение HTML всей страницы"""
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True
            }
        }))
        response = await browser["ws"].recv()
        data = json.loads(response)
        return data.get("result", {}).get("result", {}).get("value", "")
    
    @staticmethod
    async def screenshot(browser: dict) -> bytes:
        """Сделать скриншот страницы"""
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Page.captureScreenshot",
            "params": {"format": "png", "quality": 100}
        }))
        response = await browser["ws"].recv()
        data = json.loads(response)
        
        if "result" in data and "data" in data["result"]:
            image_data = base64.b64decode(data["result"]["data"])
            logger.info(f"📸 Скриншот сделан ({len(image_data)} байт)")
            return image_data
        return None
    
    @staticmethod
    async def evaluate(browser: dict, expression: str) -> Any:
        """Выполнение произвольного JavaScript"""
        browser["_id"] += 1
        await browser["ws"].send(json.dumps({
            "id": browser["_id"],
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True
            }
        }))
        response = await browser["ws"].recv()
        data = json.loads(response)
        return data.get("result", {}).get("result", {}).get("value")
    
    @staticmethod
    async def wait_for_selector(browser: dict, selector: str, timeout: int = 10) -> bool:
        """Ожидание появления элемента"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = await StealthBrowser.evaluate(
                    browser,
                    f"!!document.querySelector('{selector}')"
                )
                if result:
                    return True
            except:
                pass
            await asyncio.sleep(0.5)
        return False
    
    @staticmethod
    async def close(browser: dict):
        """Закрытие браузера"""
        try:
            await browser["ws"].close()
        except:
            pass
        try:
            browser["process"].terminate()
        except:
            pass
        logger.info("🔚 Браузер закрыт")
    
    # ============================================
    # 2.7: СИНХРОННАЯ ОБЕРТКА
    # ============================================
    
    @staticmethod
    def launch_sync(
        headless: bool = False,
        port: int = 9222,
        proxy: str = None,
        chrome_path: str = None,
        user_data_dir: str = None,
        timeout: int = 30
    ) -> dict:
        """Синхронная обертка для launch()"""
        return asyncio.run(StealthBrowser.launch(
            headless=headless,
            port=port,
            proxy=proxy,
            chrome_path=chrome_path,
            user_data_dir=user_data_dir,
            timeout=timeout
        ))