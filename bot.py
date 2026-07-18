import os
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ===== ИМПОРТ BROWSER-HARNESS =====
try:
    from browser_harness import (
        ensure_real_tab,
        goto_url,
        js,
        wait_for_load,
        wait_for_element,
        page_info,
        capture_screenshot,
        click_at_xy,
        type_text,
        press_key,
        scroll,
        new_tab,
        list_tabs,
        close_tab
    )
    HARNESS_AVAILABLE = True
    print("✅ browser-harness загружен")
except ImportError as e:
    HARNESS_AVAILABLE = False
    print(f"⚠️ browser-harness не найден: {e}")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

# ===== ОБЁРТКА ДЛЯ БРАУЗЕРА =====
class HarnessBrowser:
    def __init__(self):
        self.connected = False
    
    async def connect(self):
        if not HARNESS_AVAILABLE:
            return "❌ browser-harness не установлен"
        try:
            ensure_real_tab()
            self.connected = True
            print("✅ Браузер подключен")
            return "✅ Браузер подключен"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def navigate(self, url: str):
        if not self.connected:
            await self.connect()
        try:
            goto_url(url)
            wait_for_load(15)
            return {"success": True, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, expression: str):
        if not self.connected:
            await self.connect()
        try:
            return js(expression)
        except Exception as e:
            return {"error": str(e)}
    
    async def screenshot(self):
        if not self.connected:
            await self.connect()
        try:
            import tempfile
            path = tempfile.mktemp(suffix=".png")
            capture_screenshot(path)
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            return {"error": str(e)}
    
    async def get_info(self):
        if not self.connected:
            await self.connect()
        try:
            return page_info()
        except Exception as e:
            return {"error": str(e)}
    
    async def wait_for(self, selector: str, timeout: int = 15):
        if not self.connected:
            await self.connect()
        try:
            return wait_for_element(selector, timeout=timeout)
        except Exception as e:
            return {"error": str(e)}

browser = HarnessBrowser()

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот с browser-harness**\n\n"
        "Команды:\n"
        "/start — справка\n"
        "/status — статус браузера\n"
        "/connect — подключиться к браузеру\n"
        "/open <url> — открыть страницу\n"
        "/js <код> — выполнить JS\n"
        "/screenshot — скриншот\n"
        "/info — информация о странице\n\n"
        "Или просто напиши:\n"
        "• `открой google.com`\n"
        "• `выполни js: document.title`",
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    status_text = f"🔗 **Статус:** {'✅ Подключен' if browser.connected else '❌ Не подключен'}\n"
    status_text += f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не установлен'}\n"
    if browser.connected:
        try:
            info = await browser.get_info()
            if isinstance(info, dict) and "error" not in info:
                status_text += f"📄 **Страница:** {info.get('title', 'Нет')}\n"
                status_text += f"🔗 **URL:** {info.get('url', 'Нет')}\n"
                status_text += f"📐 **Размер:** {info.get('w', 0)}x{info.get('h', 0)}\n"
        except:
            pass
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def connect(update: Update, context):
    msg = await browser.connect()
    await update.message.reply_text(msg)

async def open_url(update: Update, context):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: `/open https://example.com`")
        return
    url = context.args[0]
    if not url.startswith("http"):
        url = "https://" + url
    await update.message.reply_text(f"🌐 Открываю {url}...")
    result = await browser.navigate(url)
    if result.get("success"):
        info = await browser.get_info()
        title = info.get("title", "Без названия") if isinstance(info, dict) else ""
        await update.message.reply_text(f"✅ {url}\n📄 {title}")
    else:
        await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")

async def execute_js(update: Update, context):
    if not context.args:
        await update.message.reply_text("❌ Укажи JS код: `/js document.title`")
        return
    expression = " ".join(context.args)
    await update.message.reply_text(f"⚡ Выполняю JS...")
    result = await browser.evaluate(expression)
    if isinstance(result, dict) and "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
    else:
        await update.message.reply_text(f"📊 Результат:\n```json\n{json.dumps(result, indent=2, ensure_ascii=False)[:4000]}\n```", parse_mode="Markdown")

async def screenshot(update: Update, context):
    await update.message.reply_text("📸 Делаю скриншот...")
    result = await browser.screenshot()
    if isinstance(result, dict) and "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
    else:
        await update.message.reply_photo(photo=result, caption="📸 Скриншот")

async def info(update: Update, context):
    result = await browser.get_info()
    if isinstance(result, dict) and "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return
    text = "📄 **Информация о странице:**\n\n"
    for key, value in result.items():
        text += f"• **{key}**: {value}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, context):
    text = update.message.text.lower()
    
    # Простые команды без /
    if text.startswith("открой "):
        url = text[7:].strip()
        if not url.startswith("http"):
            url = "https://" + url
        await update.message.reply_text(f"🌐 Открываю {url}...")
        result = await browser.navigate(url)
        if result.get("success"):
            info = await browser.get_info()
            title = info.get("title", "Без названия") if isinstance(info, dict) else ""
            await update.message.reply_text(f"✅ {url}\n📄 {title}")
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")
        return
    
    if text.startswith("выполни js:") or text.startswith("js:"):
        expression = text.split(":", 1)[1].strip()
        await update.message.reply_text(f"⚡ Выполняю JS...")
        result = await browser.evaluate(expression)
        if isinstance(result, dict) and "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            await update.message.reply_text(f"📊 Результат:\n```json\n{json.dumps(result, indent=2, ensure_ascii=False)[:4000]}\n```", parse_mode="Markdown")
        return
    
    if text.startswith("скриншот") or text == "screenshot":
        await screenshot(update, context)
        return
    
    await update.message.reply_text(
        "❓ Не понял команду.\n\n"
        "Попробуй:\n"
        "• `открой google.com`\n"
        "• `js: document.title`\n"
        "• `скриншот`\n"
        "• `/help` для всех команд"
    )

async def help_command(update: Update, context):
    await start(update, context)

# ===== ЗАПУСК =====
def main():
    # Подключаемся к браузеру при старте
    try:
        ensure_real_tab()
        browser.connected = True
        print("✅ Браузер подключен при старте")
    except Exception as e:
        print(f"⚠️ Не удалось подключиться при старте: {e}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("open", open_url))
    app.add_handler(CommandHandler("js", execute_js))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("info", info))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()