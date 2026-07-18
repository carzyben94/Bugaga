import os
import subprocess
import asyncio
import json
import re
import time
import base64
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
os.environ["BU_CDP_URL"] = "http://localhost:9222"  # Явно указываем браузер

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

# ========== Работа через CLI browser-harness ==========

async def run_harness(code: str) -> tuple[str, str]:
    """Выполняет Python-код через browser-harness CLI"""
    env = os.environ.copy()
    env["BU_CDP_URL"] = "http://localhost:9222"
    
    process = await asyncio.create_subprocess_exec(
        "browser-harness",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env
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

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        # Правильный скрипт для browser-harness
        code = f"""
# Открываем новую вкладку
new_tab("{url}")

# Ждем загрузки страницы
import time
time.sleep(2)

# Получаем информацию о странице
info = page_info()
print(info)
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        # Парсим JSON из вывода
        try:
            # Ищем JSON объект в выводе
            match = re.search(r'\{[^{}]*\}', stdout)
            if match:
                data = json.loads(match.group())
                title = data.get("title", "Без заголовка")
                url_page = data.get("url", url)
                width = data.get("w", "?")
                height = data.get("h", "?")
                
                await update.message.reply_text(
                    f"✅ **Заголовок:** {title}\n"
                    f"📐 **Размер:** {width}x{height}\n"
                    f"🔗 **URL:** {url_page}"
                )
            else:
                await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
        except json.JSONDecodeError:
            await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        # Правильный скрипт для скриншота
        code = f"""
# Открываем новую вкладку
new_tab("{url}")

# Ждем загрузки страницы
import time
time.sleep(3)

# Делаем скриншот
screenshot_data = capture_screenshot()

# Выводим результат
print(screenshot_data)
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        # Ищем base64 строку в выводе
        # PNG начинается с iVBOR
        match = re.search(r'(iVBORw0KGgo[A-Za-z0-9+/=]+)', stdout)
        
        if not match:
            # Пробуем найти любую длинную base64 строку
            match = re.search(r'([A-Za-z0-9+/=]{100,})', stdout)
        
        if match:
            try:
                base64_data = match.group(1)
                image_data = base64.b64decode(base64_data)
                
                if len(image_data) < 100:
                    await update.message.reply_text("❌ Получен пустой скриншот")
                    return
                
                await update.message.reply_photo(
                    photo=image_data,
                    caption=f"Скриншот {url}"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка декодирования: {str(e)[:100]}")
        else:
            # Показываем первые символы для отладки
            preview = stdout[:200].replace('\n', ' ').strip()
            await update.message.reply_text(
                f"❌ Не удалось извлечь скриншот\n"
                f"Ответ начинается с: {preview[:50]}..."
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

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
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды: /start, /status, /get_title, /screenshot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()