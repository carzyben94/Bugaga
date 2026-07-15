# bot.py - с логами
import os
import logging
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from browser import BrowserManager

# Настройки
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHROME_WS_URL = os.getenv("CHROME_WS_URL", "ws://localhost:9222/devtools/browser/...")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Хранилище сессий пользователей
user_sessions = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Пользователь {update.effective_user.id} вызвал /start")
    await update.message.reply_text(
        "👋 Привет! Я бот для управления браузером через CDP.\n\n"
        "Команды:\n"
        "/browse <url> - открыть страницу\n"
        "/screenshot - сделать скриншот\n"
        "/close - закрыть вкладку\n"
        "/log - получить файл логов"
    )

# Команда /browse
async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} вызвал /browse с аргументами: {context.args}")
    
    if not context.args:
        logger.warning(f"Пользователь {user_id} не указал URL")
        await update.message.reply_text("❌ Укажите URL: /browse https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    logger.debug(f"Пользователь {user_id} открывает URL: {url}")
    await update.message.reply_text(f"🌐 Открываю: {url}")
    
    try:
        # Создаём сессию если нет
        if user_id not in user_sessions:
            logger.info(f"Создаю новую сессию для пользователя {user_id}")
            browser = BrowserManager(CHROME_WS_URL)
            await browser.connect()
            target_id = await browser.create_tab()
            await browser.attach_to_tab(target_id)
            user_sessions[user_id] = {"browser": browser, "target_id": target_id}
            logger.debug(f"Сессия создана: target_id={target_id}")
        
        browser = user_sessions[user_id]["browser"]
        await browser.navigate(url)
        
        title = await browser.get_title()
        logger.info(f"Пользователь {user_id} загрузил страницу: {title}")
        await update.message.reply_text(f"✅ Загружено: {title}")
        
    except Exception as e:
        logger.error(f"Ошибка у пользователя {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /screenshot
async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} вызвал /screenshot")
    
    if user_id not in user_sessions:
        logger.warning(f"Пользователь {user_id} пытается сделать скриншот без активной сессии")
        await update.message.reply_text("❌ Сначала откройте страницу через /browse")
        return
    
    await update.message.reply_text("📸 Делаю скриншот...")
    logger.debug(f"Пользователь {user_id}: делаю скриншот")
    
    try:
        browser = user_sessions[user_id]["browser"]
        screenshot_data = await browser.screenshot()
        
        if screenshot_data:
            logger.info(f"Пользователь {user_id}: скриншот создан, размер: {len(screenshot_data)} байт")
            await update.message.reply_photo(
                photo=base64.b64decode(screenshot_data),
                caption="📸 Скриншот страницы"
            )
        else:
            logger.error(f"Пользователь {user_id}: не удалось сделать скриншот")
            await update.message.reply_text("❌ Не удалось сделать скриншот")
            
    except Exception as e:
        logger.error(f"Ошибка у пользователя {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /close
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} вызвал /close")
    
    if user_id not in user_sessions:
        logger.warning(f"Пользователь {user_id} пытается закрыть несуществующую сессию")
        await update.message.reply_text("❌ Нет активной сессии")
        return
    
    try:
        browser = user_sessions[user_id]["browser"]
        target_id = user_sessions[user_id]["target_id"]
        
        logger.info(f"Пользователь {user_id}: закрываю вкладку {target_id}")
        await browser.close_tab(target_id)
        await browser.disconnect()
        del user_sessions[user_id]
        
        logger.info(f"Пользователь {user_id}: сессия закрыта")
        await update.message.reply_text("❌ Вкладка закрыта")
        
    except Exception as e:
        logger.error(f"Ошибка у пользователя {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /log - получить файл логов
async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} запросил файл логов")
    
    try:
        # Проверяем существование файла
        log_file = "bot.log"
        if not os.path.exists(log_file):
            logger.warning(f"Файл логов {log_file} не найден")
            await update.message.reply_text("❌ Файл логов не найден")
            return
        
        # Проверяем размер файла
        file_size = os.path.getsize(log_file)
        logger.debug(f"Размер лог-файла: {file_size} байт")
        
        if file_size == 0:
            await update.message.reply_text("📝 Лог-файл пуст")
            return
        
        # Отправляем файл
        with open(log_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption=f"📋 Лог-файл ({file_size} байт)"
            )
        
        logger.info(f"Пользователь {user_id}: лог-файл отправлен")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке лога пользователю {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при отправке лога: {str(e)}")

# Запуск
def main():
    logger.info("🚀 Бот запускается...")
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("log", get_log))
    
    logger.info("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()