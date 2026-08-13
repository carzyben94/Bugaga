import os
import sys
import asyncio
import logging
import subprocess
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# ДОБАВЛЯЕМ ЛОКАЛЬНЫЙ browser-harness
# ============================================

sys.path.insert(0, "browser-harness/src")

# ============================================
# ИМПОРТЫ BROWSER HARNESS (ТОЛЬКО ТО, ЧТО ЕСТЬ)
# ============================================

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    page_info,
    current_tab,
    capture_screenshot,
    js,
    list_tabs,
    switch_tab,
    fill_input,
    click_at_xy,
    type_text,
    press_key,
    scroll,
)
from browser_harness.admin import ensure_daemon

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
cdp_url = "http://127.0.0.1:9222"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil + browser-harness**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить браузер\n"
        "/harness - тест harness функций\n"
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
        
        # Устанавливаем переменную для browser-harness
        os.environ["BU_CDP_URL"] = cdp_url
        
        # Запускаем daemon browser-harness
        ensure_daemon()
        logger.info("✅ Daemon browser-harness запущен")
        
        from veilbrowser import Browser
        browser_instance = await Browser.connect(cdp_url)
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🆔 PID: {chrome_process.pid}\n\n"
            f"Используй /check или /harness для проверки"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю браузер через harness...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        await new_tab()
        await goto_url("https://bot.sannysoft.com")
        await wait_for_load()
        
        screenshot = await capture_screenshot()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Проверка через harness"
        )
        
        result = await js("""
            () => ({
                webdriver: navigator.webdriver,
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                languages: navigator.languages
            })
        """)
        
        if result.get('webdriver') is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• webdriver: `{result.get('webdriver')}`\n"
            f"• platform: `{result.get('platform')}`\n"
            f"• languages: `{', '.join(result.get('languages', [])[:2])}`\n\n"
            f"💡 Если `false` — всё работает!"
        )
        
        await close_tab()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def test_harness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест browser-harness через helpers"""
    await update.message.reply_text("🧪 Тестирую browser-harness...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        report = "🧪 **Тест browser-harness helpers**\n\n"
        
        # 1. new_tab
        await new_tab()
        report += "✅ new_tab()\n"
        
        # 2. goto_url
        await goto_url("https://example.com")
        report += "✅ goto_url()\n"
        
        # 3. wait_for_load
        await wait_for_load()
        report += "✅ wait_for_load()\n"
        
        # 4. page_info
        info = await page_info()
        report += f"✅ page_info(): {info.get('title', 'N/A')[:30]}\n"
        
        # 5. current_tab
        tab = await current_tab()
        report += f"✅ current_tab(): {tab}\n"
        
        # 6. list_tabs
        tabs = await list_tabs()
        report += f"✅ list_tabs(): {len(tabs)} вкладок\n"
        
        # 7. js
        result = await js("navigator.userAgent")
        report += f"✅ js(): {str(result)[:40]}...\n"
        
        # 8. scroll
        await scroll(0, 100)
        report += "✅ scroll()\n"
        
        # 9. screenshot
        screenshot = await capture_screenshot()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот через harness"
        )
        
        # 10. close_tab
        await close_tab()
        report += "✅ close_tab()\n"
        
        await update.message.reply_text(report + "\n🎉 Все функции работают!")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Harness path: {'✅' if os.path.exists('browser-harness/src') else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    report += f"• BU_CDP_URL: {os.environ.get('BU_CDP_URL', '❌ не установлена')}\n"
    
    if CHROME_PATH:
        report += f"• Путь Chrome: `{CHROME_PATH}`\n"
    if chrome_process:
        report += f"• PID Chrome: `{chrome_process.pid}`\n"
    if os.path.exists('browser-harness/src'):
        report += f"• Harness: `browser-harness/src`\n"
    
    # Проверка CDP
    try:
        import requests
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            report += f"• CDP: ✅ Доступен\n"
        else:
            report += f"• CDP: ⚠️ Код {response.status_code}\n"
    except:
        report += "• CDP: ❌ Не доступен\n"
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_veil", start_veil))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("harness", test_harness))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Команды: /start_veil, /check, /harness, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()