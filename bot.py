import os
import logging
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Модель для парсинга цитат
class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

# Путь к браузеру
CHROME_PATH = '/usr/bin/chromium'

# Храним браузер и вкладку для каждого пользователя
user_browsers = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное меню"""
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/parse - Получить цитаты\n"
        "/go <url> - Открыть любой сайт\n"
        "/screen - Сделать скриншот"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает любой сайт"""
    if not context.args:
        await update.message.reply_text("❌ Укажи URL после команды\nПример: /go https://example.com")
        return
    
    url = context.args[0]
    
    # Добавляем https:// если нет протокола
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text(f"🌐 Открываю: {url}")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.binary_location = CHROME_PATH
        
        # Если у пользователя уже есть браузер - используем его
        if user_id in user_browsers:
            browser, tab = user_browsers[user_id]
            await tab.go_to(url)
            await asyncio.sleep(2)
            await update.message.reply_text(f"✅ Перешёл на {url}")
        else:
            # Создаём новый браузер
            browser = Chrome(options=options)
            tab = await browser.start()
            await tab.go_to(url)
            await asyncio.sleep(2)
            user_browsers[user_id] = (browser, tab)
            await update.message.reply_text(f"✅ Открыл: {url}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот текущей страницы"""
    user_id = update.effective_user.id
    
    try:
        # Проверяем, есть ли активный браузер
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        
        # Делаем скриншот в формате base64
        screenshot_base64 = await tab.take_screenshot(as_base64=True)
        
        # Декодируем base64 в байты для отправки
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        # Отправляем фото в Telegram
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption="🖼️ Скриншот страницы"
        )
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсит цитаты с quotes.toscrape.com"""
    await update.message.reply_text("⏳ Начинаю парсинг...")
    
    try:
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.binary_location = CHROME_PATH
        
        async with Chrome(options=options) as browser:
            tab = await browser.start()
            await tab.go_to('https://quotes.toscrape.com')
            
            await asyncio.sleep(3)
            
            quotes = await tab.extract_all(
                Quote,
                scope=".quote",
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("screen", screen))
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