import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Токен из переменных окружения Railway
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером Playwright на борту.\n"
        "Отправь /status чтобы проверить браузер."
    )

# Команда /status - проверка браузера с Stealth
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Запускаю браузер с защитой...")
    
    try:
        from playwright_extra import chromium
        from playwright_extra.stealth import StealthPlugin
        
        # Активируем Stealth
        chromium.use(StealthPlugin())
        
        browser = await chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        await page.goto('https://x.com', wait_until='networkidle')
        title = await page.title()
        await browser.close()
        
        await update.message.reply_text(f"✅ Браузер с Stealth работает!\nЗаголовок X.com: {title[:50]}...")
        
    except ImportError as e:
        await update.message.reply_text(f"❌ Ошибка импорта: {str(e)[:100]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()