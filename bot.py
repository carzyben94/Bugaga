import os
import logging
import asyncio
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

def create_full_stealth_options() -> ChromiumOptions:
    """100% стелс-конфигурация с Headless New"""
    options = ChromiumOptions()
    options.binary_location = '/usr/bin/chromium'
    
    # Аргументы командной строки
    args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-features=IsolateOrigins,site-per-process',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        '--lang=en-US',
        '--accept-lang=en-US,en;q=0.9',
        '--use-gl=swiftshader',
        '--disable-features=WebGLDraftExtensions',
        '--window-size=1920,1080',
        '--headless=new',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-client-side-phishing-detection',
        '--disable-component-extensions-with-background-pages',
        '--disable-default-apps',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-translate',
        '--disable-web-security',
        '--disable-xss-auditor',
        '--no-zygote',
        '--single-process',
        '--disable-sync'
    ]
    
    for arg in args:
        options.add_argument(arg)
    
    options.webrtc_leak_protection = True
    
    # Настройки браузера
    options.browser_preferences = {
        'intl': {'accept_languages': 'en-US,en;q=0.9'},
        'profile': {
            'default_content_setting_values': {
                'geolocation': 2,
                'notifications': 2,
                'media_stream_mic': 2,
                'media_stream_camera': 2,
                'midi_sysex': 2,
                'push_messaging': 2,
                'ppapi_broker': 2,
                'automatic_downloads': 1,
                'cookies': 1
            },
            'password_manager_enabled': False
        },
        'credentials_enable_service': False
    }
    
    return options

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /parse от пользователя {update.effective_user.id}")
    await update.message.reply_text("🔄 Запускаю браузер с Headless New + 100% маскировкой...")
    
    try:
        options = create_full_stealth_options()
        browser = Chrome(options=options)
        tab = await browser.start()
        logger.debug("Браузер запущен")
        
        # JS-скрипт для маскировки
        js_script = """
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
        
        # Внедряем JS-скрипт
        result = await tab._connection_handler.execute_command({
            'method': 'Page.addScriptToEvaluateOnNewDocument',
            'params': {'source': js_script}
        })
        logger.debug(f"JS-скрипт внедрён: {result}")
        
        # Переходим на страницу
        await tab.go_to('https://example.com')
        await asyncio.sleep(2)
        
        # Скролл
        await tab.scroll.to_bottom(humanize=True)
        await asyncio.sleep(1)
        await tab.scroll.to_top(humanize=True)
        await asyncio.sleep(0.5)
        
        # Получаем информацию
        title = await tab.title
        
        # Функция для безопасного извлечения значения
        def get_result_value(response, default='N/A'):
            try:
                return response.get('result', {}).get('result', {}).get('value', default)
            except:
                return default
        
        user_agent_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.userAgent'}
        })
        
        webdriver_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.webdriver === undefined'}
        })
        
        language_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.language'}
        })
        
        plugins_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.plugins.length'}
        })
        
        await browser.close()
        
        # Извлекаем значения с проверкой
        user_agent = get_result_value(user_agent_result)
        webdriver_hidden = get_result_value(webdriver_result, 'False')
        language = get_result_value(language_result)
        plugins_count = get_result_value(plugins_result, '0')
        
        await update.message.reply_text(
            f"✅ Заголовок: {title}\n"
            f"🛡️ WebDriver скрыт: {webdriver_hidden}\n"
            f"🌐 Язык: {language}\n"
            f"🔌 Плагинов: {plugins_count}\n"
            f"📱 User-Agent: {user_agent[:50]}...\n"
            f"🎭 Headless New: Активен"
        )
        logger.info("Команда /parse выполнена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка в /parse: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с 100% маскировкой Pydoll\n\n"
        "🚀 Особенности:\n"
        "• Headless New режим\n"
        "• Полная маскировка navigator\n"
        "• WebGL, Canvas, Audio fingerprint\n"
        "• Защита WebRTC\n"
        "• Человеческое поведение\n\n"
        "📌 Команды:\n"
        "/start - Приветствие\n"
        "/parse - Запустить браузер с маскировкой\n"
        "/log - Получить файл логов"
    )

async def send_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /log от пользователя {update.effective_user.id}")
    
    try:
        log_file_path = 'bot.log'
        
        if not os.path.exists(log_file_path):
            await update.message.reply_text("❌ Файл логов не найден.")
            return
        
        with open(log_file_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename='bot.log',
                caption="📋 Файл логов бота"
            )
        logger.info("Файл логов отправлен")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке логов: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    logger.info("Запуск бота")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", parse))
    app.add_handler(CommandHandler("log", send_log))
    app.run_polling()

if __name__ == "__main__":
    main()