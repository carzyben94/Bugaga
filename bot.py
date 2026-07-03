import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Правильные импорты Pydoll
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Модель данных
class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

# Путь к браузеру
CHROME_PATH = '/usr/bin/chromium'

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с парсингом.\n"
        "Используй /parse для получения цитат"
    )

# Команда /parse
async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Начинаю парсинг...")
    
    try:
        # Настройка браузера
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.binary_location = CHROME_PATH
        
        async with Chrome(options=options) as browser:
            tab = await browser.start()
            await tab.go_to('https://quotes.toscrape.com')
            
            # Ждём загрузки страницы
            import asyncio
            await asyncio.sleep(3)
            
            # ПРАВИЛЬНЫЙ СПОСОБ: передаём scope
            quotes = await tab.extract_all(
                Quote,
                scope=".quote",  # scope - это селектор для всех элементов
                timeout=10
            )
            
            if quotes:
                reply = "📚 Цитаты:\n\n"
                for i, q in enumerate(quotes[:5], 1):
                    reply += f"{i}. \"{q.text}\"\n   — {q.author}\n   🏷️ {q.tags}\n\n"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("😕 Ничего не найдено")
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("parse", parse))
    application.add_error_handler(error_handler)
    
    # Проверяем наличие браузера
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()