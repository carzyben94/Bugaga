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
    from browser_harness.admin import ensure_daemon, daemon_alive, restart_daemon
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
        "/screenshot - скриншот google.com\n"
        "/reset - восстановить сессию\n"
        "/restart - перезапустить браузер"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Сброс сессии перед действием
        ensure_real_tab()
        
        new_tab("https://httpbin.org/html")
        wait_for_load()
        info = page_info()
        await update.message.reply_text(
            f"📄 **Страница:**\n"
            f"• Заголовок: {info.get('title', 'нет')}\n"
            f"• URL: {info.get('url', 'нет')}"
        )
    except Exception as e:
        logger.error(f"Ошибка /info: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        # 1. СБРАСЫВАЕМ СЕССИЮ ПЕРЕД ВСЕМ
        logger.info("Сброс сессии...")
        ensure_real_tab()
        
        # 2. Открываем страницу
        logger.info("Открываем google.com...")
        new_tab("https://google.com")
        wait_for_load()
        time.sleep(2)
        
        # 3. Снова проверяем сессию
        logger.info("Проверка сессии...")
        ensure_real_tab()
        
        # 4. Устанавливаем разрешение 1280x720
        logger.info("Установка разрешения...")
        cdp("Emulation.setDeviceMetricsOverride", {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "mobile": False
        })
        time.sleep(1)
        
        # 5. Делаем скриншот
        logger.info("Делаем скриншот...")
        result = cdp("Page.captureScreenshot", {
            "format": "png",
            "quality": 80,
            "captureBeyondViewport": False
        })
        screenshot_b64 = result.get("data")
        
        if not screenshot_b64:
            raise ValueError("Скриншот пустой")
        
        # Очищаем base64
        if ',' in screenshot_b64:
            screenshot_b64 = screenshot_b64.split(',', 1)[1]
        screenshot_b64 = screenshot_b64.strip()
        
        missing_padding = len(screenshot_b64) % 4
        if missing_padding:
            screenshot_b64 += '=' * (4 - missing_padding)
        
        img_bytes = base64.b64decode(screenshot_b64)
        
        if len(img_bytes) < 1000:
            raise ValueError("Скриншот слишком маленький")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 Скриншот google.com (1280x720)"
        )
        await status_msg.edit_text("✅ Скриншот отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        # Пытаемся восстановить сессию
        try:
            ensure_real_tab()
            logger.info("Сессия восстановлена после ошибки")
        except:
            pass
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс сессии браузера"""
    try:
        ensure_real_tab()
        await update.message.reply_text("✅ Сессия восстановлена!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка сброса: {str(e)[:200]}")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск браузера"""
    status_msg = await update.message.reply_text("🔄 Перезапускаю браузер...")
    try:
        restart_daemon()
        time.sleep(2)
        ensure_daemon()
        await status_msg.edit_text("✅ Браузер перезапущен!")
    except Exception as e:
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
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("restart", restart))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()