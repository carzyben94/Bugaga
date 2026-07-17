import os
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser
from agent import get_response, parse_command

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не задан!")
    exit(1)

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Я бот-агент с управлением браузером!\n\n"
        "Просто напиши, что нужно сделать:\n"
        "• 'открой google.com'\n"
        "• 'сделай скриншот example.com'\n"
        "• 'найди заголовок страницы'\n"
        "• 'кликни на кнопку с текстом Войти'\n\n"
        "Я сам решу, какие CDP-команды использовать."
    )

async def handle_message(update: Update, context):
    user_text = update.message.text
    await update.message.reply_text("🤔 Анализирую запрос...")
    
    # 1. Получаем ответ от агента (через AI)
    agent_response = await get_response(user_text)
    print(f"🧠 Агент: {agent_response}")
    
    # 2. Пытаемся извлечь CDP-команду
    cmd = parse_command(agent_response)
    
    if not cmd:
        # Если команды нет — просто отвечаем текстом
        await update.message.reply_text(agent_response)
        return
    
    # 3. Выполняем команду через браузер
    method = cmd.get("method")
    params = cmd.get("params", {})
    
    await update.message.reply_text(f"⚡ Выполняю: {method}")
    
    browser = ChromiumBrowser()
    browser.launch(headless=True)
    
    try:
        await browser.connect()
        
        # Выполняем команду
        result = await browser.send_command(method, params)
        
        # Если это скриншот — отправляем фото
        if method == "Page.captureScreenshot":
            if "result" in result and "data" in result["result"]:
                import base64
                img_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(
                    photo=img_data,
                    caption="📸 Скриншот готов"
                )
            else:
                await update.message.reply_text(f"✅ {method} выполнен")
        
        # Если это навигация — показываем заголовок
        elif method == "Page.navigate":
            await asyncio.sleep(1)
            title = await browser.evaluate("document.title")
            await update.message.reply_text(f"✅ Перешёл на {params.get('url')}\n📄 Заголовок: {title}")
        
        # Если это выполнение JS — показываем результат
        elif method == "Runtime.evaluate":
            value = result.get("result", {}).get("result", {}).get("value")
            await update.message.reply_text(f"📊 Результат: {value}")
        
        else:
            await update.message.reply_text(f"✅ {method} выполнен\nОтвет: {json.dumps(result, indent=2)[:500]}")
        
        await browser.disconnect()
        browser.close()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        browser.close()

def main():
    print("🚀 Запуск Telegram бота с агентом...")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()