import os
import subprocess
import asyncio
import json
import re
import time
import base64
import httpx
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
os.environ["BU_CDP_URL"] = "http://localhost:9222"

# ============================================================
# 1. УПРАВЛЕНИЕ БРАУЗЕРОМ
# ============================================================

def check_browser():
    """Проверяет, запущен ли браузер и слушает ли порт 9222."""
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version", timeout=3.0)
            return response.status_code == 200
    except:
        return False

def ensure_browser():
    """Запускает Chromium в headless-режиме, если он ещё не запущен."""
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

# ============================================================
# 2. РАБОТА С CLI BROWSER-HARNESS
# ============================================================

async def run_harness(code: str) -> tuple[str, str]:
    """Выполняет Python-код через CLI browser-harness."""
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

# ============================================================
# 3. ПРЯМОЙ CDP (ЗАПАСНОЙ СПОСОБ ДЛЯ СКРИНШОТОВ)
# ============================================================

async def screenshot_cdp_direct(url: str) -> bytes:
    """
    Делает скриншот через прямое подключение к Chrome DevTools Protocol.
    Обходит browser-harness CLI.
    """
    try:
        # 1. Получаем WebSocket URL для подключения к браузеру
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version")
            data = response.json()
            ws_url = data.get("webSocketDebuggerUrl")
            if not ws_url:
                raise Exception("Не удалось получить WebSocket URL от браузера")
        
        # 2. Подключаемся к браузеру
        async with websockets.connect(ws_url) as browser_ws:
            # 3. Создаем новую вкладку
            await browser_ws.send(json.dumps({
                "id": 1,
                "method": "Target.createTarget",
                "params": {"url": url}
            }))
            create_response = await browser_ws.recv()
            target_id = json.loads(create_response).get("result", {}).get("targetId")
            if not target_id:
                raise Exception("Не удалось создать вкладку")
            
            # 4. Получаем WebSocket URL для созданной вкладки
            await browser_ws.send(json.dumps({
                "id": 2,
                "method": "Target.getTargetInfo",
                "params": {"targetId": target_id}
            }))
            info_response = await browser_ws.recv()
            page_ws_url = json.loads(info_response).get("result", {}).get("targetInfo", {}).get("webSocketDebuggerUrl")
            if not page_ws_url:
                raise Exception("Не удалось получить URL для вкладки")
            
            # 5. Подключаемся к вкладке
            async with websockets.connect(page_ws_url) as page_ws:
                # Включаем необходимые домены
                await page_ws.send(json.dumps({"id": 3, "method": "Page.enable"}))
                await page_ws.recv()
                
                # Ждем загрузки страницы
                await asyncio.sleep(3)
                
                # 6. Делаем скриншот
                await page_ws.send(json.dumps({
                    "id": 4,
                    "method": "Page.captureScreenshot",
                    "params": {"format": "png"}
                }))
                screenshot_response = await page_ws.recv()
                screenshot_data = json.loads(screenshot_response).get("result", {}).get("data")
                if not screenshot_data:
                    raise Exception("Не удалось получить данные скриншота")
                
                # 7. Закрываем вкладку
                await browser_ws.send(json.dumps({
                    "id": 5,
                    "method": "Target.closeTarget",
                    "params": {"targetId": target_id}
                }))
                await browser_ws.recv()
                
                # 8. Возвращаем декодированные байты изображения
                return base64.b64decode(screenshot_data)
                
    except Exception as e:
        raise Exception(f"Ошибка при создании скриншота через CDP: {str(e)}")

# ============================================================
# 4. ДИАГНОСТИКА
# ============================================================

async def debug_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диагностика функций скриншота в browser-harness."""
    code = """
import base64
import json

results = {}

# Проверяем capture_screenshot
try:
    new_tab("https://example.com")
    wait_for_load()
    data = capture_screenshot()
    results['capture_screenshot'] = f'✅ работает, размер: {len(data)} байт'
except Exception as e:
    results['capture_screenshot'] = f'❌ Ошибка: {str(e)[:50]}'

