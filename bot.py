import os
import logging
import asyncio
import threading
import time
import subprocess
import sys
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# ============= УСТАНОВКА PLAYWRIGHT =============
BROWSER_INSTALLED = False
BROWSER_INSTALLATION_IN_PROGRESS = False

def download_browser():
    """Устанавливает Playwright и браузеры"""
    global BROWSER_INSTALLATION_IN_PROGRESS
    
    if BROWSER_INSTALLATION_IN_PROGRESS:
        logging.warning("⚠️ Установка уже выполняется!")
        return False
    
    BROWSER_INSTALLATION_IN_PROGRESS = True
    logging.info("🔄 Установка Playwright и браузеров...")
    
    try:
        # Установка playwright
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright", "playwright-stealth"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            logging.error(f"❌ Ошибка установки playwright: {result.stderr}")
            BROWSER_INSTALLATION_IN_PROGRESS = False
            return False
        
        # Установка браузеров
        logging.info("📥 Скачивание браузера Chromium...")
        result2 = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300  # 5 минут
        )
        
        if result2.returncode == 0:
            logging.info("✅ Playwright и Chromium успешно установлены!")
            BROWSER_INSTALLATION_IN_PROGRESS = False
            return True
        else:
            logging.error(f"❌ Ошибка установки Chromium: {result2.stderr}")
            BROWSER_INSTALLATION_IN_PROGRESS = False
            return False
            
    except subprocess.TimeoutExpired:
        logging.error("❌ Таймаут установки (5 минут)!")
        BROWSER_INSTALLATION_IN_PROGRESS = False
        return False
    except Exception as e:
        logging.error(f"❌ Ошибка установки: {e}")
        BROWSER_INSTALLATION_IN_PROGRESS = False
        return False

def check_browser_installed():
    """Проверяет, установлен ли Playwright"""
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        logging.info("✅ Playwright работает!")
        return True
    except Exception as e:
        logging.warning(f"⚠️ Playwright не работает: {e}")
        return False

# Проверяем при запуске
logging.info("🔄 Проверка Playwright...")
BROWSER_INSTALLED = check_browser_installed()

if not BROWSER_INSTALLED:
    logging.info("🔄 Playwright не установлен. Попытка автоматической установки...")
    BROWSER_INSTALLED = download_browser()
    if BROWSER_INSTALLED:
        logging.info("✅ Playwright успешно установлен при запуске!")
    else:
        logging.warning("⚠️ Не удалось установить Playwright. Используйте /download_browser")

# ============= ГЛОБАЛЬНЫЙ БРАУЗЕР =============
browser_instance = None
browser_lock = threading.Lock()
browser_initialized = False

