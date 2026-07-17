import os
import asyncio
import json
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser
from agent import get_response, parse_command, clear_memory, memory

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Бот-агент с самокоррекцией!\n\n"
        "Я вижу ошибки и учусь на них.\n"
        "/clear — очистить память\n"
        "/start — справка\n\n"
        "Просто пиши, что нужно сделать."
    )

async def clear(update: Update, context):
    clear_memory()
    await update.message.reply_text("🧹 Память очищена!")

async def execute_with_retry(update: Update, user_text: str, max_retries: int = 2) -> bool:
    """Выполняет команду с повторной попыткой при ошибке"""
    
    for attempt in range(max_retries + 1):
        try:
            # Получаем ответ от агента
            error_context = memory.last_error if attempt > 0 else None
            agent_response = await get_response(user_text, error_context)
            cmd = parse_command(agent_response)
            
            if not cmd:
                await update.message.reply_text(agent_response)
                return True
            
            method = cmd.get("method")
            params = cmd.get("params", {})
            
            await update.message.reply_text(f"⚡ {method}")
            
            browser = ChromiumBrowser()
            browser.launch(headless=True)
            
            try:
                await browser.connect()
                result = await browser.send_command(method, params)
                
                # Успех — очищаем ошибку
                memory.last_error = None
                
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
                return True
                
            except Exception as e:
                error_msg = str(e)
                await update.message.reply_text(f"❌ {error_msg}")
                
                # Сохраняем ошибку в память
                memory.set_error(error_msg)
                
                await browser.disconnect()
                browser.close()
                
                if attempt < max_retries:
                    await update.message.reply_text(f"🔄 Пробую исправить... (попытка {attempt+2}/{max_retries+1})")
                else:
                    await update.message.reply_text("❌ Не удалось выполнить команду. Попробуй переформулировать.")
                continue
                
        except Exception as e:
            if attempt < max_retries:
                continue
            else:
                await update.message.reply_text(f"❌ Критическая ошибка: {e}")
                return False
    
    return False

async def handle_message(update: Update, context):
    user_text = update.message.text
    user_id = str(update.message.from_user.id)
    
    await update.message.reply_text("🤔 Думаю...")
    await execute_with_retry(update, user_text)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен с самокоррекцией")
    app.run_polling()

if __name__ == "__main__":
    main()