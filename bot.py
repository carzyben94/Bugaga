import os
import logging
import asyncio
import threading
import time
import subprocess
import sys
from datetime import datetime
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# ============= УСТАНОВКА CHROME =============
CHROME_INSTALLED = False
CHROME_INSTALLATION_IN_PROGRESS = False

def install_chrome():
    """Устанавливает Chrome в контейнере"""
    global CHROME_INSTALLATION_IN_PROGRESS
    
    if CHROME_INSTALLATION_IN_PROGRESS:
        logging.warning("⚠️ Установка Chrome уже выполняется!")
        return False
    
    CHROME_INSTALLATION_IN_PROGRESS = True
    logging.info("🔄 Установка Chrome...")
    
    try:
        # Проверяем, есть ли Chrome
        chrome_paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                logging.info(f"✅ Chrome уже установлен: {path}")
                CHROME_INSTALLATION_IN_PROGRESS = False
                return True
        
        # Устанавливаем Chrome через apt
        logging.info("📥 Скачивание и установка Chrome...")
        
        # Добавляем репозиторий Google
        subprocess.run(
            "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg",
            shell=True,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list',
            shell=True,
            check=True,
            capture_output=True
        )
        
        # Обновляем и устанавливаем
        subprocess.run(
            "apt-get update && apt-get install -y google-chrome-stable",
            shell=True,
            check=True,
            capture_output=True,
            timeout=300
        )
        
        logging.info("✅ Chrome успешно установлен!")
        CHROME_INSTALLATION_IN_PROGRESS = False
        return True
        
    except subprocess.TimeoutExpired:
        logging.error("❌ Таймаут установки Chrome!")
        CHROME_INSTALLATION_IN_PROGRESS = False
        return False
    except Exception as e:
        logging.error(f"❌ Ошибка установки Chrome: {e}")
        CHROME_INSTALLATION_IN_PROGRESS = False
        return False

def check_chrome_installed():
    """Проверяет, установлен ли Chrome"""
    chrome_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            logging.info(f"✅ Найден Chrome: {path}")
            return True
    
    # Проверяем через which
    try:
        result = subprocess.run(
            "which google-chrome || which chromium || which chromium-browser",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            logging.info(f"✅ Найден Chrome: {result.stdout.strip()}")
            return True
    except:
        pass
    
    logging.warning("⚠️ Chrome не найден!")
    return False

# Проверяем Chrome при запуске
logging.info("🔄 Проверка Chrome...")
CHROME_INSTALLED = check_chrome_installed()

if not CHROME_INSTALLED:
    logging.info("🔄 Chrome не установлен. Попытка автоматической установки...")
    CHROME_INSTALLED = install_chrome()
    if CHROME_INSTALLED:
        logging.info("✅ Chrome успешно установлен при запуске!")
    else:
        logging.warning("⚠️ Не удалось установить Chrome. Используйте /install_chrome")

# ============= ГЛОБАЛЬНЫЙ БРАУЗЕР =============
browser_instance = None
browser_lock = asyncio.Lock()
browser_initialized = False

def get_chrome_path():
    """Находит путь к Chrome"""
    chrome_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            return path
    
    try:
        result = subprocess.run(
            "which google-chrome || which chromium || which chromium-browser",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    
    return None

async def init_browser():
    """Инициализация Nodriver"""
    global browser_instance, browser_initialized
    
    async with browser_lock:
        if browser_instance is None and not browser_initialized:
            logging.info("🔄 Запуск Nodriver...")
            try:
                import nodriver as nd
                
                chrome_path = get_chrome_path()
                if not chrome_path:
                    logging.error("❌ Chrome не найден!")
                    browser_initialized = True
                    return False
                
                logging.info(f"📂 Использую Chrome: {chrome_path}")
                
                browser_instance = await nd.start(
                    headless=True,
                    window_size=(1024, 768),
                    browser_executable_path=chrome_path,
                    arguments=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials',
                        '--disable-web-security',
                        '--window-size=1024,768',
                    ]
                )
                browser_initialized = True
                logging.info("✅ Nodriver успешно запущен!")
                return True
            except Exception as e:
                logging.error(f"❌ Ошибка запуска Nodriver: {e}")
                browser_instance = None
                browser_initialized = True
                return False
    return browser_instance is not None

async def get_browser():
    """Получить экземпляр браузера"""
    global browser_instance
    if browser_instance is None and not browser_initialized:
        await init_browser()
    return browser_instance

async def create_page():
    """Создать новую страницу"""
    browser = await get_browser()
    if browser is None:
        logging.error("❌ Браузер не инициализирован")
        return None
    try:
        page = await browser.get('about:blank')
        logging.info("✅ Страница создана!")
        return page
    except Exception as e:
        logging.error(f"❌ Ошибка создания страницы: {e}")
        return None

async def do_browser_action(page, action, url=None):
    """Выполнить действие с браузером"""
    try:
        if action == "goto" and url:
            await page.get(url)
            await page.wait_for('body', timeout=30000)
            return True
        elif action == "screenshot":
            return await page.screenshot()
        elif action == "close":
            return True
        return False
    except Exception as e:
        logging.error(f"❌ Ошибка выполнения действия {action}: {e}")
        return None

# ============= ЛОГГЕР =============
class LogStorage:
    def __init__(self, max_logs=100):
        self.logs = []
        self.max_logs = max_logs
    
    def add_log(self, message, log_type="INFO", user_id=None, username=None):
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": log_type,
            "user_id": user_id,
            "username": username,
            "message": message
        }
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        logging.info(f"[{log_type}] {message}")
    
    def get_all_logs(self, limit=50):
        return self.logs[-limit:] if self.logs else []
    
    def clear_logs(self):
        self.logs.clear()
        self.add_log("Логи очищены", "SYSTEM")

