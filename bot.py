import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Импортируем модуль логирования
from modules.logger import (
    LogStorage, 
    format_logs_for_display, 
    format_logs_for_copy,
    get_logs_keyboard,
    log_command
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# Глобальное хранилище логов
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
        
        # Форматируем для отображения
        display_text = format_logs_for_display(logs)
        
        # Форматируем для копирования
        copy_text = format_logs_for_copy(logs)
        context.user_data['copy_logs'] = copy_text
        
        # Отправляем с кнопками
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
    
    emoji_map = {
        "INFO": "ℹ️",
        "COMMAND": "⚡",
        "ERROR": "❌",
        "SYSTEM": "🔧",
        "WARNING": "⚠️"
    }
    
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
    app = Application.builder().token(TOKEN).build()
    
    # Сохраняем логгер в контекст бота
    app.bot_data['log_storage'] = log_storage
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="copy_logs"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern="clear_logs"))
    
    # Логируем запуск
    log_storage.add_log("Бот запущен", "SYSTEM")
    logging.info("🚀 Бот запускается в режиме polling...")
    
    # Запуск
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()