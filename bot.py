import os
import asyncio
import logging
import subprocess
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil Browser**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить браузер\n"
        "/diag - диагностика"
    )

async def start_veil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance
    await update.message.reply_text("🔄 Запускаю Veil...")
    
    if not VEIL_OK:
        await update.message.reply_text(
            "❌ Veil не установлен!\n"
            "Установи: pip install git+https://github.com/acunningham-ship-it/veilbrowser.git#subdirectory=python"
        )
        return
    
    try:
        from veilbrowser import Browser, Fingerprint
        
        # Правильный запуск Veil 1.3.1
        browser_instance = await Browser.launch(
            headless=True,
            fingerprint=Fingerprint.preset("linux-chrome")
        )
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: http://127.0.0.1:9222\n"
            f"🛡️ Режим: антидетект\n\n"
            f"Используй /check для проверки"
        )
        
    except TypeError as e:
        # Если fingerprint не принимается, пробуем без него
        try:
            from veilbrowser import Browser
            browser_instance = await Browser.launch(headless=True)
            await update.message.reply_text(
                f"✅ **Veil запущен!** (без fingerprint)\n\n"
                f"🔌 CDP: http://127.0.0.1:9222\n\n"
                f"Используй /check для проверки"
            )
        except Exception as e2:
            await update.message.reply_text(f"❌ Ошибка: {str(e2)[:300]}")
            
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