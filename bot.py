import os
import logging
import asyncio
import subprocess
import sys
import platform
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Глобальные переменные
pw = None
browser_installed = False

# Функция установки Chromium
async def install_browser():
    global browser_installed
    
    logger.info("🔄 Начинаем установку браузера...")
    
    try:
        # Определяем ОС
        system = platform.system()
        logger.info(f"📊 ОС: {system}")
        
        if system == "Linux":
            # Для Linux (Railway использует Linux)
            commands = [
                ["apt-get", "update"],
                ["apt-get", "install", "-y", "chromium", "chromium-driver"],
                ["apt-get", "install", "-y", "fonts-liberation", "libasound2", "libatk-bridge2.0-0"],
                ["apt-get", "install", "-y", "libatk1.0-0", "libcups2", "libdbus-1-3"],
                ["apt-get", "install", "-y", "libdrm2", "libgbm1", "libgtk-3-0"],
                ["apt-get", "install", "-y", "libnspr4", "libnss3", "libx11-xcb1"],
                ["apt-get", "install", "-y", "libxcomposite1", "libxdamage1", "libxrandr2"],
                ["apt-get", "install", "-y", "xdg-utils", "wget", "curl"]
            ]
            
            for cmd in commands:
                logger.info(f"📦 Выполняем: {' '.join(cmd)}")
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    logger.warning(f"⚠️ Ошибка в команде: {stderr.decode()}")
                else:
                    logger.info(f"✅ Команда выполнена: {stdout.decode()[:200]}")
            
            # Проверяем установку
            process = await asyncio.create_subprocess_exec(
                "chromium", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"✅ Chromium установлен: {stdout.decode().strip()}")
                browser_installed = True
                os.environ['CHROME_PATH'] = '/usr/bin/chromium'
                return True
            else:
                logger.error(f"❌ Ошибка проверки Chromium: {stderr.decode()}")
                return False
                
        elif system == "Windows":
            # Для Windows - используем webdriver_manager
            logger.info("🪟 Windows: установка через webdriver_manager")
            try:
                import webdriver_manager
                browser_installed = True
                return True
            except ImportError:
                await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "pip", "install", "webdriver-manager"
                )
                browser_installed = True
                return True
                
        else:
            logger.error(f"❌ Неподдерживаемая ОС: {system}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка установки браузера: {e}")
        return False

# Функция инициализации Phantomwright
async def init_phantomwright():
    global pw, browser_installed
    
    try:
        # Проверяем установку браузера
        if not browser_installed:
            logger.info("🔄 Браузер не установлен, начинаем установку...")
            if not await install_browser():
                logger.error("❌ Не удалось установить браузер")
                return False
        
        # Импортируем Phantomwright
        try:
            from phantomwright import Phantomwright
            from phantomwright.driver import Driver
            
            # Создаем экземпляр
            pw = Phantomwright()
            logger.info("✅ Phantomwright инициализирован успешно")
            return True
            
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта Phantomwright: {e}")
            # Пытаемся установить Phantomwright
            await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "phantomwright-driver==1.58.3"
            )
            # Повторяем импорт
            from phantomwright import Phantomwright
            from phantomwright.driver import Driver
            pw = Phantomwright()
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Phantomwright: {e}")
        return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Бот запускается...\n"
        "Проверяю установку браузера..."
    )
    
    # Инициализируем в фоне
    if not pw:
        success = await init_phantomwright()
        if success:
            await update.message.reply_text(
                "✅ Браузер установлен!\n"
                "📸 Теперь отправьте URL для скриншота\n"
                "Пример: https://google.com"
            )
        else:
            await update.message.reply_text(
                "❌ Не удалось установить браузер\n"
                "Проверьте логи Railway"
            )

# Команда /install - принудительная установка
async def install_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_installed
    
    msg = await update.message.reply_text("🔄 Начинаю установку браузера...")
    
    browser_installed = False
    success = await install_browser()
    
    if success:
        await msg.edit_text("✅ Браузер успешно установлен!\n🔄 Инициализирую Phantomwright...")
        
        if await init_phantomwright():
            await msg.edit_text(
                "✅ Готово!\n"
                "📸 Отправьте URL для скриншота"
            )
        else:
            await msg.edit_text("❌ Ошибка инициализации Phantomwright")
    else:
        await msg.edit_text("❌ Ошибка установки браузера")

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pw, browser_installed
    
    status_text = "🤖 Статус бота:\n"
    status_text += f"✅ Бот работает\n"
    status_text += f"📦 Браузер: {'✅ Установлен' if browser_installed else '❌ Не установлен'}\n"
    status_text += f"🔧 Phantomwright: {'✅ Готов' if pw else '❌ Не инициализирован'}\n"
    
    await update.message.reply_text(status_text)

# Функция скриншота
async def take_screenshot(update: Update, url: str):
    global pw
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Проверяем инициализацию
    if not pw:
        msg = await update.message.reply_text("🔄 Инициализация Phantomwright...")
        if not await init_phantomwright():
            await msg.edit_text("❌ Ошибка инициализации. Попробуйте /install")
            return
        await msg.delete()
    
    try:
        msg = await update.message.reply_text("📸 Делаю скриншот...")
        
        from phantomwright.driver import Driver
        
        async with pw.start(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080'
            ]
        ) as app:
            
            driver = Driver(app)
            page = await driver.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            screenshot = await page.screenshot(full_page=True)
            
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ {url[:50]}..."
            )
            
            await msg.delete()
            logger.info(f"✅ Скриншот сделан для {url}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)[:150]}\n"
            "Попробуйте /install для переустановки"
        )

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if '.' in text and ' ' not in text:
        await take_screenshot(update, text)
    else:
        await update.message.reply_text(
            "📸 Отправьте URL для скриншота\n"
            "Пример: google.com или https://example.com\n\n"
            "Или используйте команды:\n"
            "/start - Приветствие\n"
            "/install - Установить браузер\n"
            "/status - Статус"
        )

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Ошибка. Попробуйте /install"
            )
        except:
            pass

def main():
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    try:
        app = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("install", install_command))
        app.add_handler(CommandHandler("status", status_command))
        
        # Обработчик текста
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info("💡 Используйте /install для установки браузера")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()