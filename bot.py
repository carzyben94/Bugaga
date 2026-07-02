# bot.py - Бот с Phantomwright и автоматической установкой браузера
import os
import sys
import subprocess
import logging
import asyncio
import importlib
import shutil
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Путь для Playwright браузеров
PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# ========== ПРОВЕРКА И УСТАНОВКА PHANTOMWRIGHT ==========
def install_phantomwright():
    """Устанавливает phantomwright-driver"""
    try:
        logger.info("📦 Устанавливаю phantomwright-driver...")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', 
            'phantomwright-driver==1.58.3', '--no-cache-dir'
        ])
        logger.info("✅ phantomwright-driver установлен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка установки phantomwright: {e}")
        return False

# Проверяем наличие phantomwright
PHANTOMWRIGHT_AVAILABLE = False
try:
    import importlib.util
    if importlib.util.find_spec("phantomwright"):
        from phantomwright import Phantomwright
        from phantomwright.driver import Driver
        PHANTOMWRIGHT_AVAILABLE = True
        logger.info("✅ Phantomwright найден")
    else:
        logger.warning("⚠️ Phantomwright не найден, устанавливаю...")
        if install_phantomwright():
            from phantomwright import Phantomwright
            from phantomwright.driver import Driver
            PHANTOMWRIGHT_AVAILABLE = True
            logger.info("✅ Phantomwright установлен и загружен")
except Exception as e:
    logger.error(f"❌ Ошибка импорта Phantomwright: {e}")
    PHANTOMWRIGHT_AVAILABLE = False

# ========== УСТАНОВКА БРАУЗЕРА ==========
def get_chromium_path() -> Optional[str]:
    """Находит путь к Chromium"""
    base_dir = PLAYWRIGHT_DIR
    if not os.path.exists(base_dir):
        return None
    
    for item in os.listdir(base_dir):
        if item.startswith("chromium-") and "headless" not in item:
            chrome_path = os.path.join(base_dir, item, "chrome-linux", "chrome")
            if os.path.exists(chrome_path):
                return chrome_path
    return None

def install_browser():
    """Устанавливает браузер через playwright"""
    if get_chromium_path():
        logger.info("✅ Браузер уже установлен")
        return True
    
    logger.info("⏳ Устанавливаю браузер...")
    
    try:
        # Устанавливаем playwright если нет
        try:
            import playwright
        except ImportError:
            logger.info("📦 Устанавливаю playwright...")
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', 'playwright'
            ])
        
        # Устанавливаем браузер
        subprocess.check_call([
            sys.executable, '-m', 'playwright', 'install', 'chromium'
        ])
        subprocess.check_call([
            sys.executable, '-m', 'playwright', 'install-deps'
        ])
        
        logger.info("✅ Браузер установлен через Playwright")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка установки браузера: {e}")
        return False

