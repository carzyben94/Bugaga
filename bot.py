import os
import logging
import asyncio
import threading
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from camoufox.sync_api import Camoufox

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# ============= ГЛОБАЛЬНЫЙ БРАУЗЕР (Синхронный Camoufox в потоке) =============
browser_instance = None
browser_lock = threading.Lock()
browser_thread = None

def init_browser_sync():
    """Инициализация браузера в отдельном потоке (синхронная)"""
    global browser_instance
    with browser_lock:
        if browser_instance is None:
            logging.info("🔄 Запуск Camoufox в отдельном потоке...")
            try:
                browser_instance = Camoufox(
                    headless="virtual",
                    window_size=(1024, 768),
                    preferences={
                        "dom.ipc.processCount": 1,
                        "extensions.enabledScopes": 0,
                        "media.webspeech.enabled": False,
                    }
                )
                # Вход в контекст
                browser_instance.__enter__()
                logging.info("✅ Camoufox запущен!")
                return True
            except Exception as e:
                logging.error(f"❌ Ошибка запуска Camoufox: {e}")
                browser_instance = None
                return False
    return False

def get_browser_sync():
    """Получить экземпляр браузера (синхронно)"""
    global browser_instance
    if browser_instance is None:
        init_browser_sync()
    return browser_instance

def create_page_sync():
    """Создать новую страницу (синхронно)"""
    browser = get_browser_sync()
    if browser is None:
        return None
    try:
        return browser.new_page()
    except Exception as e:
        logging.error(f"❌ Ошибка создания страницы: {e}")
        return None

# Асинхронные обертки для Telegram
async def init_browser():
    """Асинхронная обертка для инициализации браузера"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, init_browser_sync)

async def get_browser():
    """Асинхронная обертка для получения браузера"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_browser_sync)

async def create_page():
    """Асинхронная обертка для создания страницы"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, create_page_sync)

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

def get_logs_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")],
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")],
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="open_site")]
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

# Команда /start
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

# Команда /logs
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

# Команда /clear
@log_command
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_storage.clear_logs()
    await update.message.reply_text("🗑️ Логи очищены ✅", parse_mode="HTML")

# Команда /browser
@log_command
async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 <b>Управление браузером</b>\n\n"
        "Используйте кнопки для управления:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Проверить статус", callback_data="browser_status")],
            [InlineKeyboardButton("🔄 Перезапустить", callback_data="browser_restart")],
            [InlineKeyboardButton("📸 Сделать скриншот", callback_data="browser_screenshot")]
        ])
    )

# Обработчики кнопок
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

async def open_site_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открыть сайт в браузере"""
    query = update.callback_query
    await query.answer()
    
    try:
        page = await create_page()
        if page is None:
            await query.message.reply_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        # Все операции с page выполняются синхронно в потоке
        loop = asyncio.get_event_loop()
        
        def do_browser_actions():
            page.goto("https://example.com")
            page.screenshot(path="screenshot.png")
            page.close()
            return True
        
        await loop.run_in_executor(None, do_browser_actions)
        
        log_storage.add_log("Открыт сайт example.com", "BROWSER")
        await query.message.reply_text("✅ Сайт открыт! Скриншот сохранен.", parse_mode="HTML")
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка открытия сайта: {str(e)}", "ERROR")

async def browser_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса браузера"""
    query = update.callback_query
    await query.answer()
    
    global browser_instance
    if browser_instance is not None:
        await query.message.reply_text("✅ Браузер запущен и работает", parse_mode="HTML")
    else:
        await query.message.reply_text("❌ Браузер не запущен. Инициализация...", parse_mode="HTML")
        success = await init_browser()
        if success:
            await query.message.reply_text("✅ Браузер успешно запущен!", parse_mode="HTML")
        else:
            await query.message.reply_text("❌ Ошибка запуска браузера!", parse_mode="HTML")

async def browser_restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск браузера"""
    query = update.callback_query
    await query.answer()
    
    global browser_instance
    await query.message.reply_text("🔄 Перезапуск браузера...", parse_mode="HTML")
    
    if browser_instance:
        try:
            # Закрываем в отдельном потоке
            def close_browser():
                browser_instance.__exit__(None, None, None)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, close_browser)
        except:
            pass
        browser_instance = None
    
    success = await init_browser()
    
    if success:
        await query.message.reply_text("✅ Браузер перезапущен!", parse_mode="HTML")
        log_storage.add_log("Браузер перезапущен", "SYSTEM")
    else:
        await query.message.reply_text("❌ Ошибка перезапуска!", parse_mode="HTML")

async def browser_screenshot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот"""
    query = update.callback_query
    await query.answer()
    
    try:
        page = await create_page()
        if page is None:
            await query.message.reply_text("❌ Не удалось создать страницу!", parse_mode="HTML")
            return
        
        loop = asyncio.get_event_loop()
        
        def do_screenshot():
            page.goto("https://example.com")
            screenshot = page.screenshot(full_page=True)
            page.close()
            return screenshot
        
        screenshot = await loop.run_in_executor(None, do_screenshot)
        
        # Отправляем скриншот в Telegram
        from io import BytesIO
        photo = BytesIO(screenshot)
        photo.name = "screenshot.png"
        
        await query.message.reply_photo(
            photo=photo,
            caption="📸 Скриншот страницы example.com"
        )
        
        log_storage.add_log("Сделан скриншот", "BROWSER")
        
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        log_storage.add_log(f"Ошибка скриншота: {str(e)}", "ERROR")

async def start_browser_background():
    """Запуск браузера в фоне"""
    logging.info("🔄 Запуск браузера в фоне...")
    await init_browser()
    logging.info("✅ Фоновый запуск браузера завершен")

def main():
    # Создаем event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Запускаем браузер в фоне
    loop.run_until_complete(start_browser_background())
    
    # Сброс webhook перед запуском
    async def reset_webhook():
        app = Application.builder().token(TOKEN).build()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.initialize()
        await app.shutdown()
    
    loop.run_until_complete(reset_webhook())
    
    app = Application.builder().token(TOKEN).build()
    app.bot_data['log_storage'] = log_storage
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("browser", browser_command))
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(open_site_callback, pattern="open_site"))
    app.add_handler(CallbackQueryHandler(browser_status_callback, pattern="browser_status"))
    app.add_handler(CallbackQueryHandler(browser_restart_callback, pattern="browser_restart"))
    app.add_handler(CallbackQueryHandler(browser_screenshot_callback, pattern="browser_screenshot"))
    
    log_storage.add_log("Бот запущен с Camoufox", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()