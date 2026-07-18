import os
import subprocess
import time
import socket
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ... (ваш код check_browser и ensure_browser) ...

async def test_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда — открывает сайт через browser-harness"""
    try:
        # Импортируем browser-harness
        from browser_harness import Browser
        
        # Подключаемся к запущенному браузеру
        browser = Browser()
        await browser.start()
        
        # Открываем страницу
        await browser.goto("https://example.com")
        title = await browser.title()
        
        await update.message.reply_text(
            f"✅ Успешно открыл страницу!\n"
            f"Заголовок: {title}"
        )
        
        await browser.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_browser))  # Новая команда
    
    print("🚀 Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)