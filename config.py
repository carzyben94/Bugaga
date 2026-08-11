# config.py
import os
import json
import random

# ============================================================
# 1. АНТИДЕТЕКТ-ФЛАГИ CHROME (с новым headless)
# ============================================================
CHROME_FLAGS = [
    # ---------- HEADLESS (НОВАЯ ВЕРСИЯ) ----------
    '--headless=new',  # Новый headless-режим (Chrome 109+)
    '--window-size=1920,1080',
    '--force-device-scale-factor=1',
    
    # ---------- Удаление следов автоматизации ----------
    '--disable-blink-features=AutomationControlled',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-web-security',
    '--disable-site-isolation-trials',
    
    # ---------- Скрытие сигнатуры GPU ----------
    '--use-gl=swiftshader',
    '--disable-accelerated-2d-canvas',
    '--disable-accelerated-jpeg-decoding',
    '--disable-accelerated-mjpeg-decode',
    '--disable-accelerated-video-decode',
    
    # ---------- Отключение автоматических проверок ----------
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-default-apps',
    '--disable-file-system',
    '--disable-client-side-phishing-detection',
    '--disable-component-update',
    '--disable-domain-reliability',
    '--disable-sync',
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-breakpad',
    '--disable-crash-reporter',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-hang-monitor',
    '--disable-ipc-flooding-protection',
    '--disable-popup-blocking',
    '--disable-prompt-on-repost',
    '--disable-renderer-backgrounding',
    '--disable-setuid-sandbox',
    '--disable-software-rasterizer',
    '--disable-windows10-custom-titlebar',
    
    # ---------- Блокировка уведомлений ----------
    '--disable-notifications',
    '--disable-password-manager',
    '--disable-password-manager-reauthentication',
    '--disable-saving-browser-history',
    
    # ---------- Защита от утечек IP ----------
    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
    '--block-new-web-contents',
    
    # ---------- Отключение кэширования ----------
    '--disable-cache',
    '--disable-application-cache',
    '--disable-offline-load-stale-cache',
    '--disable-session-crashed-bubble',
    '--disable-infobars',
    
    # ---------- Стабильность ----------
    '--no-sandbox',
    '--disable-gpu-sandbox',
    
    # ---------- Отключение обновлений ----------
    '--disable-background-downloads',
    '--disable-remote-fonts',
    
    # ---------- Дополнительно ----------
    '--disable-print-preview',
    '--disable-3d-apis',
    '--disable-bundled-ppapi-flash',
    '--disable-rtc-smoothness-algorithm',
    '--disable-speech-api',
    '--disable-usb-keyboard-detect',
    
    # ---------- Для headless ----------
    '--disable-extensions',
    '--disable-plugins',
    '--disable-images',
    '--disable-javascript',
]

# ============================================================
# 2. ПРЕФЕРЕНСЫ БРАУЗЕРА
# ============================================================
BROWSER_PREFERENCES = {
    'intl.accept_languages': 'ja-JP,ja;q=0.9,en;q=0.8',
    'intl.charset.default': 'UTF-8',
    'profile.password_manager_enabled': False,
    'profile.default_content_settings.exceptions.notifications': {'*': {'setting': 2}},
    'profile.default_content_setting_values.popups': 2,
    'credentials_enable_service': False,
    'credentials_enable_autosignin': False,
    'safebrowsing.enabled': False,
    'safebrowsing.disable_download_protection': True,
    'download.default_directory': '/dev/null',
    'download.prompt_for_download': False,
    'download.directory_upgrade': True,
    'browser.download.folderList': 2,
    'browser.download.manager.showWhenStarting': False,
    'browser.download.manager.useWindow': False,
    'browser.download.manager.alertOnEXEOpen': False,
    'browser.download.manager.closeWhenDone': True,
    'privacy_sandbox.enabled': False,
    'privacy_sandbox.privacy_sandbox_enabled': False,
    'privacy_sandbox.privacy_sandbox_eligible': False,
    'privacy_sandbox.privacy_sandbox_consent_decision': False,
}

