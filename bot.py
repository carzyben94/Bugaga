import os
import logging
import threading
import time
import requests
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# Настройка логирования
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Flask
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

# Keep-alive
def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ БРАУЗЕР ============

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1920, "height": 1080}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

async def get_browser_page():
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-accelerated-2d-canvas',
            '--disable-pdf-viewer',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--mute-audio',
            '--no-first-run',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
    )
    
    await context.set_geolocation({"latitude": 55.7558, "longitude": 37.6173})
    await context.grant_permissions(["geolocation"])
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
        window.chrome = {
            runtime: {}
        };
    """)
    
    return page, browser, context

async def take_screenshot(url: str) -> bytes:
    page, browser, context = await get_browser_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(resolve => setTimeout(resolve, 1000));
            window.scrollTo(0, 0);
        """)
        
        await page.wait_for_timeout(1000)
        
        screenshot = await page.screenshot(full_page=True, type="png")
        return screenshot
    
    except Exception as e:
        print(f"❌ Ошибка скриншота: {e}")
        try:
            screenshot = await page.screenshot(full_page=True, type="png")
            return screenshot
        except:
            return None
    
    finally:
        await browser.close()

# ============ КОМАНДЫ БОТА ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "Команды:\n"
        "/open google.com - Открыть сайт и показать скриншот"
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите URL: /open google.com")
        return
    
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    
    await update.message.reply_text(f"🌐 Открываю {url}...")
    
    screenshot = await take_screenshot(url)
    
    if screenshot:
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"✅ {url}"
        )
    else:
        await update.message.reply_text("❌ Не удалось открыть страницу")

# ============ ЗАПУСК ============

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("open", open_command))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()