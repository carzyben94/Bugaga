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

# ==================== ЗАПУСК CHROME ====================
CHROME_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium"
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
        subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
        time.sleep(2)
        
        subprocess.Popen([
            chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--remote-debugging-port=9222",
            "--remote-debugging-address=0.0.0.0",
            "--window-size=1280,720",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info(f"✅ Chrome запущен ({chrome_path})")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Chrome: {e}")
        return False

def wait_for_chrome(max_attempts=15, delay=1):
    for attempt in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 9222))
            sock.close()
            
            if result == 0:
                try:
                    response = httpx.get("http://localhost:9222/json/list", timeout=3.0)
                    if response.status_code == 200:
                        pages = response.json()
                        if pages:
                            logger.info(f"✅ Chrome готов")
                            return True
                        else:
                            httpx.get("http://localhost:9222/json/new", timeout=3.0)
                            return True
                except:
                    pass
                    
            logger.info(f"⏳ Ожидание Chrome... ({attempt + 1}/{max_attempts})")
        except:
            pass
        
        time.sleep(delay)
    
    logger.error("❌ Chrome не запустился")
    return False

# ==================== CDP КЛИЕНТ ====================
class CDPClient:
    def __init__(self):
        self.ws = None
        self.ws_url = None
        self.is_connected = False
        self.message_id = 0
        self._response_futures = {}
        
    async def connect(self):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("http://localhost:9222/json/list")
                pages = resp.json()
                
                if not pages:
                    resp = await client.get("http://localhost:9222/json/new")
                    pages = [resp.json()]
                
                self.ws_url = pages[0]["webSocketDebuggerUrl"]
                logger.info(f"✅ WebSocket URL: {self.ws_url}")
            
            self.ws = await websockets.connect(self.ws_url)
            self.is_connected = True
            logger.info("✅ Подключение к Chrome установлено")
            
            await self.send_command("Network.enable")
            await self.send_command("Page.enable")
            await self.send_command("Runtime.enable")
            
            await self.send_command("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            
            asyncio.create_task(self._handle_messages())
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def _handle_messages(self):
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    msg_id = data.get("id")
                    
                    if msg_id and msg_id in self._response_futures:
                        future = self._response_futures.pop(msg_id)
                        if not future.done():
                            future.set_result(data)
                            
                except json.JSONDecodeError:
                    continue
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ Соединение закрыто")
            self.is_connected = False
        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}")
    
    async def send_command(self, method: str, params: dict = None, timeout: float = 10.0):
        if not self.is_connected or not self.ws:
            raise Exception("Не подключено к браузеру")
        
        self.message_id += 1
        cmd_id = self.message_id
        
        command = {"id": cmd_id, "method": method}
        if params:
            command["params"] = params
        
        future = asyncio.Future()
        self._response_futures[cmd_id] = future
        
        try:
            await self.ws.send(json.dumps(command))
            response = await asyncio.wait_for(future, timeout=timeout)
            
            if "error" in response:
                raise Exception(f"CDP ошибка: {response['error']}")
            
            return response.get("result", {})
            
        except asyncio.TimeoutError:
            self._response_futures.pop(cmd_id, None)
            raise Exception(f"Таймаут ({timeout}с) команды {method}")
        except Exception as e:
            self._response_futures.pop(cmd_id, None)
            raise Exception(f"Ошибка: {e}")
    
    async def load_page(self, url: str, timeout: float = 15.0):
        try:
            logger.info(f"🚀 Загрузка: {url}")
            
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            result = await asyncio.wait_for(
                self.send_command("Page.navigate", {"url": url}),
                timeout=timeout
            )
            
            if "errorText" in result:
                raise Exception(f"Ошибка: {result['errorText']}")
            
            await self._wait_for_load(timeout=10.0)
            
            return {"success": True, "url": url}
            
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Таймаут загрузки {url}"}
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return {"success": False, "error": str(e)}
    
    async def _wait_for_load(self, timeout=10.0):
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = await asyncio.wait_for(
                    self.send_command("Runtime.evaluate", {
                        "expression": "document.readyState"
                    }),
                    timeout=3.0
                )
                ready_state = result.get("result", {}).get("value", "loading")
                
                if ready_state == "complete":
                    logger.info("✅ Страница загружена")
                    return True
                    
            except Exception as e:
                logger.debug(f"⚠️ {e}")
            
            await asyncio.sleep(0.3)
        
        logger.warning("⚠️ Таймаут ожидания загрузки")
        return False
    
    async def capture_screenshot(self, filename: str = None):
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
        try:
            if self.ws:
                await self.ws.close()
            self.is_connected = False
        except:
            pass

# ==================== ГЛОБАЛЬНЫЙ ИНСТАНС ====================
browser = None

async def init_browser():
    global browser
    browser = CDPClient()
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
                return ["Ошибка: пустой ответ"]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ==================== ИНСТРУМЕНТЫ ====================
def sync_run_async(coro, timeout=30):
    """Запустить асинхронную функцию синхронно"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
    except:
        return asyncio.run(coro)

def goto_url(url: str) -> str:
    try:
        result = sync_run_async(browser.load_page(url, timeout=15.0), timeout=20)
        if result.get("success"):
            return f"✅ Открыл {url}"
        return f"❌ {result.get('error', 'Ошибка')}"
    except asyncio.TimeoutError:
        return "❌ Таймаут загрузки страницы"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def capture_screenshot() -> str:
    try:
        filename = f"screenshot_{int(time.time())}.png"
        result = sync_run_async(browser.capture_screenshot(filename), timeout=10)
        if result.get("success"):
            return f"✅ Скриншот: {filename}"
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def execute_js(script: str) -> str:
    try:
        result = sync_run_async(browser.execute_js(script), timeout=10)
        if result.get("success"):
            return str(result.get("result", "✅ Выполнено"))
        return f"❌ {result.get('error', 'Ошибка')}"
    except Exception as e:
        return f"❌ {str(e)[:100]}"

def page_info() -> str:
    try:
        result = sync_run_async(browser.get_page_info(), timeout=10)
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
        lm = AgnesLM(api_key=AGNES_API_KEY, temperature=0.3, max_tokens=2000)
        settings.configure(lm=lm)
        browser_agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=5,
        )
        logger.info("✅ DSPy агент создан")
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")

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
        # Правильный способ вызвать агента в отдельном потоке
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Создаем функцию для выполнения в потоке
            def run_agent():
                return browser_agent(question=query)
            
            # Запускаем в потоке с таймаутом
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor, 
                run_agent
            )
        
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
            
    except asyncio.TimeoutError:
        await msg.edit_text("❌ Таймаут выполнения (слишком долго)")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ЗАПУСК ====================
def main():
    logger.info("🚀 Запуск бота...")
    
    if start_chrome():
        if wait_for_chrome():
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
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()