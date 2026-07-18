import os
import subprocess
import time
import httpx
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ========== Управление браузером ==========

def check_browser():
    """Проверяет браузер через HTTP-запрос"""
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version", timeout=3.0)
            return response.status_code == 200
    except:
        return False

def ensure_browser():
    """Запускает браузер и ждет готовности"""
    chrome_path = "/usr/bin/chromium"
    
    if check_browser():
        print("✅ Браузер уже запущен")
        return True
    
    print("🔄 Запускаем браузер...")
    
    cmd = [
        chrome_path,
        "--headless",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--remote-debugging-port=9222",
        "--remote-debugging-address=0.0.0.0",
        "--user-data-dir=/tmp/chrome-profile",
        "about:blank"
    ]
    
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    for i in range(30):
        time.sleep(1)
        if check_browser():
            print(f"✅ Браузер запущен! (через {i+1} сек)")
            return True
        print(f"   Ожидание... {i+1}/30")
    
    print("❌ Не удалось запустить браузер")
    return False

# ========== Команды бота ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и проверка браузера"""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    await update.message.reply_text(
        f"🤖 Бот с browser-harness запущен!\n"
        f"Браузер: {status}\n\n"
        f"Доступные команды:\n"
        f"/get_title <url> - получить заголовок страницы\n"
        f"/screenshot <url> - сделать скриншот\n"
        f"/search <query> - поиск в Google\n"
        f"/status - статус браузера"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса браузера"""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    await update.message.reply_text(f"Браузер: {status}")

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить заголовок страницы"""
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        from browser_harness import Browser
        from browser_harness.utils import connect_to_browser
        
        # Подключаемся к существующему браузеру
        browser = await connect_to_browser("http://localhost:9222")
        
        # Открываем страницу
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        
        title = await page.title()
        await page.close()
        
        await update.message.reply_text(
            f"✅ Заголовок: {title}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать скриншот страницы"""
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        from browser_harness import Browser
        from browser_harness.utils import connect_to_browser
        import base64
        from io import BytesIO
        
        browser = await connect_to_browser("http://localhost:9222")
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        
        # Делаем скриншот
        screenshot_bytes = await page.screenshot(full_page=True)
        await page.close()
        
        # Отправляем фото
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"Скриншот {url}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def search_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск в Google"""
    if not context.args:
        await update.message.reply_text("❗ Введите запрос: /search python programming")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        from browser_harness import Browser
        from browser_harness.utils import connect_to_browser
        
        browser = await connect_to_browser("http://localhost:9222")
        page = await browser.new_page()
        
        # Идем в Google
        await page.goto("https://www.google.com")
        
        # Вводим запрос
        search_input = await page.wait_for_selector('input[name="q"]')
        await search_input.fill(query)
        await search_input.press("Enter")
        
        # Ждем результаты
        await page.wait_for_selector('h3', timeout=5000)
        
        # Получаем первые 5 результатов
        results = await page.query_selector_all('h3')
        titles = []
        for i, result in enumerate(results[:5]):
            title = await result.text_content()
            if title:
                titles.append(f"{i+1}. {title}")
        
        await page.close()
        
        if titles:
            response = "🔍 Результаты поиска:\n\n" + "\n".join(titles)
        else:
            response = "❌ Результатов не найдено"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ========== Запуск ==========

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    # Запускаем браузер
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("search", search_google))
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды: /start, /status, /get_title, /screenshot, /search")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()