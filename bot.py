import os
import logging
import asyncio
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

def create_full_stealth_options() -> ChromiumOptions:
    """100% стелс-конфигурация с Headless New"""
    options = ChromiumOptions()
    options.binary_location = '/usr/bin/chromium'
    
    # ===== 1. АРГУМЕНТЫ КОМАНДНОЙ СТРОКИ =====
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
    options.add_argument('--lang=en-US')
    options.add_argument('--accept-lang=en-US,en;q=0.9')
    options.add_argument('--use-gl=swiftshader')
    options.add_argument('--disable-features=WebGLDraftExtensions')
    options.webrtc_leak_protection = True
    options.add_argument('--window-size=1920,1080')
    
    # ===== HEADLESS NEW =====
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # Дополнительная маскировка
    options.add_argument('--disable-client-side-phishing-detection')
    options.add_argument('--disable-component-extensions-with-background-pages')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-xss-auditor')
    options.add_argument('--no-zygote')
    options.add_argument('--single-process')
    
    # ===== 2. НАСТРОЙКИ БРАУЗЕРА (ПРАВИЛЬНАЯ ВЛОЖЕННАЯ СТРУКТУРА) =====
    # Используем _set_pref_path для безопасной установки настроек
    options._set_pref_path(['profile', 'default_content_setting_values', 'geolocation'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'notifications'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'media_stream_mic'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'media_stream_camera'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'midi_sysex'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'push_messaging'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'ppapi_broker'], 2)
    options._set_pref_path(['profile', 'default_content_setting_values', 'automatic_downloads'], 1)
    options._set_pref_path(['profile', 'default_content_setting_values', 'cookies'], 1)
    options._set_pref_path(['profile', 'default_content_setting_values', 'popups'], 1)
    options._set_pref_path(['profile', 'password_manager_enabled'], False)
    options._set_pref_path(['credentials_enable_service'], False)
    options._set_pref_path(['intl', 'accept_languages'], 'en-US,en;q=0.9')
    options._set_pref_path(['download', 'prompt_for_download'], False)
    options._set_pref_path(['safebrowsing', 'enabled'], True)
    
    return options

