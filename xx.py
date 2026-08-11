import subprocess
import time
import os

CHROME_PATH = "/usr/bin/chromium"

if os.path.exists(CHROME_PATH):
    print("⏳ Запуск Chrome...")
    
    process = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--remote-debugging-port=9222"
    ], stdout=None, stderr=None)  # Вывод в консоль
    
    time.sleep(3)
    print("✅ Chrome запущен на порту 9222")
    print(f"📌 PID: {process.pid}")
else:
    print(f"❌ Chrome не найден по пути {CHROME_PATH}!")