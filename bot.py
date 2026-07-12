import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Добавляем текущую папку в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ---------- Команда для проверки файлов ----------

async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать файлы в директории и проверить accessibility.py"""
    try:
        files = os.listdir('.')
        msg = "📁 **Файлы на сервере:**\n"
        for f in sorted(files):
            msg += f"  • {f}\n"
        
        # Проверяем, есть ли accessibility.py
        if 'accessibility.py' in files:
            msg += "\n✅ **accessibility.py НАЙДЕН!**"
        else:
            msg += "\n❌ **accessibility.py НЕ НАЙДЕН!**"
        
        # Проверяем, есть ли bot.py
        if 'bot.py' in files:
            msg += "\n✅ **bot.py НАЙДЕН!**"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- Тест импорта ----------

async def test_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить, импортируется ли модуль"""
    try:
        from accessibility import UniversalModel
        await update.message.reply_text("✅ **Модуль accessibility.py успешно импортирован!**")
    except ImportError as e:
        await update.message.reply_text(f"❌ **Ошибка импорта:**\n{str(e)}")

# ---------- Старт ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Бот работает!**\n\n"
        "/files - показать файлы на сервере\n"
        "/test_import - проверить импорт accessibility.py"
    )

# ---------- Main ----------

def main():
    print("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", files_command))
    app.add_handler(CommandHandler("test_import", test_import))
    
    print("🚀 Бот запущен! Команды: /files, /test_import")
    app.run_polling()

if __name__ == "__main__":
    main()