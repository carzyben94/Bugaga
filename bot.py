import os
import asyncio
import logging
import subprocess
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ============================================
# ПРОВЕРКА VEIL
# ============================================

def check_veil():
    try:
        import veilbrowser
        return True, getattr(veilbrowser, '__version__', 'unknown')
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
CHROME_PATH = check_chrome()

# ============================================
# БРАУЗЕР
# ============================================

browser_instance = None
chrome_process = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil Browser**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить браузер\n"
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
        # 1. Сначала запускаем Chrome вручную с --no-sandbox
        if not CHROME_PATH:
            await update.message.reply_text("❌ Chrome не найден в системе!")
            return
        
        await update.message.reply_text("🔄 Запускаю Chrome вручную...")
        
        # Запускаем Chrome с нужными флагами
        chrome_process = subprocess.Popen(
            [
                CHROME_PATH,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--remote-debugging-port=9222",
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Ждём, пока Chrome запустится
        await asyncio.sleep(2)
        
        # 2. Подключаем Veil к запущенному Chrome через CDP
        from veilbrowser import Browser, Fingerprint
        
        browser_instance = await Browser.connect("http://127.0.0.1:9222")
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: http://127.0.0.1:9222\n"
            f"🛡️ Режим: антидетект\n"
            f"🆔 PID Chrome: {chrome_process.pid}\n\n"
            f"Используй /check для проверки"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю браузер...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        page = await browser_instance.new_page()
        await page.goto("https://bot.sannysoft.com")
        await asyncio.sleep(3)
        
        screenshot = await page.screenshot()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Проверка браузера"
        )
        
        webdriver = await page.evaluate("navigator.webdriver")
        
        if webdriver is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• navigator.webdriver = `{webdriver}`\n\n"
            f"💡 Если `false` — всё работает!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика Veil**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    
    if CHROME_PATH:
        report += f"• Путь Chrome: `{CHROME_PATH}`\n"
    
    if chrome_process:
        report += f"• PID Chrome: `{chrome_process.pid}`\n"
    
    if not VEIL_OK:
        report += "\n💡 Установи Veil:\n"
        report += "`pip install git+https://github.com/acunningham-ship-it/veilbrowser.git#subdirectory=python`"
    
    if not CHROME_PATH:
        report += "\n\n❌ Chrome не найден! Установи в Dockerfile:\n"
        report += "```dockerfile\nRUN apt-get install -y chromium\n```"
    
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
    
    logger.info("🤖 Veil бот запущен!")
    logger.info("📋 Команды: /start_veil, /check, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()