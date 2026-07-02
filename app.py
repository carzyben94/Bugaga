import asyncio
import os
import logging
from typing import Optional
from playwright.async_api import async_playwright
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Глобальные переменные для браузера
browser_instance = None
playwright_instance = None

async def get_browser():
    """Получить или создать экземпляр браузера"""
    global browser_instance, playwright_instance
    
    if browser_instance is None or not browser_instance.is_connected():
        logger.info("🔄 Запускаем браузер...")
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        logger.info("✅ Браузер запущен!")
    
    return browser_instance

# ============ КОМАНДЫ БОТА ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🤖 Привет! Я бот с CDP-браузером!\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение\n"
        "/status - статус браузера\n"
        "/screenshot <url> - сделать скриншот страницы\n"
        "/html <url> - получить HTML страницы\n"
        "/exec <js-код> - выполнить JavaScript\n"
        "/close - закрыть браузер\n"
        "/help - помощь"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - статус браузера"""
    global browser_instance
    
    if browser_instance and browser_instance.is_connected():
        status_text = "✅ Браузер активен"
        try:
            contexts = browser_instance.contexts
            status_text += f"\n📂 Контекстов: {len(contexts)}"
            for ctx in contexts:
                pages = ctx.pages
                status_text += f"\n  📄 Страниц: {len(pages)}"
        except:
            pass
    else:
        status_text = "❌ Браузер не запущен"
    
    await update.message.reply_text(status_text)

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /screenshot <url> - сделать скриншот"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        browser = await get_browser()
        page = await browser.new_page()
        
        await page.goto(url, wait_until='networkidle', timeout=30000)
        screenshot_bytes = await page.screenshot(full_page=True)
        
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"✅ Скриншот {url}"
        )
        await page.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /html <url> - получить HTML"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /html https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"📄 Загружаю {url}...")
    
    try:
        browser = await get_browser()
        page = await browser.new_page()
        
        await page.goto(url, wait_until='networkidle', timeout=30000)
        html = await page.content()
        
        # Обрезаем длинный HTML
        if len(html) > 4000:
            html = html[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(
            f"✅ HTML страницы {url}:\n\n```html\n{html}\n```",
            parse_mode='Markdown'
        )
        await page.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def exec_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /exec <js-код> - выполнить JavaScript"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите JS-код:\n"
            "/exec document.title\n"
            "/exec document.querySelector('h1').textContent"
        )
        return
    
    js_code = ' '.join(context.args)
    await update.message.reply_text(f"⚡ Выполняю: `{js_code}`", parse_mode='Markdown')
    
    try:
        browser = await get_browser()
        page = await browser.new_page()
        
        # Открываем пустую страницу
        await page.goto('about:blank')
        
        # Выполняем JS
        result = await page.evaluate(js_code)
        
        # Форматируем результат
        if result is None:
            result_text = "null"
        elif isinstance(result, (str, int, float, bool)):
            result_text = str(result)
        else:
            result_text = str(result)
            if len(result_text) > 1000:
                result_text = result_text[:1000] + "... (обрезано)"
        
        await update.message.reply_text(
            f"✅ Результат:\n```\n{result_text}\n```",
            parse_mode='Markdown'
        )
        await page.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /close - закрыть браузер"""
    global browser_instance, playwright_instance
    
    if browser_instance:
        try:
            await browser_instance.close()
            logger.info("✅ Браузер закрыт")
        except:
            pass
        browser_instance = None
    
    if playwright_instance:
        try:
            await playwright_instance.stop()
        except:
            pass
        playwright_instance = None
    
    await update.message.reply_text("🔒 Браузер закрыт")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "📖 Помощь:\n\n"
        "/start - приветствие\n"
        "/status - статус браузера\n"
        "/screenshot <url> - скриншот страницы\n"
        "/html <url> - HTML страницы\n"
        "/exec <js-код> - выполнить JS\n"
        "/close - закрыть браузер\n"
        "/help - эта справка"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений"""
    text = update.message.text
    if text.startswith('http'):
        # Если пользователь прислал URL, предлагаем действия
        keyboard = [
            [InlineKeyboardButton("📸 Скриншот", callback_data=f'screenshot_{text}')],
            [InlineKeyboardButton("📄 HTML", callback_data=f'html_{text}')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🌐 Что сделать с {text}?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Я понимаю только команды. Напишите /help для списка."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith('screenshot_'):
        url = data.replace('screenshot_', '')
        # Передаём в контекст и вызываем screenshot
        context.args = [url]
        await screenshot(update, context)
    
    elif data.startswith('html_'):
        url = data.replace('html_', '')
        context.args = [url]
        await get_html(update, context)

# ============ ЗАПУСК ============

async def main():
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("screenshot", screenshot))
    application.add_handler(CommandHandler("html", get_html))
    application.add_handler(CommandHandler("exec", exec_js))
    application.add_handler(CommandHandler("close", close_browser))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("🚀 Бот запущен!")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())