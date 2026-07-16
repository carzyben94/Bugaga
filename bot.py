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
        "/browser - открыть ссылку\n"
        "/close - закрыть браузер"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ссылку\nПример: /browser google.com")
            return
        
        url = context.args[0]
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        browser = context.user_data.get('browser')
        
        if not browser:
            browser = await Browser().start()
            context.user_data['browser'] = browser
            context.user_data['eval'] = Eval(browser)
        
        await browser.goto(url)
        
        screenshot_data = await browser.screenshot()
        image_bytes = base64.b64decode(screenshot_data)
        
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"✅ {url}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        if 'browser' in context.user_data:
            try:
                await context.user_data['browser'].close()
            except:
                pass
            context.user_data['browser'] = None
            context.user_data['eval'] = None

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser = context.user_data.get('browser')
    if browser:
        await browser.close()
        context.user_data['browser'] = None
        context.user_data['eval'] = None
        await update.message.reply_text("✅")
    else:
        await update.message.reply_text("❌")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()