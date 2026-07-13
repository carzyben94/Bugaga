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
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
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
        print(f"[{timestamp}] [{level}] {message}")  # ← Вывод в консоль

file_logger = FileLogger()

# ---------- БРАУЗЕР ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.target_id = None
    
    def ensure_browser(self):
        """Проверяет и запускает Chrome"""
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("✅ Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("🔄 Запускаю Chrome...", "INFO")
            try:
                # ПРОБУЕМ РАЗНЫЕ ФЛАГИ
                subprocess.Popen([
                    CHROME_PATH,
                    "--headless=new",  # ← новый headless режим
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                    "--disable-features=BlockInsecurePrivateNetworkRequests",
                    f"--remote-debugging-port={CDP_PORT}",
                    "--remote-debugging-address=0.0.0.0",
                    "--user-data-dir=/tmp/chrome-profile"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                time.sleep(5)  # ← ДАЕМ ВРЕМЯ ЗАПУСТИТЬСЯ
                
                # Проверяем
                try:
                    requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
                    file_logger.log("✅ Chrome запущен успешно", "INFO")
                    return True
                except:
                    file_logger.log("❌ Chrome не отвечает после запуска", "ERROR")
                    return False
                    
            except Exception as e:
                file_logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
                return False
    
    def get_or_create_tab(self):
        """Создает НОВУЮ вкладку для каждого запроса"""
        try:
            # Создаем свежую вкладку
            file_logger.log("🔄 Создаю новую вкладку...", "INFO")
            resp = requests.get(f"http://localhost:{CDP_PORT}/json/new")
            tab = resp.json()
            file_logger.log(f"✅ Вкладка создана: {tab['id']}", "INFO")
            return tab["webSocketDebuggerUrl"], tab["id"]
        except Exception as e:
            file_logger.log(f"❌ Ошибка создания вкладки: {e}", "ERROR")
            raise
    
    async def connect(self):
        """Подключение к новой вкладке"""
        if not self.ensure_browser():
            raise Exception("❌ Chrome не доступен")
        
        ws_url, self.target_id = self.get_or_create_tab()
        file_logger.log(f"🔗 Подключаюсь к WebSocket: {ws_url}", "INFO")
        
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
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        file_logger.log("✅ Домены активированы", "INFO")
    
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
                    return data
            except asyncio.TimeoutError:
                raise Exception("Таймаут ожидания ответа от Chrome")
    
    async def navigate_and_screenshot(self, url):
        """Навигация и скриншот"""
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        await self.connect()
        
        # ПРОБУЕМ НАВИГАЦИЮ
        try:
            file_logger.log(f"📤 Отправляю Page.navigate...", "INFO")
            result = await self.send("Page.navigate", {"url": url})
            file_logger.log(f"📥 Ответ навигации: {json.dumps(result)[:200]}", "INFO")
            
            # Проверяем ошибку навигации
            if "error" in result:
                raise Exception(f"Ошибка навигации: {result['error']}")
            
            # Ждем загрузку
            await self.wait_for_page_load()
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка навигации: {e}", "ERROR")
            # ПРОБУЕМ ЧЕРЕЗ EVALUATE
            file_logger.log("🔄 Пробую через window.location...", "INFO")
            await self.send("Runtime.evaluate", {
                "expression": f"window.location.href = '{url}'"
            })
            await asyncio.sleep(3)
            await self.wait_for_page_load()
        
        # Делаем скриншот
        screenshot_data = await self.screenshot()
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот")
        
        await self.ws.close()
        return screenshot_data
    
    async def wait_for_page_load(self):
        """Ожидание загрузки с отладкой"""
        file_logger.log("⏳ Ожидаю загрузку...", "INFO")
        start_time = time.time()
        
        while time.time() - start_time < PAGE_LOAD_TIMEOUT:
            try:
                # Проверяем readyState
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                
                ready_state = result.get("result", {}).get("result", {}).get("value", "")
                file_logger.log(f"📊 ReadyState: {ready_state}", "DEBUG")
                
                if ready_state in ["complete", "interactive"]:
                    file_logger.log(f"✅ Страница загружена ({ready_state})", "INFO")
                    return True
                
                # Проверяем URL
                url_result = await self.send("Runtime.evaluate", {
                    "expression": "window.location.href"
                })
                current_url = url_result.get("result", {}).get("result", {}).get("value", "")
                file_logger.log(f"📍 Текущий URL: {current_url}", "DEBUG")
                
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
            
            file_logger.log(f"❌ Нет данных в ответе: {result}", "ERROR")
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    file_logger.log(f"👤 Пользователь {user} (ID: {user_id})", "INFO")
    
    await update.message.reply_text(
        "👋 Отправь URL и я сделаю скриншот\n"
        "Пример: https://google.com\n\n"
        "📁 /log — получить файл логов\n"
        "🔄 /clear — очистить логи"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    file_logger.log(f"👤 {user} (ID: {user_id}) запросил: {url}", "INFO")
    
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
    """Отправляет файл логов"""
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Файл логов ещё не создан")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt",
                caption=f"📋 Логи за {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def clear_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает логи"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Логи очищены\n")
            await update.message.reply_text("✅ Логи очищены")
        else:
            await update.message.reply_text("📭 Файл логов не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- ЗАПУСК ----------
def main():
    print("="*50)
    print("🚀 ЗАПУСК БОТА")
    print("="*50)
    
    file_logger.log("="*50, "INFO")
    file_logger.log("🚀 БОТ ЗАПУЩЕН", "INFO")
    file_logger.log(f"Chrome путь: {CHROME_PATH}", "INFO")
    file_logger.log(f"CDP порт: {CDP_PORT}", "INFO")
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(CommandHandler("clear", clear_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("✅ Бот готов!")
    print("📁 Команды: /start, /log, /clear")
    print("="*50)
    
    app.run_polling()

if __name__ == "__main__":
    main()