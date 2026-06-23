import os
import logging
import threading
import time
import requests
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from browser import take_screenshot, get_page_content, execute_js

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Flask
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!", "mode": "polling"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

# Keep-alive
def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ КОМАНДЫ БОТА ============

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Команды:\n"
        "/open google.com - Открыть сайт и показать скриншот\n"
        "/screenshot google.com - Скриншот\n"
        "/html google.com - HTML код\n"
        "/js google.com 'document.title' - Выполнить JS"
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 Команды:\n\n"
        "/open google.com - Скриншот сайта\n"
        "/screenshot google.com - То же самое\n"
        "/html google.com - HTML код\n"
        "/js google.com 'document.title' - Выполнить JS"
    )

# /open - ОТКРЫТЬ САЙТ И СДЕЛАТЬ СКРИН
async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите URL: /open google.com")
        return
    
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    
    await update.message.reply_text(f"🌐 Открываю {url}...")
    
    screenshot = await take_screenshot(url)
    
    if screenshot:
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"✅ {url}"
        )
    else:
        await update.message.reply_text("❌ Не удалось открыть страницу")

# /screenshot
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите URL: /screenshot google.com")
        return
    
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    
    await update.message.reply_text("📸 Делаю скриншот...")
    
    screenshot = await take_screenshot(url)
    
    if screenshot:
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"✅ {url}"
        )
    else:
        await update.message.reply_text("❌ Не удалось сделать скриншот")

# /html
async def html_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите URL: /html google.com")
        return
    
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    
    await update.message.reply_text("📄 Получаю HTML...")
    
    content = await get_page_content(url)
    
    if content:
        if len(content) > 4000:
            content = content[:4000] + "\n\n... (обрезано)"
        await update.message.reply_text(f"```html\n{content}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Не удалось получить HTML")

# /js
async def js_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /js google.com 'document.title'")
        return
    
    url = args[0]
    script = ' '.join(args[1:])
    
    if not url.startswith("http"):
        url = "https://" + url
    
    await update.message.reply_text("⚡ Выполняю JS...")
    
    result = await execute_js(url, script)
    
    if result is not None:
        await update.message.reply_text(f"✅ Результат:\n```\n{result}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Не удалось выполнить скрипт")

# ============ ЗАПУСК ============

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("open", open_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("html", html_command))
    bot_app.add_handler(CommandHandler("js", js_command))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()