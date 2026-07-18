import os
import sys
import time
import logging
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 1. ПУТЬ К BROWSER-HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

# ============================================================
# 2. ИМПОРТ (ВСЁ ЧТО НУЖНО)
# ============================================================

from browser_harness.helpers import *
from browser_harness.admin import ensure_daemon

# ============================================================
# 3. НАСТРОЙКА
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Подключаемся к браузеру
os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# 4. КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🤖 **Browser Harness Bot**\n\n"
        "/ping — проверка\n"
        "/screenshot — скриншот google.com"
    )

async def ping(update, context):
    await update.message.reply_text("🏓 Pong!")

async def screenshot(update, context):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        # 1. Открываем вкладку
        new_tab("https://google.com")
        wait_for_load()
        time.sleep(2)
        
        # 2. Переключаем сессию на активную вкладку
        ensure_real_tab()
        
        # 3. Скриншот (встроенный хелпер)
        img_b64 = capture_screenshot(max_dim=800)
        
        if not img_b64:
            raise ValueError("Скриншот пустой")
        
        # Очищаем base64
        if ',' in img_b64:
            img_b64 = img_b64.split(',', 1)[1]
        img_b64 = img_b64.strip()
        
        missing_padding = len(img_b64) % 4
        if missing_padding:
            img_b64 += '=' * (4 - missing_padding)
        
        img_bytes = base64.b64decode(img_b64)
        
        if len(img_bytes) < 1000:
            raise ValueError("Скриншот слишком маленький")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 Скриншот google.com"
        )
        await msg.edit_text("✅ Скриншот отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 5. ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()