import os
import sys
import asyncio
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# ДОБАВЛЯЕМ ЛОКАЛЬНЫЙ browser-harness
# ============================================

# Добавляем путь к локальной версии browser-harness
LOCAL_HARNESS_PATH = os.path.join(os.path.dirname(__file__), "browser-harness", "src")
if os.path.exists(LOCAL_HARNESS_PATH):
    sys.path.insert(0, LOCAL_HARNESS_PATH)
    print(f"✅ Добавлен локальный browser-harness: {LOCAL_HARNESS_PATH}")
else:
    print(f"⚠️ Локальный browser-harness не найден: {LOCAL_HARNESS_PATH}")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ============================================
# ПРОВЕРКА КОМПОНЕНТОВ
# ============================================

def check_veil():
    try:
        import veilbrowser
        return True, getattr(veilbrowser, '__version__', 'unknown')
    except ImportError:
        return False, None

def check_harness():
    try:
        import browser_harness
        return True, getattr(browser_harness, '__version__', 'unknown')
    except ImportError:
        return False, None

def check_chrome():
    paths = ["/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    return None

VEIL_OK, VEIL_VER = check_veil()
HARNESS_OK, HARNESS_VER = check_harness()
CHROME_PATH = check_chrome()

# ============================================
# БРАУЗЕР
# ============================================

browser_instance = None
chrome_process = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil + browser-harness**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить через harness\n"
        "/diag - диагностика"
    )

async def start_veil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, chrome_process
    await update.message.reply_text("🔄 Запускаю Veil...")
    
    if not VEIL_OK:
        await update.message.reply_text(
            "❌ Veil не установлен!\n"
            "Установи: pip install git+https://github.com/acunningham-ship-it/veilbrowser.git#subdirectory=python"
        )
        return
    
    try:
        if not CHROME_PATH:
            await update.message.reply_text("❌ Chrome не найден!")
            return
        
        await update.message.reply_text("🔄 Запускаю Chrome с маскировкой...")
        
        # Запускаем Chrome
        chrome_process = subprocess.Popen(
            [
                CHROME_PATH,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--remote-debugging-port=9222",
                "--use-gl=angle",
                "--use-angle=gl-egl",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                f"--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        await asyncio.sleep(2)
        
        # Подключаем Veil
        from veilbrowser import Browser
        browser_instance = await Browser.connect("http://127.0.0.1:9222")
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: http://127.0.0.1:9222\n"
            f"🆔 PID: {chrome_process.pid}\n\n"
            f"Используй /check для проверки через harness"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю через browser-harness...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        # Используем browser-harness для проверки
        from browser_harness import BrowserSession
        
        # Подключаемся через CDP
        async with BrowserSession(cdp_url="http://127.0.0.1:9222") as session:
            page = await session.new_page()
            await page.goto("https://bot.sannysoft.com")
            await asyncio.sleep(3)
            
            # Скриншот
            screenshot = await page.screenshot()
            await update.message.reply_photo(
                photo=screenshot,
                caption="📸 Проверка через harness"
            )
            
            # Проверка webdriver
            result = await page.evaluate("""
                () => ({
                    webdriver: navigator.webdriver,
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    languages: navigator.languages
                })
            """)
            
            if result['webdriver'] is False:
                verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
            else:
                verdict = "⚠️ **Браузер как бот**"
            
            await update.message.reply_text(
                f"🔍 **Результат через harness**\n\n"
                f"{verdict}\n"
                f"• webdriver: `{result['webdriver']}`\n"
                f"• platform: `{result['platform']}`\n"
                f"• languages: `{', '.join(result['languages'][:2])}`\n\n"
                f"💡 Если `false` — всё работает!"
            )
        
    except ImportError as e:
        await update.message.reply_text(
            f"❌ browser-harness не найден!\n"
            f"Проверь путь: {LOCAL_HARNESS_PATH}\n\n"
            f"Ошибка: {str(e)[:100]}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Harness: {'✅' if HARNESS_OK else '❌'} {HARNESS_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Локальный harness: {'✅' if os.path.exists(LOCAL_HARNESS_PATH) else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    
    if CHROME_PATH:
        report += f"• Путь Chrome: `{CHROME_PATH}`\n"
    if chrome_process:
        report += f"• PID Chrome: `{chrome_process.pid}`\n"
    if os.path.exists(LOCAL_HARNESS_PATH):
        report += f"• Путь harness: `{LOCAL_HARNESS_PATH}`\n"
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_veil", start_veil))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()