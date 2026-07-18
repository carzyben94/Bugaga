import os
import sys
import time
import logging
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import *
from browser_harness.admin import ensure_daemon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

async def start(update, context):
    await update.message.reply_text(
        "🤖 **Browser Harness Bot**\n\n"
        "Бот работает!\n"
        "Используй команды:\n"
        "/ping — проверка\n"
        "/screenshot — скриншот google.com"
    )

async def ping(update, context):
    await update.message.reply_text("🏓 Pong!")

async def screenshot(update, context):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        new_tab("https://google.com")
        wait_for_load()
        time.sleep(2)
        
        ensure_real_tab()
        
        result = cdp(
            "Page.captureScreenshot",
            format="jpeg",
            quality=85,
            captureBeyondViewport=False
        )
        screenshot_b64 = result.get("data")
        
        if not screenshot_b64:
            raise ValueError("Скриншот пустой")
        
        if ',' in screenshot_b64:
            screenshot_b64 = screenshot_b64.split(',', 1)[1]
        screenshot_b64 = screenshot_b64.strip()
        
        missing_padding = len(screenshot_b64) % 4
        if missing_padding:
            screenshot_b64 += '=' * (4 - missing_padding)
        
        img_bytes = base64.b64decode(screenshot_b64)
        
        if len(img_bytes) < 1000:
            raise ValueError(f"Скриншот слишком маленький: {len(img_bytes)} байт")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 Скриншот google.com (JPEG, 85%)"
        )
        await msg.edit_text("✅ Скриншот отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()