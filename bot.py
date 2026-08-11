import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pyppeteer import launch
from pyppeteer.errors import PageError

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Глобальные переменные
browser = None
pages = {}

async def init_browser():
    """Инициализация браузера"""
    global browser
    if not browser:
        browser = await launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
    return browser

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client Bot\n\n"
        "Команды:\n"
        "/open <url> - открыть страницу\n"
        "/screenshot - скриншот текущей страницы\n"
        "/click <selector> - клик по элементу\n"
        "/type <selector> <text> - ввести текст\n"
        "/evaluate <js_code> - выполнить JS\n"
        "/close - закрыть текущую страницу\n"
        "/pages - список открытых страниц"
    )

async def open_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открыть новую страницу"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите URL: /open https://example.com")
            return
        
        url = context.args[0]
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        b = await init_browser()
        page = await b.newPage()
        
        # Сохраняем страницу
        page_id = str(id(page))
        pages[page_id] = page
        
        await page.goto(url, waitUntil='networkidle0')
        
        title = await page.title()
        await update.message.reply_text(
            f"✅ Страница открыта\n"
            f"📄 {title}\n"
            f"🔗 {url}\n"
            f"🆔 ID: {page_id[:8]}..."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот"""
    try:
        if not pages:
            await update.message.reply_text("❌ Нет открытых страниц. Используйте /open")
            return
        
        # Берем последнюю открытую страницу
        page = list(pages.values())[-1]
        
        screenshot_bytes = await page.screenshot(fullPage=True)
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"📸 Скриншот страницы"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def click_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кликнуть по элементу"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите селектор: /click #button")
            return
        
        if not pages:
            await update.message.reply_text("❌ Нет открытых страниц")
            return
        
        selector = ' '.join(context.args)
        page = list(pages.values())[-1]
        
        await page.waitForSelector(selector, timeout=5000)
        await page.click(selector)
        
        await update.message.reply_text(f"✅ Кликнул по: {selector}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввести текст"""
    try:
        if len(context.args) < 2:
            await update.message.reply_text("❌ /type <selector> <text>")
            return
        
        if not pages:
            await update.message.reply_text("❌ Нет открытых страниц")
            return
        
        selector = context.args[0]
        text = ' '.join(context.args[1:])
        page = list(pages.values())[-1]
        
        await page.waitForSelector(selector, timeout=5000)
        await page.click(selector)
        await page.type(selector, text)
        
        await update.message.reply_text(f"✅ Введено: {text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить JavaScript"""
    try:
        if not context.args:
            await update.message.reply_text("❌ /evaluate <js_code>")
            return
        
        if not pages:
            await update.message.reply_text("❌ Нет открытых страниц")
            return
        
        js_code = ' '.join(context.args)
        page = list(pages.values())[-1]
        
        result = await page.evaluate(js_code)
        await update.message.reply_text(f"✅ Результат:\n{str(result)[:1000]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def close_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть страницу"""
    try:
        if not pages:
            await update.message.reply_text("❌ Нет открытых страниц")
            return
        
        page_id = list(pages.keys())[-1]
        page = pages.pop(page_id)
        await page.close()
        
        await update.message.reply_text(f"✅ Страница закрыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def list_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список открытых страниц"""
    if not pages:
        await update.message.reply_text("📭 Нет открытых страниц")
        return
    
    msg = "📄 Открытые страницы:\n\n"
    for i, (page_id, page) in enumerate(pages.items(), 1):
        try:
            url = await page.url()
            title = await page.title()
            msg += f"{i}. {title[:30]}\n   {url[:50]}\n   ID: {page_id[:8]}...\n\n"
        except:
            msg += f"{i}. Страница {page_id[:8]}...\n"
    
    await update.message.reply_text(msg[:4000])

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("open", open_page))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("click", click_element))
    app.add_handler(CommandHandler("type", type_text))
    app.add_handler(CommandHandler("evaluate", evaluate_js))
    app.add_handler(CommandHandler("close", close_page))
    app.add_handler(CommandHandler("pages", list_pages))
    
    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()