import os
import json
import time
import subprocess
import base64
import requests
import asyncio
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- КОНФИГ ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CDP_PORT = 9222
WEBSOCKET_MAX_SIZE = 20 * 1024 * 1024
PAGE_LOAD_TIMEOUT = 20

# ---------- ЛОГИРОВАНИЕ ----------
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
        print(f"[{timestamp}] [{level}] {message}")

file_logger = FileLogger()

# ---------- БРАУЗЕР ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.target_id = None
    
    def find_chrome(self):
        """Ищет Chrome в разных местах"""
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "google-chrome",
            "chromium-browser",
            "chromium"
        ]
        
        for path in chrome_paths:
            try:
                result = subprocess.run([path, "--version"], 
                                      capture_output=True, 
                                      timeout=2)
                if result.returncode == 0:
                    file_logger.log(f"✅ Найден Chrome: {path}", "INFO")
                    return path
            except:
                continue
        
        return None
    
    def ensure_browser(self):
        """Проверяет и запускает Chrome"""
        file_logger.log("🔍 Проверяю Chrome...", "INFO")
        
        # Проверяем, отвечает ли Chrome
        try:
            resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            if resp.status_code == 200:
                file_logger.log("✅ Chrome уже запущен и отвечает", "INFO")
                file_logger.log(f"📌 Версия: {resp.json().get('Browser', 'unknown')}", "INFO")
                return True
        except Exception as e:
            file_logger.log(f"⚠️ Chrome не отвечает: {e}", "WARNING")
        
        # Ищем Chrome
        chrome_path = self.find_chrome()
        if not chrome_path:
            file_logger.log("❌ Chrome не найден в системе!", "ERROR")
            return False
        
        file_logger.log(f"🔄 Запускаю Chrome: {chrome_path}", "INFO")
        
        try:
            # Убиваем старые процессы Chrome
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
            time.sleep(2)
            
            # Запускаем с правильными флагами
            subprocess.Popen([
                chrome_path,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--remote-debugging-port=9222",
                "--remote-debugging-address=0.0.0.0",
                "--user-data-dir=/tmp/chrome-profile"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            file_logger.log("⏳ Жду запуска Chrome (5 сек)...", "INFO")
            time.sleep(5)
            
            # Проверяем несколько раз
            for i in range(5):
                try:
                    resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
                    if resp.status_code == 200:
                        file_logger.log("✅ Chrome запущен успешно!", "INFO")
                        return True
                except:
                    pass
                time.sleep(1)
            
            file_logger.log("❌ Chrome не отвечает после запуска", "ERROR")
            return False
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            return False
    
    def get_or_create_tab(self, url=None):
        """
        Создает новую вкладку через правильный HTTP-метод согласно документации CDP
        Документация: PUT /json/new?{url} или POST /json/new
        """
        try:
            # Сначала проверяем /json/version
            version_resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=3)
            file_logger.log(f"✅ Chrome version: {version_resp.json().get('Browser', 'unknown')}", "INFO")
            
            # Способ 1: PUT с URL (как в документации)
            if url:
                full_url = f"http://localhost:{CDP_PORT}/json/new?{url}"
            else:
                full_url = f"http://localhost:{CDP_PORT}/json/new"
            
            file_logger.log(f"🔄 Пробую PUT: {full_url}", "INFO")
            resp = requests.put(full_url, timeout=3)
            
            # Способ 2: Если PUT не работает, пробуем POST
            if resp.status_code == 405:
                file_logger.log("🔄 PUT вернул 405, пробую POST...", "INFO")
                resp = requests.post(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            
            # Способ 3: Если POST не работает, пробуем GET (некоторые старые версии)
            if resp.status_code == 405:
                file_logger.log("🔄 POST вернул 405, пробую GET (старая версия)...", "INFO")
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/new", timeout=3)
            
            if resp.status_code != 200:
                file_logger.log(f"❌ HTTP {resp.status_code}: {resp.text[:200]}", "ERROR")
                raise Exception(f"HTTP {resp.status_code}")
            
            if not resp.text or not resp.text.strip():
                file_logger.log("❌ Пустой ответ от Chrome", "ERROR")
                raise Exception("Пустой ответ")
            
            tab = resp.json()
            file_logger.log(f"✅ Вкладка создана: {tab.get('id', 'unknown')}", "INFO")
            file_logger.log(f"🔗 WebSocket URL: {tab.get('webSocketDebuggerUrl', 'unknown')[:50]}...", "INFO")
            return tab["webSocketDebuggerUrl"], tab["id"]
            
        except requests.exceptions.ConnectionError:
            file_logger.log("❌ Chrome не отвечает (ConnectionError)", "ERROR")
            raise Exception("Chrome не запущен")
        except json.JSONDecodeError as e:
            file_logger.log(f"❌ Ошибка JSON: {e}", "ERROR")
            file_logger.log(f"Ответ Chrome: {resp.text[:500]}", "ERROR")
            raise Exception(f"Невалидный JSON от Chrome")
        except Exception as e:
            file_logger.log(f"❌ Ошибка создания вкладки: {e}", "ERROR")
            raise
    
    async def connect(self):
        """Подключение к вкладке"""
        if not self.ensure_browser():
            raise Exception("❌ Chrome не доступен")
        
        ws_url, self.target_id = self.get_or_create_tab()
        file_logger.log(f"🔗 Подключаюсь к WebSocket...", "INFO")
        
        try:
            self.ws = await websockets.connect(
                ws_url,
                max_size=WEBSOCKET_MAX_SIZE,
                timeout=10
            )
            file_logger.log(f"✅ WebSocket подключен", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка WebSocket: {e}", "ERROR")
            raise
        
        # Активируем домены
        try:
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            file_logger.log("✅ Домены активированы", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка активации доменов: {e}", "ERROR")
            raise
    
    async def send(self, method, params=None):
        """Отправка CDP команды"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        file_logger.log(f"📤 Отправляю: {method}", "DEBUG")
        await self.ws.send(json.dumps(msg))
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("id") == self.msg_id:
                    if "error" in data:
                        error_msg = data["error"].get("message", "Unknown CDP error")
                        error_code = data["error"].get("code", 0)
                        raise Exception(f"CDP Error [{error_code}]: {error_msg}")
                    file_logger.log(f"📥 Получен ответ для {method}", "DEBUG")
                    return data
            except asyncio.TimeoutError:
                raise Exception("Таймаут ожидания ответа")
    
    async def navigate_and_screenshot(self, url):
        """Навигация и скриншот"""
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        await self.connect()
        
        # Навигация
        try:
            result = await self.send("Page.navigate", {"url": url})
            file_logger.log(f"✅ Навигация отправлена", "INFO")
            
            # Проверяем frameId
            if "result" in result and "frameId" in result["result"]:
                file_logger.log(f"📌 Frame ID: {result['result']['frameId']}", "INFO")
        except Exception as e:
            file_logger.log(f"❌ Ошибка навигации: {e}", "ERROR")
            raise
        
        # Ждем загрузку
        await self.wait_for_page_load()
        
        # Скриншот
        screenshot_data = await self.screenshot()
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот")
        
        await self.ws.close()
        return screenshot_data
    
    async def wait_for_page_load(self):
        """Ожидание загрузки"""
        file_logger.log("⏳ Ожидаю загрузку...", "INFO")
        start_time = time.time()
        
        while time.time() - start_time < PAGE_LOAD_TIMEOUT:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                
                ready_state = result.get("result", {}).get("result", {}).get("value", "")
                file_logger.log(f"📊 ReadyState: {ready_state}", "DEBUG")
                
                if ready_state in ["complete", "interactive"]:
                    file_logger.log(f"✅ Страница загружена ({ready_state})", "INFO")
                    return True
                
                # Проверяем, есть ли body
                body_result = await self.send("Runtime.evaluate", {
                    "expression": "document.body !== null"
                })
                has_body = body_result.get("result", {}).get("result", {}).get("value", False)
                if has_body and ready_state == "loading":
                    file_logger.log("📄 Body загружен, продолжаем...", "DEBUG")
                
            except Exception as e:
                file_logger.log(f"⚠️ Ошибка проверки: {e}", "WARNING")
            
            await asyncio.sleep(0.5)
        
        file_logger.log("⏰ Таймаут загрузки", "WARNING")
        return False
    
    async def screenshot(self):
        """Скриншот"""
        try:
            file_logger.log("📸 Делаю скриншот...", "INFO")
            
            await self.send("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False,
                "scale": 1
            })
            
            result = await self.send("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 80,
                "captureBeyondViewport": False
            })
            
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                file_logger.log(f"✅ Скриншот {len(img_data)//1024} KB", "INFO")
                return img_data
            
            file_logger.log(f"❌ Нет данных в ответе", "ERROR")
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(
        "👋 Отправь URL и я сделаю скриншот\n"
        "Пример: https://google.com\n\n"
        "📁 /log — получить файл логов"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user.first_name
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Добавь http:// или https://")
        return
    
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        browser = BrowserCDP()
        screenshot = await browser.navigate_and_screenshot(url)
        
        await update.message.reply_photo(
            screenshot, 
            caption=f"✅ {url}"
        )
        file_logger.log(f"✅ Скриншот отправлен {user}", "INFO")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"❌ Ошибка: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Файл логов ещё не создан")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- ЗАПУСК ----------
def main():
    print("="*50)
    print("🚀 ЗАПУСК БОТА")
    print("="*50)
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("✅ Бот готов!")
    app.run_polling()

if __name__ == "__main__":
    main()