import os
import asyncio
import json
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser
from agent import get_response, parse_command, clear_memory

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Я бот-агент с памятью!\n\n"
        "Я запоминаю контекст разговора.\n"
        "Команды:\n"
        "/clear — очистить память\n"
        "/start — это сообщение\n\n"
        "Просто пиши, что нужно сделать."
    )

async def clear(update: Update, context):
    clear_memory()
    await update.message.reply_text("🧹 Память очищена!")

async def handle_message(update: Update, context):
    user_text = update.message.text
    user_id = str(update.message.from_user.id)
    
    await update.message.reply_text("🤔 Думаю...")
    
    # Передаём user_id для разделения памяти по пользователям
    agent_response = await get_response(user_text, user_id)
    cmd = parse_command(agent_response)
    
    if not cmd:
        await update.message.reply_text(agent_response)
        return
    
    method = cmd.get("method")
    params = cmd.get("params", {})
    
    await update.message.reply_text(f"⚡ {method}")
    
    browser = ChromiumBrowser()
    browser.launch(headless=True)
    
    try:
        await browser.connect()
        result = await browser.send_command(method, params)
        
        if method == "Page.captureScreenshot":
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(photo=img_data, caption="📸 Скриншот")
            else:
                await update.message.reply_text("✅ Скриншот сделан")
        
        elif method == "Page.navigate":
            await asyncio.sleep(1)
            title = await browser.evaluate("document.title")
            await update.message.reply_text(f"✅ {params.get('url')}\n📄 {title}")
        
        elif method == "Runtime.evaluate":
            value = result.get("result", {}).get("result", {}).get("value")
            await update.message.reply_text(f"📊 {value}")
        
        else:
            await update.message.reply_text(f"✅ Выполнено")
        
        await browser.disconnect()
        browser.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")
        browser.close()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен с памятью")
    app.run_polling()

if __name__ == "__main__":
    main()