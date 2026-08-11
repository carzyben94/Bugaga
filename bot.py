import os
import logging
import asyncio
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions

# Настройка логирования в файл
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),  # Логи в файл
        logging.StreamHandler(sys.stdout)  # И в консоль
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

def create_full_stealth_options() -> ChromiumOptions:
    """100% стелс-конфигурация с Headless New"""
    logger.debug("Начинаем создание опций браузера")
    options = ChromiumOptions()
    options.binary_location = '/usr/bin/chromium'
    
    # ===== АРГУМЕНТЫ КОМАНДНОЙ СТРОКИ =====
    logger.debug("Добавляем аргументы командной строки")
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
        try:
            options.add_argument(arg)
            logger.debug(f"Добавлен аргумент: {arg}")
        except Exception as e:
            logger.warning(f"Не удалось добавить аргумент {arg}: {e}")
    
    # ===== НАСТРОЙКИ WEBRTC =====
    logger.debug("Настраиваем WebRTC")
    options.webrtc_leak_protection = True
    
    # ===== НАСТРОЙКИ БРАУЗЕРА =====
    logger.debug("Настраиваем browser_preferences")
    
    # Проверяем тип browser_preferences до изменения
    logger.debug(f"Тип browser_preferences до: {type(options.browser_preferences)}")
    logger.debug(f"Значение browser_preferences до: {options.browser_preferences}")
    
    try:
        # Пробуем установить как словарь
        preferences = {
            'intl': {
                'accept_languages': 'en-US,en;q=0.9'
            },
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
                'password_manager_enabled': False,
                'content_settings': {
                    'exceptions': {
                        'geolocation': {
                            'https://*,*': {
                                'last_modified': '13000000000000000',
                                'setting': 2
                            }
                        }
                    }
                }
            },
            'credentials_enable_service': False,
            'download': {
                'default_directory': '/tmp/downloads',
                'prompt_for_download': False
            },
            'safebrowsing': {
                'enabled': False
            }
        }
        
        logger.debug(f"Тип preferences: {type(preferences)}")
        logger.debug(f"Preferences: {preferences}")
        
        # Пробуем установить
        options.browser_preferences = preferences
        logger.debug("browser_preferences успешно установлен")
        logger.debug(f"Тип browser_preferences после: {type(options.browser_preferences)}")
        
    except Exception as e:
        logger.error(f"Ошибка при установке browser_preferences: {e}", exc_info=True)
        # Если не работает, пробуем альтернативный способ
        logger.debug("Пробуем альтернативный способ - через словарь")
        try:
            # Создаем новый словарь и присваиваем по ключам
            if isinstance(options.browser_preferences, dict):
                logger.debug("browser_preferences уже словарь, обновляем")
                options.browser_preferences.update(preferences)
            else:
                logger.debug("browser_preferences не словарь, создаем новый")
                # Если это строка, преобразуем в словарь
                if isinstance(options.browser_preferences, str):
                    logger.debug(f"browser_preferences это строка: {options.browser_preferences}")
                    # Создаем новый словарь
                    options.browser_preferences = {}
                    options.browser_preferences.update(preferences)
                else:
                    options.browser_preferences = preferences
            logger.debug("Альтернативный способ сработал")
        except Exception as e2:
            logger.error(f"Альтернативный способ тоже не сработал: {e2}", exc_info=True)
    
    logger.debug("Опции созданы успешно")
    return options

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /parse от пользователя {update.effective_user.id}")
    await update.message.reply_text("🔄 Запускаю браузер с Headless New + 100% маскировкой...")
    
    try:
        logger.debug("Создаем опции браузера")
        options = create_full_stealth_options()
        
        logger.debug("Создаем экземпляр Chrome")
        browser = Chrome(options=options)
        
        logger.debug("Запускаем браузер")
        tab = await browser.start()
        logger.debug("Браузер запущен успешно")
        
        # ===== JS-СКРИПТЫ МАСКИРОВКИ =====
        logger.debug("Внедряем JS-скрипты маскировки")
        try:
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
            logger.debug("JS-скрипты внедрены успешно")
        except Exception as e:
            logger.error(f"Ошибка при внедрении JS: {e}", exc_info=True)
            raise
        
        # ===== ОСНОВНАЯ ЛОГИКА =====
        logger.debug("Переходим на example.com")
        await tab.go_to('https://example.com')
        await asyncio.sleep(2)
        
        logger.debug("Выполняем скролл")
        await tab.scroll.to_bottom(humanize=True)
        await asyncio.sleep(1)
        await tab.scroll.to_top(humanize=True)
        await asyncio.sleep(0.5)
        
        # Получаем информацию
        logger.debug("Получаем информацию о странице")
        title = await tab.title
        user_agent = await tab._connection_handler.execute_command(
            'Runtime.evaluate',
            {'expression': 'navigator.userAgent'}
        )
        
        is_webdriver_hidden = await tab._connection_handler.execute_command(
            'Runtime.evaluate',
            {'expression': 'navigator.webdriver === undefined'}
        )
        
        language = await tab._connection_handler.execute_command(
            'Runtime.evaluate',
            {'expression': 'navigator.language'}
        )
        
        logger.debug("Закрываем браузер")
        await browser.close()
        
        await update.message.reply_text(
            f"✅ Заголовок: {title}\n"
            f"🛡️ WebDriver скрыт: {is_webdriver_hidden['result']['value']}\n"
            f"🌐 Язык: {language['result']['value']}\n"
            f"📱 User-Agent: {user_agent['result']['value'][:50]}...\n"
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
        "• Человеческое поведение\n"
        "• Настройки браузера через Preferences\n\n"
        "📌 Команды:\n"
        "/start - Приветствие\n"
        "/parse - Запустить браузер с маскировкой\n"
        "/log - Получить файл логов"
    )

async def send_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл логов в чат"""
    logger.info(f"Получена команда /log от пользователя {update.effective_user.id}")
    
    try:
        log_file_path = 'bot.log'
        
        # Проверяем, существует ли файл
        if not os.path.exists(log_file_path):
            await update.message.reply_text("❌ Файл логов не найден. Возможно, бот только что запущен.")
            return
        
        # Проверяем размер файла
        file_size = os.path.getsize(log_file_path)
        logger.debug(f"Размер файла логов: {file_size} байт")
        
        # Если файл слишком большой (> 50MB), отправляем только последние строки
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
        
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text("⚠️ Файл логов слишком большой. Отправляю последние 1000 строк.")
            
            # Читаем последние 1000 строк
            with open(log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-1000:] if len(lines) > 1000 else lines
                
            # Создаем временный файл с последними строками
            temp_file = 'bot_last.log'
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.writelines(last_lines)
            
            # Отправляем файл
            with open(temp_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename='bot_last.log',
                    caption=f"📋 Последние {len(last_lines)} строк логов"
                )
            
            # Удаляем временный файл
            os.remove(temp_file)
        else:
            # Отправляем полный файл
            with open(log_file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename='bot.log',
                    caption="📋 Полный файл логов бота"
                )
            
        logger.info("Файл логов отправлен успешно")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке логов: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при отправке логов: {str(e)}")

def main():
    logger.info("Запуск бота")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parse", parse))
    app.add_handler(CommandHandler("log", send_log))  # Добавляем команду /log
    logger.info("Бот запущен, начинаем polling")
    app.run_polling()

if __name__ == "__main__":
    main()