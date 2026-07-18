import os
import subprocess
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def check_browser():
    """Проверяет браузер через HTTP-запрос (без websockets)"""
    try:
        response = requests.get("http://localhost:9222/json/version", timeout=3)
        return response.status_code == 200
    except:
        return False

def ensure_browser():
    """Запускает браузер и ждет готовности"""
    chrome_path = "/usr/bin/chromium"
    
    # Проверяем, не запущен ли уже
    if check_browser():
        print("✅ Браузер уже запущен")
        return True
    
    print("🔄 Запускаем браузер...")
    
    # Запускаем Chromium
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
    
    # Ждем запуска (до 30 секунд)
    for i in range(30):
        time.sleep(1)
        if check_browser():
            print(f"✅ Браузер запущен! (через {i+1} сек)")
            return True
        print(f"   Ожидание... {i+1}/30")
    
    print("❌ Не удалось запустить браузер")
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    
    # Дополнительная информация для отладки
    info = ""
    if not browser_ok:
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 9222))
            info = f"\nПорт 9222: {'открыт' if result == 0 else f'закрыт (код {result})'}"
            sock.close()
        except:
            pass
    
    await update.message.reply_text(
        f"🤖 Бот запущен!\n"
        f"Браузер: {status}{info}\n"
        f"Готов к выполнению задач!"
    )

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    # Запускаем браузер ДО бота
    if not ensure_browser():
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: Браузер не запустился, некоторые функции могут не работать")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("🚀 Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()