# Проверяем screenshot (возможно другое имя)
try:
    data = screenshot()
    results['screenshot()'] = f'✅ работает, размер: {len(data)} байт'
except Exception as e:
    results['screenshot()'] = f'❌ Ошибка: {str(e)[:50]}'

# Проверяем tab.screenshot() (если new_tab возвращает объект)
try:
    tab = new_tab("https://example.com")
    data = tab.screenshot()
    results['tab.screenshot()'] = f'✅ работает, размер: {len(data)} байт'
except Exception as e:
    results['tab.screenshot()'] = f'❌ Ошибка: {str(e)[:50]}'

print(json.dumps(results))
"""
    stdout, stderr = await run_harness(code)
    
    msg = "🔍 Диагностика скриншотов:\n\n"
    if stdout:
        try:
            data = json.loads(stdout.strip())
            for key, value in data.items():
                msg += f"• {key}: {value}\n"
        except:
            msg += stdout
    if stderr:
        msg += f"\nОшибки CLI: {stderr[:200]}"
    
    await update.message.reply_text(msg[:4000])

# ============================================================
# 5. КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение со списком команд."""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    await update.message.reply_text(
        f"🤖 Бот с browser-harness запущен!\n"
        f"Браузер: {status}\n\n"
        f"Доступные команды:\n"
        f"/get_title <url> - получить заголовок страницы\n"
        f"/screenshot <url> - сделать скриншот (автовыбор способа)\n"
        f"/status - статус браузера и CLI\n"
        f"/debug_screenshot - диагностика API скриншотов"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус браузера и CLI."""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
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
    """Получает заголовок страницы через browser-harness."""
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        code = f"""
import json
new_tab("{url}")
wait_for_load()
info = page_info()
print(json.dumps(info))
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        try:
            data = json.loads(stdout.strip())
            title = data.get("title", "Без заголовка")
            await update.message.reply_text(f"✅ Заголовок: {title}")
        except json.JSONDecodeError:
            await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Делает скриншот страницы.
    Сначала пробует browser-harness, при ошибке переключается на прямой CDP.
    """
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        # ПРОБУЕМ СПОСОБ 1: capture_screenshot() через browser-harness
        code = f"""
import base64
new_tab("{url}")
wait_for_load()
try:
    data = capture_screenshot()
    print('CAPTURE:', base64.b64encode(data).decode())
except Exception as e:
    print('ERROR:', str(e))
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        # Проверяем, есть ли ошибка в выводе
        if stdout.startswith('ERROR:'):
            error_msg = stdout.split('ERROR:', 1)[1].strip()
            await update.message.reply_text(f"⚠️ browser-harness не справился: {error_msg[:100]}")
            await update.message.reply_text("🔄 Пробую альтернативный способ (прямой CDP)...")
            
            # ПРОБУЕМ СПОСОБ 2: Прямой CDP
            try:
                image_bytes = await screenshot_cdp_direct(url)
                await update.message.reply_photo(
                    photo=image_bytes,
                    caption=f"Скриншот {url} (через прямой CDP)"
                )
                return
            except Exception as cdp_error:
                await update.message.reply_text(f"❌ И прямой CDP не сработал: {str(cdp_error)[:200]}")
                return
        
        # Обработка успешного скриншота через browser-harness
        if stdout.startswith('CAPTURE:'):
            base64_part = stdout.split('CAPTURE:', 1)[1].strip()
            try:
                image_data = base64.b64decode(base64_part)
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
            await update.message.reply_text(f"❌ Неизвестный ответ: {stdout[:100]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 6. ЗАПУСК БОТА
# ============================================================

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    # Запускаем браузер
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug_screenshot", debug_screenshot))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды:")
    print("   /start - приветствие")
    print("   /status - статус браузера и CLI")
    print("   /debug_screenshot - диагностика API скриншотов")
    print("   /get_title <url> - получить заголовок страницы")
    print("   /screenshot <url> - сделать скриншот (автовыбор способа)")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()