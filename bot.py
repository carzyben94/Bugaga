import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from browser_harness import Harness
import websockets

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HARNESS_WS_URL = os.getenv("HARNESS_WS_URL", "ws://localhost:9222/devtools/browser")

# Глобальный экземпляр Harness
harness = None

async def init_harness():
    global harness
    try:
        # Подключаемся к запущенному Chromium через WebSocket
        harness = await Harness.connect(
            browser_ws_endpoint=HARNESS_WS_URL,
            headless=True
        )
        print(f"✅ Harness подключен к {HARNESS_WS_URL}")
        return harness
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с browser-harness готов!\n"
        "Команды:\n"
        "/navigate <url> - перейти на страницу\n"
        "/screenshot - сделать скриншот\n"
        "/click <selector> - кликнуть элемент\n"
        "/fill <selector> <text> - заполнить поле\n"
        "/get_text <selector> - получить текст"
    )

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /navigate https://example.com")
        return
    
    url = context.args[0]
    try:
        # Создаем новую вкладку
        tab = await harness.new_tab()
        await tab.goto(url, wait_until="networkidle")
        
        # Сохраняем tab в context.user_data
        context.user_data['tab'] = tab
        
        await update.message.reply_text(f"✅ Перешли на {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Сначала перейдите на страницу: /navigate")
        return
    
    try:
        screenshot_bytes = await tab.screenshot()
        await update.message.reply_photo(screenshot_bytes)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def click_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите селектор: /click #button")
        return
    
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Сначала перейдите на страницу")
        return
    
    selector = ' '.join(context.args)
    try:
        await tab.click(selector)
        await update.message.reply_text(f"✅ Кликнули по {selector}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def fill_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите: /fill #input текст")
        return
    
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Сначала перейдите на страницу")
        return
    
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    
    try:
        await tab.fill(selector, text)
        await update.message.reply_text(f"✅ Заполнили {selector}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите селектор: /get_text h1")
        return
    
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Сначала перейдите на страницу")
        return
    
    selector = ' '.join(context.args)
    try:
        text = await tab.text_content(selector)
        await update.message.reply_text(f"📝 {text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tab = context.user_data.get('tab')
    if tab:
        await tab.close()
        context.user_data['tab'] = None
        await update.message.reply_text("✅ Вкладка закрыта")
    else:
        await update.message.reply_text("Нет активной вкладки")

def main():
    # Инициализируем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("click", click_element))
    app.add_handler(CommandHandler("fill", fill_field))
    app.add_handler(CommandHandler("get_text", get_text))
    app.add_handler(CommandHandler("close", close_tab))
    
    # Запускаем бота
    print("🤖 Бот запускается...")
    
    # Создаем event loop и подключаем harness
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_harness())
    
    if harness:
        print("✅ Harness готов к работе")
        app.run_polling()
    else:
        print("❌ Harness не подключился")

if __name__ == "__main__":
    main()