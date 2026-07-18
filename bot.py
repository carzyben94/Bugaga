import os
import subprocess
import time
import httpx
import asyncio
import json
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ========== Универсальные импорты browser-harness ==========

def get_browser_harness():
    """Универсальная функция импорта browser-harness"""
    try:
        # Способ 1: прямой импорт
        from browser_harness import Browser, connect
        return Browser, connect
    except ImportError:
        pass
    
    try:
        # Способ 2: из core
        from browser_harness.core import BrowserHarness
        return BrowserHarness, None
    except ImportError:
        pass
    
    try:
        # Способ 3: из cdp
        from browser_harness.cdp import CDPClient
        return CDPClient, None
    except ImportError:
        pass
    
    try:
        # Способ 4: из client
        from browser_harness.client import BrowserClient
        return BrowserClient, None
    except ImportError:
        pass
    
    # Если ничего не найдено - возвращаем None
    return None, None

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

# ========== Работа с браузером через CDP ==========

async def get_page_cdp():
    """Подключается к браузеру через CDP и возвращает WebSocket"""
    try:
        # Получаем WebSocket URL
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version")
            data = response.json()
            ws_url = data.get("webSocketDebuggerUrl")
        
        if not ws_url:
            raise Exception("Не найден WebSocket URL")
        
        # Подключаемся
        ws = await websockets.connect(ws_url)
        return ws
    except Exception as e:
        raise Exception(f"Ошибка подключения к браузеру: {str(e)}")

async def execute_in_browser(script):
    """Выполняет JavaScript в браузере и возвращает результат"""
    try:
        ws = await get_page_cdp()
        
        # Создаем новую страницу
        await ws.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": "about:blank"}
        }))
        response = await ws.recv()
        result = json.loads(response)
        target_id = result.get("result", {}).get("targetId")
        
        if not target_id:
            await ws.close()
            raise Exception("Не удалось создать страницу")
        
        # Получаем WebSocket URL для страницы
        await ws.send(json.dumps({
            "id": 2,
            "method": "Target.getTargetInfo",
            "params": {"targetId": target_id}
        }))
        response = await ws.recv()
        result = json.loads(response)
        page_ws_url = result.get("result", {}).get("targetInfo", {}).get("webSocketDebuggerUrl")
        
        if not page_ws_url:
            await ws.close()
            raise Exception("Не найден URL страницы")
        
        # Подключаемся к странице
        page_ws = await websockets.connect(page_ws_url)
        
        # Включаем необходимые домены
        await page_ws.send(json.dumps({"id": 3, "method": "Page.enable"}))
        await page_ws.recv()
        await page_ws.send(json.dumps({"id": 4, "method": "Runtime.enable"}))
        await page_ws.recv()
        
        # Выполняем скрипт
        await page_ws.send(json.dumps({
            "id": 5,
            "method": "Runtime.evaluate",
            "params": {"expression": script}
        }))
        response = await page_ws.recv()
        result = json.loads(response)
        
        # Закрываем страницу
        await page_ws.close()
        await ws.send(json.dumps({
            "id": 6,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id}
        }))
        await ws.close()
        
        # Извлекаем результат
        result_data = result.get("result", {}).get("result", {})
        return result_data.get("value", "Без результата")
        
    except Exception as e:
        raise Exception(f"Ошибка выполнения: {str(e)}")

