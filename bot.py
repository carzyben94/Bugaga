import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from cloakbrowser import launch  # ✅ синхронный, без await

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Используй /check <url>")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text("⏳ Загружаю...")
    
    try:
        # ✅ launch — синхронный, НЕ await
        browser = launch(headless=True, fingerprint=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        title = page.title()
        content = page.content()
        browser.close()
        
        await update.message.reply_text(f"✅ {title}\n\n{content[:500]}")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.run_polling()

if __name__ == "__main__":
    main()