def format_logs_for_window(logs, limit=30):
    if not logs:
        return "📭 Логов пока нет"
    
    lines = []
    emoji_map = {
        "INFO": "ℹ️", 
        "COMMAND": "⚡", 
        "ERROR": "❌", 
        "SYSTEM": "🔧", 
        "WARNING": "⚠️",
        "BROWSER": "🌐"
    }
    
    for log in logs[:limit]:
        timestamp = log["timestamp"][11:19]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        emoji = emoji_map.get(log_type, "📌")
        
        if username:
            lines.append(f"{emoji} {timestamp} [{log_type}] @{username}")
        else:
            lines.append(f"{emoji} {timestamp} [{log_type}]")
        lines.append(f"   {message[:60]}{'...' if len(message) > 60 else ''}")
        lines.append("")
    
    return "\n".join(lines)

def format_logs_clean(logs, limit=30):
    if not logs:
        return "Логов нет"
    
    lines = []
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        user_info = f" [@{username}]" if username else ""
        lines.append(f"[{timestamp}] {log_type}{user_info}")
        lines.append(f"  {message}")
        lines.append("")
    
    return "\n".join(lines)

# ============= КЛАВИАТУРЫ =============

def get_logs_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")],
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_browser_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="open_site")],
        [InlineKeyboardButton("✅ Проверить статус", callback_data="browser_status")],
        [InlineKeyboardButton("🔄 Перезапустить", callback_data="browser_restart")],
        [InlineKeyboardButton("📸 Сделать скриншот", callback_data="browser_screenshot")],
        [InlineKeyboardButton("📥 Установить Chrome", callback_data="install_chrome")]
    ]
    return InlineKeyboardMarkup(keyboard)

def log_command(func):
    async def wrapper(update, context):
        user = update.effective_user
        user_id = user.id if user else None
        username = user.username if user else None
        command = update.message.text if update.message else "unknown"
        
        log_storage = context.bot_data.get('log_storage')
        if log_storage:
            log_storage.add_log(
                f"Команда: {command}",
                "COMMAND",
                user_id=user_id,
                username=username
            )
        
        return await func(update, context)
    return wrapper

# ===================================

log_storage = LogStorage()

# ============= КОМАНДЫ =============

@log_command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅" if CHROME_INSTALLED else "❌"
    await update.message.reply_text(
        f"🖥️ <b>Stealth Browser Bot (Nodriver)</b>\n\n"
        f"📋 /logs  – показать логи\n"
        f"🗑️ /clear – очистить логи\n"
        f"🌐 /browser – управление браузером\n"
        f"📥 /install_chrome – установить Chrome\n\n"
        f"⚡ Chrome: {status}\n"
        f"🛡️ Защита: Nodriver (Stealth)\n\n"
        f"<i>Бот сам установит Chrome при первом запуске</i>",
        parse_mode="HTML"
    )

