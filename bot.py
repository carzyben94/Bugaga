import os 
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ====== ПРОВЕРКА МОДУЛЯ test.py ======
try:
    from test import test_function, TestClass
    logger.info("✅ test.py — НАЙДЕН!")
    logger.info(f"   📌 test_function(): {test_function()}")
    obj = TestClass()
    logger.info(f"   📌 TestClass.name: {obj.name}")
    MODULE_LOADED = True
except ModuleNotFoundError as e:
    logger.error(f"❌ test.py — НЕ НАЙДЕН! Ошибка: {e}")
    MODULE_LOADED = False
except Exception as e:
    logger.error(f"❌ test.py — ОШИБКА: {e}")
    MODULE_LOADED = False

# ====== КОМАНДЫ ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = "👋 Привет! Я бот на Railway.\n\n"
    if MODULE_LOADED:
        msg += "✅ Модуль test.py — ЗАГРУЖЕН!"
    else:
        msg += "❌ Модуль test.py — НЕ НАЙДЕН!"
    await update.message.reply_text(msg)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет наличие модуля test.py"""
    if MODULE_LOADED:
        await update.message.reply_text("✅ Модуль test.py найден и загружен!")
    else:
        await update.message.reply_text("❌ Модуль test.py не найден!")

# ====== ЗАПУСК ======
def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    
    logger.info("🚀 Бот запущен!")
    if MODULE_LOADED:
        logger.info("✅ test.py — ПОДКЛЮЧЕН")
    else:
        logger.warning("⚠️ test.py — ОТСУТСТВУЕТ")
    
    app.run_polling()

if __name__ == "__main__":
    main()