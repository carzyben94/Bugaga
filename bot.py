import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from browser_harness.helpers import goto_url, js, capture_screenshot

# Токен из переменных окружения Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        # Проверяем браузер
        goto_url("https://example.com")
        title = js("document.title")
        await update.message.reply_text(f"✅ Браузер готов! Загружено: {title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screenshot"""
    try:
        capture_screenshot("screenshot.png")
        with open("screenshot.png", "rb") as f:
            await update.message.reply_photo(f)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    """Запуск бота"""
    if not TELEGRAM_TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    # Запускаем поллинг (опрос Telegram API)
    print("🤖 Бот запущен. Жду команды...")
    app.run_polling(allowed_updates=[])

if __name__ == "__main__":
    main()