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

# Куки в компактном формате
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178232552081152335", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178232552081152335", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178232552081152335", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_WrN9cfSG2zvM3RbiT1ZEkw==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "9437c2dd7e6dd3b655cd4166f1fe303365f56d91", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "6348cd308326bbc75e48654d2a7488c58d9d34f10712b0f1b3d7bde9e67a028c46de54fbbbace15ab6a518f71b27945510c1dc91b2ef7c9360aaf009883b0c5e326f4196c02e32c930a7c2222c4af9ff", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "Q_7xL8xOeTr7wEs9IKrku6FvBYFgQ66n2aAnMu3y1P4-1782677214.6550717-1.0.1.1-OZkEIr0AmPv26VE8f6.2K9ZLininp7rxWXyurqH.Nd4rkkGYHIGQThsakV2sgDqDsQ_3w7c7tSuHCk_J.QnG82ww8SOFtvgZBlyzDvaP5_U3zdSt85sRSMasmOtZm74q", "domain": ".x.com", "path": "/"}
]

# Храним браузер и страницу глобально
browser_instance = None
page_instance = None

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с браузером Playwright\n\n"
        "Доступные команды:\n"
        "/go <url> - открыть любой сайт\n"
        "/xlogin - зайти в X.com\n"
        "/screen - скриншот текущей страницы\n"
        "/status - проверить браузер\n"
        "/stats - статистика"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, page_instance
    
    # Проверяем, есть ли URL
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        from playwright.async_api import async_playwright
        
        # Если браузер уже запущен, используем его
        if browser_instance and page_instance:
            try:
                await page_instance.goto(url, wait_until='networkidle')
                await msg.edit_text(f"✅ Открыл: {url}")
                return
            except:
                browser_instance = None
                page_instance = None
        
        # Создаём новый браузер
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context_browser = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context_browser.new_page()
            
            await page.goto(url, wait_until='networkidle')
            
            # Сохраняем браузер и страницу
            browser_instance = browser
            page_instance = page
            
            await msg.edit_text(f"✅ Открыл: {url}")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, page_instance
    
    msg = await update.message.reply_text("⏳ Захожу в X.com с куками...")
    
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
        
        # Закрываем старый браузер если есть
        if browser_instance:
            try:
                await browser_instance.close()
            except:
                pass
            browser_instance = None
            page_instance = None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            await context.add_cookies(COOKIES)
            
            page = await context.new_page()
            await stealth_async(page)
            
            await page.goto('https://x.com', wait_until='networkidle')
            
            # Проверяем авторизацию
            is_logged_in = await page.evaluate('!!document.querySelector("[data-testid=primaryColumn]")')
            title = await page.title()
            
            # Сохраняем браузер и страницу
            browser_instance = browser
            page_instance = page
            
            await msg.edit_text(
                f"✅ Зашёл в X.com!\n"
                f"📌 Заголовок: {title[:60]}\n"
                f"🔐 Авторизация: {'✅' if is_logged_in else '❌'}"
            )
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global page_instance, browser_instance
    
    if not page_instance:
        await update.message.reply_text("❌ Сначала открой страницу: /go или /xlogin")
        return
    
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        # Делаем скриншот
        screenshot = await page_instance.screenshot(full_page=True)
        
        # Отправляем фото в чат
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот текущей страницы"
        )
        
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, page_instance
    
    msg = await update.message.reply_text("⏳ Проверка браузера...")
    
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
        
        # Проверяем, открыт ли браузер
        if browser_instance and page_instance:
            try:
                # Пробуем получить URL
                url = await page_instance.url
                title = await page_instance.title()
                
                await msg.edit_text(
                    f"✅ Браузер работает!\n"
                    f"📌 Страница: {title[:40]}\n"
                    f"🔗 URL: {url[:50]}"
                )
                return
            except:
                browser_instance = None
                page_instance = None
        
        # Создаём новый браузер для проверки
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page()
            await stealth_async(page)
            await page.goto('https://x.com', wait_until='networkidle')
            title = await page.title()
            await browser.close()
            
            await msg.edit_text(
                f"✅ Браузер работает!\n"
                f"📌 Заголовок: {title[:60]}"
            )
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, page_instance
    
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    installed = os.path.exists(browser_path)
    
    # Проверяем, открыт ли браузер
    is_open = "❌"
    url = "Нет"
    if browser_instance and page_instance:
        try:
            url = await page_instance.url
            is_open = "✅"
        except:
            is_open = "❌"
    
    await update.message.reply_text(
        f"📊 Статистика\n\n"
        f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"🌐 Браузер: {'✅' if installed else '❌'}\n"
        f"📂 Браузер открыт: {is_open}\n"
        f"🔗 Текущий URL: {url[:50]}\n"
        f"🍪 Куки: {len(COOKIES)} шт."
    )

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()