# ============================================================
# 3. ЦИФРОВОЙ ОТПЕЧАТОК (Fingerprint)
# ============================================================
FINGERPRINT_CONFIG = {
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'platform': 'Win32',
    'accept_language': 'ja-JP,ja;q=0.9,en;q=0.8',
    'timezone': 'Asia/Tokyo',
    'geolocation': {
        'latitude': 35.6895,
        'longitude': 139.6917,
        'accuracy': 10
    },
    'screen_resolution': {
        'width': 1920,
        'height': 1080,
        'color_depth': 24,
        'pixel_ratio': 1
    },
    'hardware_concurrency': 8,
    'device_memory': 8,
    'webgl_vendor': 'Google Inc. (Intel)',
    'webgl_renderer': 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)',
    'webrtc_leak_protection': True,
    'webrtc_ip_handling_policy': 'disable_non_proxied_udp',
    'audio_fingerprint': True,
    'canvas_fingerprint': True,
}

# ============================================================
# 4. STEALTH JS - ПОЛНЫЙ СКРИПТ ДЛЯ ИНЪЕКЦИИ
# ============================================================
def get_stealth_js():
    """Генерация полного stealth-скрипта на основе конфига"""
    return f"""
    // ============================================================
    // 1. МАСКИРОВКА NAVIGATOR
    // ============================================================
    
    // Удаление navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
    
    // Маскировка языка (синхронизация с Accept-Language)
    Object.defineProperty(navigator, 'language', {{get: () => '{FINGERPRINT_CONFIG["accept_language"].split(",")[0]}'}});
    Object.defineProperty(navigator, 'languages', {{get: () => {json.dumps(FINGERPRINT_CONFIG["accept_language"].split(","))}}});
    
    // Маскировка платформы
    Object.defineProperty(navigator, 'platform', {{get: () => '{FINGERPRINT_CONFIG["platform"]}'}});
    
    // Маскировка аппаратных характеристик
    Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {FINGERPRINT_CONFIG["hardware_concurrency"]}}});
    Object.defineProperty(navigator, 'deviceMemory', {{get: () => {FINGERPRINT_CONFIG["device_memory"]}}});
    
    // Маскировка разрешения экрана
    Object.defineProperty(screen, 'width', {{get: () => {FINGERPRINT_CONFIG["screen_resolution"]["width"]}}});
    Object.defineProperty(screen, 'height', {{get: () => {FINGERPRINT_CONFIG["screen_resolution"]["height"]}}});
    Object.defineProperty(screen, 'colorDepth', {{get: () => {FINGERPRINT_CONFIG["screen_resolution"]["color_depth"]}}});
    Object.defineProperty(screen, 'pixelDepth', {{get: () => {FINGERPRINT_CONFIG["screen_resolution"]["color_depth"]}}});
    
    // ============================================================
    // 2. МАСКИРОВКА ЧАСОВОГО ПОЯСА (timezone)
    // ============================================================
    
    // Переопределение getTimezoneOffset
    const originalGetTimezoneOffset = Date.prototype.getTimezoneOffset;
    Date.prototype.getTimezoneOffset = function() {{
        const timezoneOffset = {{
            'Asia/Tokyo': -540,
            'America/New_York': 300,
            'Europe/London': 0,
            'Europe/Moscow': -180,
            'Asia/Shanghai': -480,
            'Asia/Singapore': -480,
            'Australia/Sydney': -660,
            'Pacific/Auckland': -720,
            'America/Los_Angeles': 480,
            'America/Chicago': 360,
            'America/Denver': 420,
            'America/Phoenix': 420,
            'America/Anchorage': 540,
            'Pacific/Honolulu': 600
        }};
        return timezoneOffset['{FINGERPRINT_CONFIG["timezone"]}'] || 0;
    }};
    
    // Переопределение Intl.DateTimeFormat для таймзоны
    const originalDateTimeFormat = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function(locales, options) {{
        if (options && options.timeZone) {{
            options.timeZone = '{FINGERPRINT_CONFIG["timezone"]}';
        }}
        return new originalDateTimeFormat(locales, options);
    }};
    Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;
    
    // ============================================================
    // 3. МАСКИРОВКА ГЕОЛОКАЦИИ
    // ============================================================
    
    if (navigator.geolocation) {{
        const originalGetCurrentPosition = navigator.geolocation.getCurrentPosition;
        const originalWatchPosition = navigator.geolocation.watchPosition;
        
        const mockPosition = {{
            coords: {{
                latitude: {FINGERPRINT_CONFIG["geolocation"]["latitude"]},
                longitude: {FINGERPRINT_CONFIG["geolocation"]["longitude"]},
                accuracy: {FINGERPRINT_CONFIG["geolocation"]["accuracy"]},
                altitude: null,
                altitudeAccuracy: null,
                heading: null,
                speed: null
            }},
            timestamp: Date.now()
        }};
        
        navigator.geolocation.getCurrentPosition = function(success, error, options) {{
            if (success) success(mockPosition);
        }};
        
        navigator.geolocation.watchPosition = function(success, error, options) {{
            if (success) success(mockPosition);
            return 0;
        }};
    }}
    
    // ============================================================
    // 4. МАСКИРОВКА WEBGL
    // ============================================================
    
    const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
        if (parameter === 37445) {{
            return '{FINGERPRINT_CONFIG["webgl_vendor"]}';
        }}
        if (parameter === 37446) {{
            return '{FINGERPRINT_CONFIG["webgl_renderer"]}';
        }}
        return originalGetParameter.call(this, parameter);
    }};
    
    // ============================================================
    // 5. МАСКИРОВКА CANVAS (рандомизация)
    // ============================================================
    
    if ({str(FINGERPRINT_CONFIG["canvas_fingerprint"]).lower()}) {{
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
            if (type === 'image/png' || !type) {{
                const ctx = this.getContext('2d');
                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                const data = imageData.data;
                for (let i = 0; i < data.length; i += 4) {{
                    data[i] += (Math.random() - 0.5) * 0.1;
                }}
                ctx.putImageData(imageData, 0, 0);
            }}
            return originalToDataURL.call(this, type, quality);
        }};
        
        CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {{
            const imageData = originalGetImageData.call(this, x, y, w, h);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {{
                data[i] += (Math.random() - 0.5) * 0.1;
            }}
            return imageData;
        }};
    }}
    
    // ============================================================
    // 6. МАСКИРОВКА AUDIO CONTEXT
    // ============================================================
    
    if ({str(FINGERPRINT_CONFIG["audio_fingerprint"]).lower()}) {{
        const originalGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(channel) {{
            const data = originalGetChannelData.call(this, channel);
            for (let i = 0; i < data.length; i++) {{
                data[i] += (Math.random() - 0.5) * 0.001;
            }}
            return data;
        }};
    }}
    
    // ============================================================
    // 7. МАСКИРОВКА CLIENT HINTS
    // ============================================================
    
    Object.defineProperty(navigator, 'userAgentData', {{
        get: () => ({{
            brands: [
                {{brand: 'Chromium', version: '120'}},
                {{brand: 'Google Chrome', version: '120'}},
                {{brand: 'Not?A_Brand', version: '24'}}
            ],
            mobile: false,
            platform: '{FINGERPRINT_CONFIG["platform"]}',
            getHighEntropyValues: async (hints) => {{
                const result = {{}};
                if (hints.includes('architecture')) result.architecture = 'x86';
                if (hints.includes('bitness')) result.bitness = '64';
                if (hints.includes('fullVersionList')) {{
                    result.fullVersionList = [
                        {{brand: 'Chromium', version: '120.0.0.0'}},
                        {{brand: 'Google Chrome', version: '120.0.0.0'}},
                        {{brand: 'Not?A_Brand', version: '24.0.0.0'}}
                    ];
                }}
                if (hints.includes('model')) result.model = '';
                if (hints.includes('platformVersion')) result.platformVersion = '10.0.0';
                if (hints.includes('uaFullVersion')) result.uaFullVersion = '{FINGERPRINT_CONFIG["user_agent"].split("Chrome/")[1].split(" ")[0]}';
                return result;
            }}
        }})
    }});
    
    // ============================================================
    // 8. МАСКИРОВКА BATTERY STATUS API
    // ============================================================
    
    if (navigator.getBattery) {{
        const originalGetBattery = navigator.getBattery;
        navigator.getBattery = function() {{
            return Promise.resolve({{
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1,
                onchargingchange: null,
                onchargingtimechange: null,
                ondischargingtimechange: null,
                onlevelchange: null
            }});
        }};
    }}
    
    // ============================================================
    // 9. МАСКИРОВКА PERMISSIONS
    // ============================================================
    
    if (navigator.permissions) {{
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = function(descriptor) {{
            if (descriptor.name === 'geolocation') {{
                return Promise.resolve({{state: 'prompt', onchange: null}});
            }}
            if (descriptor.name === 'notifications') {{
                return Promise.resolve({{state: 'denied', onchange: null}});
            }}
            return originalQuery.call(this, descriptor);
        }};
    }}
    
    console.log('✅ Stealth маскировка полностью применена');
    console.log('🕐 Таймзона: {FINGERPRINT_CONFIG["timezone"]}');
    console.log('📍 Геолокация: {FINGERPRINT_CONFIG["geolocation"]["latitude"]}, {FINGERPRINT_CONFIG["geolocation"]["longitude"]}');
    """

