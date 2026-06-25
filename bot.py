import os
import logging
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# ПРОВЕРКА ФАЙЛОВ
logging.info(f"📁 Текущая директория: {os.getcwd()}")
logging.info(f"📁 Файлы: {os.listdir('.')}")

# Проверяем наличие logger.py
if os.path.exists("logger.py"):
    logging.info("✅ logger.py найден!")
else:
    logging.error("❌ logger.py НЕ НАЙДЕН!")
    logging.error("Создаю файл logger.py...")
    
    # Создаём logger.py если его нет
    with open("logger.py", "w") as f:
        f.write("""
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
    
    def get_stats(self):
        types_count = {}
        for log in self.logs:
            log_type = log["type"]
            types_count[log_type] = types_count.get(log_type, 0) + 1
        return {"total": len(self.logs), "by_type": types_count}

def format_logs_for_display(logs, limit=30):
    if not logs:
        return "📭 <b>Логов пока нет</b>"
    
    lines = []
    lines.append("📋 <b>ВСЕ ЛОГИ</b>")
    lines.append(f"🕐 <b>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</b>")
    lines.append("═" * 30)
    lines.append("")
    
    emoji_map = {"INFO": "ℹ️", "COMMAND": "⚡", "ERROR": "❌", "SYSTEM": "🔧", "WARNING": "⚠️"}
    
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        emoji = emoji_map.get(log_type, "📌")
        user_info = f" @{username}" if username else ""
        lines.append(f"<code>{timestamp}</code> {emoji} [{log_type}]{user_info}")
        lines.append(f"  {message}")
        lines.append("")
    
    return "\n".join(lines)

def format_logs_for_copy(logs, limit=30):
    if not logs:
        return "Логов нет"
    
    lines = []
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        user_info = f" @{username}" if username else ""
        lines.append(f"[{timestamp}] [{log_type}]{user_info}")
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
""")
    logging.info("✅ logger.py создан!")

# Теперь импортируем
try:
    from logger import (
        LogStorage,
        format_logs_for_display,
        format_logs_for_copy,
        get_logs_keyboard,
        log_command
    )
    logging.info("✅ Импорт logger.py успешен!")
except ImportError as e:
    logging.error(f"❌ Ошибка импорта: {e}")
    # Импортируем из созданного файла
    from logger import (
        LogStorage,
        format_logs_for_display,
        format_logs_for_copy,
        get_logs_keyboard,
        log_command
    )

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# Создаём хранилище логов
log_storage = LogStorage()

# Команда /start
@log_command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот работает!\n\n"
        "Команды:\n"
        "/start - приветствие\n"
        "/logs - показать логи\n"
        "/clear - очистить логи\n"
        "/stats - статистика бота"
    )

# Команда /logs
@log_command
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📡 <i>Собираю логи...</i>", parse_mode="HTML")
    
    try:
        logs = log_storage.get_all_logs(limit=50)
        
        if not logs:
            await status_msg.edit_text("📭 <b>Логов пока нет</b>", parse_mode="HTML")
            return
        
        display_text = format_logs_for_display(logs)
        copy_text = format_logs_for_copy(logs)
        context.user_data['copy_logs'] = copy_text
        
        await status_msg.edit_text(
            display_text,
            parse_mode="HTML",
            reply_markup=get_logs_keyboard(),
            disable_web_page_preview=True
        )
        
        log_storage.add_log("Показаны логи", "INFO")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Ошибка:</b>\n<code>{str(e)}</code>", parse_mode="HTML")
        log_storage.add_log(f"Ошибка в /logs: {str(e)}", "ERROR")

# Команда /clear
@log_command
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_storage.clear_logs()
    await update.message.reply_text("🗑️ <b>Логи очищены</b>", parse_mode="HTML")

# Команда /stats
@log_command
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = log_storage.get_stats()
    
    lines = [
        "📊 <b>СТАТИСТИКА БОТА</b>",
        "═" * 30,
        f"📝 Всего логов: <b>{stats['total']}</b>",
        ""
    ]
    
    emoji_map = {"INFO": "ℹ️", "COMMAND": "⚡", "ERROR": "❌", "SYSTEM": "🔧", "WARNING": "⚠️"}
    
    for log_type, count in stats['by_type'].items():
        emoji = emoji_map.get(log_type, "📌")
        lines.append(f"{emoji} {log_type}: <b>{count}</b>")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# Обработчик кнопки копирования
async def copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    copy_text = context.user_data.get('copy_logs', '')
    
    if copy_text:
        await query.message.reply_text(
            f"📋 <b>Логи (скопируйте текст ниже)</b>\n\n"
            f"<pre>{copy_text}</pre>",
            parse_mode="HTML"
        )
        log_storage.add_log("Скопированы логи", "SYSTEM")
        await query.answer("✅ Логи отправлены!")
    else:
        await query.answer("❌ Логи не найдены", show_alert=True)

# Обработчик кнопки очистки
async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    log_storage.clear_logs()
    await query.message.edit_text("🗑️ <b>Логи очищены</b>", parse_mode="HTML")
    await query.answer("✅ Логи очищены!")

def main():
    # Создаём приложение
    from telegram.ext import Application
    app = Application.builder().token(TOKEN).build()
    
    app.bot_data['log_storage'] = log_storage
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    
    log_storage.add_log("Бот запущен", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()