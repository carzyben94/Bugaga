import os
import sys
import subprocess
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Устанавливаем путь для браузера
PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

def install_playwright_browser():
    """Устанавливает Chromium для Playwright при первом запуске"""
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    
    if os.path.exists(browser_path):
        print("✅ Браузер уже установлен")
        return True
    
    print("⏳ Устанавливаю браузер Chromium...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Браузер успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки браузера: {e}")
        return False

# Устанавливаем браузер при запуске
install_playwright_browser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 Проверить браузер", callback_data="status")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером Playwright на борту.\n\n"
        "Выбери действие:",
        reply_markup=reply_markup
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка браузера с красивым выводом"""
    # Определяем, откуда пришёл запрос (из команды или кнопки)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        edit = True
    else:
        message = update.message
        edit = False
    
    status_text = "🔍 **Проверка браузера...**\n\n"
    status_text += f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
    status_text += "━" * 20 + "\n"
    
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
        
        status_text += "⏳ Запускаю браузер...\n"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            await stealth_async(page)
            
            status_text += "🌐 Загружаю X.com...\n"
            await page.goto('https://x.com', wait_until='networkidle')
            
            title = await page.title()
            url = page.url
            
            await browser.close()
            
            status_text += "\n✅ **Браузер работает!**\n"
            status_text += f"📌 Заголовок: `{title[:50]}...`\n"
            status_text += f"🔗 URL: `{url[:50]}`\n"
            status_text += f"🛡️ Stealth: активирован"
            
    except ImportError as e:
        status_text += f"\n❌ Ошибка импорта: `{str(e)[:50]}`"
    except Exception as e:
        status_text += f"\n❌ Ошибка: `{str(e)[:50]}`"
    
    # Кнопка "Обновить"
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="status")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit:
        await message.edit_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика бота"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    stats_text = "📊 **Статистика бота**\n\n"
    stats_text += f"🕐 Время работы: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    stats_text += f"🧠 Память: {sys.getsizeof(os.environ.get('TELEGRAM_BOT_TOKEN', '')) // 1024} KB\n"
    stats_text += f"🌐 Браузер: {'✅ установлен' if os.path.exists(os.path.join(PLAYWRIGHT_DIR, 'chromium-1091', 'chrome-linux', 'chrome')) else '❌ не установлен'}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "status":
        await status(update, context)
    elif query.data == "stats":
        await stats(update, context)
    elif query.data == "start":
        keyboard = [
            [InlineKeyboardButton("🌐 Проверить браузер", callback_data="status")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "👋 Привет! Я бот с браузером Playwright на борту.\n\n"
            "Выбери действие:",
            reply_markup=reply_markup
        )

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()