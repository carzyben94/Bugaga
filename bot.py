import os
import logging
import subprocess
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

# Функция поиска Chrome
def find_chrome_path():
    """Ищет установленный Chrome/Chromium по разным путям"""
    
    # Список возможных путей
    possible_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chrome',
        '/snap/bin/chromium',
        '/usr/local/bin/chromium',
        '/usr/lib/chromium/chromium',
        '/usr/lib/chromium-browser/chromium-browser',
        '/opt/google/chrome/chrome',
        '/usr/bin/chromedriver',  # Иногда драйвер тоже работает
    ]
    
    # Проверяем каждый путь
    for path in possible_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            logger.info(f"✅ Найден браузер: {path}")
            return path
    
    # Если не нашли - пробуем через which
    try:
        for cmd in ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'chrome']:
            result = subprocess.run(['which', cmd], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                logger.info(f"✅ Найден браузер через which: {path}")
                return path
    except Exception as e:
        logger.warning(f"Ошибка при поиске через which: {e}")
    
    # Пробуем найти через find (медленно, но надежно)
    try:
        result = subprocess.run(
            ['find', '/usr', '-name', '*chrome*', '-o', '-name', '*chromium*'],
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.stdout:
            for line in result.stdout.split('\n'):
                if line and os.access(line, os.X_OK):
                    logger.info(f"✅ Найден браузер через find: {line}")
                    return line
    except Exception as e:
        logger.warning(f"Ошибка при поиске через find: {e}")
    
    logger.error("❌ Браузер не найден!")
    return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с парсингом.\n"
        "Используй /parse для получения цитат\n"
        "Используй /check для проверки браузера"
    )

# Команда /check - проверка браузера
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет, найден ли браузер"""
    chrome_path = find_chrome_path()
    
    if chrome_path:
        await update.message.reply_text(f"✅ Браузер найден:\n`{chrome_path}`")
    else:
        await update.message.reply_text(
            "❌ Браузер не найден!\n"
            "Проверь установку Chrome в Dockerfile"
        )

# Команда /parse
async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Начинаю парсинг...")
    
    try:
        # Ищем браузер
        chrome_path = find_chrome_path()
        
        if not chrome_path:
            await update.message.reply_text(
                "❌ Браузер не найден!\n"
                "Используй /check для диагностики"
            )
            return
        
        # Настройка браузера
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.binary_location = chrome_path
        
        await update.message.reply_text(f"🔄 Запускаю браузер: {chrome_path}")
        
        async with Chrome(options=options) as browser:
            tab = await browser.start()
            await tab.go_to('https://quotes.toscrape.com')
            
            quotes = await tab.extract_all(Quote, timeout=5)
            
            if quotes:
                reply = "📚 Цитаты:\n\n"
                for i, q in enumerate(quotes[:3], 1):
                    reply += f"{i}. \"{q.text}\"\n   — {q.author}\n   🏷️ {q.tags}\n\n"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("😕 Ничего не найдено")
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check))  # Новая команда
    application.add_handler(CommandHandler("parse", parse))
    application.add_error_handler(error_handler)
    
    # При запуске проверяем браузер
    chrome_path = find_chrome_path()
    if chrome_path:
        logger.info(f"✅ Браузер найден: {chrome_path}")
    else:
        logger.error("❌ Браузер НЕ НАЙДЕН! Проверь Dockerfile")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()