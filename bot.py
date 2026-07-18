import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Явно импортируем функции для управления браузером
from browser_harness.helpers import goto_url, js, capture_screenshot
from browser_harness.daemon import CDPClient

# Токен из переменных окружения Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# 🔥 Инициализируем подключение к Chromium один раз при старте
cdp = CDPClient("http://localhost:9222")  # или WS-адрес из Chrome

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        # Убедимся, что подключение активно
        if not cdp.is_connected():
            cdp.connect()
        
        # Переходим на страницу
        goto_url("https://example.com")
        title = js("document.title")
        await update.message.reply_text(f"✅ Браузер готов! Загружено: {title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /screenshot"""
    try:
        if not cdp.is_connected():
            cdp.connect()
        
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
    
    # Подключаемся к Chromium при старте
    try:
        cdp.connect()
        print("✅ Подключение к Chromium установлено")
    except Exception as e:
        print(f"⚠️ Предупреждение: {e}")
        print("   Бот запустится, но команды с браузером не работают")
    
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    # Запускаем поллинг
    print("🤖 Бот запущен. Жду команды...")
    app.run_polling(allowed_updates=[])

if __name__ == "__main__":
    main()