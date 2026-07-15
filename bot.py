# bot.py - минималистичная версия
import os
import logging
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from browser import BrowserManager

# Настройки
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHROME_WS_URL = os.getenv("CHROME_WS_URL", "ws://localhost:9222/devtools/browser/...")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище сессий пользователей
user_sessions = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для управления браузером через CDP.\n\n"
        "Команды:\n"
        "/browse <url> - открыть страницу\n"
        "/screenshot - сделать скриншот\n"
        "/close - закрыть вкладку"
    )

# Команда /browse
async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /browse https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    await update.message.reply_text(f"🌐 Открываю: {url}")
    
    try:
        # Создаём сессию если нет
        if user_id not in user_sessions:
            browser = BrowserManager(CHROME_WS_URL)
            await browser.connect()
            target_id = await browser.create_tab()
            await browser.attach_to_tab(target_id)
            user_sessions[user_id] = {"browser": browser, "target_id": target_id}
        
        browser = user_sessions[user_id]["browser"]
        await browser.navigate(url)
        
        title = await browser.get_title()
        await update.message.reply_text(f"✅ Загружено: {title}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /screenshot
async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сначала откройте страницу через /browse")
        return
    
    await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        browser = user_sessions[user_id]["browser"]
        screenshot_data = await browser.screenshot()
        
        if screenshot_data:
            # Отправляем как фото (base64)
            await update.message.reply_photo(
                photo=base64.b64decode(screenshot_data),
                caption="📸 Скриншот страницы"
            )
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /close
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Нет активной сессии")
        return
    
    try:
        browser = user_sessions[user_id]["browser"]
        target_id = user_sessions[user_id]["target_id"]
        
        await browser.close_tab(target_id)
        await browser.disconnect()
        del user_sessions[user_id]
        
        await update.message.reply_text("❌ Вкладка закрыта")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Запуск
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("close", close))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()