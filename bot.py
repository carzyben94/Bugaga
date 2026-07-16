import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт только browser
import browser

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Доступные команды:\n"
        "/browser - запустить браузер"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = browser.some_function()  # замените на реальную функцию
        await update.message.reply_text(f"🌐 Результат:\n{result}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_cmd))
    
    print("✅ Бот запущен!")
    print("📋 Доступные команды: /start, /browser")
    app.run_polling()

if __name__ == "__main__":
    main()