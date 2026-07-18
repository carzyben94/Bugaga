import os
import asyncio
import subprocess
import time
import json
import shutil
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не задан")
    exit(1)

# ===== НАДЁЖНЫЙ ПОИСК БРАУЗЕРА =====
def find_chrome():
    """Ищет Chrome/Chromium по 20+ путям"""
    
    # Имена исполняемых файлов
    possible_names = [
        "chromium", "chromium-browser", "chrome", "google-chrome",
        "google-chrome-stable", "chrome-browser"
    ]
    
    # Возможные пути
    possible_paths = [
        # Стандартные пути
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/local/bin/chromium",
        "/usr/local/bin/chrome",
        "/usr/local/bin/google-chrome",
        # Snap-пути
        "/snap/bin/chromium",
        "/snap/bin/chrome",
        # Docker-пути
        "/app/chromium/chrome",
        "/app/chrome/chrome",
        # Другие
        "/opt/google/chrome/chrome",
        "/opt/chromium/chrome",
        "/usr/lib/chromium-browser/chromium-browser",
        "/usr/lib/chromium/chromium",
        "/usr/lib/google-chrome/chrome",
        "/usr/lib64/google-chrome/chrome",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        # Windows (WSL)
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    ]
    
    # Проверяем через which
    for name in possible_names:
        path = shutil.which(name)
        if path and os.path.exists(path) and os.access(path, os.X_OK):
            print(f"✅ Найден Chrome через which: {path}")
            return path
    
    # Проверяем пути
    for path in possible_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            print(f"✅ Найден Chrome по пути: {path}")
            return path
    
    # Пробуем find (медленно, но надёжно)
    try:
        result = subprocess.run(
            ["find", "/", "-name", "chromium", "-type", "f", "-executable", "2>/dev/null"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if line and os.access(line, os.X_OK):
                print(f"✅ Найден Chrome через find: {line}")
                return line
    except:
        pass
    
    print("❌ Браузер не найден!")
    return None

# ===== ЗАПУСК БРАУЗЕРА =====
def start_browser():
    """Запускает браузер с CDP-портом"""
    
    # Проверяем, не запущен ли уже браузер
    try:
        import httpx
        resp = httpx.get("http://localhost:9222/json/version", timeout=1)
        if resp.status_code == 200:
            print("✅ Браузер уже запущен")
            return True
    except:
        pass
    
    chrome_path = find_chrome()
    if not chrome_path:
        print("❌ Браузер не найден!")
        return False
    
    cmd = [
        chrome_path,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--remote-debugging-port=9222",
        "--remote-debugging-address=0.0.0.0",
        "--user-data-dir=/tmp/chrome-profile",
    ]
    
    print(f"🚀 Запуск браузера: {chrome_path}")
    print(f"📋 Команда: {' '.join(cmd)}")
    
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
    
    # Ждём запуска
    for attempt in range(15):
        time.sleep(1)
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/version", timeout=1)
            if resp.status_code == 200:
                print(f"✅ Браузер запущен (попытка {attempt+1})")
                return True
        except:
            print(f"⏳ Ожидание браузера... ({attempt+1}/15)")
    
    print("❌ Не удалось запустить браузер")
    return False

# ===== ЗАПУСК БРАУЗЕРА ПРИ СТАРТЕ =====
print("🚀 Инициализация...")
browser_started = start_browser()

# ===== ИМПОРТ BROWSER-HARNESS =====
try:
    from browser_harness import helpers as BH
    HARNESS_AVAILABLE = True
    print("✅ browser-harness загружен")
except ImportError:
    HARNESS_AVAILABLE = False
    print("⚠️ browser-harness не найден")

# ===== КЛАСС БРАУЗЕРА =====
class HarnessBrowser:
    def __init__(self):
        self.connected = False
    
    async def connect(self):
        if not HARNESS_AVAILABLE:
            return "❌ browser-harness не доступен"
        try:
            if BH and hasattr(BH, 'ensure_real_tab'):
                BH.ensure_real_tab()
            elif BH and hasattr(BH, 'ensure_tab'):
                BH.ensure_tab()
            else:
                from browser_harness import ensure_real_tab
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
            if BH and hasattr(BH, 'goto_url'):
                BH.goto_url(url)
            else:
                from browser_harness import goto_url
                goto_url(url)
            return {"success": True, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, expression: str):
        if not self.connected:
            await self.connect()
        try:
            if BH and hasattr(BH, 'js'):
                return BH.js(expression)
            else:
                from browser_harness import js
                return js(expression)
        except Exception as e:
            return {"error": str(e)}

browser = HarnessBrowser()

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот с browser-harness**\n\n"
        f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не установлен'}\n"
        f"🌐 **Браузер:** {'✅ Запущен' if browser_started else '❌ Не запущен'}\n\n"
        "Команды:\n"
        "/start — справка\n"
        "/status — статус\n"
        "/connect — подключиться к браузеру\n"
        "/open <url> — открыть страницу\n"
        "/js <код> — выполнить JS\n\n"
        "Или просто напиши:\n"
        "• `открой google.com`\n"
        "• `js: document.title`",
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    text = f"🔗 **Статус подключения:** {'✅ Подключен' if browser.connected else '❌ Не подключен'}\n"
    text += f"🌐 **Браузер:** {'✅ Запущен' if browser_started else '❌ Не запущен'}\n"
    text += f"📦 **browser-harness:** {'✅ Доступен' if HARNESS_AVAILABLE else '❌ Не установлен'}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

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
        await update.message.reply_text(f"✅ {url}")
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

async def handle_message(update: Update, context):
    text = update.message.text.lower()
    
    if text.startswith("открой "):
        url = text[7:].strip()
        if not url.startswith("http"):
            url = "https://" + url
        await update.message.reply_text(f"🌐 Открываю {url}...")
        result = await browser.navigate(url)
        if result.get("success"):
            await update.message.reply_text(f"✅ {url}")
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")
        return
    
    if text.startswith("js:") or text.startswith("выполни js:"):
        expression = text.split(":", 1)[1].strip()
        await update.message.reply_text(f"⚡ Выполняю JS...")
        result = await browser.evaluate(expression)
        if isinstance(result, dict) and "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            await update.message.reply_text(f"📊 Результат:\n```json\n{json.dumps(result, indent=2, ensure_ascii=False)[:4000]}\n```", parse_mode="Markdown")
        return
    
    await update.message.reply_text("❓ Не понял. Попробуй `открой google.com` или `/help`")

# ===== ЗАПУСК =====
def main():
    if HARNESS_AVAILABLE and browser_started:
        try:
            from browser_harness import ensure_real_tab
            ensure_real_tab()
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