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
import concurrent.futures
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

# ==================== НАСТРОЙКА ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

# ==================== ЗАПУСК CHROME ====================
CHROME_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]

def find_chrome():
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None

def start_chrome():
    chrome_path = find_chrome()
    if not chrome_path:
        logger.error("❌ Chrome не найден!")
        return False
    
    try:
        # Убиваем старые процессы
        subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
        time.sleep(2)
        
        # Запускаем с минимальными параметрами
        subprocess.Popen([
            chrome_path,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=9222",
            "--window-size=1280,720",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info(f"✅ Chrome запущен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def wait_for_chrome(max_attempts=20, delay=1):
    for attempt in range(max_attempts):
        try:
            # Проверяем порт
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 9222))
            sock.close()
            
            if result == 0:
                # Проверяем /json/list
                response = httpx.get("http://localhost:9222/json/list", timeout=2.0)
                if response.status_code == 200:
                    pages = response.json()
                    if pages:
                        logger.info(f"✅ Chrome готов")
                        return True
                    else:
                        # Создаем страницу
                        httpx.get("http://localhost:9222/json/new", timeout=2.0)
                        return True
                    
            logger.info(f"⏳ Ожидание Chrome... ({attempt + 1}/{max_attempts})")
        except Exception as e:
            logger.debug(f"⚠️ {e}")
        
        time.sleep(delay)
    
    logger.error("❌ Chrome не запустился")
    return False

# ==================== ПРОСТОЙ CDP КЛИЕНТ ====================
class SimpleCDPClient:
    def __init__(self):
        self.ws = None
        self.is_connected = False
        self.msg_id = 0
        
    async def connect(self):
        try:
            # Получаем WebSocket URL
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:9222/json/list", timeout=5.0)
                pages = resp.json()
                
                if not pages:
                    resp = await client.get("http://localhost:9222/json/new", timeout=5.0)
                    pages = [resp.json()]
                
                ws_url = pages[0]["webSocketDebuggerUrl"]
                logger.info(f"✅ WebSocket URL: {ws_url}")
            
            # Подключаемся
            self.ws = await websockets.connect(ws_url)
            self.is_connected = True
            logger.info("✅ Подключено к Chrome")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def send_command(self, method, params=None, timeout=10.0):
        """Отправить команду и получить ответ"""
        if not self.is_connected:
            raise Exception("Не подключено")
        
        self.msg_id += 1
        cmd = {"id": self.msg_id, "method": method}
        if params:
            cmd["params"] = params
        
        try:
            # Отправляем
            await self.ws.send(json.dumps(cmd))
            
            # Ждем ответ
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
                data = json.loads(response)
                
                if data.get("id") == self.msg_id:
                    if "error" in data:
                        raise Exception(f"CDP ошибка: {data['error']}")
                    return data.get("result", {})
                    
        except asyncio.TimeoutError:
            raise Exception(f"Таймаут {method}")
        except Exception as e:
            raise Exception(f"Ошибка: {e}")
    
    async def navigate(self, url):
        """Перейти по URL"""
        try:
            # Проверяем URL
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            # Навигация
            result = await self.send_command("Page.navigate", {"url": url}, timeout=10.0)
            
            if "errorText" in result:
                return {"success": False, "error": result["errorText"]}
            
            # Ждем загрузки
            await self.wait_for_load()
            
            return {"success": True, "url": url}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def wait_for_load(self, timeout=10.0):
        """Ждем загрузки"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = await self.send_command("Runtime.evaluate", {
                    "expression": "document.readyState"
                }, timeout=3.0)
                
                state = result.get("result", {}).get("value", "loading")
                if state == "complete":
                    logger.info("✅ Страница загружена")
                    return True
                    
            except Exception as e:
                logger.debug(f"⚠️ {e}")
            
            await asyncio.sleep(0.3)
        
        return False
    
    async def screenshot(self, filename=None):
        """Сделать скриншот"""
        try:
            result = await self.send_command("Page.captureScreenshot", {
                "format": "png"
            }, timeout=10.0)
            
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            
            data = base64.b64decode(result["data"])
            with open(filename, "wb") as f:
                f.write(data)
            
            return {"success": True, "filename": filename}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, script):
        """Выполнить JS"""
        try:
            result = await self.send_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True
            }, timeout=10.0)
            
            value = result.get("result", {}).get("value")
            return {"success": True, "result": value}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_info(self):
        """Информация о странице"""
        try:
            url_result = await self.evaluate("window.location.href")
            title_result = await self.evaluate("document.title")
            
            url = url_result.get("result", "unknown") if url_result.get("success") else "unknown"
            title = title_result.get("result", "unknown") if title_result.get("success") else "unknown"
            
            return {"success": True, "url": url, "title": title}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def close(self):
        if self.ws:
            await self.ws.close()
        self.is_connected = False

# ==================== ГЛОБАЛЬНЫЙ КЛИЕНТ ====================
browser = None

async def init_browser():
    global browser
    browser = SimpleCDPClient()
    return await browser.connect()

# ==================== DSPy ====================
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
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            return ["Ошибка: нет API ключа"]
        
        api_messages = messages or [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": 0.3,
            "max_tokens": 2000
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
                if "choices" in data:
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ"]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ==================== ИНСТРУМЕНТЫ ====================
def run_async(coro):
    """Запуск асинхронной функции"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=30)
    except RuntimeError:
        return asyncio.run(coro)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=30)
    except:
        return asyncio.run(coro)

