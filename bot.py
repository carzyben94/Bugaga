import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ===== Логирование =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== Глобальный браузер (один на всех) =====
browser = None

# ===== Команды =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот.\n\n"
        "Команды:\n"
        "/screen <url> — сделать скриншот страницы\n"
        "/log — скачать лог"
    )

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот страницы"""
    global browser
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажи URL: /screen https://example.com")
        return
    
    url = args[0]
    user_id = update.effective_user.id
    
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        # Запускаем браузер если ещё не запущен
        if browser is None:
            from browser import Browser
            browser = await Browser().start()
            logger.info("✅ Браузер запущен")
        
        # Переходим на страницу
        await browser.goto(url)
        
        # Делаем скриншот
        screenshot_base64 = await browser.screenshot()
        
        # Отправляем фото
        import base64
        photo_bytes = base64.b64decode(screenshot_base64)
        
        await update.message.reply_photo(
            photo=photo_bytes,
            caption=f"✅ Скриншот {url}\nРазмер: {len(photo_bytes)} байт"
        )
        
        logger.info(f"User {user_id} сделал скриншот {url}")
        
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить файл лога"""
    user_id = update.effective_user.id
    
    try:
        with open("bot.log", "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption=f"📋 Лог бота ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            )
        logger.info(f"User {user_id} скачал лог")
    except FileNotFoundError:
        await update.message.reply_text("❌ Файл лога не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ===== Запуск =====
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("log", log))
    
    logger.info("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()