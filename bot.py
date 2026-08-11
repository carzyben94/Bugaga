import os
import logging
import subprocess
import asyncio
import httpx
import websockets
import json
import base64
import time
import socket
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

# ==================== ЗАПУСК CHROME С ПРАВИЛЬНЫМИ ПАРАМЕТРАМИ ====================
CHROME_PATH = "/usr/bin/chromium"
CHROME_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium"
]

def find_chrome():
    """Найти Chrome/Chromium в системе"""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None

def start_chrome():
    """Запускает Chromium с правильными параметрами для CDP"""
    chrome_path = find_chrome()
    if not chrome_path:
        logger.error("❌ Chrome/Chromium не найден!")
        return False
    
    try:
        # Убиваем старые процессы
        subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
        time.sleep(2)
        
        # Запускаем с правильными параметрами
        subprocess.Popen([
            chrome_path,
            "--headless=new",  # Новый headless режим
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--remote-debugging-port=9222",
            "--remote-debugging-address=0.0.0.0",
            "--window-size=1280,720",
            "--disable-blink-features=AutomationControlled",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info(f"✅ Chrome запущен ({chrome_path})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Chrome: {e}")
        return False

def wait_for_chrome(max_attempts=20, delay=2):
    """Ожидание готовности Chrome с проверкой порта"""
    for attempt in range(max_attempts):
        try:
            # Проверяем доступность порта
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 9222))
            sock.close()
            
            if result == 0:
                # Проверяем /json/list
                response = httpx.get("http://localhost:9222/json/list", timeout=5.0)
                if response.status_code == 200:
                    pages = response.json()
                    if pages:
                        logger.info(f"✅ Chrome готов (попытка {attempt + 1})")
                        return True
                    else:
                        # Создаем новую страницу если нет
                        try:
                            httpx.get("http://localhost:9222/json/new", timeout=5.0)
                        except:
                            pass
            else:
                logger.info(f"⏳ Ожидание Chrome... (попытка {attempt + 1}/{max_attempts})")
        except Exception as e:
            logger.debug(f"⚠️ Ошибка проверки: {e}")
        
        time.sleep(delay)
    
    logger.error("❌ Chrome не запустился за отведенное время")
    return False

# ==================== CDP КЛИЕНТ ====================
class CDPClient:
    def __init__(self):
        self.ws = None
        self.ws_url = None
        self.is_connected = False
        self.message_id = 0
        
    async def connect(self):
        """Подключение к Chrome через WebSocket"""
        try:
            # Получаем WebSocket URL
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:9222/json/list", timeout=10.0)
                pages = resp.json()
                
                if not pages:
                    # Создаем новую страницу
                    resp = await client.get("http://localhost:9222/json/new", timeout=10.0)
                    pages = [resp.json()]
                
                self.ws_url = pages[0]["webSocketDebuggerUrl"]
                logger.info(f"✅ WebSocket URL: {self.ws_url}")
            
            # Подключаемся к WebSocket
            self.ws = await websockets.connect(
                self.ws_url,
                timeout=30.0,
                ping_interval=10,
                ping_timeout=10
            )
            self.is_connected = True
            logger.info("✅ Подключение к Chrome через WebSocket установлено")
            
            # Включаем домены
            await self.send_command("Network.enable")
            await self.send_command("Page.enable")
            await self.send_command("Runtime.enable")
            await self.send_command("DOM.enable")
            
            # Устанавливаем viewport
            await self.send_command("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def send_command(self, method: str, params: dict = None):
        """Отправить CDP команду"""
        if not self.is_connected or not self.ws:
            raise Exception("Не подключено к браузеру")
        
        self.message_id += 1
        command = {
            "id": self.message_id,
            "method": method
        }
        if params:
            command["params"] = params
        
        try:
            # Отправляем
            await self.ws.send(json.dumps(command))
            
            # Ждем ответ с таймаутом
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(response)
                
                if data.get("id") == self.message_id:
                    if "error" in data:
                        raise Exception(f"CDP ошибка: {data['error']}")
                    return data.get("result", {})
                    
        except asyncio.TimeoutError:
            raise Exception("Таймаут ожидания CDP ответа")
        except Exception as e:
            raise Exception(f"Ошибка CDP: {e}")
    
    async def load_page(self, url: str):
        """Загрузить страницу с ожиданием"""
        try:
            logger.info(f"🚀 Загрузка: {url}")
            
            # Проверяем URL
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            # Навигация
            result = await self.send_command("Page.navigate", {"url": url})
            
            if "errorText" in result:
                raise Exception(f"Ошибка навигации: {result['errorText']}")
            
            # Ждем загрузки
            await self._wait_for_load()
            
            return {"success": True, "url": url}
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return {"success": False, "error": str(e)}
    
    async def _wait_for_load(self, timeout=30):
        """Ожидание загрузки страницы"""
        try:
            # Ждем готовности документа
            start = time.time()
            while time.time() - start < timeout:
                try:
                    result = await self.send_command("Runtime.evaluate", {
                        "expression": "document.readyState"
                    })
                    ready_state = result.get("result", {}).get("value", "loading")
                    
                    if ready_state == "complete":
                        logger.info("✅ Страница загружена")
                        await asyncio.sleep(1)  # Доп. задержка для рендеринга
                        return True
                        
                except Exception as e:
                    logger.debug(f"⚠️ Ошибка проверки readyState: {e}")
                
                await asyncio.sleep(0.5)
            
            logger.warning("⚠️ Таймаут ожидания загрузки")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка ожидания: {e}")
            return False
    
    async def capture_screenshot(self, filename: str = None):
        """Сделать скриншот"""
        try:
            result = await self.send_command("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            })
            
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            
            image_data = base64.b64decode(result["data"])
            with open(filename, "wb") as f:
                f.write(image_data)
            
            return {"success": True, "filename": filename}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def execute_js(self, script: str):
        """Выполнить JavaScript"""
        try:
            result = await self.send_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True
            })
            
            value = result.get("result", {}).get("value")
            return {"success": True, "result": value}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_page_info(self):
        """Получить информацию о странице"""
        try:
            url_result = await self.send_command("Runtime.evaluate", {
                "expression": "window.location.href"
            })
            title_result = await self.send_command("Runtime.evaluate", {
                "expression": "document.title"
            })
            
            url = url_result.get("result", {}).get("value", "unknown")
            title = title_result.get("result", {}).get("value", "unknown")
            
            return {"success": True, "url": url, "title": title}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Закрыть соединение"""
        try:
            if self.ws:
                await self.ws.close()
            self.is_connected = False
        except:
            pass

# ==================== ГЛОБАЛЬНЫЙ ИНСТАНС ====================
browser = None

async def init_browser():
    """Инициализация браузера"""
    global browser
    browser = CDPClient()
    success = await browser.connect()
    if success:
        logger.info("✅ Браузер инициализирован")
    else:
        logger.error("❌ Не удалось инициализировать браузер")
    return success

# ==================== DSPy АДАПТЕР И ИНСТРУМЕНТЫ ====================
class AgnesLM(dspy.LM):
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        super().__init__(
            model=model, 
            model_type="chat",
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
            cache=False
        )
        self.provider = "agnes-ai"
        self.forward_contract = "legacy"
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            return ["Ошибка: API ключ не задан"]
        
        params = {**self.kwargs, **kwargs}
        api_messages = messages or [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", 0.3),
            "max_tokens": params.get("max_tokens", 2000)
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ от API"]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# Инструменты для DSPy
def sync_run_async(coro):
    """Запустить асинхронную функцию синхронно"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=60)
    except RuntimeError:
        return asyncio.run(coro)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=60)
    except:
        return asyncio.run(coro)

