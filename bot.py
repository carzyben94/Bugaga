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

async def inject_stealth_scripts(tab):
    """Внедрение JS-скриптов для маскировки"""
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
    
    await tab._connection_handler.execute_command({
        'method': 'Page.addScriptToEvaluateOnNewDocument',
        'params': {'source': js_script}
    })
    logger.debug("JS-скрипты маскировки внедрены")

async def get_element_text(tab, selector):
    """Утилита для получения текста элемента по CSS-селектору"""
    try:
        result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {
                'expression': f'''
                    (() => {{
                        const el = document.querySelector('{selector}');
                        return el ? el.textContent.trim() : '';
                    }})()
                '''
            }
        })
        return result.get('result', {}).get('result', {}).get('value', '')
    except Exception as e:
        logger.debug(f"Ошибка получения текста для {selector}: {e}")
        return ''

async def get_elements_count(tab, selector):
    """Утилита для подсчёта элементов по CSS-селектору"""
    try:
        result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {
                'expression': f'''
                    (() => {{
                        return document.querySelectorAll('{selector}').length;
                    }})()
                '''
            }
        })
        return result.get('result', {}).get('result', {}).get('value', 0)
    except Exception as e:
        logger.debug(f"Ошибка подсчёта элементов для {selector}: {e}")
        return 0

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /parse от пользователя {update.effective_user.id}")
    
    # Получаем URL из аргументов команды (если есть)
    url = 'https://example.com'
    if context.args:
        url = context.args[0]
        await update.message.reply_text(f"🔄 Запускаю браузер для парсинга: {url}")
    else:
        await update.message.reply_text("🔄 Запускаю браузер с Headless New + 100% маскировкой...")
    
    try:
        options = create_full_stealth_options()
        browser = Chrome(options=options)
        tab = await browser.start()
        logger.debug("Браузер запущен")
        
        # Внедряем JS-скрипты маскировки
        await inject_stealth_scripts(tab)
        
        # Переходим на страницу
        logger.debug(f"Переход на {url}")
        await tab.go_to(url)
        await asyncio.sleep(2)
        
        # ===== ПРОДВИНУТОЕ ЧЕЛОВЕЧЕСКОЕ ПОВЕДЕНИЕ =====
        logger.debug("Выполняем человеческие действия...")
        
        # 1. Скролл с человеческим поведением
        await tab.scroll.to_bottom(humanize=True)
        await asyncio.sleep(1)
        await tab.scroll.to_top(humanize=True)
        await asyncio.sleep(1)
        
        # 2. Поиск элементов с find_all=True (возвращает список)
        # Поиск всех ссылок
        links = await tab.find(tag_name='a', find_all=True)
        logger.debug(f"Найдено ссылок: {len(links)}")
        
        if links and len(links) > 1:
            try:
                # Кликаем по второй ссылке с человеческим поведением
                await links[1].click(humanize=True)
                logger.debug("Клик по ссылке выполнен")
                await asyncio.sleep(2)
                # Возвращаемся назад
                await tab.go_back()
                await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Не удалось кликнуть по ссылке: {e}")
        
        # 3. Поиск элементов разными способами
        # Поиск по CSS-селектору (один элемент)
        h1_elements = await tab.find(css_selector='h1', find_all=True)
        h1_text = await h1_elements[0].text if h1_elements else 'Не найдено'
        logger.debug(f"H1 текст: {h1_text}")
        
        # Поиск по классу (все элементы)
        elements_by_class = await tab.find(class_name='container', find_all=True)
        logger.debug(f"Найдено элементов с классом 'container': {len(elements_by_class)}")
        
        # Поиск по тексту (все элементы, содержащие текст)
        elements_with_text = await tab.find(text='Example', find_all=True)
        logger.debug(f"Найдено элементов с текстом 'Example': {len(elements_with_text)}")
        
        # 4. Ввод текста с человеческим поведением (если есть поля ввода)
        input_fields = await tab.find(tag_name='input', find_all=True)
        if input_fields:
            try:
                await input_fields[0].type_text("Пример текста от бота", humanize=True)
                logger.debug("Текст введён с человеческим поведением")
            except Exception as e:
                logger.debug(f"Не удалось ввести текст: {e}")
        
        # 5. Наведение мыши с человеческим поведением (если есть элементы)
        if elements_by_class:
            try:
                await elements_by_class[0].hover(humanize=True)
                logger.debug("Наведение мыши выполнено")
                await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Не удалось выполнить наведение: {e}")
        
        # ===== ИЗВЛЕЧЕНИЕ ДАННЫХ =====
        logger.debug("Извлекаем данные со страницы...")
        
        # Получаем заголовок страницы
        title = await tab.title
        
        # Извлекаем данные через JS
        h1_text = await get_element_text(tab, 'h1')
        paragraph = await get_element_text(tab, 'p')
        links_count = await get_elements_count(tab, 'a')
        body_text = await get_element_text(tab, 'body')
        body_text_length = len(body_text)
        
        # Пытаемся извлечь информацию о товаре (если есть)
        product_name = await get_element_text(tab, '.product-name, .product-title, h1')
        product_price_raw = await get_element_text(tab, '.price, .product-price')
        product_description = await get_element_text(tab, '.description, .product-description, p')
        
        # Парсим цену
        try:
            product_price = float(product_price_raw.replace('$', '').replace('€', '').replace(',', '').strip()) if product_price_raw else 0.0
        except:
            product_price = 0.0
        
        # Получаем User-Agent
        user_agent_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.userAgent'}
        })
        user_agent = user_agent_result.get('result', {}).get('result', {}).get('value', 'N/A')
        
        # Проверяем маскировку WebDriver
        webdriver_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.webdriver === undefined'}
        })
        webdriver_hidden = webdriver_result.get('result', {}).get('result', {}).get('value', False)
        
        # Получаем язык
        language_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.language'}
        })
        language = language_result.get('result', {}).get('result', {}).get('value', 'N/A')
        
        # Получаем количество плагинов
        plugins_result = await tab._connection_handler.execute_command({
            'method': 'Runtime.evaluate',
            'params': {'expression': 'navigator.plugins.length'}
        })
        plugins_count = plugins_result.get('result', {}).get('result', {}).get('value', 0)
        
        await browser.close()
        
        # ===== ФОРМИРУЕМ ОТВЕТ =====
        response = f"✅ Парсинг завершён!\n"
        response += f"📍 URL: {url}\n"
        response += f"📄 Заголовок: {title}\n"
        response += f"🛡️ WebDriver скрыт: {webdriver_hidden}\n"
        response += f"🌐 Язык: {language}\n"
        response += f"🔌 Плагинов: {plugins_count}\n"
        response += f"📱 User-Agent: {user_agent[:50]}...\n"
        response += f"🎭 Headless New: Активен\n\n"
        
        response += f"📊 Детали страницы:\n"
        response += f"• H1: {h1_text[:50] if h1_text else 'Не найдено'}\n"
        response += f"• Параграф: {paragraph[:100] if paragraph else 'Не найдено'}...\n"
        response += f"• Количество ссылок: {links_count}\n"
        response += f"• Длина текста: {body_text_length} символов\n"
        
        # Если есть информация о товаре
        if product_name and product_name != h1_text:
            response += f"\n🛒 Информация о товаре:\n"
            response += f"• Название: {product_name[:50]}\n"
            response += f"• Цена: ${product_price:.2f}\n" if product_price > 0 else "• Цена: Не указана\n"
            if product_description:
                response += f"• Описание: {product_description[:50]}...\n"
        
        # Отправляем результат
        if len(response) > 4000:
            with open('result.txt', 'w', encoding='utf-8') as f:
                f.write(response)
            with open('result.txt', 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename='result.txt',
                    caption="📋 Результат парсинга (полный)"
                )
            os.remove('result.txt')
        else:
            await update.message.reply_text(response)
        
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
        "• Человеческое поведение (скроллы, клики, ввод)\n"
        "• Гибкий поиск элементов (find_all=True)\n"
        "• Извлечение данных (заголовки, цены, описания)\n\n"
        "📌 Команды:\n"
        "/start - Приветствие\n"
        "/parse [URL] - Парсинг сайта\n"
        "/log - Получить файл логов\n\n"
        "💡 Примеры:\n"
        "/parse\n"
        "/parse https://example.com\n"
        "/parse https://books.toscrape.com"
    )

async def send_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /log от пользователя {update.effective_user.id}")
    
    try:
        log_file_path = 'bot.log'
        
        if not os.path.exists(log_file_path):
            await update.message.reply_text("❌ Файл логов не найден.")
            return
        
        # Проверяем размер файла
        file_size = os.path.getsize(log_file_path)
        
        if file_size > 50 * 1024 * 1024:  # 50 MB
            # Читаем последние 1000 строк
            with open(log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-1000:] if len(lines) > 1000 else lines
            
            temp_file = 'bot_last.log'
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.writelines(last_lines)
            
            with open(temp_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename='bot_last.log',
                    caption=f"📋 Последние {len(last_lines)} строк логов"
                )
            os.remove(temp_file)
        else:
            with open(log_file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename='bot.log',
                    caption="📋 Полный файл логов бота"
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
    logger.info("Бот запущен, начинаем polling")
    app.run_polling()

if __name__ == "__main__":
    main()