# Устанавливаем браузер при запуске
if not get_chromium_path():
    logger.info("🔄 Браузер не найден, устанавливаю...")
    install_browser()

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
pw_instance = None
browser_data = None
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None
}

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    """Получает экземпляр браузера"""
    global pw_instance, browser_data
    
    # Проверяем существующий браузер
    if browser_data:
        try:
            # Проверяем, жив ли браузер
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
            pw_instance = None
    
    # Создаем новый браузер
    try:
        if not PHANTOMWRIGHT_AVAILABLE:
            raise Exception("Phantomwright не доступен")
        
        from phantomwright import Phantomwright
        from phantomwright.driver import Driver
        
        pw_instance = Phantomwright()
        
        # Запускаем браузер
        app = await pw_instance.start(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,720',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        driver = Driver(app)
        page = await driver.new_page()
        
        # Устанавливаем юзер-агент
        await page.set_user_agent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Анти-детект
        await page.evaluate('''
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        ''')
        
        browser_data = {
            'app': app,
            'driver': driver,
            'page': page,
            'started_at': datetime.now()
        }
        
        logger.info("✅ Браузер запущен через Phantomwright")
        return browser_data
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        browser_data = None
        pw_instance = None
        
        # Пробуем через Playwright как запасной вариант
        try:
            logger.info("🔄 Пробую запустить через Playwright...")
            from playwright.async_api import async_playwright
            
            p = await async_playwright().start()
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            page = await browser.new_page()
            
            browser_data = {
                'playwright': p,
                'browser': browser,
                'page': page,
                'started_at': datetime.now(),
                'using': 'playwright'
            }
            
            logger.info("✅ Браузер запущен через Playwright")
            return browser_data
            
        except Exception as e2:
            logger.error(f"❌ Ошибка запуска через Playwright: {e2}")
            raise Exception(f"Не удалось запустить браузер: {e2}")

async def close_browser():
    """Закрывает браузер"""
    global browser_data, pw_instance
    
    if browser_data:
        try:
            if browser_data.get('using') == 'playwright':
                await browser_data['browser'].close()
                await browser_data['playwright'].stop()
            else:
                await browser_data['app'].stop()
        except:
            pass
        browser_data = None
        pw_instance = None
        logger.info("✅ Браузер закрыт")

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Бот с Phantomwright**\n\n"
        "📸 Команды:\n"
        "/start - Это меню\n"
        "/status - Статус бота\n"
        "/screenshot <url> - Скриншот страницы\n"
        "/browser - Информация о браузере\n"
        "/close - Закрыть браузер\n\n"
        "💡 Пример: /screenshot google.com"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус"""
    status_msg = "📊 **СТАТУС БОТА**\n\n"
    
    # Phantomwright
    status_msg += f"📦 Phantomwright: {'✅' if PHANTOMWRIGHT_AVAILABLE else '❌'}\n"
    
    # Браузер
    if browser_data:
        status_msg += f"🌐 Браузер: ✅ Запущен\n"
        uptime = (datetime.now() - browser_data['started_at']).total_seconds()
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        status_msg += f"⏱️ Аптайм: {hours}ч {minutes}м\n"
        using = browser_data.get('using', 'phantomwright')
        status_msg += f"🔧 Драйвер: {using}\n"
    else:
        status_msg += f"🌐 Браузер: ❌ Не запущен\n"
    
    # Путь к Chromium
    chromium_path = get_chromium_path()
    if chromium_path:
        status_msg += f"📁 Chromium: ✅ {chromium_path}\n"
    else:
        status_msg += f"📁 Chromium: ❌ Не найден\n"
    
    await update.message.reply_text(status_msg, parse_mode='Markdown')

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот URL"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /screenshot <url>\n"
            "Пример: /screenshot google.com"
        )
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Переходим по URL
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        # Делаем скриншот
        screenshot = await page.screenshot(full_page=True)
        
        # Отправляем
        await msg.delete()
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"✅ Скриншот: {url[:50]}..."
        )
        
        logger.info(f"✅ Скриншот сделан для {url}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def browser_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о браузере"""
    msg = await update.message.reply_text("🔍 Проверяю браузер...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Получаем информацию
        info = await page.evaluate('''
            () => {
                return {
                    url: window.location.href,
                    title: document.title,
                    userAgent: navigator.userAgent,
                    screenWidth: window.screen.width,
                    screenHeight: window.screen.height,
                    language: navigator.language,
                    platform: navigator.platform
                }
            }
        ''')
        
        response = "🌐 **Информация о браузере**\n\n"
        response += f"📍 URL: {info.get('url', 'Нет')}\n"
        response += f"📌 Title: {info.get('title', 'Нет')[:50]}\n"
        response += f"📱 User-Agent: {info.get('userAgent', 'Нет')[:80]}...\n"
        response += f"🖥️ Размер: {info.get('screenWidth')}x{info.get('screenHeight')}\n"
        response += f"🌍 Язык: {info.get('language', 'Нет')}\n"
        response += f"💻 Платформа: {info.get('platform', 'Нет')}\n"
        
        await msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

async def install_browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная установка браузера"""
    msg = await update.message.reply_text("🔄 Устанавливаю браузер...")
    
    # Закрываем старый браузер
    await close_browser()
    
    # Устанавливаем
    if install_browser():
        await msg.edit_text("✅ Браузер установлен успешно!")
    else:
        await msg.edit_text("❌ Ошибка установки браузера!")

# ========== ОБРАБОТЧИК ОШИБОК ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте /status для проверки."
            )
        except:
            pass

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("browser", browser_info))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("install_browser", install_browser_cmd))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"📦 Phantomwright: {'✅' if PHANTOMWRIGHT_AVAILABLE else '❌'}")
    logger.info(f"🌐 Браузер: {'✅' if get_chromium_path() else '❌'}")
    logger.info("Команды: /start, /status, /screenshot, /browser, /close, /install_browser")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()