@log_command
async def install_chrome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для установки Chrome"""
    global CHROME_INSTALLED, CHROME_INSTALLATION_IN_PROGRESS
    
    if CHROME_INSTALLATION_IN_PROGRESS:
        await update.message.reply_text("⏳ Установка уже выполняется...", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text("⏳ Установка Chrome... Это может занять 2-3 минуты.", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, install_chrome)
    
    if success:
        CHROME_INSTALLED = True
        await status_msg.edit_text("✅ Chrome успешно установлен!", parse_mode="HTML")
        log_storage.add_log("Chrome установлен по команде", "SYSTEM")
    else:
        await status_msg.edit_text("❌ Ошибка установки! Проверьте логи.", parse_mode="HTML")

@log_command
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Загрузка...", parse_mode="HTML")
    
    try:
        logs = log_storage.get_all_logs(limit=30)
        
        if not logs:
            await status_msg.edit_text("📭 Логов пока нет", parse_mode="HTML")
            return
        
        display_text = format_logs_for_window(logs)
        clean_text = format_logs_clean(logs)
        
        context.user_data['copy_logs'] = clean_text
        
        await status_msg.edit_text(
            f"<pre>{display_text}</pre>",
            parse_mode="HTML",
            reply_markup=get_logs_keyboard(),
            disable_web_page_preview=True
        )
        
        log_storage.add_log("Показаны логи", "INFO")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка в /logs: {str(e)}", "ERROR")

@log_command
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_storage.clear_logs()
    await update.message.reply_text("🗑️ Логи очищены ✅", parse_mode="HTML")

@log_command
async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 <b>Управление браузером Nodriver</b>\n\n"
        "🛡️ Stealth-режим активен\n"
        "Используйте кнопки для управления:",
        parse_mode="HTML",
        reply_markup=get_browser_keyboard()
    )

# ============= ОБРАБОТЧИКИ КНОПОК =============

async def install_chrome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback для установки Chrome"""
    global CHROME_INSTALLED, CHROME_INSTALLATION_IN_PROGRESS
    
    query = update.callback_query
    await query.answer()
    
    if CHROME_INSTALLATION_IN_PROGRESS:
        await query.message.reply_text("⏳ Установка уже выполняется...", parse_mode="HTML")
        return
    
    status_msg = await query.message.reply_text("⏳ Установка Chrome... Это может занять 2-3 минуты.", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, install_chrome)
    
    if success:
        CHROME_INSTALLED = True
        await status_msg.edit_text("✅ Chrome успешно установлен!", parse_mode="HTML")
        log_storage.add_log("Chrome установлен по кнопке", "SYSTEM")
    else:
        await status_msg.edit_text("❌ Ошибка установки! Проверьте логи.", parse_mode="HTML")

async def copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    copy_text = context.user_data.get('copy_logs', '')
    
    if copy_text:
        await query.message.reply_text(
            f"<pre>{copy_text}</pre>",
            parse_mode="HTML"
        )
        log_storage.add_log("Скопированы логи", "SYSTEM")
        await query.answer("✅ Логи отправлены!")
    else:
        await query.answer("❌ Нет данных", show_alert=True)

async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    log_storage.clear_logs()
    await query.message.edit_text("🗑️ Логи очищены ✅", parse_mode="HTML")
    await query.answer("✅ Очищено!")

async def browser_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global browser_instance
    
    if not CHROME_INSTALLED:
        await query.message.reply_text("❌ Chrome не установлен! Нажмите '📥 Установить Chrome'", parse_mode="HTML")
        return
    
    if browser_instance is not None:
        await query.message.reply_text(
            "✅ Браузер запущен и работает\n🛡️ Stealth-защита активна",
            parse_mode="HTML"
        )
    else:
        await query.message.reply_text("❌ Браузер не запущен. Инициализация...", parse_mode="HTML")
        success = await init_browser()
        if success:
            await query.message.reply_text("✅ Браузер успешно запущен!", parse_mode="HTML")
        else:
            await query.message.reply_text("❌ Ошибка запуска браузера!", parse_mode="HTML")

async def browser_restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global browser_instance, browser_initialized
    
    if not CHROME_INSTALLED:
        await query.message.reply_text("❌ Chrome не установлен! Нажмите '📥 Установить Chrome'", parse_mode="HTML")
        return
    
    await query.message.reply_text("🔄 Перезапуск браузера...", parse_mode="HTML")
    
    if browser_instance:
        try:
            await browser_instance.stop()
        except:
            pass
        browser_instance = None
        browser_initialized = False
    
    success = await init_browser()
    
    if success:
        await query.message.reply_text("✅ Браузер перезапущен!", parse_mode="HTML")
        log_storage.add_log("Браузер перезапущен", "SYSTEM")
    else:
        await query.message.reply_text("❌ Ошибка перезапуска!", parse_mode="HTML")

