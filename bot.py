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
os.environ["BU_CDP_URL"] = "http://localhost:9222"

# ========== Управление браузером ==========

def check_browser():
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version", timeout=3.0)
            return response.status_code == 200
    except:
        return False

def ensure_browser():
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
        f"/status - статус браузера\n"
        f"/debug_api - диагностика API"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def debug_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диагностика API browser-harness"""
    code = """
import json
results = {}

# Пробуем new_tab как контекстный менеджер
try:
    with new_tab() as tab:
        results['with_new_tab'] = '✅ РАБОТАЕТ'
        results['tab_methods'] = [m for m in dir(tab) if not m.startswith('_')][:5]
except Exception as e:
    results['with_new_tab'] = f'❌ {str(e)[:50]}'

# Пробуем new_tab как функция
try:
    tab = new_tab()
    results['new_tab_as_function'] = '✅ РАБОТАЕТ'
    results['tab_methods_func'] = [m for m in dir(tab) if not m.startswith('_')][:5]
    tab.close()
except Exception as e:
    results['new_tab_as_function'] = f'❌ {str(e)[:50]}'

# Пробуем new_tab с URL
try:
    tab = new_tab("https://example.com")
    results['new_tab_with_url'] = '✅ РАБОТАЕТ'
    # Пробуем получить заголовок
    try:
        title = tab.title()
        results['tab.title()'] = f'✅ {title[:30]}'
    except:
        results['tab.title()'] = '❌ НЕ РАБОТАЕТ'
    tab.close()
except Exception as e:
    results['new_tab_with_url'] = f'❌ {str(e)[:50]}'

print(json.dumps(results))
"""
    stdout, stderr = await run_harness(code)
    
    msg = "🔍 Диагностика API:\n\n"
    if stdout:
        try:
            data = json.loads(stdout.strip())
            for key, value in data.items():
                msg += f"• {key}: {value}\n"
        except:
            msg += stdout
    if stderr:
        msg += f"\nОшибки: {stderr[:200]}"
    
    await update.message.reply_text(msg[:4000])

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /get_title https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        # ✅ Универсальный способ: пробуем разные варианты
        code = f"""
import json

try:
    # Способ 1: new_tab как функция с URL
    tab = new_tab("{url}")
    title = tab.title()
    print(json.dumps({{"title": title, "url": tab.url if hasattr(tab, 'url') else "{url}"}}))
    tab.close()
except Exception as e1:
    try:
        # Способ 2: new_tab как функция без URL
        tab = new_tab()
        tab.get("{url}")
        title = tab.title()
        print(json.dumps({{"title": title, "url": "{url}"}}))
        tab.close()
    except Exception as e2:
        try:
            # Способ 3: контекстный менеджер
            with new_tab() as tab:
                tab.get("{url}")
                title = tab.title()
                print(json.dumps({{"title": title, "url": "{url}"}}))
        except Exception as e3:
            print(json.dumps({{"error": f"Все способы не сработали: e1={{str(e1)[:30]}}, e2={{str(e2)[:30]}}, e3={{str(e3)[:30]}}"}}))
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        try:
            data = json.loads(stdout.strip())
            if "error" in data:
                await update.message.reply_text(f"❌ {data['error']}")
            else:
                title = data.get("title", "Без заголовка")
                await update.message.reply_text(f"✅ Заголовок: {title}")
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
        # ✅ Универсальный способ для скриншота
        code = f"""
import base64
import json

try:
    # Пробуем получить скриншот
    tab = new_tab("{url}")
    screenshot_bytes = tab.screenshot()
    print(base64.b64encode(screenshot_bytes).decode())
    tab.close()
except Exception as e1:
    try:
        # Альтернативный способ
        tab = new_tab()
        tab.get("{url}")
        screenshot_bytes = tab.screenshot()
        print(base64.b64encode(screenshot_bytes).decode())
        tab.close()
    except Exception as e2:
        print(json.dumps({{"error": f"Ошибка скриншота: e1={{str(e1)[:30]}}, e2={{str(e2)[:30]}}"}}))
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        # Проверяем, не вернулась ли ошибка JSON
        try:
            data = json.loads(stdout.strip())
            if "error" in data:
                await update.message.reply_text(f"❌ {data['error']}")
                return
        except json.JSONDecodeError:
            pass  # Это не JSON, значит это base64
        
        # Ищем base64 строку
        match = re.search(r'(iVBORw0KGgo[A-Za-z0-9+/=]+)', stdout)
        
        if not match:
            match = re.search(r'([A-Za-z0-9+/=]{100,})', stdout)
        
        if match:
            try:
                image_data = base64.b64decode(match.group(1))
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
            preview = stdout[:200].replace('\n', ' ').strip()
            await update.message.reply_text(
                f"❌ Не удалось извлечь скриншот\n"
                f"Ответ: {preview[:50]}..."
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== Запуск ==========

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug_api", debug_api))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды: /start, /status, /debug_api, /get_title, /screenshot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()