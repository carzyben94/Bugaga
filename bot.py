import os
import logging
import asyncio
import threading
import time
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

# ============= ГЛОБАЛЬНЫЙ БРАУЗЕР =============
browser_instance = None
browser_lock = threading.Lock()
browser_initialized = False

def init_browser_sync():
    """Инициализация браузера по документации Camoufox 0.4.11"""
    global browser_instance, browser_initialized
    with browser_lock:
        if browser_instance is None and not browser_initialized:
            logging.info("🔄 Запуск Camoufox...")
            try:
                from camoufox.sync_api import Camoufox
                
                browser_instance = Camoufox(
                    headless="virtual",
                    window=(1024, 768),
                    humanize=True,
                    firefox_user_prefs={
                        "dom.ipc.processCount": 1,
                        "extensions.enabledScopes": 0,
                        "media.webspeech.enabled": False,
                    },
                    config={
                        "navigator.language": "ru-RU",
                        "navigator.languages": ["ru-RU", "ru", "en-US", "en"],
                        "headers.Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
                    }
                )
                browser_instance.__enter__()
                browser_initialized = True
                logging.info("✅ Camoufox запущен!")
                return True
            except Exception as e:
                logging.error(f"❌ Ошибка запуска Camoufox: {e}")
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
    """Создать новую страницу"""
    browser = get_browser_sync()
    if browser is None:
        return None
    try:
        context = browser.new_context(
            viewport={"width": 1024, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            locale="ru-RU",
            timezone_id="Europe/Moscow"
        )
        page = context.new_page()
        return page
    except Exception as e:
        logging.error(f"❌ Ошибка создания страницы: {e}")
        return None

def do_browser_action_sync(page, action, url=None):
    """Выполнить действие с браузером"""
    try:
        if action == "goto" and url:
            page.goto(url)
            return True
        elif action == "screenshot":
            return page.screenshot(full_page=True)
        elif action == "close":
            page.close()
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
    """Клавиатура для логов — БЕЗ кнопки 'Открыть сайт'"""
    keyboard = [
        [InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")],
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_browser_keyboard():
    """Клавиатура для управления браузером"""
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
    await update.message.reply_text(
        "🖥️ <b>Stealth Browser Bot</b>\n\n"
        "📋 /logs  – показать логи\n"
        "🗑️ /clear – очистить логи\n"
        "🌐 /browser – управление браузером\n\n"
        "⚡ Браузер запускается автоматически при первой команде",
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
        "🌐 <b>Управление браузером</b>\n\n"
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
    if browser_instance is not None:
        await query.message.reply_text("✅ Браузер запущен и работает", parse_mode="HTML")
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
    await query.message.reply_text("🔄 Перезапуск браузера...", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    
    if browser_instance:
        try:
            def close_browser():
                browser_instance.__exit__(None, None, None)
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
    
    loop = asyncio.get_event_loop()
    
    try:
        page = await loop.run_in_executor(None, create_page_sync)
        if page is None:
            await query.message.reply_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        await loop.run_in_executor(None, do_browser_action_sync, page, "goto", "https://example.com")
        screenshot = await loop.run_in_executor(None, do_browser_action_sync, page, "screenshot", None)
        await loop.run_in_executor(None, do_browser_action_sync, page, "close", None)
        
        if screenshot:
            from io import BytesIO
            photo = BytesIO(screenshot)
            photo.name = "screenshot.png"
            await query.message.reply_photo(photo=photo, caption="📸 Скриншот example.com")
            log_storage.add_log("Сделан скриншот", "BROWSER")
        else:
            await query.message.reply_text("❌ Ошибка создания скриншота!", parse_mode="HTML")
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка скриншота: {str(e)}", "ERROR")

# ============= НОВЫЙ ОБРАБОТЧИК ДЛЯ ОТКРЫТИЯ САЙТА =============

async def open_site_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает URL у пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Сохраняем состояние, что пользователь в режиме ввода URL
    context.user_data['waiting_for_url'] = True
    
    await query.message.reply_text(
        "🌐 <b>Введите URL сайта</b>\n\n"
        "Примеры:\n"
        "• https://x.com\n"
        "• https://github.com\n"
        "• https://example.com\n\n"
        "❗ Введите полный адрес с https://",
        parse_mode="HTML"
    )

async def handle_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает введенный URL"""
    # Проверяем, ждем ли мы URL
    if not context.user_data.get('waiting_for_url'):
        return
    
    url = update.message.text.strip()
    
    # Проверяем, что URL начинается с http:// или https://
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ <b>Неверный формат URL</b>\n\n"
            "URL должен начинаться с http:// или https://\n\n"
            "Пример: https://x.com",
            parse_mode="HTML"
        )
        return
    
    # Сбрасываем состояние
    context.user_data['waiting_for_url'] = False
    
    # Отправляем сообщение о начале загрузки
    status_msg = await update.message.reply_text(f"⏳ Открываю {url}...", parse_mode="HTML")
    
    loop = asyncio.get_event_loop()
    
    try:
        # Создаем страницу
        page = await loop.run_in_executor(None, create_page_sync)
        if page is None:
            await status_msg.edit_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        # Открываем URL
        success = await loop.run_in_executor(None, do_browser_action_sync, page, "goto", url)
        
        if success:
            # Делаем скриншот
            screenshot = await loop.run_in_executor(None, do_browser_action_sync, page, "screenshot", None)
            await loop.run_in_executor(None, do_browser_action_sync, page, "close", None)
            
            if screenshot:
                from io import BytesIO
                photo = BytesIO(screenshot)
                photo.name = "screenshot.png"
                
                await status_msg.delete()
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"✅ <b>Сайт открыт:</b>\n{url}",
                    parse_mode="HTML"
                )
                log_storage.add_log(f"Открыт сайт: {url}", "BROWSER")
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
        logging.info("🔄 Фоновый поток браузера запущен")
        init_browser_sync()
        while True:
            time.sleep(60)
    
    thread = threading.Thread(target=run_browser, daemon=True)
    thread.start()
    logging.info("✅ Фоновый поток запущен")

def main():
    start_browser_thread()
    
    # Сброс webhook перед запуском
    async def reset_webhook():
        app = Application.builder().token(TOKEN).build()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.initialize()
        await app.shutdown()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(reset_webhook())
    
    app = Application.builder().token(TOKEN).build()
    app.bot_data['log_storage'] = log_storage
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("browser", browser_command))
    
    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(browser_status_callback, pattern="browser_status"))
    app.add_handler(CallbackQueryHandler(browser_restart_callback, pattern="browser_restart"))
    app.add_handler(CallbackQueryHandler(browser_screenshot_callback, pattern="browser_screenshot"))
    app.add_handler(CallbackQueryHandler(open_site_callback, pattern="open_site"))
    
    # Обработчик текстовых сообщений (для ввода URL)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input))
    
    log_storage.add_log("Бот запущен с Camoufox", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()