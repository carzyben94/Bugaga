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
    
    # Заголовок с рамкой
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║          📋  ВСЕ ЛОГИ  📋           ║")
    lines.append("╚══════════════════════════════════════╝")
    lines.append("")
    lines.append(f"🕐 <b>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</b>")
    lines.append("")
    lines.append("┌─────────────────────────────────────┐")
    
    emoji_map = {
        "INFO": "ℹ️", 
        "COMMAND": "⚡", 
        "ERROR": "❌", 
        "SYSTEM": "🔧", 
        "WARNING": "⚠️"
    }
    
    color_map = {
        "INFO": "🔵",
        "COMMAND": "🟣",
        "ERROR": "🔴",
        "SYSTEM": "🟠",
        "WARNING": "🟡"
    }
    
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        
        emoji = emoji_map.get(log_type, "📌")
        color = color_map.get(log_type, "⚪")
        
        user_info = f" 👤 @{username}" if username else ""
        
        # Каждый лог в отдельной строке с красивым оформлением
        lines.append(f"│ {color} {emoji} <b>{log_type}</b>")
        lines.append(f"│    🕐 {timestamp}")
        lines.append(f"│    💬 {message[:60]}{'...' if len(message) > 60 else ''}")
        if user_info:
            lines.append(f"│    {user_info}")
        lines.append("│")
    
    lines.append("└─────────────────────────────────────┘")
    lines.append("")
    lines.append(f"📊 <b>Всего логов:</b> {len(logs[:limit])}")
    lines.append("🔹 <i>Последние записи</i>")
    
    return "\n".join(lines)

def format_logs_for_copy(logs, limit=30):
    if not logs:
        return "Логов нет"
    
    lines = []
    lines.append("=" * 50)
    lines.append("📋 ВСЕ ЛОГИ")
    lines.append("=" * 50)
    lines.append("")
    
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        user_info = f" [@{username}]" if username else ""
        lines.append(f"[{timestamp}] {log_type}{user_info}")
        lines.append(f"  {message}")
        lines.append("-" * 40)
    
    lines.append("")
    lines.append("=" * 50)
    lines.append(f"Всего записей: {len(logs[:limit])}")
    
    return "\n".join(lines)

def get_logs_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")],
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")],
        [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stats_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Посмотреть логи", callback_data="view_logs")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_stats(stats):
    lines = []
    
    # Красивый заголовок
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║        📊  СТАТИСТИКА  📊           ║")
    lines.append("╚══════════════════════════════════════╝")
    lines.append("")
    lines.append(f"🕐 <b>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</b>")
    lines.append("")
    lines.append("┌─────────────────────────────────────┐")
    lines.append(f"│  📝 <b>ВСЕГО ЛОГОВ:</b> {stats['total']}")
    lines.append("│")
    
    emoji_map = {
        "INFO": "ℹ️", 
        "COMMAND": "⚡", 
        "ERROR": "❌", 
        "SYSTEM": "🔧", 
        "WARNING": "⚠️"
    }
    
    color_map = {
        "INFO": "🔵",
        "COMMAND": "🟣",
        "ERROR": "🔴",
        "SYSTEM": "🟠",
        "WARNING": "🟡"
    }
    
    # Прогресс-бары для каждого типа
    max_count = max(stats['by_type'].values()) if stats['by_type'] else 1
    
    for log_type, count in stats['by_type'].items():
        emoji = emoji_map.get(log_type, "📌")
        color = color_map.get(log_type, "⚪")
        percent = int((count / stats['total']) * 20) if stats['total'] > 0 else 0
        bar = "█" * percent + "░" * (20 - percent)
        lines.append(f"│  {color} {emoji} <b>{log_type}</b>")
        lines.append(f"│     {count} записей")
        lines.append(f"│     {bar} {int(percent*5)}%")
        lines.append("│")
    
    # Красивая статистика в виде графиков
    lines.append("└─────────────────────────────────────┘")
    lines.append("")
    lines.append("📈 <i>Активность бота</i>")
    
    # Статистика по типам в виде круговой диаграммы (текстовой)
    total = stats['total']
    if total > 0:
        lines.append("")
        for log_type, count in stats['by_type'].items():
            emoji = emoji_map.get(log_type, "📌")
            percent = int((count / total) * 100)
            # Создаём мини-диаграмму
            blocks = "▓" * int(percent / 5) + "░" * (20 - int(percent / 5))
            lines.append(f"  {emoji} {blocks} {percent}% ({count})")
    
    return "\n".join(lines)

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
        "🤖 <b>Добро пожаловать в Log Bot!</b>\n\n"
        "┌─────────────────────────────────────┐\n"
        "│  📋 <b>/logs</b>  – Посмотреть логи   │\n"
        "│  📊 <b>/stats</b> – Статистика        │\n"
        "│  🗑️ <b>/clear</b> – Очистить логи    │\n"
        "└─────────────────────────────────────┘\n\n"
        "🔹 <i>Нажмите на кнопки для управления</i>",
        parse_mode="HTML"
    )

