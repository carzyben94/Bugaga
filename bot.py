import os
import asyncio
import subprocess
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def check_browser():
    """Проверяет доступность браузера с детальным логгированием"""
    endpoints = [
        "ws://localhost:9222",
        "ws://localhost:9222/devtools/browser",
        "ws://127.0.0.1:9222",
        "ws://127.0.0.1:9222/devtools/browser"
    ]
    
    for url in endpoints:
        try:
            print(f"🔄 Пробую подключиться к {url}")
            async with websockets.connect(url, timeout=5) as ws:
                print(f"✅ Подключено к {url}")
                return True, url
        except Exception as e:
            print(f"❌ Ошибка для {url}: {str(e)[:50]}")
            continue
    
    # Если ничего не работает — проверяем, запущен ли Chromium
    try:
        result = subprocess.run(
            ["pgrep", "-f", "chromium"],
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(f"🔍 Процессы Chromium: {result.stdout.strip()}")
        else:
            print("❌ Chromium не запущен!")
    except Exception as e:
        print(f"⚠️ Не удалось проверить процессы: {e}")
    
    return False, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok, url = await check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    await update.message.reply_text(
        f"🤖 Бот запущен!\n"
        f"Браузер: {status}\n"
        f"URL: {url or 'не найден'}\n"
        f"Готов к выполнению задач!"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отладки — показывает системную информацию"""
    import socket
    import subprocess
    
    # Проверяем, слушает ли порт 9222
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 9222))
    port_status = "открыт" if result == 0 else f"закрыт (код {result})"
    sock.close()
    
    # Проверяем процессы
    ps = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    chromium_lines = [line for line in ps.stdout.split('\n') if 'chromium' in line.lower()]
    
    msg = (
        f"🔍 Отладка:\n"
        f"Порт 9222: {port_status}\n"
        f"Процессов Chromium: {len(chromium_lines)}\n"
    )
    if chromium_lines:
        msg += f"Пример процесса: {chromium_lines[0][:80]}..."
    
    await update.message.reply_text(msg)

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    
    print("🚀 Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()