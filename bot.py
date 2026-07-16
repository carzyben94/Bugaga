import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт Browser класса из browser.py
from browser import Browser

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Доступные команды:\n"
        "/browser - запустить браузер и сделать скриншот"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🌐 Запускаю браузер...")
        
        # Создаем и запускаем браузер
        browser = await Browser().start()
        
        # Переходим на сайт (можно поменять URL)
        await browser.goto("https://example.com")
        
        # Делаем скриншот
        screenshot_data = await browser.screenshot()
        
        # Отправляем скриншот
        await update.message.reply_photo(
            photo=screenshot_data,
            caption="✅ Скриншот страницы"
        )
        
        # Закрываем браузер
        await browser.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_cmd))
    
    print("✅ Бот запущен!")
    print("📋 Доступные команды: /start, /browser")
    app.run_polling()

if __name__ == "__main__":
    main()