# ========== Команды бота ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и проверка браузера"""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    # Проверяем доступность browser-harness
    BrowserClass, _ = get_browser_harness()
    harness_status = "✅ установлен" if BrowserClass else "❌ не найден"
    
    await update.message.reply_text(
        f"🤖 Бот с browser-harness запущен!\n"
        f"Браузер: {status}\n"
        f"browser-harness: {harness_status}\n\n"
        f"Доступные команды:\n"
        f"/get_title <url> - получить заголовок страницы\n"
        f"/screenshot <url> - сделать скриншот\n"
        f"/search <query> - поиск в Google\n"
        f"/status - статус браузера\n"
        f"/test_harness - тест browser-harness"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса браузера"""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    BrowserClass, _ = get_browser_harness()
    harness_status = "✅ установлен" if BrowserClass else "❌ не найден"
    
    await update.message.reply_text(
        f"Браузер: {status}\n"
        f"browser-harness: {harness_status}"
    )

async def test_harness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирует импорт browser-harness"""
    try:
        BrowserClass, ConnectFunc = get_browser_harness()
        
        if BrowserClass:
            await update.message.reply_text(
                f"✅ browser-harness найден!\n"
                f"Класс: {BrowserClass.__name__}\n"
                f"Пробую создать экземпляр..."
            )
            
            try:
                # Пробуем создать экземпляр
                if ConnectFunc:
                    browser = ConnectFunc("http://localhost:9222")
                else:
                    browser = BrowserClass("http://localhost:9222")
                
                await update.message.reply_text(
                    f"✅ Экземпляр создан успешно!\n"
                    f"Тип: {type(browser).__name__}"
                )
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка создания: {str(e)}")
        else:
            await update.message.reply_text("❌ browser-harness не найден в системе")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка теста: {str(e)}")

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить заголовок страницы"""
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        # Пробуем использовать browser-harness сначала
        BrowserClass, ConnectFunc = get_browser_harness()
        
        if BrowserClass:
            try:
                # Пытаемся использовать browser-harness
                if ConnectFunc:
                    browser = ConnectFunc("http://localhost:9222")
                else:
                    browser = BrowserClass("http://localhost:9222")
                
                # Пробуем получить заголовок через browser-harness
                if hasattr(browser, 'get_title'):
                    title = await browser.get_title(url)
                elif hasattr(browser, 'get'):
                    page = await browser.get(url)
                    title = await page.title()
                else:
                    raise Exception("Неизвестный API browser-harness")
                
                await update.message.reply_text(f"✅ Заголовок: {title}")
                return
                
            except Exception as e:
                print(f"browser-harness не сработал: {e}, пробуем CDP...")
        
        # Если browser-harness не сработал - используем прямой CDP
        script = f"""
            (async function() {{
                window.location.href = '{url}';
                await new Promise(resolve => setTimeout(resolve, 3000));
                return document.title || 'Без заголовка';
            }})()
        """
        
        title = await execute_in_browser(script)
        await update.message.reply_text(f"✅ Заголовок: {title}")
        
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
        # Используем CDP для скриншота
        ws = await get_page_cdp()
        
        # Создаем новую страницу
        await ws.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": url}
        }))
        response = await ws.recv()
        result = json.loads(response)
        target_id = result.get("result", {}).get("targetId")
        
        if not target_id:
            await ws.close()
            raise Exception("Не удалось создать страницу")
        
        # Получаем WebSocket URL для страницы
        await ws.send(json.dumps({
            "id": 2,
            "method": "Target.getTargetInfo",
            "params": {"targetId": target_id}
        }))
        response = await ws.recv()
        result = json.loads(response)
        page_ws_url = result.get("result", {}).get("targetInfo", {}).get("webSocketDebuggerUrl")
        
        if not page_ws_url:
            await ws.close()
            raise Exception("Не найден URL страницы")
        
        # Подключаемся к странице
        page_ws = await websockets.connect(page_ws_url)
        
        # Включаем Page
        await page_ws.send(json.dumps({"id": 3, "method": "Page.enable"}))
        await page_ws.recv()
        
        # Ждем загрузки
        await asyncio.sleep(3)
        
        # Делаем скриншот
        await page_ws.send(json.dumps({
            "id": 4,
            "method": "Page.captureScreenshot",
            "params": {"format": "png"}
        }))
        response = await page_ws.recv()
        result = json.loads(response)
        screenshot_data = result.get("result", {}).get("data", "")
        
        # Закрываем все
        await page_ws.close()
        await ws.send(json.dumps({
            "id": 5,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id}
        }))
        await ws.close()
        
        if screenshot_data:
            import base64
            image_bytes = base64.b64decode(screenshot_data)
            await update.message.reply_photo(
                photo=image_bytes,
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
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        # Используем CDP для поиска
        script = f"""
            (async function() {{
                window.location.href = '{search_url}';
                await new Promise(resolve => setTimeout(resolve, 5000));
                
                const titles = document.querySelectorAll('h3');
                const results = [];
                for (let i = 0; i < Math.min(5, titles.length); i++) {{
                    const text = titles[i].textContent.trim();
                    if (text) results.push(text);
                }}
                return results.join('\\n') || 'Результатов не найдено';
            }})()
        """
        
        results = await execute_in_browser(script)
        
        if results and results != "Результатов не найдено":
            response = "🔍 Результаты поиска:\n\n" + "\n".join([f"{i+1}. {r}" for i, r in enumerate(results.split('\n'))])
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
    app.add_handler(CommandHandler("test_harness", test_harness))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("search", search_google))
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды: /start, /status, /test_harness, /get_title, /screenshot, /search")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()