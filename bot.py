# bot.py - Минимальный файл бота

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем всё из stealth.py
from stealth import (
    browser, current_page, timing_config, ensure_browser,
    CDPPage, CDPBrowser, Stealth, StealthConfig, TimingConfig
)

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client (Full Stealth)\n\n"
        "Команды:\n"
        "/screenshot - скриншот\n"
        "/pdf - сохранить PDF\n"
        "/newpage <url> - новая страница\n"
        "/navigate <url> - перейти\n"
        "/evaluate <js> - выполнить JS\n"
        "/click <selector> - клик (humanized)\n"
        "/type <selector> <text> - ввод (humanized)\n"
        "/scroll - прокрутить вниз\n"
        "/html - получить HTML\n"
        "/tabs - список страниц\n"
        "/status - статус"
    )

async def newpage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    url = context.args[0] if context.args else "about:blank"
    page = await browser.new_page(url)
    if page:
        current_page = page
        await update.message.reply_text(f"✅ Новая страница: {url}")
    else:
        await update.message.reply_text("❌ Не удалось создать страницу")

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if not context.args:
        await update.message.reply_text("❌ /navigate https://example.com")
        return
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    url = context.args[0]
    await current_page.goto(url)
    await update.message.reply_text(f"✅ Переход на {url}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    await update.message.reply_text("🔄 Делаю скриншот...")
    img_data = await current_page.screenshot()
    await update.message.reply_photo(photo=img_data, caption="📸 Скриншот")

async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if not context.args:
        await update.message.reply_text("❌ /evaluate document.title")
        return
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    js = ' '.join(context.args)
    result = await current_page.evaluate(js)
    await update.message.reply_text(f"✅ {str(result)[:1000]}")

async def click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if not context.args:
        await update.message.reply_text("❌ /click #button")
        return
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    selector = ' '.join(context.args)
    await update.message.reply_text(f"🖱️ Кликаю по {selector}...")
    result = await current_page.click(selector, humanize=True, config=timing_config)
    await update.message.reply_text(f"✅ Клик по: {selector}" if result else f"❌ Не найден: {selector}")

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if len(context.args) < 2:
        await update.message.reply_text("❌ /type #input text")
        return
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    await update.message.reply_text(f"⌨️ Ввожу текст...")
    result = await current_page.type_text(selector, text, humanize=True, config=timing_config)
    await update.message.reply_text(f"✅ Введено: {text}" if result else f"❌ Не найден: {selector}")

async def scroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    await update.message.reply_text("📜 Прокручиваю вниз...")
    await current_page.scroll_to_bottom(humanize=True)
    await update.message.reply_text("✅ Прокрутка выполнена")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    html_content = await current_page.html()
    await update.message.reply_text(f"📄 HTML:\n{html_content[:1000]}")

async def list_tabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    pages = browser.get_pages_list()
    if not pages:
        await update.message.reply_text("📭 Нет страниц")
        return
    msg = "📄 Страницы:\n\n"
    for i, page in enumerate(pages, 1):
        title = page.get('title', 'Без названия')[:30]
        url = page.get('url', '')[:50]
        msg += f"{i}. {title}\n   {url}\n\n"
    await update.message.reply_text(msg[:4000])

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = "📊 Статус:\n\n"
    status_msg += f"Страница: {'✅' if current_page else '❌'}\n"
    status_msg += f"Страниц: {len(browser.pages)}\n"
    status_msg += f"Маскировка: ✅ (Stealth)\n"
    status_msg += f"Humanize: ✅\n"
    if current_page and current_page._is_connected:
        try:
            url = await current_page.url()
            title = await current_page.title()
            status_msg += f"\nURL: {url[:60]}\n"
            status_msg += f"Title: {title[:30]}"
        except:
            pass
    await update.message.reply_text(status_msg)

# ============================================================
# ЗАПУСК БОТА
# ============================================================

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newpage", newpage))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(CommandHandler("click", click))
    app.add_handler(CommandHandler("type", type_text))
    app.add_handler(CommandHandler("scroll", scroll))
    app.add_handler(CommandHandler("html", get_html))
    app.add_handler(CommandHandler("tabs", list_tabs))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 CDP Client (Full Stealth) запущен")
    print("📁 Всего 2 файла: bot.py + stealth.py")
    app.run_polling()

if __name__ == "__main__":
    main()