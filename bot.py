import os
import asyncio
import json
import base64
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from browser import ChromiumBrowser
from agent import (
    get_response, parse_command, clear_memory, add_log,
    get_logs, clear_logs, get_memory_stats, flush_pending_saves
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

keep_browser = False
browser_instance = None

async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Бот-агент\n\n"
        "/start — справка\n"
        "/clear — очистить память\n"
        "/logai — логи\n"
        "/logclear — очистить логи\n"
        "/keep — удержание браузера\n"
        "/close — закрыть браузер\n"
        "/status — статус"
    )

async def status(update: Update, context):
    global keep_browser, browser_instance
    stats = get_memory_stats()
    logs = get_logs()
    text = (
        f"📊 Статус\n"
        f"Память: {stats['history_count']}/{stats['max_history']}\n"
        f"Ошибок: {'Есть' if stats['last_error'] else 'Нет'}\n"
        f"Логов: {len(logs)}\n"
        f"Удержание: {'ВКЛ' if keep_browser else 'ВЫКЛ'}\n"
        f"Браузер: {'Запущен' if browser_instance else 'Нет'}\n"
        f"GitHub: {'✅' if os.environ.get('GITHUB_TOKEN') else '❌'}"
    )
    await update.message.reply_text(text)

async def toggle_keep_browser(update: Update, context):
    global keep_browser
    keep_browser = not keep_browser
    await update.message.reply_text(f"🔄 Удержание: {'ВКЛ' if keep_browser else 'ВЫКЛ'}")

async def close_browser_command(update: Update, context):
    global browser_instance, keep_browser
    if browser_instance:
        await browser_instance.disconnect()
        browser_instance.close()
        browser_instance = None
        keep_browser = False
        add_log("browser_closed", "Закрыт", "info")
        flush_pending_saves()
        await update.message.reply_text("🛑 Браузер закрыт")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

async def clear(update: Update, context):
    clear_memory()
    flush_pending_saves()
    await update.message.reply_text("🧹 Память очищена")

async def show_logs(update: Update, context):
    logs = get_logs()
    if not logs:
        await update.message.reply_text("📭 Логов нет")
        return
    lines = []
    for log in logs[-20:]:
        timestamp = log.get("timestamp", "")[11:19]
        action = log.get("action", "")
        details = log.get("details", "")
        status = log.get("status", "")
        emoji = "✅" if status == "success" else "❌" if status == "error" else "ℹ️"
        lines.append(f"{timestamp} {emoji} {action}: {details}")
    await update.message.reply_text("\n".join(lines))

async def clear_logs_command(update: Update, context):
    clear_logs()
    flush_pending_saves()
    await update.message.reply_text("🧹 Логи очищены")

async def get_browser():
    global browser_instance
    if keep_browser:
        if browser_instance is None:
            browser_instance = ChromiumBrowser()
            browser_instance.launch(headless=True)
            await browser_instance.connect()
            add_log("browser_kept", "Удержан", "success")
        return browser_instance
    else:
        browser = ChromiumBrowser()
        browser.launch(headless=True)
        await browser.connect()
        return browser

async def execute_with_retry(update: Update, user_text: str, max_retries: int = 2) -> bool:
    add_log("user_input", user_text, "info")
    for attempt in range(max_retries + 1):
        browser = None
        try:
            agent_response = await get_response(user_text)
            cmd = parse_command(agent_response)
            if not cmd:
                add_log("agent_response", agent_response[:100], "info")
                await update.message.reply_text(agent_response)
                return True
            method = cmd.get("method")
            params = cmd.get("params", {})
            add_log("command", f"{method}", "info")
            await update.message.reply_text(f"⚡ {method}")
            browser = await get_browser()
            result = await browser.send_command(method, params)
            add_log("success", method, "success")
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
                await update.message.reply_text("✅ Выполнено")
            if not keep_browser:
                await browser.disconnect()
                browser.close()
                flush_pending_saves()
            return True
        except Exception as e:
            error_msg = str(e)
            add_log("error", error_msg[:150], "error")
            await update.message.reply_text(f"❌ {error_msg}")
            if browser and not keep_browser:
                await browser.disconnect()
                browser.close()
            if attempt < max_retries:
                add_log("retry", f"Попытка {attempt+2}", "info")
                await update.message.reply_text(f"🔄 Попытка {attempt+2}/{max_retries+1}")
            else:
                await update.message.reply_text("❌ Не удалось выполнить")
            continue
    return False

async def handle_message(update: Update, context):
    user_text = update.message.text
    await update.message.reply_text("🤔 Думаю...")
    await execute_with_retry(update, user_text)

def main():
    add_log("bot_started", "Бот запущен", "success")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("logai", show_logs))
    app.add_handler(CommandHandler("logclear", clear_logs_command))
    app.add_handler(CommandHandler("keep", toggle_keep_browser))
    app.add_handler(CommandHandler("close", close_browser_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()