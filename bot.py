import os
import sys
import time
import logging
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 1. ДОБАВЛЯЕМ ПУТЬ К BROWSER-HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

# ============================================================
# 2. ИМПОРТ ХЕЛПЕРОВ
# ============================================================

try:
    from browser_harness.helpers import *
    from browser_harness.admin import ensure_daemon, daemon_alive
    print("✅ Импорт успешен!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# ============================================================
# 3. НАСТРОЙКА
# ============================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# Подключаемся к браузеру
os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# 4. КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с browser-harness**\n\n"
        "Команды:\n"
        "/ping - проверка\n"
        "/info - информация о странице\n"
        "/screenshot - скриншот google.com"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_tab("https://httpbin.org/html")
        wait_for_load()
        info = page_info()
        await update.message.reply_text(
            f"📄 **Страница:**\n"
            f"• Заголовок: {info.get('title', 'нет')}\n"
            f"• URL: {info.get('url', 'нет')}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        # 1. Открываем вкладку
        new_tab("https://google.com")
        
        # 2. Ждём загрузку
        wait_for_load()
        
        # 3. Дополнительная задержка
        time.sleep(2)
        
        # 4. Убеждаемся, что мы в правильной вкладке
        ensure_real_tab()
        
        # 5. Используем ВСТРОЕННЫЙ ХЕЛПЕР capture_screenshot()
        #    вместо cdp("Page.captureScreenshot", ...)
        img_b64 = capture_screenshot(max_dim=800)
        
        if not img_b64:
            raise ValueError("Скриншот пустой")
        
        # Очищаем base64-строку
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
        await status_msg.edit_text("✅ Скриншот отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        # Восстанавливаем сессию
        try:
            ensure_real_tab()
        except:
            pass
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 5. ЗАПУСК
# ============================================================

def main():
    print("🚀 Запуск бота...")
    
    if daemon_alive():
        print("✅ Daemon уже запущен")
    else:
        print("⚠️ Daemon не запущен, запускаем...")
        ensure_daemon()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()