# Команда /logs
@log_command
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📡 <i>Собираю логи...</i>", parse_mode="HTML")
    
    try:
        logs = log_storage.get_all_logs(limit=50)
        
        if not logs:
            await status_msg.edit_text(
                "📭 <b>Логов пока нет</b>\n\n"
                "🔹 Начните использовать бота, чтобы появились записи",
                parse_mode="HTML"
            )
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
        await status_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )
        log_storage.add_log(f"Ошибка в /logs: {str(e)}", "ERROR")

# Команда /stats
@log_command
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📡 <i>Собираю статистику...</i>", parse_mode="HTML")
    
    try:
        stats = log_storage.get_stats()
        
        if stats['total'] == 0:
            await status_msg.edit_text(
                "📊 <b>Статистика пуста</b>\n\n"
                "🔹 Нет записей для отображения",
                parse_mode="HTML"
            )
            return
        
        display_text = format_stats(stats)
        
        await status_msg.edit_text(
            display_text,
            parse_mode="HTML",
            reply_markup=get_stats_keyboard(),
            disable_web_page_preview=True
        )
        
        log_storage.add_log("Показана статистика", "INFO")
            
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

# Команда /clear
@log_command
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_storage.clear_logs()
    await update.message.reply_text(
        "🗑️ <b>Логи очищены</b>\n\n"
        "✅ Все записи удалены",
        parse_mode="HTML"
    )

# Обработчики кнопок
async def copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    copy_text = context.user_data.get('copy_logs', '')
    
    if copy_text:
        await query.message.reply_text(
            f"📋 <b>Логи для копирования</b>\n\n"
            f"<pre>{copy_text}</pre>",
            parse_mode="HTML"
        )
        log_storage.add_log("Скопированы логи", "SYSTEM")
        await query.answer("✅ Логи отправлены!")
    else:
        await query.answer("❌ Логи не найдены", show_alert=True)

async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    log_storage.clear_logs()
    
    await query.message.edit_text(
        "🗑️ <b>Логи очищены</b>\n\n"
        "✅ Все записи удалены",
        parse_mode="HTML"
    )
    await query.answer("✅ Логи очищены!")

async def show_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        stats = log_storage.get_stats()
        
        if stats['total'] == 0:
            await query.message.reply_text(
                "📊 <b>Статистика пуста</b>",
                parse_mode="HTML"
            )
            return
        
        display_text = format_stats(stats)
        await query.message.reply_text(
            display_text,
            parse_mode="HTML",
            reply_markup=get_stats_keyboard(),
            disable_web_page_preview=True
        )
        
        await query.answer("📊 Статистика готова!")
            
    except Exception as e:
        await query.answer("❌ Ошибка", show_alert=True)

async def view_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Возвращаемся к логам
    await logs_command(update, context)

async def refresh_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Обновляю...")
    
    await stats_command(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.bot_data['log_storage'] = log_storage
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    # Callback кнопок
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    app.add_handler(CallbackQueryHandler(show_stats_callback, pattern="show_stats"))
    app.add_handler(CallbackQueryHandler(view_logs_callback, pattern="view_logs"))
    app.add_handler(CallbackQueryHandler(refresh_stats_callback, pattern="refresh_stats"))
    
    log_storage.add_log("Бот запущен", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()