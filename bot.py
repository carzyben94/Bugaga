import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

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
    """Форматирует логи для отдельного окна с прокруткой"""
    if not logs:
        return "📭 Логов пока нет"
    
    lines = []
    
    emoji_map = {
        "INFO": "ℹ️", 
        "COMMAND": "⚡", 
        "ERROR": "❌", 
        "SYSTEM": "🔧", 
        "WARNING": "⚠️"
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
    """Чистый текст для копирования"""
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
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")]
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

# Создаём хранилище логов
log_storage = LogStorage()

# Команда /start
@log_command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>Log Bot</b>\n\n"
        "📋 /logs  – показать логи\n"
        "🗑️ /clear – очистить логи",
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

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.bot_data['log_storage'] = log_storage
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    
    log_storage.add_log("Бот запущен", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 