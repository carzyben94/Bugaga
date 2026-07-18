import os
import subprocess
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ========== Управление браузером ==========

def check_browser():
    """Проверяет браузер через HTTP-запрос"""
    try:
        import httpx
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
    
    import time
    for i in range(30):
        time.sleep(1)
        if check_browser():
            print(f"✅ Браузер запущен! (через {i+1} сек)")
            return True
        print(f"   Ожидание... {i+1}/30")
    
    print("❌ Не удалось запустить браузер")
    return False

# ========== Работа через CLI browser-harness ==========

async def run_harness(code: str) -> tuple[str, str]:
    """Выполняет Python-код через browser-harness CLI"""
    process = await asyncio.create_subprocess_exec(
        "browser-harness",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate(code.encode())
    return stdout.decode(), stderr.decode()

# ========== Команды бота ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    await update.message.reply_text(
        f"🤖 Бот с browser-harness запущен!\n"
        f"Браузер: {status}\n\n"
        f"Доступные команды:\n"
        f"/get_title <url> - получить заголовок страницы\n"
        f"/screenshot <url> - сделать скриншот\n"
        f"/status - статус браузера"
    )

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        code = f"""
new_tab("{url}")
print(page_info())
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка: {stderr[:200]}")
            return
        
        # Парсим вывод page_info()
        import re
        # page_info() выдает JSON с информацией о странице
        try:
            import json
            # Ищем JSON в выводе
            match = re.search(r'\{.*\}', stdout)
            if match:
                data = json.loads(match.group())
                title = data.get("title", "Без заголовка")
                await update.message.reply_text(f"✅ Заголовок: {title}")
            else:
                await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
        except:
            await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        code = f"""
import base64
new_tab("{url}")
data = capture_screenshot()
print(data)
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка: {stderr[:200]}")
            return
        
        # Декодируем base64 в изображение
        import base64
        import re
        # Ищем base64 строку в выводе
        match = re.search(r'[A-Za-z0-9+/=]+', stdout)
        if match:
            image_data = base64.b64decode(match.group())
            await update.message.reply_photo(
                photo=image_data,
                caption=f"Скриншот {url}"
            )
        else:
            await update.message.reply_text("❌ Не удалось получить скриншот")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    # Проверяем доступность CLI
    try:
        process = await asyncio.create_subprocess_exec(
            "browser-harness", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        version = stdout.decode().strip() if stdout else "неизвестно"
        cli_status = f"✅ {version}"
    except:
        cli_status = "❌ не найден"
    
    await update.message.reply_text(
        f"Браузер: {status}\n"
        f"CLI browser-harness: {cli_status}"
    )

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    print("🚀 Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()