import os
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт модулей
from browser import Browser
from eval import Eval

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Доступные команды:\n"
        "/browser <ссылка> - открыть сайт и сделать скриншот\n"
        "/close - закрыть браузер\n\n"
        "Пример: /browser https://google.com"
    )

async def browser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Проверяем ссылку
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ссылку!\n"
                "Пример: /browser https://google.com"
            )
            return
        
        url = context.args[0]
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Проверяем, есть ли уже браузер
        browser = context.user_data.get('browser')
        eval_obj = context.user_data.get('eval')
        
        if not browser:
            await update.message.reply_text("🌐 Запускаю браузер...")
            browser = await Browser().start()
            context.user_data['browser'] = browser
            context.user_data['eval'] = Eval(browser)
        else:
            await update.message.reply_text("🔄 Браузер уже запущен, открываю ссылку...")
        
        # Переходим по ссылке
        await browser.goto(url)
        
        # Делаем скриншот
        screenshot_data = await browser.screenshot()
        image_bytes = base64.b64decode(screenshot_data)
        
        # Отправляем
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"✅ Скриншот: {url}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        # Если ошибка, закрываем браузер
        if 'browser' in context.user_data:
            try:
                await context.user_data['browser'].close()
            except:
                pass
            context.user_data['browser'] = None
            context.user_data['eval'] = None

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser = context.user_data.get('browser')
    if browser:
        await browser.close()
        context.user_data['browser'] = None
        context.user_data['eval'] = None
        await update.message.reply_text("🛑 Браузер закрыт")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser", browser_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    
    print("✅ Бот запущен!")
    print("📋 Команды: /browser <ссылка>, /close")
    app.run_polling()

if __name__ == "__main__":
    main()