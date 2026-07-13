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
        self.load_event_received = asyncio.Event()
    
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
                    f"--remote-debugging-port={CDP_PORT}"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(3)
                file_logger.log("Chrome запущен успешно", "INFO")
                return True
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    async def connect(self):
        """Подключение к браузеру через WebSocket (асинхронно)"""
        if not self.ensure_browser():
            raise Exception("Chrome не доступен")
        
        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version")
        ws_url = resp.json()["webSocketDebuggerUrl"]
        
        self.ws = await websockets.connect(ws_url)
        file_logger.log("Подключен к Chrome CDP", "INFO")
        
        # Проверяем соединение
        version = await self.send("Browser.getVersion")
        browser_name = version.get('result', {}).get('product', 'Unknown')
        file_logger.log(f"Браузер: {browser_name}", "INFO")
        
        # Активируем домены
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        file_logger.log("Домены активированы", "INFO")
    
    async def send(self, method, params=None):
        """Отправка CDP команды (асинхронно)"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        data = json.loads(response)
        
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown CDP error")
            error_code = data["error"].get("code", 0)
            raise Exception(f"CDP Error [{error_code}]: {error_msg}")
        
        return data
    
    async def listen_for_events(self):
        """Слушает события от браузера"""
        try:
            while True:
                response = await self.ws.recv()
                data = json.loads(response)
                
                if "method" in data:
                    if data["method"] == "Page.loadEventFired":
                        file_logger.log("Страница загружена (событие получено)", "INFO")
                        self.load_event_received.set()
                        break
                    elif data["method"] == "Page.domContentEventFired":
                        file_logger.log("DOM загружен", "DEBUG")
                        
        except websockets.exceptions.ConnectionClosed:
            file_logger.log("WebSocket соединение закрыто", "WARNING")
        except Exception as e:
            file_logger.log(f"Ошибка при прослушивании событий: {e}", "ERROR")
    
    async def wait_for_load(self, timeout=30):
        """Ожидает событие загрузки страницы"""
        try:
            await asyncio.wait_for(self.load_event_received.wait(), timeout=timeout)
            file_logger.log("Страница загружена успешно", "INFO")
            return True
        except asyncio.TimeoutError:
            file_logger.log("Таймаут ожидания загрузки страницы", "WARNING")
            return False
    
    async def navigate_and_screenshot(self, url):
        """Навигация и создание скриншота с ожиданием загрузки"""
        file_logger.log(f"Навигация на {url}", "INFO")
        await self.connect()
        
        self.load_event_received.clear()
        asyncio.create_task(self.listen_for_events())
        
        # Навигация
        await self.send("Page.navigate", {"url": url})
        file_logger.log("Навигация инициирована", "INFO")
        
        # Ждём загрузку
        loaded = await self.wait_for_load(timeout=30)
        
        if not loaded:
            file_logger.log("Страница не загрузилась за 30 секунд, делаем скриншот принудительно", "WARNING")
            await asyncio.sleep(2)
        
        # Скриншот
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        
        if "result" not in result or "data" not in result["result"]:
            file_logger.log(f"Неожиданный ответ от CDP: {result}", "ERROR")
            raise Exception("Не удалось получить скриншот")
        
        file_logger.log(f"Скриншот создан для {url}", "INFO")
        
        await self.ws.close()
        return base64.b64decode(result["result"]["data"])

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запустил бота", "INFO")
    
    await update.message.reply_text(
        "👋 Отправь URL и я сделаю скриншот\n"
        "Пример: https://google.com\n\n"
        "📁 /log — получить файл логов"
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
        await update.message.reply_photo(screenshot, caption=f"✅ {url}")
        file_logger.log(f"Скриншот отправлен пользователю {user}", "INFO")
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка для {user} ({url}): {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл логов в Telegram (доступно всем)"""
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

# ---------- ЗАПУСК ----------
def main():
    file_logger.log("="*50, "INFO")
    file_logger.log("БОТ ЗАПУЩЕН", "INFO")
    file_logger.log(f"Chrome путь: {CHROME_PATH}", "INFO")
    file_logger.log(f"CDP порт: {CDP_PORT}", "INFO")
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        file_logger.log("TELEGRAM_BOT_TOKEN не указан!", "ERROR")
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("🚀 Бот запущен! Логи пишутся в bot_logs.txt")
    print("📁 Команды: /start, /log")
    app.run_polling()

if __name__ == "__main__":
    main()