import os
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser  # ← правильный импорт

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не задан!")
    print("Установи: export TELEGRAM_BOT_TOKEN='твой_токен'")
    exit(1)

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Привет! Я бот с управлением браузером.\n\n"
        "Команды:\n"
        "/start - показать это сообщение\n"
        "открой <url> - открыть сайт и показать заголовок\n"
        "скрин <url> - открыть сайт и прислать скриншот\n"
        "текст <url> - показать текст страницы\n"
        "клик <url> <селектор> - кликнуть по элементу"
    )

async def handle_message(update: Update, context):
    user_text = update.message.text
    
    # ===== ОТКРЫТЬ САЙТ =====
    if user_text.lower().startswith("открой") or user_text.lower().startswith("open"):
        parts = user_text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Укажи URL: открой https://example.com")
            return
        
        url = parts[1]
        if not url.startswith("http"):
            url = "https://" + url
        
        await update.message.reply_text(f"🌐 Открываю {url}...")
        
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        
        try:
            await browser.connect()
            await browser.navigate(url)
            title = await browser.evaluate("document.title")
            await browser.disconnect()
            browser.close()
            
            await update.message.reply_text(f"✅ {url}\n📄 Заголовок: {title}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            browser.close()
        return
    
    # ===== СКРИНШОТ =====
    if user_text.lower().startswith("скрин") or user_text.lower().startswith("screenshot"):
        parts = user_text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Укажи URL: скрин https://example.com")
            return
        
        url = parts[1]
        if not url.startswith("http"):
            url = "https://" + url
        
        await update.message.reply_text(f"📸 Делаю скриншот {url}...")
        
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        
        try:
            await browser.connect()
            await browser.set_viewport(1280, 720)
            await browser.navigate(url)
            
            img_data = await browser.screenshot()
            
            await browser.disconnect()
            browser.close()
            
            await update.message.reply_photo(
                photo=img_data,
                caption=f"📸 Скриншот {url}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            browser.close()
        return
    
    # ===== ТЕКСТ СТРАНИЦЫ =====
    if user_text.lower().startswith("текст") or user_text.lower().startswith("text"):
        parts = user_text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Укажи URL: текст https://example.com")
            return
        
        url = parts[1]
        if not url.startswith("http"):
            url = "https://" + url
        
        await update.message.reply_text(f"📖 Читаю {url}...")
        
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        
        try:
            await browser.connect()
            await browser.navigate(url)
            
            text = await browser.evaluate("document.body.innerText")
            text = text[:4000]
            
            await browser.disconnect()
            browser.close()
            
            await update.message.reply_text(f"📄 Текст страницы {url}:\n\n{text}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            browser.close()
        return
    
    # ===== КЛИК =====
    if user_text.lower().startswith("клик") or user_text.lower().startswith("click"):
        parts = user_text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ Укажи URL и селектор: клик https://example.com h1")
            return
        
        url = parts[1]
        selector = parts[2]
        if not url.startswith("http"):
            url = "https://" + url
        
        await update.message.reply_text(f"🖱️ Кликаю по {selector} на {url}...")
        
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        
        try:
            await browser.connect()
            await browser.navigate(url)
            await browser.click(selector)
            await asyncio.sleep(0.5)
            
            img_data = await browser.screenshot()
            
            await browser.disconnect()
            browser.close()
            
            await update.message.reply_photo(
                photo=img_data,
                caption=f"🖱️ Клик по {selector} выполнен на {url}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            browser.close()
        return
    
    # ===== ЗАГЛУШКА =====
    await update.message.reply_text(
        "🤖 Я пока умею только:\n"
        "• открой <url>\n"
        "• скрин <url>\n"
        "• текст <url>\n"
        "• клик <url> <селектор>"
    )

def main():
    print("🚀 Запуск Telegram бота...")
    print(f"🤖 Токен: {TOKEN[:10]}...")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен! Напиши /start в Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()