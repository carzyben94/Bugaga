import os
import asyncio
import logging
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# API браузера внутри контейнера
BROWSER_API = os.environ.get("BROWSER_API", "http://localhost:8080")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Команды:\n"
        "/check <url> - открыть сайт через Camoufox\n"
        "/screenshot - сделать скриншот текущей страницы\n"
        "/status - статус браузера\n"
        "/dspy <запрос> - задать вопрос DSPy (через API)"
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text("⏳ Открываю через Camoufox...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Переходим на URL
            resp = await client.post(
                f"{BROWSER_API}/",
                json={"action": "goto", "url": url}
            )
            
            if resp.status_code != 200:
                await msg.edit_text(f"❌ Ошибка API: {resp.status_code}")
                return
            
            # Получаем информацию о странице
            info = await client.post(
                f"{BROWSER_API}/",
                json={"action": "get_info"}
            )
            data = info.json()
            
            title = data.get("title", "Без названия")
            current_url = data.get("url", url)
            
            await msg.edit_text(f"✅ **{title}**\n\n{current_url}", parse_mode='Markdown')
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{BROWSER_API}/screenshot/browser?whLargest=1024")
            
            if resp.status_code != 200:
                await msg.edit_text(f"❌ Ошибка: {resp.status_code}")
                return
            
            # Отправляем фото
            await update.message.reply_photo(
                photo=resp.content,
                caption="📸 Скриншот через Camoufox"
            )
            await msg.delete()
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BROWSER_API}/")
            
            await update.message.reply_text(
                f"📦 **Статус**\n"
                f"• Браузер: ✅ Работает\n"
                f"• API: {BROWSER_API}\n"
                f"• Статус: {resp.status_code}\n"
                f"• Движок: Camoufox (Firefox)",
                parse_mode='Markdown'
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Браузер не отвечает: {str(e)[:100]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка запроса к DSPy через MCP-сервер"""
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Примеры:\n"
            "`/dspy открой google.com и покажи заголовок`\n"
            "`/dspy найди все ссылки на python.org`\n"
            "`/dspy сделай скриншот`",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Отправляем запрос к MCP-серверу
            resp = await client.post(
                f"{BROWSER_API}/mcp",
                json={"query": query}
            )
            
            if resp.status_code != 200:
                await msg.edit_text(f"❌ Ошибка MCP: {resp.status_code}")
                return
            
            data = resp.json()
            answer = data.get("result", data.get("answer", "❌ Пустой ответ"))
            
            if len(answer) > 4000:
                answer = answer[:4000] + "\n\n... (обрезано)"
            
            await msg.edit_text(
                f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
                parse_mode='MarkdownV2'
            )
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"📋 Команды: /start, /check, /screenshot, /status, /dspy")
    logger.info(f"🌐 Browser API: {BROWSER_API}")
    
    app.run_polling()

if __name__ == "__main__":
    main()