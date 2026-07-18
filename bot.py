import os
import subprocess
import asyncio
import json
import re
import time
import base64
import httpx
import urllib.parse
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
# 3. КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение со списком команд."""
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    await update.message.reply_text(
        f"🤖 **Бот с browser-harness запущен!**\n"
        f"Браузер: {status}\n\n"
        f"📋 **Доступные команды:**\n"
        f"/get_title <url> - получить заголовок страницы\n"
        f"/screenshot <url> - сделать скриншот\n"
        f"/search <query> - поиск в Google\n"
        f"/status - статус браузера и CLI\n"
        f"/debug_api - диагностика API"
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
        f"**Браузер:** {status}\n"
        f"**CLI browser-harness:** {cli_status}"
    )

async def debug_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диагностика API browser-harness."""
    code = """
import json
results = {}

# Проверяем все основные функции
try:
    new_tab("about:blank")
    results['new_tab'] = '✅ работает'
except Exception as e:
    results['new_tab'] = f'❌ {str(e)[:30]}'

try:
    goto_url("https://example.com")
    results['goto_url'] = '✅ работает'
except Exception as e:
    results['goto_url'] = f'❌ {str(e)[:30]}'

try:
    wait_for_load()
    results['wait_for_load'] = '✅ работает'
except Exception as e:
    results['wait_for_load'] = f'❌ {str(e)[:30]}'

try:
    info = page_info()
    results['page_info'] = f'✅ работает: {info.get("title", "no title")[:20]}'
except Exception as e:
    results['page_info'] = f'❌ {str(e)[:30]}'

try:
    data = capture_screenshot()
    results['capture_screenshot'] = f'✅ работает, размер: {len(data)} байт'
except Exception as e:
    results['capture_screenshot'] = f'❌ {str(e)[:30]}'

try:
    tabs = list_tabs()
    results['list_tabs'] = f'✅ работает, найдено: {len(tabs)}'
except Exception as e:
    results['list_tabs'] = f'❌ {str(e)[:30]}'

try:
    result = js("return document.title")
    results['js'] = f'✅ работает: {result[:20]}'
except Exception as e:
    results['js'] = f'❌ {str(e)[:30]}'

print(json.dumps(results))
"""
    stdout, stderr = await run_harness(code)
    
    msg = "🔍 **Диагностика API:**\n\n"
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
            url_page = data.get("url", url)
            width = data.get("w", "?")
            height = data.get("h", "?")
            
            await update.message.reply_text(
                f"✅ **Заголовок:** {title}\n"
                f"📐 **Размер:** {width}x{height}\n"
                f"🔗 **URL:** {url_page}"
            )
        except json.JSONDecodeError:
            await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот страницы через browser-harness."""
    if not context.args:
        await update.message.reply_text("❗ Укажите URL: /screenshot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        code = f"""
import base64
new_tab("{url}")
wait_for_load()
screenshot_data = capture_screenshot(max_dim=1800)
print(base64.b64encode(screenshot_data).decode())
"""
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        # Ищем base64 строку
        match = re.search(r'(iVBORw0KGgo[A-Za-z0-9+/=]+)', stdout)
        if match:
            try:
                image_data = base64.b64decode(match.group(1))
                if len(image_data) < 10240:  # 10KB
                    await update.message.reply_text(f"⚠️ Скриншот слишком маленький ({len(image_data)} байт)")
                    return
                
                await update.message.reply_photo(
                    photo=image_data,
                    caption=f"Скриншот {url}"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка декодирования: {str(e)[:100]}")
        else:
            await update.message.reply_text("❌ Не удалось извлечь скриншот")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def search_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск в Google через прямую навигацию (без сложного JS)."""
    if not context.args:
        await update.message.reply_text("❗ Введите запрос: /search python programming")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        # ✅ ПРОСТОЙ СПОСОБ — как в /get_title, но с поисковым URL
        code = f'''
import json
new_tab("{search_url}")
wait_for_load()
info = page_info()
print(json.dumps(info))
'''
        stdout, stderr = await run_harness(code)
        
        if stderr:
            await update.message.reply_text(f"❌ Ошибка CLI: {stderr[:200]}")
            return
        
        try:
            data = json.loads(stdout.strip())
            title = data.get("title", "Без заголовка")
            await update.message.reply_text(
                f"✅ **Результаты поиска для:** {query}\n"
                f"📄 **Страница:** {title}"
            )
        except json.JSONDecodeError:
            await update.message.reply_text(f"✅ Результат: {stdout[:200]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 4. ЗАПУСК
# ============================================================

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug_api", debug_api))
    app.add_handler(CommandHandler("get_title", get_title))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("search", search_google))
    
    print("🚀 Бот запускается...")
    print("📋 Доступные команды:")
    print("   /start - приветствие")
    print("   /status - статус браузера и CLI")
    print("   /debug_api - диагностика API")
    print("   /get_title <url> - получить заголовок страницы")
    print("   /screenshot <url> - сделать скриншот")
    print("   /search <query> - поиск в Google")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()