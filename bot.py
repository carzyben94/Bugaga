import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 1. ДОБАВЛЯЕМ ПУТЬ К BROWSER-HARNESS (ОТНОСИТЕЛЬНЫЙ)
# ============================================================

# bot.py лежит рядом с папкой browser-harness/
sys.path.insert(0, "browser-harness/src")

# ============================================================
# 2. ПЫТАЕМСЯ ИМПОРТИРОВАТЬ
# ============================================================

try:
    from browser_harness.helpers import *
    from browser_harness.admin import ensure_daemon, daemon_alive
    print("✅ Импорт helpers.py успешен!")
    print("✅ Импорт admin.py успешен!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# ============================================================
# 3. ПРОВЕРЯЕМ, ЧТО ХЕЛПЕРЫ ДОСТУПНЫ
# ============================================================

print("📋 Доступные хелперы:")
for name in dir():
    if name in ['new_tab', 'goto_url', 'wait_for_load', 'page_info', 
                'capture_screenshot', 'click_at_xy', 'type_text', 
                'press_key', 'scroll', 'js', 'cdp', 'ensure_real_tab']:
        print(f"  ✅ {name}")

# ============================================================
# 4. НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
# 5. КОНФИГУРАЦИЯ
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# Подключаемся к браузеру
os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# 6. КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с browser-harness работает!**\n\n"
        "Команды:\n"
        "/ping - проверить бота\n"
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
        new_tab("https://google.com")
        wait_for_load()
        
        import base64
        result = cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
        screenshot_b64 = result.get("data")
        
        if ',' in screenshot_b64:
            screenshot_b64 = screenshot_b64.split(',', 1)[1]
        screenshot_b64 = screenshot_b64.strip()
        missing_padding = len(screenshot_b64) % 4
        if missing_padding:
            screenshot_b64 += '=' * (4 - missing_padding)
        img_bytes = base64.b64decode(screenshot_b64)
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 Скриншот google.com"
        )
        await status_msg.edit_text("✅ Скриншот отправлен!")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 7. ЗАПУСК
# ============================================================

def main():
    print("🚀 Запуск бота...")
    
    # Проверяем, что daemon жив
    if daemon_alive():
        print("✅ Daemon уже запущен")
    else:
        print("⚠️ Daemon не запущен, пробуем запустить...")
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