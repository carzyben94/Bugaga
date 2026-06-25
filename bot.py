import os
import logging
import asyncio
import threading
import time
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

# ============= ПРОВЕРКА NODRIVER =============
def check_nodriver_installed():
    """Проверяет, установлен ли Nodriver"""
    try:
        import nodriver as nd
        logging.info("✅ Nodriver установлен!")
        return True
    except ImportError:
        logging.warning("⚠️ Nodriver не установлен!")
        return False

NODRIVER_INSTALLED = check_nodriver_installed()

# ============= ГЛОБАЛЬНЫЙ БРАУЗЕР =============
browser_instance = None
browser_lock = asyncio.Lock()
browser_initialized = False

async def init_browser():
    """Инициализация Nodriver"""
    global browser_instance, browser_initialized
    
    if not NODRIVER_INSTALLED:
        logging.error("❌ Nodriver не установлен!")
        return False
    
    async with browser_lock:
        if browser_instance is None and not browser_initialized:
            logging.info("🔄 Запуск Nodriver...")
            try:
                import nodriver as nd
                
                browser_instance = await nd.start(
                    headless=False,  # False для лучшей маскировки
                    window_size=(1024, 768),
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
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    ]
                )
                browser_initialized = True
                logging.info("✅ Nodriver запущен!")
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
        [InlineKeyboardButton("📸 Сделать скриншот", callback_data="browser_screenshot")]
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
    status = "✅" if NODRIVER_INSTALLED else "❌"
    await update.message.reply_text(
        f"🖥️ <b>Stealth Browser Bot (Nodriver)</b>\n\n"
        f"📋 /logs  – показать логи\n"
        f"🗑️ /clear – очистить логи\n"
        f"🌐 /browser – управление браузером\n\n"
        f"⚡ Браузер: {status}\n"
        f"🛡️ Защита: Nodriver (Stealth)\n\n"
        f"<i>Nodriver автоматически скачивает Chromium при первом запуске</i>",
        parse_mode="HTML"
    )

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
    
    if not NODRIVER_INSTALLED:
        await query.message.reply_text("❌ Nodriver не установлен!", parse_mode="HTML")
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
    
    if not NODRIVER_INSTALLED:
        await query.message.reply_text("❌ Nodriver не установлен!", parse_mode="HTML")
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
    
    if not NODRIVER_INSTALLED:
        await query.message.reply_text("❌ Nodriver не установлен!", parse_mode="HTML")
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
    
    if not NODRIVER_INSTALLED:
        await query.message.reply_text("❌ Nodriver не установлен!", parse_mode="HTML")
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
    
    if not NODRIVER_INSTALLED:
        await update.message.reply_text("❌ Nodriver не установлен!", parse_mode="HTML")
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
        if NODRIVER_INSTALLED:
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
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(browser_status_callback, pattern="browser_status"))
    app.add_handler(CallbackQueryHandler(browser_restart_callback, pattern="browser_restart"))
    app.add_handler(CallbackQueryHandler(browser_screenshot_callback, pattern="browser_screenshot"))
    app.add_handler(CallbackQueryHandler(open_site_callback, pattern="open_site"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input))
    
    log_storage.add_log("Бот запущен с Nodriver", "SYSTEM")
    logging.info("🚀 Бот с Nodriver запущен!")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()