def goto_url(url: str) -> str:
    """Открыть URL"""
    try:
        result = run_async(browser.navigate(url))
        if result.get("success"):
            return f"✅ Открыл {url}"
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def capture_screenshot() -> str:
    """Сделать скриншот"""
    try:
        filename = f"screenshot_{int(time.time())}.png"
        result = run_async(browser.screenshot(filename))
        if result.get("success"):
            return f"✅ Скриншот: {filename}"
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def execute_js(script: str) -> str:
    """Выполнить JavaScript"""
    try:
        result = run_async(browser.evaluate(script))
        if result.get("success"):
            return str(result.get("result", "✅ Выполнено"))
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def page_info() -> str:
    """Информация о странице"""
    try:
        result = run_async(browser.get_info())
        if result.get("success"):
            return f"URL: {result['url']}\nЗаголовок: {result['title']}"
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

tools = [
    Tool(goto_url),
    Tool(capture_screenshot),
    Tool(execute_js),
    Tool(page_info),
]

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
browser_agent = None
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

if AGNES_API_KEY:
    try:
        lm = AgnesLM(api_key=AGNES_API_KEY)
        settings.configure(lm=lm)
        browser_agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=5,
        )
        logger.info("✅ DSPy агент создан")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Chrome готов" if browser and browser.is_connected else "❌ Chrome не доступен"
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"🤖 Бот готов!\n\n"
        f"🌐 {status}\n"
        f"🧠 {dspy_status}\n\n"
        f"/dspy <запрос> — выполнить задачу\n"
        f"/start — информация\n\n"
        f"📝 Пример: /dspy открой google.com"
    )

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Напиши задачу после /dspy")
        return
    
    query = " ".join(context.args)
    logger.info(f"🧠 Запрос: {query}")
    
    msg = await update.message.reply_text("⏳ Думаю...")
    
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            def run_agent():
                return browser_agent(question=query)
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(executor, run_agent)
        
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
        if wait_for_chrome():
            # Инициализируем браузер
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(init_browser())
            if success:
                logger.info("✅ Браузер готов")
            else:
                logger.error("❌ Браузер не готов")
        else:
            logger.error("❌ Chrome не готов")
    else:
        logger.error("❌ Не удалось запустить Chrome")
    
    # Бот
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()