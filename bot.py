import os
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
    try:
        await update.message.reply_text("🌐 Запускаю браузер...")
        
        browser = await Browser().start()
        context.user_data['browser'] = browser
        context.user_data['eval'] = Eval(browser)
        
        await browser.goto("https://example.com")
        
        screenshot_data = await browser.screenshot()
        await update.message.reply_photo(
            photo=screenshot_data,
            caption="✅ Скриншот страницы"
        )
        
        await browser.close()
        context.user_data['browser'] = None
        context.user_data['eval'] = None
        
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