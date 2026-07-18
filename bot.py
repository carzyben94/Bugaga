import os
import asyncio
import subprocess
import time
import json
import shutil
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

# ===== УНИВЕРСАЛЬНЫЙ ИМПОРТ BROWSER-HARNESS =====
HARNESS_AVAILABLE = False
BH = None

try:
    import browser_harness
    print(f"📦 browser-harness загружен: {browser_harness.__file__}")
    print(f"📋 Доступно: {[x for x in dir(browser_harness) if not x.startswith('_')]}")
    
    # Пробуем разные варианты
    if hasattr(browser_harness, 'helpers'):
        BH = browser_harness.helpers
        print("✅ Использую browser_harness.helpers")
    elif hasattr(browser_harness, 'cdp'):
        BH = browser_harness
        print("✅ Использую browser_harness.cdp")
    else:
        # Пробуем импортировать напрямую
        try:
            from browser_harness import helpers
            BH = helpers
            print("✅ Использую helpers напрямую")
        except ImportError:
            # Последний вариант — использовать как есть
            BH = browser_harness
            print("✅ Использую browser_harness напрямую")
    
    HARNESS_AVAILABLE = True
    
except ImportError as e:
    print(f"⚠️ browser-harness не найден: {e}")

# ===== НАДЁЖНЫЙ ПОИСК БРАУЗЕРА =====
def find_chrome():
    possible_names = [
        "chromium", "chromium-browser", "chrome", "google-chrome",
        "google-chrome-stable", "chrome-browser"
    ]
    
    possible_paths = [
        "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/chrome",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/local/bin/chromium", "/usr/local/bin/chrome",
        "/usr/local/bin/google-chrome", "/snap/bin/chromium", "/snap/bin/chrome",
        "/opt/google/chrome/chrome", "/opt/chromium/chrome",
        "/usr/lib/chromium-browser/chromium-browser", "/usr/lib/chromium/chromium",
        "/usr/lib/google-chrome/chrome", "/usr/lib64/google-chrome/chrome",
    ]
    
    for name in possible_names:
        path = shutil.which(name)
        if path and os.path.exists(path) and os.access(path, os.X_OK):
            print(f"✅ Найден Chrome: {path}")
            return path
    
    for path in possible_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            print(f"✅ Найден Chrome: {path}")
            return path
    
    print("❌ Браузер не найден!")
    return None

# ===== ЗАПУСК БРАУЗЕРА =====
def start_browser():
    try:
        resp = httpx.get("http://localhost:9222/json/version", timeout=1)
        if resp.status_code == 200:
            print("✅ Браузер уже запущен")
            return True
    except:
        pass
    
    chrome_path = find_chrome()
    if not chrome_path:
        return False
    
    cmd = [
        chrome_path,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--remote-debugging-port=9222",
        "--user-data-dir=/tmp/chrome-profile",
    ]
    
    print(f"🚀 Запуск: {chrome_path}")
    
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
        return False
    
    for attempt in range(15):
        time.sleep(1)
        try:
            resp = httpx.get("http://localhost:9222/json/version", timeout=1)
            if resp.status_code == 200:
                print(f"✅ Браузер запущен ({attempt+1})")
                return True
        except:
            print(f"⏳ Ожидание... ({attempt+1}/15)")
    
    return False

print("🚀 Инициализация...")
browser_started = start_browser()