def init_browser_sync():
    """Инициализация браузера Playwright с stealth"""
    global browser_instance, browser_initialized
    
    if not BROWSER_INSTALLED:
        logging.error("❌ Playwright не установлен! Запустите /download_browser")
        return False
    
    with browser_lock:
        if browser_instance is None and not browser_initialized:
            logging.info("🔄 Запуск Playwright с stealth...")
            try:
                from playwright.sync_api import sync_playwright
                from playwright_stealth import stealth_sync
                
                # Создаем контекст с настройками антидетекта
                playwright = sync_playwright().start()
                
                # Маскируем браузер под реальный
                browser = playwright.chromium.launch(
                    headless=False,  # Для лучшей маскировки используем False
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials',
                        '--disable-web-security',
                        '--disable-features=BlockInsecurePrivateNetworkRequests',
                        '--disable-features=OutOfBlinkCors',
                        '--window-size=1024,768',
                    ]
                )
                
                # Создаем контекст с реальными параметрами
                context = browser.new_context(
                    viewport={'width': 1024, 'height': 768},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='ru-RU',
                    timezone_id='Europe/Moscow',
                    permissions=['geolocation'],
                    extra_http_headers={
                        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                        'Sec-Ch-Ua-Mobile': '?0',
                        'Sec-Ch-Ua-Platform': '"Windows"',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )
                
                # Создаем страницу и применяем stealth
                page = context.new_page()
                
                # Применяем stealth-маскировку
                stealth_sync(page)
                
                # Дополнительная маскировка через CDP
                page.add_init_script("""
                    // Переопределяем navigator.webdriver
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Маскируем chrome
                    Object.defineProperty(navigator, 'chrome', {
                        get: () => ({
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        })
                    });
                    
                    // Подменяем plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Маскируем languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['ru-RU', 'ru', 'en-US', 'en']
                    });
                    
                    // Убираем следы автоматизации
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                """)
                
                # Сохраняем все в глобальную переменную
                browser_instance = {
                    'playwright': playwright,
                    'browser': browser,
                    'context': context,
                    'page': page
                }
                
                browser_initialized = True
                logging.info("✅ Playwright с stealth запущен!")
                return True
                
            except Exception as e:
                logging.error(f"❌ Ошибка запуска Playwright: {e}")
                browser_instance = None
                browser_initialized = True
                return False
                
    return browser_instance is not None

def get_browser_sync():
    """Получить экземпляр браузера"""
    global browser_instance
    if browser_instance is None and not browser_initialized:
        init_browser_sync()
    return browser_instance

def create_page_sync():
    """Создать новую страницу (используем существующую)"""
    browser = get_browser_sync()
    if browser is None:
        logging.error("❌ Браузер не инициализирован")
        return None
    
    try:
        # Возвращаем существующую страницу
        return browser['page']
    except Exception as e:
        logging.error(f"❌ Ошибка получения страницы: {e}")
        return None

def do_browser_action_sync(page, action, url=None):
    """Выполнить действие с браузером"""
    try:
        if action == "goto" and url:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            return True
        elif action == "screenshot":
            # Делаем скриншот с высоким качеством
            return page.screenshot(full_page=True)
        elif action == "close":
            # В playwright не закрываем страницу, чтобы не терять сессию
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
        [InlineKeyboardButton("📥 Скачать браузер", callback_data="download_browser")]
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
    status = "✅" if BROWSER_INSTALLED else "❌"
    await update.message.reply_text(
        f"🖥️ <b>Stealth Browser Bot (Playwright)</b>\n\n"
        f"📋 /logs  – показать логи\n"
        f"🗑️ /clear – очистить логи\n"
        f"🌐 /browser – управление браузером\n"
        f"📥 /download_browser – скачать браузер\n\n"
        f"⚡ Браузер: {status}\n"
        f"🛡️ Защита: playwright-stealth\n\n"
        f"<i>Если браузер не работает, нажмите /download_browser</i>",
        parse_mode="HTML"
    )

@log_command
async def download_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для скачивания браузера"""
    global BROWSER_INSTALLED, BROWSER_INSTALLATION_IN_PROGRESS
    
    if BROWSER_INSTALLATION_IN_PROGRESS:
        await update.message.reply_text("⏳ Установка уже выполняется...", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text("⏳ Установка Playwright... Это может занять 2-3 минуты.", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, download_browser)
    
    if success:
        BROWSER_INSTALLED = True
        await status_msg.edit_text("✅ Playwright и браузер успешно установлены!", parse_mode="HTML")
        log_storage.add_log("Playwright установлен по команде /download_browser", "SYSTEM")
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
        "🌐 <b>Управление браузером Playwright</b>\n\n"
        "🛡️ Stealth-режим активен\n"
        "Используйте кнопки для управления:",
        parse_mode="HTML",
        reply_markup=get_browser_keyboard()
    )

# ============= ОБРАБОТЧИКИ КНОПОК =============

async def download_browser_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BROWSER_INSTALLED, BROWSER_INSTALLATION_IN_PROGRESS
    
    query = update.callback_query
    await query.answer()
    
    if BROWSER_INSTALLATION_IN_PROGRESS:
        await query.message.reply_text("⏳ Установка уже выполняется...", parse_mode="HTML")
        return
    
    status_msg = await query.message.reply_text("⏳ Установка Playwright... Это может занять 2-3 минуты.", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, download_browser)
    
    if success:
        BROWSER_INSTALLED = True
        await status_msg.edit_text("✅ Playwright и браузер успешно установлены!", parse_mode="HTML")
        log_storage.add_log("Playwright установлен по кнопке", "SYSTEM")
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
    
    if not BROWSER_INSTALLED:
        await query.message.reply_text("❌ Playwright не установлен! Нажмите '📥 Скачать браузер'", parse_mode="HTML")
        return
    
    if browser_instance is not None:
        await query.message.reply_text(
            "✅ Браузер запущен и работает\n🛡️ Stealth-защита активна",
            parse_mode="HTML"
        )
    else:
        await query.message.reply_text("❌ Браузер не запущен. Инициализация...", parse_mode="HTML")
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, init_browser_sync)
        if success:
            await query.message.reply_text("✅ Браузер успешно запущен!", parse_mode="HTML")
        else:
            await query.message.reply_text("❌ Ошибка запуска браузера!", parse_mode="HTML")

async def browser_restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global browser_instance, browser_initialized
    
    if not BROWSER_INSTALLED:
        await query.message.reply_text("❌ Playwright не установлен! Нажмите '📥 Скачать браузер'", parse_mode="HTML")
        return
    
    await query.message.reply_text("🔄 Перезапуск браузера...", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    
    if browser_instance:
        try:
            def close_browser():
                if browser_instance:
                    browser_instance['browser'].close()
                    browser_instance['playwright'].stop()
            await loop.run_in_executor(None, close_browser)
        except:
            pass
        browser_instance = None
        browser_initialized = False
    
    success = await loop.run_in_executor(None, init_browser_sync)
    
    if success:
        await query.message.reply_text("✅ Браузер перезапущен!", parse_mode="HTML")
        log_storage.add_log("Браузер перезапущен", "SYSTEM")
    else:
        await query.message.reply_text("❌ Ошибка перезапуска!", parse_mode="HTML")

async def browser_screenshot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not BROWSER_INSTALLED:
        await query.message.reply_text("❌ Playwright не установлен! Нажмите '📥 Скачать браузер'", parse_mode="HTML")
        return
    
    loop = asyncio.get_event_loop()
    
    try:
        page = await loop.run_in_executor(None, create_page_sync)
        if page is None:
            await query.message.reply_text("❌ Не удалось получить страницу!", parse_mode="HTML")
            return
        
        await loop.run_in_executor(None, do_browser_action_sync, page, "goto", "https://example.com")
        screenshot = await loop.run_in_executor(None, do_browser_action_sync, page, "screenshot", None)
        
        if screenshot:
            from io import BytesIO
            photo = BytesIO(screenshot)
            photo.name = "screenshot.png"
            await query.message.reply_photo(
                photo=photo, 
                caption="📸 Скриншот example.com\n🛡️ Сделан через playwright-stealth"
            )
            log_storage.add_log("Сделан скриншот через Playwright", "BROWSER")
        else:
            await query.message.reply_text("❌ Ошибка создания скриншота!", parse_mode="HTML")
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка скриншота: {str(e)}", "ERROR")

async def open_site_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not BROWSER_INSTALLED:
        await query.message.reply_text("❌ Playwright не установлен! Нажмите '📥 Скачать браузер'", parse_mode="HTML")
        return
    
    context.user_data['waiting_for_url'] = True
    
    await query.message.reply_text(
        "🌐 <b>Введите URL сайта</b>\n\n"
        "Примеры:\n"
        "• https://x.com\n"
        "• https://github.com\n"
        "• https://example.com\n\n"
        "❗ Введите полный адрес с https://\n"
        "🛡️ Будет использован stealth-режим",
        parse_mode="HTML"
    )

async def handle_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_url'):
        return
    
    if not BROWSER_INSTALLED:
        await update.message.reply_text("❌ Playwright не установлен! Нажмите /download_browser", parse_mode="HTML")
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
    
    loop = asyncio.get_event_loop()
    
    try:
        page = await loop.run_in_executor(None, create_page_sync)
        if page is None:
            await status_msg.edit_text("❌ Не удалось получить страницу!", parse_mode="HTML")
            return
        
        success = await loop.run_in_executor(None, do_browser_action_sync, page, "goto", url)
        
        if success:
            screenshot = await loop.run_in_executor(None, do_browser_action_sync, page, "screenshot", None)
            
            if screenshot:
                from io import BytesIO
                photo = BytesIO(screenshot)
                photo.name = "screenshot.png"
                
                await status_msg.delete()
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"✅ <b>Сайт открыт через stealth:</b>\n{url}",
                    parse_mode="HTML"
                )
                log_storage.add_log(f"Открыт сайт через Playwright: {url}", "BROWSER")
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
        logging.info("🔄 Фоновый поток браузера Playwright запущен")
        if BROWSER_INSTALLED:
            init_browser_sync()
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
    app.add_handler(CommandHandler("download_browser", download_browser_command))
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(browser_status_callback, pattern="browser_status"))
    app.add_handler(CallbackQueryHandler(browser_restart_callback, pattern="browser_restart"))
    app.add_handler(CallbackQueryHandler(browser_screenshot_callback, pattern="browser_screenshot"))
    app.add_handler(CallbackQueryHandler(open_site_callback, pattern="open_site"))
    app.add_handler(CallbackQueryHandler(download_browser_callback, pattern="download_browser"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input))
    
    log_storage.add_log("Бот запущен с Playwright + stealth", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()