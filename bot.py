import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from cloakbrowser.sync import launch  # ← синхронный импорт

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Используй /check <url>")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text("⏳ Загружаю страницу через CloakBrowser...")
    
    try:
        # 🔥 Синхронный запуск (не async/await)
        browser = launch(
            headless=True,
            fingerprint=True
        )
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        title = page.title()
        content = page.content()
        browser.close()
        
        response = f"✅ {title}\n\n{content[:500]}..."
        await update.message.reply_text(response[:4096])
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.run_polling()

if __name__ == "__main__":
    main()