import os
import asyncio
import json
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

# ===== ИМПОРТ BROWSER-HARNESS =====
HARNESS_AVAILABLE = False
BH = None

try:
    import browser_harness
    HARNESS_AVAILABLE = True
    print(f"✅ browser-harness загружен (версия: {getattr(browser_harness, '__version__', 'unknown')})")
    print(f"📦 Доступно: {[x for x in dir(browser_harness) if not x.startswith('_')]}")
    
    # Пробуем получить helpers
    if hasattr(browser_harness, 'helpers'):
        BH = browser_harness.helpers
        print("✅ Использую browser_harness.helpers")
    elif hasattr(browser_harness, 'cdp'):
        BH = browser_harness
        print("✅ Использую browser_harness напрямую")
    else:
        # Пробуем импортировать из подмодулей
        try:
            from browser_harness import helpers as bh_helpers
            BH = bh_helpers
            print("✅ Использую browser_harness.helpers (прямой импорт)")
        except ImportError:
            print("⚠️ Не удалось найти helpers")
            HARNESS_AVAILABLE = False
            
except ImportError as e:
    print(f"⚠️ browser-harness не найден: {e}")
    HARNESS_AVAILABLE = False

# ===== ОБЁРТКА ДЛЯ БРАУЗЕРА =====
class HarnessBrowser:
    def __init__(self):
        self.connected = False
    
    async def connect(self):
        if not HARNESS_AVAILABLE or BH is None:
            return "❌ browser-harness не доступен"
        try:
            # Пробуем разные варианты подключения
            if hasattr(BH, 'ensure_real_tab'):
                BH.ensure_real_tab()
            elif hasattr(BH, 'ensure_tab'):
                BH.ensure_tab()
            elif hasattr(BH, 'connect'):
                BH.connect()
            else:
                # Пробуем найти функцию в browser_harness
                import browser_harness
                if hasattr(browser_harness, 'ensure_real_tab'):
                    browser_harness.ensure_real_tab()
                else:
                    print("⚠️ Не найдена функция для подключения")
                    return "❌ Не найдена функция подключения"
            self.connected = True
            print("✅ Браузер подключен")
            return "✅ Браузер подключен"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def navigate(self, url: str):
        if not self.connected:
            await self.connect()
        try:
            if BH and hasattr(BH, 'goto_url'):
                BH.goto_url(url)
            elif BH and hasattr(BH, 'navigate'):
                BH.navigate(url)
            else:
                # Пробуем через cdp
                await self.cdp("Page.navigate", {"url": url})
            return {"success": True, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, expression: str):
        if not self.connected:
            await self.connect()
        try:
            if BH and hasattr(BH, 'js'):
                return BH.js(expression)
            elif BH and hasattr(BH, 'evaluate'):
                return BH.evaluate(expression)
            else:
                # Пробуем через cdp
                return await self.cdp("Runtime.evaluate", {
                    "expression": expression,
                    "returnByValue": True
                })
        except Exception as e:
            return {"error": str(e)}
    
    async def cdp(self, method: str, params: dict = None):
        """Прямой вызов CDP"""
        if not self.connected:
            await self.connect()
        try:
            if BH and hasattr(BH, 'cdp'):
                return BH.cdp(method, **(params or {}))
            else:
                return {"error": "cdp не доступен"}
        except Exception as e:
            return {"error": str(e)}
    
    async def screenshot(self):
        if not self.connected:
            await self.connect()
        try:
            import tempfile
            path = tempfile.mktemp(suffix=".png")
            if BH and hasattr(BH, 'capture_screenshot'):
                BH.capture_screenshot(path)
            elif BH and hasattr(BH, 'screenshot'):
                BH.screenshot(path)
            else:
                # Пробуем через cdp
                result = await self.cdp("Page.captureScreenshot", {"format": "png"})
                if result and "data" in result:
                    import base64
                    return base64.b64decode(result["data"])
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            return {"error": str(e)}
    
    async def get_info(self):
        if not self.connected:
            await self.connect()
        try:
            if BH and hasattr(BH, 'page_info'):
                return BH.page_info()
            else:
                title = await self.evaluate("document.title")
                url = await self.evaluate("window.location.href")
                return {"title": title, "url": url}
        except Exception as e:
            return {"error": str(e)}

browser = HarnessBrowser()

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот с browser-harness**\n\n"
        f"📦 **Статус:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не доступен'}\n\n"
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
        "• `выполни js: document.title`\n"
        "• `скриншот`",
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    status_text = f"🔗 **Статус:** {'✅ Подключен' if browser.connected else '❌ Не подключен'}\n"
    status_text += f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не установлен'}\n"
    if BH:
        status_text += f"📋 **Доступные функции:** {[x for x in dir(BH) if not x.startswith('_')][:10]}...\n"
    if browser.connected:
        try:
            info = await browser.get_info()
            if isinstance(info, dict) and "error" not in info:
                status_text += f"📄 **Страница:** {info.get('title', 'Нет')}\n"
                status_text += f"🔗 **URL:** {info.get('url', 'Нет')}\n"
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

# ===== ЗАПУСК =====
def main():
    # Пробуем подключиться при старте
    if HARNESS_AVAILABLE and BH:
        try:
            if hasattr(BH, 'ensure_real_tab'):
                BH.ensure_real_tab()
                browser.connected = True
                print("✅ Браузер подключен при старте")
        except Exception as e:
            print(f"⚠️ Не удалось подключиться при старте: {e}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("open", open_url))
    app.add_handler(CommandHandler("js", execute_js))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("info", info))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен")
    print(f"📦 browser-harness: {'Доступен' if HARNESS_AVAILABLE else 'Не доступен'}")
    if BH:
        print(f"📋 Доступные функции: {[x for x in dir(BH) if not x.startswith('_')][:10]}...")
    app.run_polling()

if __name__ == "__main__":
    main()