def goto_url(url: str) -> str:
    """Перейти на URL"""
    try:
        result = sync_run_async(browser.load_page(url))
        if result.get("success"):
            return f"✅ Успешно открыл {url}"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def capture_screenshot() -> str:
    """Сделать скриншот"""
    try:
        filename = f"screenshot_{int(time.time())}.png"
        result = sync_run_async(browser.capture_screenshot(filename))
        if result.get("success"):
            return f"✅ Скриншот сохранен: {filename}"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def execute_js(script: str) -> str:
    """Выполнить JavaScript"""
    try:
        result = sync_run_async(browser.execute_js(script))
        if result.get("success"):
            return str(result.get("result", "✅ JS выполнен"))
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def page_info() -> str:
    """Получить информацию о странице"""
    try:
        result = sync_run_async(browser.get_page_info())
        if result.get("success"):
            return f"URL: {result['url']}\nЗаголовок: {result['title']}"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

tools = [
    Tool(goto_url),
    Tool(capture_screenshot),
    Tool(execute_js),
    Tool(page_info),
]

# ==================== СОЗДАНИЕ АГЕНТА ====================
browser_agent = None
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if AGNES_API_KEY:
    try:
        lm = AgnesLM(api_key=AGNES_API_KEY, temperature=0.3, max_tokens=2000)
        settings.configure(lm=lm)
        browser_agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info("✅ DSPy агент создан")
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Chrome готов" if browser and browser.is_connected else "❌ Chrome не доступен"
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"🤖 Бот готов к работе!\n\n"
        f"🌐 {status}\n"
        f"🧠 {dspy_status}\n\n"
        f"📌 Команды:\n"
        f"/dspy <запрос> — выполнить задачу\n"
        f"/start — информация\n\n"
        f"📝 Пример: /dspy открой google.com и сделай скриншот"
    )

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Напиши задачу после /dspy\nПример: /dspy открой google.com")
        return
    
    query = " ".join(context.args)
    logger.info(f"🧠 Запрос: {query}")
    
    msg = await update.message.reply_text("⏳ Думаю...")
    
    try:
        result = browser_agent(question=query)
        
        if isinstance(result, list):
            answer = result[0] if result else "Нет ответа"
        elif hasattr(result, 'answer'):
            answer = result.answer
        else:
            answer = str(result)
        
        if answer:
            await msg.edit_text(f"✅ {answer[:4000]}")
        else:
            await msg.edit_text("❌ Пустой ответ")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ЗАПУСК ====================
def main():
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Chrome
    if start_chrome():
        # Ждем готовности
        if wait_for_chrome():
            # Инициализируем браузер
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(init_browser())
        else:
            logger.error("❌ Chrome не готов")
    else:
        logger.error("❌ Не удалось запустить Chrome")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()