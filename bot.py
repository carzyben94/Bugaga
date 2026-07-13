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
WEBSOCKET_MAX_SIZE = 20 * 1024 * 1024  # 20 МБ

# ---------- ЛОГИРОВАНИЕ ----------
LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- БРАУЗЕР (АСИНХРОННЫЙ) ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.target_id = None
    
    def ensure_browser(self):
        """Проверяет и запускает Chrome если не запущен"""
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("Запускаю Chrome...", "INFO")
            try:
                subprocess.Popen([
                    CHROME_PATH,
                    "--headless",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    f"--remote-debugging-port={CDP_PORT}"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(3)
                file_logger.log("Chrome запущен успешно", "INFO")
                return True
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    def get_or_create_tab(self):
        """Получает существующую вкладку или создает новую"""
        try:
            resp = requests.get(f"http://localhost:{CDP_PORT}/json/list")
            pages = resp.json()
            
            if pages:
                # Берем первую существующую вкладку
                tab = pages[0]
                file_logger.log(f"Использую существующую вкладку: {tab['id']}", "INFO")
                return tab["webSocketDebuggerUrl"], tab["id"]
            else:
                # Создаем новую вкладку через HTTP
                file_logger.log("Создаю новую вкладку", "INFO")
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/new")
                tab = resp.json()
                return tab["webSocketDebuggerUrl"], tab["id"]
        except Exception as e:
            file_logger.log(f"Ошибка при получении вкладки: {e}", "ERROR")
            raise
    
    async def connect(self):
        """Подключение к существующей вкладке"""
        if not self.ensure_browser():
            raise Exception("Chrome не доступен")
        
        # Получаем WS URL вкладки
        ws_url, self.target_id = self.get_or_create_tab()
        
        # Подключаемся напрямую к вкладке с увеличенным лимитом
        self.ws = await websockets.connect(
            ws_url,
            max_size=WEBSOCKET_MAX_SIZE  # 20 МБ
        )
        file_logger.log(f"Подключен к вкладке: {self.target_id} (max_size: {WEBSOCKET_MAX_SIZE//1024//1024}MB)", "INFO")
        
        # Активируем домены (БЕЗ session_id!)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        file_logger.log("Домены активированы", "INFO")
    
    async def send(self, method, params=None):
        """Отправка CDP команды (без session_id)"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            response = await self.ws.recv()
            data = json.loads(response)
            
            if data.get("id") == self.msg_id:
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown CDP error")
                    error_code = data["error"].get("code", 0)
                    raise Exception(f"CDP Error [{error_code}]: {error_msg}")
                return data
    
    async def screenshot(self):
        """Скриншот страницы (1280x720)"""
        try:
            file_logger.log("📸 Делаю скриншот...", "INFO")
            
            # Устанавливаем разрешение 1280x720
            await self.send("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False,
                "scale": 1
            })
            
            # Делаем скриншот (уже в 1280x720)
            result = await self.send("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 80,
                "captureBeyondViewport": False  # ← только видимая область
            })
            
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                file_logger.log(f"✅ Скриншот 1280x720 ({len(img_data)} байт / {len(img_data)//1024} KB)", "INFO")
                return img_data
            
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None
    
    async def navigate_and_screenshot(self, url):
        """Навигация и создание скриншота"""
        file_logger.log(f"Навигация на {url}", "INFO")
        await self.connect()
        
        # Навигация (без session_id!)
        await self.send("Page.navigate", {"url": url})
        file_logger.log("Навигация инициирована", "INFO")
        
        # Ждём загрузку
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState === 'complete'"
                })
                
                if result.get("result", {}).get("result", {}).get("value") == True:
                    file_logger.log("Страница загружена (readyState complete)", "INFO")
                    break
            except:
                pass
            await asyncio.sleep(0.5)
        else:
            file_logger.log("Таймаут ожидания загрузки страницы", "WARNING")
        
        # Делаем скриншот
        screenshot_data = await self.screenshot()
        
        if not screenshot_data:
            raise Exception("Не удалось получить скриншот")
        
        # Закрываем WebSocket (не закрываем вкладку!)
        await self.ws.close()
        
        return screenshot_data

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запустил бота", "INFO")
    
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
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запросил: {url}", "INFO")
    
    if not url.startswith(('http://', 'https://')):
        file_logger.log(f"Неверный URL от {user}: {url}", "WARNING")
        await update.message.reply_text("❌ Добавь http:// или https://")
        return
    
    await update.message.reply_text(f"🔄 Загружаю {url}...")
    
    try:
        browser = BrowserCDP()
        screenshot = await browser.navigate_and_screenshot(url)
        
        # Отправляем скриншот
        await update.message.reply_photo(
            screenshot, 
            caption=f"✅ {url}\n📐 1280x720"
        )
        file_logger.log(f"Скриншот отправлен пользователю {user}", "INFO")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка для {user} ({url}): {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл логов в Telegram"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запросил лог-файл", "INFO")
    
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Файл логов ещё не создан")
            return
        
        file_size = os.path.getsize(LOG_FILE)
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(f"⚠️ Файл слишком большой ({file_size // 1024 // 1024}MB)")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt",
                caption=f"📋 Логи бота за {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        file_logger.log(f"Лог-файл отправлен пользователю {user}", "INFO")
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка при отправке лога {user}: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def clear_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает файл логов"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) очистил логи", "INFO")
    
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Логи очищены пользователем {user}\n")
            await update.message.reply_text("✅ Логи очищены")
        else:
            await update.message.reply_text("📭 Файл логов не найден")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка при очистке логов: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

# ---------- ЗАПУСК ----------
def main():
    file_logger.log("="*50, "INFO")
    file_logger.log("БОТ ЗАПУЩЕН", "INFO")
    file_logger.log(f"Chrome путь: {CHROME_PATH}", "INFO")
    file_logger.log(f"CDP порт: {CDP_PORT}", "INFO")
    file_logger.log(f"WebSocket max_size: {WEBSOCKET_MAX_SIZE//1024//1024}MB", "INFO")
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        file_logger.log("TELEGRAM_BOT_TOKEN не указан!", "ERROR")
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(CommandHandler("clear", clear_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("🚀 Бот запущен! Логи пишутся в bot_logs.txt")
    print("📁 Команды: /start, /log, /clear")
    print(f"📦 WebSocket max_size: {WEBSOCKET_MAX_SIZE//1024//1024}MB")
    
    app.run_polling()

if __name__ == "__main__":
    main()