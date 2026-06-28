import os
import sys
import subprocess
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# Свежие куки
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "gt", "value": "2071329406237220892", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": ".I7b6GGmlN4fNcwOMuw9lT0dsT0ARfcIVwJt0bKVn1A-1782678389.549309-1.0.1.1-ZyWyQlXJpxNQRq6_2VYG2dr8Gz2iv_dZ2DrW2mnM.xR8yrtzsdhU310hzPoDkIQZYC6QGWKef5dCUOQQKZdp5_AmnVQS5zZ1p67ydtzPrydFxyV6zl740zd69v0Xs3JC", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"}
]

browser_data = None

def install_playwright_browser():
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    if os.path.exists(browser_path):
        print("✅ Браузер уже установлен")
        return True
    print("⏳ Устанавливаю браузер Chromium...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
        print("✅ Браузер успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки браузера: {e}")
        return False

install_playwright_browser()

async def get_browser():
    global browser_data
    
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
    
    if browser_data:
        try:
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox']
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720}
    )
    page = await context.new_page()
    await stealth_async(page)
    
    browser_data = {
        'playwright': p,
        'browser': browser,
        'context': context,
        'page': page
    }
    
    return browser_data

async def close_browser():
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с браузером Playwright\n\n"
        "Доступные команды:\n"
        "/go <url> - открыть сайт\n"
        "/xlogin - вход в X.com\n"
        "/screen - скриншот\n"
        "/status - состояние браузера\n"
        "/stats - статистика\n"
        "/close - закрыть браузер"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await msg.edit_text(f"✅ Открыл: {url}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Добавляем куки
        await browser['context'].add_cookies(COOKIES)
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=15000)
        
        # Проверяем авторизацию
        is_logged_in = await page.evaluate('!!document.querySelector("[data-testid=primaryColumn]")')
        title = await page.title()
        
        await msg.edit_text(
            f"✅ Зашёл в X.com!\n"
            f"📌 Заголовок: {title[:60] if title else 'Нет заголовка'}\n"
            f"🔐 Авторизация: {'✅' if is_logged_in else '❌'}"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(full_page=True)
        
        await msg.delete()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот текущей страницы"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверка браузера...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        url = await page.url
        title = await page.title()
        
        await msg.edit_text(
            f"✅ Браузер работает!\n"
            f"📌 Страница: {title[:40] if title else 'Нет заголовка'}\n"
            f"🔗 URL: {url[:50]}"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    installed = os.path.exists(browser_path)
    
    is_open = "❌"
    url = "Нет"
    if browser_data:
        try:
            page = browser_data['page']
            url = await page.url
            is_open = "✅"
        except:
            is_open = "❌ (закрыт)"
    
    await update.message.reply_text(
        f"📊 Статистика\n\n"
        f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"🌐 Браузер: {'✅' if installed else '❌'}\n"
        f"📂 Браузер открыт: {is_open}\n"
        f"🔗 Текущий URL: {url[:50]}\n"
        f"🍪 Куки: {len(COOKIES)} шт."
    )

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    
    await msg.edit_text("✅ Браузер закрыт!")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("close", close))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()