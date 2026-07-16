import os
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт модулей
from browser import Browser
from eval import Eval

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Доступные команды:\n"
        "/browser - запустить браузер и сделать скриншот"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser = None
    try:
        await update.message.reply_text("🌐 Запускаю браузер...")
        
        browser = await Browser().start()
        
        await browser.goto("https://example.com")
        
        # Получаем скриншот в base64
        screenshot_data = await browser.screenshot()
        
        # Декодируем base64 в байты
        image_bytes = base64.b64decode(screenshot_data)
        
        # Отправляем как фото
        await update.message.reply_photo(
            photo=image_bytes,
            caption="✅ Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    finally:
        if browser:
            await browser.close()

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