import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Проверяем, что браузер доступен
async def check_browser():
    import websockets
    try:
        async with websockets.connect("ws://localhost:9222/devtools/browser") as ws:
            return True
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = await check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    await update.message.reply_text(
        f"🤖 Бот запущен!\n"
        f"Браузер: {status}\n"
        f"Готов к выполнению задач!"
    )

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("🚀 Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()