# ============================================================
# 5. НАСТРОЙКИ ПРОКСИ
# ============================================================
PROXY_CONFIG = {
    'enabled': False,
    'server': None,  # 'http://user:pass@residential.proxy.com:8080'
    'bypass_list': ['localhost', '127.0.0.1', '*.local', '*.internal'],
    'rotation': {
        'enabled': False,
        'strategy': 'random',
        'rotation_interval': 10,
        'proxy_list': []
    }
}

# ============================================================
# 6. ОЧЕЛОВЕЧИВАНИЕ (Humanization)
# ============================================================
HUMANIZATION_CONFIG = {
    'mouse': {
        'enabled': True,
        'bezier_curves': True,
        'fitts_law': True,
        'tremor': True,
        'overshoot_chance': 0.7,
        'jitter': 2,
        'overshoot_distance': 15,
        'correction_chance': 0.8,
        'micro_corrections': True,
        'smoothness': 0.8,
    },
    'keyboard': {
        'enabled': True,
        'typo_chance': 0.02,
        'delay_min': 0.03,
        'delay_max': 0.12,
        'thinking_pause_chance': 0.02,
        'distraction_pause_chance': 0.005,
        'typo_adjacent_key_chance': 0.7,
        'typo_missing_key_chance': 0.15,
        'typo_double_key_chance': 0.15,
        'punctuation_pause': True,
        'punctuation_pause_duration': 0.2,
    },
    'scroll': {
        'enabled': True,
        'jitter': 3,
        'micro_pause_chance': 0.05,
        'overshoot_chance': 0.15,
        'momentum': True,
        'friction': True,
        'overshoot_amount': 30,
        'momentum_decay': 0.98,
        'friction_coefficient': 0.9,
        'bounce_effect': True,
    },
    'navigation': {
        'enabled': True,
        'wait_before_navigate': 0.1,
        'wait_before_interact': 0.3,
        'max_load_time': 30,
        'check_console_errors': True,
    },
    'click': {
        'enabled': True,
        'jitter': 2,
        'hold_min': 0.05,
        'hold_max': 0.15,
        'double_click_delay': 0.25,
    }
}

