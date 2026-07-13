import os
import json
import time
import subprocess
import base64
import requests
import asyncio
import websockets
import random
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

# ---------- МАСКИРОВКА ----------
def get_random_window_position():
    """Генерирует случайную позицию окна"""
    return {
        "left": random.randint(50, 300),
        "top": random.randint(50, 200),
        "width": random.randint(1200, 1920),
        "height": random.randint(800, 1080)
    }

class BrowserMask:
    """Настройки маскировки браузера"""
    
    @staticmethod
    def get_launch_args():
        """Возвращает аргументы запуска Chrome с маскировкой"""
        window = get_random_window_position()
        
        args = [
            CHROME_PATH,
            "--headless=new",  # Новый headless режим (сложнее обнаружить)
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            
            # Скрытие отпечатков GPU/WebGL
            "--use-gl=swiftshader",
            "--disable-reading-from-canvas",
            "--disable-features=AudioServiceOutOfProcess",
            "--disable-accelerated-2d-canvas",
            "--disable-accelerated-video-decode",
            
            # Безопасность и скрытие автоматизации
            "--disable-blink-features=AutomationControlled",  # Ключевой флаг!
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-webgl",  # Скрываем GPU
            
            # Скрываем автоматизацию
            "--disable-automation",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-client-side-phishing-detection",
            "--disable-crash-reporter",
            "--disable-component-update",
            "--disable-logging",
            "--disable-prompt-on-repost",
            "--disable-sync",
            
            # Настройки окна
            f"--window-position={window['left']},{window['top']}",
            f"--window-size={window['width']},{window['height']}",
            
            # Дополнительно
            "--no-default-browser-check",
            "--no-first-run",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--password-store=basic",
            "--use-mock-keychain",
            "--export-tagged-pdf",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            
            # Убираем следы headless
            "--enable-features=NetworkService,NetworkServiceInProcess",
            
            # User-Agent подмена
            f"--user-agent={self.get_random_user_agent()}",
            
            f"--remote-debugging-port={CDP_PORT}"
        ]
        
        return args
    
    @staticmethod
    def get_random_user_agent():
        """Генерирует реалистичный User-Agent"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]
        return random.choice(user_agents)

# ---------- БРАУЗЕР (АСИНХРОННЫЙ) ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.session_id = None
        self.target_id = None
        self.mask = BrowserMask()
    
    def ensure_browser(self):
        """Проверяет и запускает Chrome с маскировкой если не запущен"""
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("Запускаю Chrome с маскировкой...", "INFO")
            try:
                args = self.mask.get_launch_args()
                file_logger.log(f"Аргументы Chrome: {' '.join(args[:5])}...", "DEBUG")
                
                subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "LANG": "en_US.UTF-8"}
                )
                time.sleep(5)  # Даём время на запуск с маскировкой
                file_logger.log("Chrome запущен успешно с маскировкой", "INFO")
                return True
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    async def connect(self):
        """Подключение к браузеру и создание новой вкладки"""
        if not self.ensure_browser():
            raise Exception("Chrome не доступен")
        
        # Подключаемся к браузеру
        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version")
        ws_url = resp.json()["webSocketDebuggerUrl"]
        
        self.ws = await websockets.connect(ws_url)
        file_logger.log("Подключен к браузеру", "INFO")
        
        # Устанавливаем настройки эмуляции (маскировка)
        await self.set_emulation_settings()
        
        # Создаём новую вкладку
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        self.target_id = result["result"]["targetId"]
        file_logger.log(f"Создана вкладка: {self.target_id}", "INFO")
        
        # Прикрепляемся к вкладке
        attach_result = await self.send("Target.attachToTarget", {
            "targetId": self.target_id,
            "flatten": True
        })
        self.session_id = attach_result["result"]["sessionId"]
        file_logger.log(f"Прикреплен к вкладке", "INFO")
        
        # Активируем домены через сессию
        await self.send("Page.enable", session_id=self.session_id)
        await self.send("Runtime.enable", session_id=self.session_id)
        await self.send("Network.enable", session_id=self.session_id)
        file_logger.log("Домены активированы", "INFO")
        
        # Скрываем WebDriver (маскировка)
        await self.send("Runtime.evaluate", {
            "expression": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true,
                    enumerable: true
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                    configurable: true,
                    enumerable: true
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                    configurable: true,
                    enumerable: true
                });
                console.log('✅ WebDriver скрыт');
            """
        }, session_id=self.session_id)
        file_logger.log("Скрыты следы автоматизации", "INFO")
    
    async def set_emulation_settings(self):
        """Устанавливает настройки эмуляции для маскировки"""
        # Эмуляция устройства (реалистичные параметры)
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": random.randint(1200, 1920),
            "height": random.randint(800, 1080),
            "deviceScaleFactor": 1,
            "mobile": False,
            "scale": 1
        })
        
        # Эмуляция геолокации (США)
        await self.send("Emulation.setGeolocationOverride", {
            "latitude": 37.7749 + random.uniform(-1, 1),
            "longitude": -122.4194 + random.uniform(-1, 1),
            "accuracy": 100
        })
        file_logger.log("Настройки эмуляции установлены", "INFO")
    
    async def send(self, method, params=None, session_id=None):
        """Отправка CDP команды с поддержкой сессий"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        if session_id:
            msg["sessionId"] = session_id
        
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
    
    async def navigate_and_screenshot(self, url):
        """Навигация и создание скриншота с маскировкой"""
        file_logger.log(f"Навигация на {url}", "INFO")
        await self.connect()
        
        # Навигация через сессию
        await self.send("Page.navigate", {"url": url}, session_id=self.session_id)
        file_logger.log("Навигация инициирована", "INFO")
        
        # Ждём загрузку через Runtime.evaluate
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                result = await self.send("Runtime.evaluate", {
                    "expression": "document.readyState === 'complete'"
                }, session_id=self.session_id)
                
                if result.get("result", {}).get("result", {}).get("value") == True:
                    file_logger.log("Страница загружена", "INFO")
                    break
            except:
                pass
            await asyncio.sleep(0.5)
        else:
            file_logger.log("Таймаут ожидания загрузки страницы", "WARNING")
        
        # Скриншот через сессию
        result = await self.send("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True
        }, session_id=self.session_id)
        
        if "result" not in result or "data" not in result["result"]:
            file_logger.log(f"Неожиданный ответ от CDP: {result}", "ERROR")
            raise Exception("Не удалось получить скриншот")
        
        file_logger.log(f"Скриншот создан для {url}", "INFO")
        
        # Закрываем вкладку
        await self.send("Target.closeTarget", {"targetId": self.target_id})
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
        "📁 /log — получить файл логов\n"
        "🕵️ Маскировка включена (stealth mode)"
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
    
    await update.message.reply_text(f"🔄 Загружаю {url} (stealth mode)...")
    
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

# ---------- ЗАПУСК ----------
def main():
    file_logger.log("="*50, "INFO")
    file_logger.log("БОТ ЗАПУЩЕН (STEALTH MODE)", "INFO")
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
    
    print("🚀 Бот запущен в STEALTH режиме!")
    print("🕵️ Маскировка: headless=new, отключен webdriver, случайный User-Agent")
    print("📁 Команды: /start, /log")
    
    app.run_polling()

if __name__ == "__main__":
    main()