async def browser_screenshot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not CHROME_INSTALLED:
        await query.message.reply_text("❌ Chrome не установлен! Нажмите '📥 Установить Chrome'", parse_mode="HTML")
        return
    
    try:
        page = await create_page()
        if page is None:
            await query.message.reply_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        await do_browser_action(page, "goto", "https://example.com")
        screenshot = await do_browser_action(page, "screenshot", None)
        
        if screenshot:
            photo = BytesIO(screenshot)
            photo.name = "screenshot.png"
            await query.message.reply_photo(
                photo=photo, 
                caption="📸 Скриншот example.com\n🛡️ Сделан через Nodriver"
            )
            log_storage.add_log("Сделан скриншот через Nodriver", "BROWSER")
        else:
            await query.message.reply_text("❌ Ошибка создания скриншота!", parse_mode="HTML")
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка скриншота: {str(e)}", "ERROR")

async def open_site_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not CHROME_INSTALLED:
        await query.message.reply_text("❌ Chrome не установлен! Нажмите '📥 Установить Chrome'", parse_mode="HTML")
        return
    
    context.user_data['waiting_for_url'] = True
    
    await query.message.reply_text(
        "🌐 <b>Введите URL сайта</b>\n\n"
        "Примеры:\n"
        "• https://x.com\n"
        "• https://github.com\n"
        "• https://example.com\n\n"
        "❗ Введите полный адрес с https://\n"
        "🛡️ Будет использован stealth-режим Nodriver",
        parse_mode="HTML"
    )

async def handle_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_url'):
        return
    
    if not CHROME_INSTALLED:
        await update.message.reply_text("❌ Chrome не установлен! Нажмите /install_chrome", parse_mode="HTML")
        context.user_data['waiting_for_url'] = False
        return
    
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ <b>Неверный формат URL</b>\n\n"
            "URL должен начинаться с http:// или https://\n\n"
            "Пример: https://x.com",
            parse_mode="HTML"
        )
        return
    
    context.user_data['waiting_for_url'] = False
    
    status_msg = await update.message.reply_text(f"⏳ Открываю {url}...", parse_mode="HTML")
    
    try:
        page = await create_page()
        if page is None:
            await status_msg.edit_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        success = await do_browser_action(page, "goto", url)
        
        if success:
            screenshot = await do_browser_action(page, "screenshot", None)
            
            if screenshot:
                photo = BytesIO(screenshot)
                photo.name = "screenshot.png"
                
                await status_msg.delete()
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"✅ <b>Сайт открыт через Nodriver:</b>\n{url}",
                    parse_mode="HTML"
                )
                log_storage.add_log(f"Открыт сайт через Nodriver: {url}", "BROWSER")
            else:
                await status_msg.edit_text(f"✅ Сайт открыт, но скриншот не сохранился:\n{url}", parse_mode="HTML")
        else:
            await status_msg.edit_text(f"❌ Ошибка открытия:\n{url}", parse_mode="HTML")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка открытия {url}: {str(e)}", "ERROR")

# ============= ЗАПУСК =============

def start_browser_thread():
    def run_browser():
        logging.info("🔄 Фоновый поток браузера Nodriver запущен")
        if CHROME_INSTALLED:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(init_browser())
        while True:
            time.sleep(60)
    
    thread = threading.Thread(target=run_browser, daemon=True)
    thread.start()
    logging.info("✅ Фоновый поток запущен")

def main():
    start_browser_thread()
    
    async def reset_webhook():
        app = Application.builder().token(TOKEN).build()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.initialize()
        await app.shutdown()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(reset_webhook())
    
    app = Application.builder().token(TOKEN).build()
    app.bot_data['log_storage'] = log_storage
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("browser", browser_command))
    app.add_handler(CommandHandler("install_chrome", install_chrome_command))
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(browser_status_callback, pattern="browser_status"))
    app.add_handler(CallbackQueryHandler(browser_restart_callback, pattern="browser_restart"))
    app.add_handler(CallbackQueryHandler(browser_screenshot_callback, pattern="browser_screenshot"))
    app.add_handler(CallbackQueryHandler(open_site_callback, pattern="open_site"))
    app.add_handler(CallbackQueryHandler(install_chrome_callback, pattern="install_chrome"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input))
    
    log_storage.add_log("Бот запущен с Nodriver + автоустановкой Chrome", "SYSTEM")
    logging.info("🚀 Бот с Nodriver запущен!")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()