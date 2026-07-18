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

# ========== Работа с browser-harness ==========

async def get_browser():
    """Подключается к браузеру через CDP"""
    try:
        # Пробуем разные способы импорта
        try:
            from browser_harness.cdp import CDPClient
            client = CDPClient("http://localhost:9222")
            return client
        except ImportError:
            pass
        
        try:
            from browser_harness.core import BrowserHarness
            harness = BrowserHarness("http://localhost:9222")
            return harness
        except ImportError:
            pass
        
        # Самый простой вариант - через websocket напрямую
        import websockets
        import json
        
        # Получаем WebSocket URL из /json/version
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version")
            data = response.json()
            ws_url = data.get("webSocketDebuggerUrl")
            
            if ws_url:
                ws = await websockets.connect(ws_url)
                return ws
        
        raise Exception("Не удалось подключиться к браузеру")
        
    except Exception as e:
        raise Exception(f"Ошибка подключения к браузеру: {str(e)}")

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
        # Используем asyncio.subprocess для выполнения команды browser-harness
        import asyncio
        
        # Временный скрипт для получения заголовка
        script = f"""
import asyncio
import json
import websockets
import httpx

async def get_title():
    try:
        # Получаем WebSocket URL
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version")
            data = response.json()
            ws_url = data.get("webSocketDebuggerUrl")
        
        if not ws_url:
            return "Ошибка: не найден WebSocket URL"
        
        # Подключаемся
        async with websockets.connect(ws_url) as ws:
            # Создаем новую страницу
            await ws.send(json.dumps({{"id": 1, "method": "Target.createTarget", "params": {{"url": "about:blank"}}}}))
            response = await ws.recv()
            result = json.loads(response)
            target_id = result.get("result", {{}}).get("targetId")
            
            if not target_id:
                return "Ошибка: не удалось создать страницу"
            
            # Получаем WebSocket URL для страницы
            await ws.send(json.dumps({{"id": 2, "method": "Target.getTargetInfo", "params": {{"targetId": target_id}}}}))
            response = await ws.recv()
            result = json.loads(response)
            page_ws_url = result.get("result", {{}}).get("targetInfo", {{}}).get("webSocketDebuggerUrl")
            
            if not page_ws_url:
                return "Ошибка: не найден URL страницы"
            
            # Подключаемся к странице
            async with websockets.connect(page_ws_url) as page_ws:
                # Включаем Page
                await page_ws.send(json.dumps({{"id": 3, "method": "Page.enable"}}))
                await page_ws.recv()
                
                # Навигация
                await page_ws.send(json.dumps({{"id": 4, "method": "Page.navigate", "params": {{"url": "{url}"}}}}))
                await page_ws.recv()
                
                # Получаем заголовок
                await page_ws.send(json.dumps({{"id": 5, "method": "Runtime.evaluate", "params": {{"expression": "document.title"}}}}))
                response = await page_ws.recv()
                result = json.loads(response)
                title = result.get("result", {{}}).get("result", {{}}).get("value", "Без заголовка")
                
                # Закрываем страницу
                await ws.send(json.dumps({{"id": 6, "method": "Target.closeTarget", "params": {{"targetId": target_id}}}}))
                
                return title
    except Exception as e:
        return f"Ошибка: {{str(e)}}"

if __name__ == "__main__":
    result = asyncio.run(get_title())
    print(result)
"""
        
        # Выполняем скрипт через subprocess
        process = await asyncio.create_subprocess_exec(
            "python3", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if stdout:
            title = stdout.decode().strip()
            await update.message.reply_text(f"✅ Заголовок: {title}")
        else:
            error = stderr.decode().strip() if stderr else "Неизвестная ошибка"
            await update.message.reply_text(f"❌ Ошибка: {error}")
            
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
        import asyncio
        import base64
        
        # Простой скрипт для скриншота через CDP
        script = f"""
import asyncio
import json
import websockets
import httpx
import base64

async def take_screenshot():
    try:
        # Получаем WebSocket URL
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version")
            data = response.json()
            ws_url = data.get("webSocketDebuggerUrl")
        
        if not ws_url:
            return None, "Не найден WebSocket URL"
        
        async with websockets.connect(ws_url) as ws:
            # Создаем новую страницу
            await ws.send(json.dumps({{"id": 1, "method": "Target.createTarget", "params": {{"url": "about:blank"}}}}))
            response = await ws.recv()
            result = json.loads(response)
            target_id = result.get("result", {{}}).get("targetId")
            
            if not target_id:
                return None, "Не удалось создать страницу"
            
            # Получаем WebSocket URL для страницы
            await ws.send(json.dumps({{"id": 2, "method": "Target.getTargetInfo", "params": {{"targetId": target_id}}}}))
            response = await ws.recv()
            result = json.loads(response)
            page_ws_url = result.get("result", {{}}).get("targetInfo", {{}}).get("webSocketDebuggerUrl")
            
            if not page_ws_url:
                return None, "Не найден URL страницы"
            
            async with websockets.connect(page_ws_url) as page_ws:
                # Включаем Page
                await page_ws.send(json.dumps({{"id": 3, "method": "Page.enable"}}))
                await page_ws.recv()
                
                # Навигация
                await page_ws.send(json.dumps({{"id": 4, "method": "Page.navigate", "params": {{"url": "{url}"}}}}))
                await page_ws.recv()
                
                # Ждем загрузки
                await asyncio.sleep(2)
                
                # Делаем скриншот
                await page_ws.send(json.dumps({{"id": 5, "method": "Page.captureScreenshot", "params": {{"format": "png"}}}}))
                response = await page_ws.recv()
                result = json.loads(response)
                screenshot_data = result.get("result", {{}}).get("data", "")
                
                # Закрываем страницу
                await ws.send(json.dumps({{"id": 6, "method": "Target.closeTarget", "params": {{"targetId": target_id}}}}))
                
                if screenshot_data:
                    return base64.b64decode(screenshot_data), None
                else:
                    return None, "Не удалось сделать скриншот"
    except Exception as e:
        return None, str(e)

if __name__ == "__main__":
    data, error = asyncio.run(take_screenshot())
    if error:
        print(f"ERROR: {{error}}")
    else:
        import sys
        sys.stdout.buffer.write(data)
"""
        
        # Выполняем скрипт
        process = await asyncio.create_subprocess_exec(
            "python3", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if stderr:
            error_msg = stderr.decode().strip()
            if "ERROR:" in error_msg:
                error_msg = error_msg.split("ERROR:")[1].strip()
                await update.message.reply_text(f"❌ {error_msg}")
                return
        
        if stdout:
            # Отправляем скриншот
            await update.message.reply_photo(
                photo=stdout,
                caption=f"Скриншот {url}"
            )
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
            
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
        # Получаем заголовки результатов через простой парсинг
        import re
        
        # Используем curl для получения HTML
        import asyncio
        
        # Кодируем запрос для URL
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        process = await asyncio.create_subprocess_exec(
            "curl", "-s", "-L", search_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if stdout:
            html = stdout.decode('utf-8', errors='ignore')
            
            # Ищем заголовки результатов
            # Простое извлечение текста между <h3> тегами
            titles = re.findall(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
            
            # Очищаем от HTML тегов
            clean_titles = []
            for title in titles[:5]:
                clean = re.sub(r'<[^>]+>', '', title)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if clean and len(clean) > 3:
                    clean_titles.append(clean)
            
            if clean_titles:
                response = "🔍 Результаты поиска:\n\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(clean_titles)])
            else:
                response = "❌ Результатов не найдено"
            
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ Не удалось выполнить поиск")
            
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