# ===== УНИВЕРСАЛЬНЫЙ КЛАСС БРАУЗЕРА =====
class HarnessBrowser:
    def __init__(self):
        self.connected = False
        self._bh = BH
    
    def _call(self, func_name, *args, **kwargs):
        """Универсальный вызов функций browser-harness"""
        if not HARNESS_AVAILABLE:
            raise Exception("browser-harness не доступен")
        
        # Пробуем найти функцию
        if hasattr(self._bh, func_name):
            return getattr(self._bh, func_name)(*args, **kwargs)
        
        # Пробуем в helpers
        try:
            from browser_harness import helpers
            if hasattr(helpers, func_name):
                return getattr(helpers, func_name)(*args, **kwargs)
        except:
            pass
        
        # Пробуем через cdp
        if hasattr(self._bh, 'cdp') and func_name == 'goto_url':
            return self._bh.cdp("Page.navigate", url=args[0])
        
        raise Exception(f"Функция {func_name} не найдена")
    
    async def connect(self):
        if not HARNESS_AVAILABLE:
            return "❌ browser-harness не доступен"
        try:
            # Пробуем разные способы
            if hasattr(self._bh, 'ensure_real_tab'):
                self._bh.ensure_real_tab()
            elif hasattr(self._bh, 'ensure_tab'):
                self._bh.ensure_tab()
            else:
                # Пробуем через helpers
                try:
                    from browser_harness import helpers
                    if hasattr(helpers, 'ensure_real_tab'):
                        helpers.ensure_real_tab()
                except:
                    pass
            self.connected = True
            print("✅ Браузер подключен")
            return "✅ Браузер подключен"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def navigate(self, url: str):
        if not self.connected:
            await self.connect()
        try:
            if hasattr(self._bh, 'goto_url'):
                self._bh.goto_url(url)
            else:
                try:
                    from browser_harness import helpers
                    if hasattr(helpers, 'goto_url'):
                        helpers.goto_url(url)
                    else:
                        self._call('cdp', "Page.navigate", url=url)
                except:
                    self._call('cdp', "Page.navigate", url=url)
            return {"success": True, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, expression: str):
        if not self.connected:
            await self.connect()
        try:
            if hasattr(self._bh, 'js'):
                return self._bh.js(expression)
            else:
                try:
                    from browser_harness import helpers
                    if hasattr(helpers, 'js'):
                        return helpers.js(expression)
                except:
                    pass
                # Через CDP
                result = await self._call('cdp', "Runtime.evaluate", 
                                          expression=expression, 
                                          returnByValue=True)
                if result and 'result' in result and 'result' in result['result']:
                    return result['result']['result'].get('value')
                return result
        except Exception as e:
            return {"error": str(e)}

browser = HarnessBrowser()

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот с browser-harness**\n\n"
        f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не доступен'}\n"
        f"🌐 **Браузер:** {'✅ Запущен' if browser_started else '❌ Не запущен'}\n\n"
        "Команды:\n"
        "/status — статус\n"
        "/connect — подключиться\n"
        "/open <url> — открыть\n"
        "/js <код> — выполнить JS\n\n"
        "Или просто:\n"
        "• `открой google.com`\n"
        "• `js: document.title`",
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    text = f"🔗 **Статус:** {'✅ Подключен' if browser.connected else '❌ Не подключен'}\n"
    text += f"🌐 **Браузер:** {'✅ Запущен' if browser_started else '❌ Не запущен'}\n"
    text += f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не доступен'}\n"
    if BH:
        text += f"📋 **Доступно:** {[x for x in dir(BH) if not x.startswith('_')][:5]}...\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def connect(update: Update, context):
    msg = await browser.connect()
    await update.message.reply_text(msg)

async def open_url(update: Update, context):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL")
        return
    url = context.args[0]
    if not url.startswith("http"):
        url = "https://" + url
    await update.message.reply_text(f"🌐 Открываю {url}...")
    result = await browser.navigate(url)
    if result.get("success"):
        await update.message.reply_text(f"✅ {url}")
    else:
        await update.message.reply_text(f"❌ {result.get('error')}")

async def execute_js(update: Update, context):
    if not context.args:
        await update.message.reply_text("❌ Укажи JS код")
        return
    expression = " ".join(context.args)
    await update.message.reply_text(f"⚡ Выполняю...")
    result = await browser.evaluate(expression)
    if isinstance(result, dict) and "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
    else:
        await update.message.reply_text(f"📊 Результат:\n```json\n{json.dumps(result, indent=2, ensure_ascii=False)[:4000]}\n```", parse_mode="Markdown")

async def handle_message(update: Update, context):
    text = update.message.text.lower()
    if text.startswith("открой "):
        url = text[7:].strip()
        if not url.startswith("http"):
            url = "https://" + url
        result = await browser.navigate(url)
        if result.get("success"):
            await update.message.reply_text(f"✅ {url}")
        else:
            await update.message.reply_text(f"❌ {result.get('error')}")
        return
    
    if text.startswith("js:") or text.startswith("выполни js:"):
        expression = text.split(":", 1)[1].strip()
        result = await browser.evaluate(expression)
        if isinstance(result, dict) and "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            await update.message.reply_text(f"📊 Результат:\n```json\n{json.dumps(result, indent=2, ensure_ascii=False)[:4000]}\n```", parse_mode="Markdown")
        return

def main():
    if HARNESS_AVAILABLE and browser_started:
        try:
            if hasattr(BH, 'ensure_real_tab'):
                BH.ensure_real_tab()
            elif hasattr(BH, 'ensure_tab'):
                BH.ensure_tab()
            browser.connected = True
            print("✅ Браузер подключен при старте")
        except Exception as e:
            print(f"⚠️ Не удалось подключиться: {e}")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("open", open_url))
    app.add_handler(CommandHandler("js", execute_js))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()