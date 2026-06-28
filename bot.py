import os
import sys
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Устанавливаем путь для браузера
PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

def install_playwright_browser():
    """Устанавливает Chromium для Playwright при первом запуске"""
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    
    if os.path.exists(browser_path):
        print("✅ Браузер уже установлен")
        return True
    
    print("⏳ Устанавливаю браузер Chromium...")
    try:
        # Устанавливаем браузер через командную строку
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Устанавливаем системные зависимости
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps"],
            check=True,
            capture_output=True,
            text=True
        )
        
        print("✅ Браузер успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки браузера: {e}")
        return False

# Устанавливаем браузер при запуске
install_playwright_browser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером Playwright на борту.\n"
        "Отправь /status чтобы проверить браузер."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Запускаю браузер с защитой...")
    
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            await stealth_async(page)
            await page.goto('https://x.com', wait_until='networkidle')
            title = await page.title()
            await browser.close()
            
            await update.message.reply_text(f"✅ Браузер со Stealth работает!\nЗаголовок X.com: {title[:50]}...")
        
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