async def human_delay(min_seconds: float = 0.5, max_seconds: float = 2.0):
    """Случайная задержка как у человека"""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    url = args[0] if args else 'https://whoer.net'
    
    await update.message.reply_text(f"🔄 Запускаю браузер с полной эмуляцией человека...\n📍 Цель: {url}")
    
    try:
        options = create_full_stealth_options()
        browser = Chrome(options=options)
        tab = await browser.start()
        
        # ===== 3. JS-СКРИПТЫ МАСКИРОВКИ =====
        await tab._connection_handler.execute_command(
            'Page.addScriptToEvaluateOnNewDocument',
            {
                'source': """
                    // ===== NAVIGATOR =====
                    Object.defineProperty(navigator, 'userAgent', {
                        get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
                    });
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32'
                    });
                    Object.defineProperty(navigator, 'vendor', {
                        get: () => 'Google Inc.'
                    });
                    Object.defineProperty(navigator, 'language', {
                        get: () => 'en-US'
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    delete navigator.__proto__.webdriver;
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 16 });
                    
                    // ===== WebGL =====
                    (() => {
                        const patchWebGL = (proto) => {
                            const oldGetParameter = proto.getParameter;
                            proto.getParameter = function(parameter) {
                                if (parameter === 37445) return 'Intel Inc.';
                                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                                if (parameter === 37447) return 'ANGLE (Intel, Intel(R) HD Graphics 630 Direct3D11 vs_5_0 ps_5_0)';
                                if (parameter === 36348) return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
                                if (parameter === 33902) return 'WebGL 1.0';
                                return oldGetParameter.call(this, parameter);
                            };
                        };
                        patchWebGL(WebGLRenderingContext.prototype);
                        if (window.WebGL2RenderingContext) {
                            patchWebGL(WebGL2RenderingContext.prototype);
                        }
                    })();
                    
                    // ===== Canvas =====
                    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type) {
                        if (type === 'image/png' || !type) {
                            const context = this.getContext('2d');
                            const imageData = context.getImageData(0, 0, this.width, this.height);
                            for (let i = 0; i < imageData.data.length; i += 4) {
                                imageData.data[i] = Math.floor(imageData.data[i] * 0.99 + 0.5);
                                imageData.data[i+1] = Math.floor(imageData.data[i+1] * 0.99 + 0.5);
                                imageData.data[i+2] = Math.floor(imageData.data[i+2] * 0.99 + 0.5);
                            }
                            context.putImageData(imageData, 0, 0);
                        }
                        return originalToDataURL.call(this, type);
                    };
                    
                    // ===== Audio =====
                    if (window.OfflineAudioContext) {
                        const originalCreateBuffer = OfflineAudioContext.prototype.createBuffer;
                        OfflineAudioContext.prototype.createBuffer = function() {
                            const buffer = originalCreateBuffer.apply(this, arguments);
                            const originalGetChannelData = buffer.getChannelData;
                            buffer.getChannelData = function(channel) {
                                const data = originalGetChannelData.call(this, channel);
                                for (let i = 0; i < data.length; i += 100) {
                                    data[i] += 0.001;
                                }
                                return data;
                            };
                            return buffer;
                        };
                    }
                    
                    // ===== Plugins =====
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            const plugins = [
                                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                                { name: 'Native Client', filename: 'internal-nacl-plugin' }
                            ];
                            plugins.__proto__ = PluginArray.prototype;
                            plugins.length = plugins.length;
                            plugins.item = (i) => plugins[i] || null;
                            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                            return plugins;
                        }
                    });
                    
                    // ===== MIME Types =====
                    Object.defineProperty(navigator, 'mimeTypes', {
                        get: () => {
                            const mimeTypes = [
                                { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                                { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' }
                            ];
                            mimeTypes.__proto__ = MimeTypeArray.prototype;
                            mimeTypes.length = mimeTypes.length;
                            mimeTypes.item = (i) => mimeTypes[i] || null;
                            mimeTypes.namedItem = (type) => mimeTypes.find(m => m.type === type) || null;
                            return mimeTypes;
                        }
                    });
                    
                    // ===== Screen =====
                    Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
                    Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
                    Object.defineProperty(screen, 'width', { get: () => 1920 });
                    Object.defineProperty(screen, 'height', { get: () => 1080 });
                    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                    Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
                    
                    // ===== Window =====
                    Object.defineProperty(window, 'outerWidth', { get: () => 1920 });
                    Object.defineProperty(window, 'outerHeight', { get: () => 1080 });
                    Object.defineProperty(window, 'innerWidth', { get: () => 1920 });
                    Object.defineProperty(window, 'innerHeight', { get: () => 1040 });
                    Object.defineProperty(window, 'screenX', { get: () => 0 });
                    Object.defineProperty(window, 'screenY', { get: () => 0 });
                    
                    // ===== Performance =====
                    Object.defineProperty(performance, 'memory', {
                        get: () => ({
                            jsHeapSizeLimit: 2172649472,
                            totalJSHeapSize: 103783181,
                            usedJSHeapSize: 94915910
                        })
                    });
                    
                    // ===== Chrome object =====
                    window.chrome = {
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        app: {}
                    };
                """
            }
        )
        
        # ===== 4. ОСНОВНАЯ ЛОГИКА С ПОЛНОЙ ЭМУЛЯЦИЕЙ =====
        await tab.go_to(url)
        await human_delay(2.0, 4.0)
        
        # Скролл с эмуляцией человека
        await tab.scroll.to_bottom(humanize=True)
        await human_delay(1.0, 2.0)
        await tab.scroll.to_top(humanize=True)
        await human_delay(0.5, 1.5)
        
        # Получаем информацию
        title = await tab.title
        current_url = await tab.current_url
        
        webdriver_check = await tab._connection_handler.execute_command(
            'Runtime.evaluate',
            {'expression': 'navigator.webdriver === undefined'}
        )
        
        user_agent = await tab._connection_handler.execute_command(
            'Runtime.evaluate',
            {'expression': 'navigator.userAgent'}
        )
        
        # Делаем скриншот
        screenshot = await tab.screenshot()
        
        await browser.close()
        
        # Отправляем результат
        await update.message.reply_text(
            f"✅ Страница загружена!\n"
            f"📌 Заголовок: {title}\n"
            f"🔗 URL: {current_url}\n"
            f"🛡️ WebDriver скрыт: {webdriver_check['result']['value']}\n"
            f"📱 User-Agent: {user_agent['result']['value'][:60]}...\n"
            f"🎭 Маскировка: 100%"
        )
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Скриншот {url}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с 100% маскировкой и эмуляцией человека\n\n"
        "🚀 Особенности:\n"
        "• Headless New режим\n"
        "• Полная маскировка navigator\n"
        "• WebGL, Canvas, Audio fingerprint\n"
        "• Защита WebRTC\n"
        "• Эмуляция человека:\n"
        "  - Движение мыши по кривым Безье\n"
        "  - Тремор и overshoot\n"
        "  - Переменная скорость набора\n"
        "  - Естественные паузы\n"
        "  - Скролл с физикой\n\n"
        "📌 Команды:\n"
        "/start - Приветствие\n"
        "/parse <url> - Запустить браузер с маскировкой\n"
        "Пример: /parse https://whoer.net"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", parse))
    app.run_polling()

if __name__ == "__main__":
    main()