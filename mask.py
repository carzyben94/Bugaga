import random
import logging
from typing import Dict, Any, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)


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


class Mask:
    """
    100% маскировка браузера — полная копия Pydoll.
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    ]

    WEBGL_VENDORS = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (AMD)",
        "Google Inc. (Intel)",
        "NVIDIA Corporation",
        "Advanced Micro Devices, Inc.",
        "Intel Corporation"
    ]

    WEBGL_RENDERERS = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ]

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
        return random.choice(Mask.USER_AGENTS)

    @staticmethod
    def random_webgl_vendor() -> str:
        return random.choice(Mask.WEBGL_VENDORS)

    @staticmethod
    def random_webgl_renderer() -> str:
        return random.choice(Mask.WEBGL_RENDERERS)

    @staticmethod
    def get_launch_args(chrome_path: str, debug_port: int) -> List[str]:
        """Флаги запуска Chrome (как в Pydoll)"""
        window = Mask.random_window_position()
        user_agent = Mask.random_user_agent()

        return [
            chrome_path,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",

            # ===== Скрываем автоматизацию =====
            "--disable-blink-features=AutomationControlled",
            "--disable-automation",

            # ===== GPU и WebGL =====
            "--use-gl=egl",
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-zero-copy",

            # ===== Отключаем всё лишнее =====
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

            # ===== Настройки окна =====
            f"--window-position={window['left']},{window['top']}",
            f"--window-size={window['width']},{window['height']}",

            # ===== Дополнительно =====
            "--no-default-browser-check",
            "--no-first-run",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--password-store=basic",
            "--use-mock-keychain",
            "--export-tagged-pdf",
            "--enable-features=NetworkService,NetworkServiceInProcess",

            # ===== User-Agent (только HTTP-заголовок) =====
            f"--user-agent={user_agent}",

            f"--remote-debugging-port={debug_port}",
            "about:blank"
        ]

    @staticmethod
    def get_js_mask() -> str:
        """
        JS-маскировка 100% как в Pydoll.
        Выполняется через Page.addScriptToEvaluateOnNewDocument.
        """
        webgl_vendor = Mask.random_webgl_vendor()
        webgl_renderer = Mask.random_webgl_renderer()
        chrome_version = random.randint(118, 120)
        hardware_concurrency = random.randint(4, 16)
        device_memory = random.choice([4, 8, 16, 32])
        rtt = random.randint(20, 100)
        downlink = round(random.uniform(5, 20), 1)
        effective_type = random.choice(['4g', '3g'])
        connection_type = random.choice(['wifi', 'ethernet'])
        screen_height = random.randint(800, 1080)
        screen_width = random.randint(1200, 1920)
        platform = random.choice(['Win32', 'MacIntel', 'Linux x86_64'])
        lang = random.choice(['en-US', 'en-GB', 'fr-FR', 'de-DE', 'ru-RU'])
        timezone = random.choice([
            'America/New_York', 'Europe/London', 'Europe/Paris',
            'Europe/Berlin', 'Europe/Moscow', 'Asia/Tokyo'
        ])

        return f"""
        (function() {{
            console.log('🕵️ Pydoll маскировка...');

            // ========== 1. NAVIGATOR (как в Pydoll) ==========

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

            // userAgentData (Client Hints)
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
                                architecture: 'x86',
                                bitness: '64',
                                model: '',
                                platform: '{platform}',
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
                                platform: '{platform}',
                                mobile: false
                            }};
                        }}
                    }};
                }},
                configurable: true,
                enumerable: true
            }});

            // Connection
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

            // ========== 2. WEBGL (как в Pydoll) ==========

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
                    }}
                    return context;
                }}
                return originalGetContext.call(this, contextId, attributes);
            }};

            // ========== 3. SCREEN (как в Pydoll) ==========

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

            // ========== 4. CHROME (как в Pydoll) ==========

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

            // ========== 5. TIMING ШУМ (как в Pydoll) ==========

            const originalPerfNow = performance.now;
            performance.now = function() {{
                return originalPerfNow.call(this) + (Math.random() * 0.1);
            }};

            const originalDateNow = Date.now;
            Date.now = function() {{
                return originalDateNow.call(this) + Math.floor(Math.random() * 5);
            }};

            // ========== 6. DOCUMENT (как в Pydoll) ==========

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

            console.log('✅ Pydoll маскировка применена');
        }})()
        """

    # ========== HUMANIZE (как в Pydoll) ==========

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
            const stepsPerFrame = Math.max(1, Math.floor(totalSteps / 60));

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
                const freq = 0.5 + Math.random() * 0.5;
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
                const alphabet = 'abcdefghijklmnopqrstuvwxyz';
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
                let isTypo = false;
                if (Math.random() < 0.02 && index < chars.length - 1) {{
                    const typoChar = generateTypo(char);
                    if (typoChar) {{
                        el.value += typoChar;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        isTypo = true;

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
            let scrolled = 0;

            // Физика: импульс + трение
            let velocity = 50 + Math.random() * 100;
            const friction = 0.92 + Math.random() * 0.05;
            const minVelocity = 10;

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
                scrolled += finalDelta;
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