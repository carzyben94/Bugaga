import subprocess
import time
import os
import sys

CHROME_PATH = "/usr/bin/chromium"

print("🚀 Старт скрипта...")

if os.path.exists(CHROME_PATH):
    print("⏳ Запуск Chrome...")
    
    process = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--remote-debugging-port=9222"
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    time.sleep(3)
    print("✅ Chrome запущен на порту 9222")
    print(f"📌 PID: {process.pid}")
else:
    print(f"❌ Chrome не найден по пути {CHROME_PATH}!")
    print("📌 Установите Chrome через Dockerfile или nixpacks")

# Держим контейнер активным
print("🔄 Контейнер работает, Chrome в фоне...")
while True:
    time.sleep(60)
    print("💓 Heartbeat: Chrome всё ещё работает")