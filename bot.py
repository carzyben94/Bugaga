import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        options = ChromiumOptions()
        options.binary_location = "/usr/bin/google-chrome"
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        browser = Chrome(options=options)
        async with browser:
            tab = await browser.start()
            await tab.go_to("https://example.com")
            title = await tab.title
            
        await update.message.reply_text(f"✅ {title}")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()