# ============================================================
# 7. СКРИНШОТЫ
# ============================================================
SCREENSHOT_CONFIG = {
    'format': 'png',
    'quality': 100,
    'fullPage': True,
    'captureBeyondViewport': True,
}

# ============================================================
# 8. ТАЙМАУТЫ
# ============================================================
TIMEOUTS = {
    'navigation': 30000,
    'screenshot': 10000,
    'script': 5000,
    'page_load': 30000,
    'element_wait': 5000,
}

# ============================================================
# 9. TELEGRAM
# ============================================================
BOT_CONFIG = {
    'token': os.environ.get("TELEGRAM_BOT_TOKEN"),
    'polling_timeout': 30,
}

# ============================================================
# 10. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_combined_config():
    """Получить объединенную конфигурацию"""
    return {
        'chrome_flags': CHROME_FLAGS,
        'preferences': BROWSER_PREFERENCES,
        'fingerprint': FINGERPRINT_CONFIG,
        'proxy': PROXY_CONFIG,
        'humanization': HUMANIZATION_CONFIG,
        'screenshot': SCREENSHOT_CONFIG,
        'timeouts': TIMEOUTS,
        'bot': BOT_CONFIG,
        'stealth_js': get_stealth_js()
    }

def get_random_user_agent():
    """Получить случайный User-Agent из списка"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    ]
    return random.choice(user_agents)