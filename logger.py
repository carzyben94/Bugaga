import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class LogStorage:
    """Хранилище логов бота"""
    
    def __init__(self, max_logs=100):
        self.logs = []
        self.max_logs = max_logs
    
    def add_log(self, message, log_type="INFO", user_id=None, username=None):
        """Добавляет лог в хранилище"""
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
        """Возвращает последние логи"""
        return self.logs[-limit:] if self.logs else []
    
    def clear_logs(self):
        """Очищает логи"""
        self.logs.clear()
        self.add_log("Логи очищены", "SYSTEM")
    
    def get_stats(self):
        """Возвращает статистику по логам"""
        types_count = {}
        for log in self.logs:
            log_type = log["type"]
            types_count[log_type] = types_count.get(log_type, 0) + 1
        return {
            "total": len(self.logs),
            "by_type": types_count
        }


def format_logs_for_display(logs, limit=30):
    """Форматирует логи для отображения в Telegram"""
    if not logs:
        return "📭 <b>Логов пока нет</b>"
    
    lines = []
    lines.append("📋 <b>ВСЕ ЛОГИ</b>")
    lines.append(f"🕐 <b>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</b>")
    lines.append("═" * 30)
    lines.append("")
    
    for log in logs[:limit]:
        timestamp = log["timestamp"]
        log_type = log["type"]
        message = log["message"]
        username = log.get("username", "")
        
        emoji = {
            "INFO": "ℹ️",
            "COMMAND": "⚡",
            "ERROR": "❌",
            "SYSTEM": "🔧",
            "WARNING": "⚠️"
        }.get(log_type, "📌")
        
        user_info = f" @{username}" if username else ""
        lines.append(f"<code>{timestamp}</code> {emoji} [{log_type}]{user_info}")
        lines.append(f"  {message}")
        lines.append("")
    
    return "\n".join(lines)


def format_logs_for_copy(logs, limit=30):
    """Форматирует логи для копирования (без HTML)"""
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
    """Создаёт клавиатуру для управления логами"""
    keyboard = [
        [InlineKeyboardButton("📋 Копировать логи", callback_data="copy_logs")],
        [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")]
    ]
    return InlineKeyboardMarkup(keyboard)


def log_command(func):
    """Декоратор для автоматического логирования команд"""
    async def wrapper(update, context):
        user = update.effective_user
        user_id = user.id if user else None
        username = user.username if user else None
        command = update.message.text if update.message else "unknown"
        
        # Получаем логгер из контекста
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