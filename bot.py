import os
import logging
import subprocess
import asyncio
import httpx
import websockets
import json
import base64
import time
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
CHROME_PATH = "/usr/bin/chromium"

def start_chrome():
    """Запускает Chromium в headless-режиме с удалённой отладкой"""
    try:
        subprocess.Popen([
            CHROME_PATH,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=9222",
            "--window-size=1280,720"
        ])
        logger.info("✅ Chrome/Chromium запущен (debug port: 9222)")
        return True
    except FileNotFoundError:
        logger.error("❌ Chrome не найден по пути: %s", CHROME_PATH)
        return False
    except Exception as e:
        logger.error("❌ Ошибка запуска Chrome: %s", e)
        return False

# ==================== CDP КЛИЕНТ (ПОДХОД PYDOLL) ====================
class CDPClient:
    """Клиент для работы с Chrome DevTools Protocol (подход pydoll)"""
    
    def __init__(self):
        self.ws = None
        self.ws_url = None
        self.is_connected = False
        self.message_id = 0
        self.pending_requests = {}
        self.event_handlers = {}
        
    async def connect(self, max_retries=10, delay=1):
        """Подключение к Chrome через WebSocket"""
        # Получаем WebSocket URL
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get("http://localhost:9222/json/list", timeout=3.0)
                    pages = resp.json()
                    if pages:
                        self.ws_url = pages[0]["webSocketDebuggerUrl"]
                        break
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries}: {e}")
            
            await asyncio.sleep(delay)
        else:
            logger.error("❌ Не удалось получить WebSocket URL")
            return False
        
        # Подключаемся к WebSocket
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.is_connected = True
            logger.info("✅ Подключение к Chrome через WebSocket установлено")
            
            # Включаем необходимые домены
            await self.send_command("Network.enable")
            await self.send_command("Page.enable")
            await self.send_command("Runtime.enable")
            await self.send_command("DOM.enable")
            
            # Запускаем обработчик событий
            asyncio.create_task(self._handle_events())
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def send_command(self, method: str, params: dict = None):
        """Отправить CDP команду"""
        if not self.is_connected:
            raise Exception("Не подключено к браузеру")
        
        self.message_id += 1
        cmd_id = self.message_id
        
        command = {
            "id": cmd_id,
            "method": method
        }
        if params:
            command["params"] = params
        
        # Отправляем команду
        await self.ws.send(json.dumps(command))
        
        # Ожидаем ответ
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(response)
                
                # Если это ответ на нашу команду
                if data.get("id") == cmd_id:
                    if "error" in data:
                        raise Exception(f"CDP ошибка: {data['error']}")
                    return data.get("result", {})
                
                # Если это событие - обрабатываем отдельно
                if "method" in data:
                    await self._handle_event(data)
                    
            except asyncio.TimeoutError:
                raise Exception("Таймаут ожидания ответа от CDP")
    
    async def _handle_events(self):
        """Обработчик событий CDP"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    if "method" in data:
                        await self._handle_event(data)
                except json.JSONDecodeError:
                    continue
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ Соединение с WebSocket закрыто")
            self.is_connected = False
        except Exception as e:
            logger.error(f"❌ Ошибка обработки событий: {e}")
    
    async def _handle_event(self, event):
        """Обработка конкретного события"""
        method = event.get("method")
        params = event.get("params", {})
        
        # Логируем важные события
        if method == "Page.loadEventFired":
            logger.info("✅ Событие Page.loadEventFired")
        elif method == "Page.domContentEventFired":
            logger.info("✅ Событие Page.domContentEventFired")
        elif method == "Network.requestWillBeSent":
            logger.debug(f"🌐 Запрос: {params.get('request', {}).get('url', 'unknown')}")
        elif method == "Network.responseReceived":
            logger.debug(f"📥 Ответ: {params.get('response', {}).get('url', 'unknown')}")
        
        # Вызываем зарегистрированные обработчики
        if method in self.event_handlers:
            for handler in self.event_handlers[method]:
                await handler(params)
    
    def on(self, event_name: str):
        """Декоратор для регистрации обработчика событий"""
        def decorator(handler):
            if event_name not in self.event_handlers:
                self.event_handlers[event_name] = []
            self.event_handlers[event_name].append(handler)
            return handler
        return decorator
    
    # ==================== МЕТОДЫ ЗАГРУЗКИ СТРАНИЦ (ПОДХОД PYDOLL) ====================
    
    async def goto_url(self, url: str, timeout: int = 30):
        """Переход по URL с полным ожиданием загрузки"""
        try:
            logger.info(f"🚀 Навигация: {url}")
            
            # Отправляем команду навигации с таймаутом
            result = await asyncio.wait_for(
                self.send_command("Page.navigate", {"url": url}),
                timeout=timeout
            )
            
            # Проверяем ошибку навигации
            if "errorText" in result:
                raise Exception(f"Ошибка навигации: {result['errorText']}")
            
            logger.info("✅ Навигация завершена")
            
            # Ждем загрузки страницы
            await self.wait_for_load()
            
            return {"success": True, "url": url}
            
        except asyncio.TimeoutError:
            raise Exception(f"Таймаут загрузки {url}")
        except Exception as e:
            raise Exception(f"Ошибка загрузки: {e}")
    
    async def wait_for_load(self, timeout: int = 30):
        """Ожидание полной загрузки страницы"""
        try:
            # Ждем событие DOM Content Loaded
            logger.info("⏳ Ожидание DOM Content Loaded...")
            await asyncio.wait_for(
                self._wait_for_event("Page.domContentEventFired"),
                timeout=timeout
            )
            logger.info("✅ DOM Content Loaded")
            
            # Ждем событие полной загрузки
            logger.info("⏳ Ожидание полной загрузки...")
            await asyncio.wait_for(
                self._wait_for_event("Page.loadEventFired"),
                timeout=timeout
            )
            logger.info("✅ Страница полностью загружена")
            
            # Дополнительно ждем готовности документа
            await self.wait_for_ready_state()
            
            # Ждем завершения сетевых запросов
            await self.wait_for_network_idle()
            
            # Небольшая задержка для рендеринга
            await asyncio.sleep(1)
            
            logger.info("✅ Все ресурсы загружены")
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Таймаут ожидания загрузки")
        except Exception as e:
            logger.error(f"❌ Ошибка ожидания загрузки: {e}")
    
    async def _wait_for_event(self, event_name: str, timeout: int = 30):
        """Ожидание конкретного события"""
        future = asyncio.Future()
        
        def handler(params):
            if not future.done():
                future.set_result(params)
        
        # Регистрируем обработчик
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(handler)
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            # Удаляем обработчик
            if event_name in self.event_handlers:
                self.event_handlers[event_name].remove(handler)
    
    async def wait_for_ready_state(self, timeout: int = 10):
        """Ожидание готовности документа"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = await self.send_command("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                ready_state = result.get("result", {}).get("value", "loading")
                
                if ready_state == "complete":
                    logger.info(f"✅ document.readyState = {ready_state}")
                    return True
                
                logger.debug(f"⏳ document.readyState = {ready_state}")
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"⚠️ Ошибка проверки readyState: {e}")
                await asyncio.sleep(0.1)
        
        logger.warning("⚠️ Таймаут ожидания readyState = complete")
        return False
    
    async def wait_for_network_idle(self, timeout: int = 5):
        """Ожидание завершения сетевых запросов"""
        try:
            # Получаем количество активных запросов через CDP
            result = await self.send_command("Network.getPendingRequests")
            pending = result.get("pendingRequests", [])
            
            start_time = time.time()
            while pending and (time.time() - start_time) < timeout:
                logger.debug(f"⏳ Активных запросов: {len(pending)}")
                await asyncio.sleep(0.5)
                result = await self.send_command("Network.getPendingRequests")
                pending = result.get("pendingRequests", [])
            
            if pending:
                logger.warning(f"⚠️ Осталось активных запросов: {len(pending)}")
            else:
                logger.info("✅ Все сетевые запросы завершены")
                
        except Exception as e:
            logger.debug(f"⚠️ Ошибка проверки сети: {e}")
    
    async def wait_for_element(self, selector: str, timeout: int = 10):
        """Ожидание появления элемента на странице"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = await self.send_command("Runtime.evaluate", {
                    "expression": f"document.querySelector('{selector}') !== null"
                })
                exists = result.get("result", {}).get("value", False)
                
                if exists:
                    logger.info(f"✅ Элемент '{selector}' найден")
                    return True
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"⚠️ Ошибка поиска элемента: {e}")
                await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Элемент '{selector}' не найден за {timeout}с")
    
    async def wait_for_url(self, expected_url: str, timeout: int = 10):
        """Ожидание конкретного URL"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = await self.send_command("Runtime.evaluate", {
                    "expression": "window.location.href"
                })
                current_url = result.get("result", {}).get("value", "")
                
                if current_url == expected_url:
                    logger.info(f"✅ URL соответствует: {expected_url}")
                    return True
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"⚠️ Ошибка проверки URL: {e}")
                await asyncio.sleep(0.1)
        
        return False
    
    async def load_page(self, url: str, wait_for_selector: str = None, timeout: int = 30):
        """Полная загрузка страницы (комбинированный подход)"""
        try:
            # 1. Навигация
            await self.goto_url(url, timeout)
            
            # 2. Ждем готовности DOM
            await self.wait_for_ready_state()
            
            # 3. Ждем завершения сети
            await self.wait_for_network_idle()
            
            # 4. Если указан селектор - ждем его появления
            if wait_for_selector:
                await self.wait_for_element(wait_for_selector, timeout)
            
            # 5. Дополнительная задержка для анимаций/рендеринга
            await asyncio.sleep(1)
            
            logger.info(f"✅ Страница {url} полностью загружена")
            return {"success": True, "url": url}
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== ДРУГИЕ МЕТОДЫ ====================
    
    async def capture_screenshot(self, filename: str = None):
        """Сделать скриншот"""
        try:
            result = await self.send_command("Page.captureScreenshot")
            
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            
            # Декодируем base64 и сохраняем
            image_data = base64.b64decode(result["data"])
            with open(filename, "wb") as f:
                f.write(image_data)
            
            logger.info(f"✅ Скриншот сохранен: {filename}")
            return {"success": True, "filename": filename}
            
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return {"success": False, "error": str(e)}
    
    async def execute_js(self, script: str):
        """Выполнить JavaScript"""
        try:
            result = await self.send_command("Runtime.evaluate", {
                "expression": script
            })
            
            value = result.get("result", {}).get("value")
            logger.info(f"✅ JS выполнен: {script[:50]}...")
            return {"success": True, "result": value}
            
        except Exception as e:
            logger.error(f"❌ Ошибка JS: {e}")
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
            
            return {
                "success": True,
                "url": url,
                "title": title
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации: {e}")
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Закрыть соединение"""
        try:
            if self.ws:
                await self.ws.close()
            self.is_connected = False
            logger.info("✅ Соединение закрыто")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия: {e}")

# ==================== ГЛОБАЛЬНЫЙ ИНСТАНС ====================
browser = None

async def init_browser():
    """Инициализация браузера"""
    global browser
    browser = CDPClient()
    await browser.connect()
    return browser

# ==================== DSPy АДАПТЕР ====================
class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI"""
    
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
            logger.error("❌ AGNES_API_KEY не задан")
            return ["Ошибка: API ключ не задан"]
        
        params = {**self.kwargs, **kwargs}
        
        if messages:
            api_messages = messages
        else:
            api_messages = [{"role": "user", "content": prompt or ""}]
        
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
                    result = data["choices"][0]["message"]["content"]
                    return [result]
                return ["Ошибка: пустой ответ от API"]
                
        except httpx.TimeoutException:
            return ["Ошибка: таймаут API (60 сек)"]
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ==================== СИГНАТУРА DSPy ====================
class BrowserTask(Signature):
    """Ты агент с доступом к браузеру через CDP.
    Используй инструменты для выполнения задач пользователя.
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ==================== ИНСТРУМЕНТЫ ДЛЯ DSPy ====================
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
    """Перейти на URL с полным ожиданием загрузки"""
    try:
        result = sync_run_async(browser.load_page(url))
        if result.get("success"):
            return f"✅ Страница {url} полностью загружена"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def capture_screenshot() -> str:
    """Сделать скриншот страницы"""
    try:
        filename = f"screenshot_{int(time.time())}.png"
        result = sync_run_async(browser.capture_screenshot(filename))
        if result.get("success"):
            return f"✅ Скриншот сохранен: {filename}"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def execute_js(script: str) -> str:
    """Выполнить JavaScript на странице"""
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
            return f"URL: {result['url']}\nTitle: {result['title']}"
        return f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def wait_for_element(selector: str, timeout: int = 10) -> str:
    """Ожидать появление элемента"""
    try:
        sync_run_async(browser.wait_for_element(selector, timeout))
        return f"✅ Элемент '{selector}' появился"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# Создаем инструменты
tools = [
    Tool(goto_url),
    Tool(capture_screenshot),
    Tool(execute_js),
    Tool(page_info),
    Tool(wait_for_element),
]

# ==================== СОЗДАНИЕ АГЕНТА ====================
def create_browser_agent():
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")
        return None

# ==================== ТОКЕН БОТА ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

# ==================== ИНИЦИАЛИЗАЦИЯ DSPy ====================
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
browser_agent = None

if AGNES_API_KEY:
    try:
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000
        )
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        browser_agent = create_browser_agent()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации DSPy: {e}")
        browser_agent = None
else:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /start"""
    status = "✅ Chrome готов к работе" if browser and browser.is_connected else "❌ Chrome не доступен"
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"👋 Привет! Бот запущен и работает.\n\n"
        f"{status}\n"
        f"{dspy_status}\n\n"
        f"📌 Доступные команды:\n"
        f"/dspy <запрос> — выполнить задачу через агента\n"
        f"/start — показать это сообщение\n\n"
        f"🔧 Агент умеет:\n"
        f"• Загружать страницы с полным ожиданием\n"
        f"• Делать скриншоты\n"
        f"• Выполнять JavaScript\n"
        f"• Ожидать элементы\n"
        f"• Получать информацию о странице"
    )

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
    if not browser_agent:
        await update.message.reply_text(
            "❌ DSPy не инициализирован.\n"
            "Проверьте AGNES_API_KEY"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 **Примеры использования:**\n"
            "/dspy открыть google.com и сделать скриншот\n"
            "/dspy перейти на youtube.com и показать заголовок\n"
            "/dspy загрузить страницу и подождать кнопку 'login'",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} запросил: {query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        result = browser_agent(question=query)
        
        if isinstance(result, list):
            answer = result[0] if result else "Пустой ответ"
        elif hasattr(result, 'answer'):
            answer = result.answer
        else:
            answer = str(result)
        
        if answer and answer.strip():
            answer_escaped = escape_markdown(answer[:4000], version=2)
            await status_msg.edit_text(
                f"✅ **Результат:**\n{answer_escaped}",
                parse_mode='MarkdownV2'
            )
        else:
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ЗАПУСК БОТА ====================
def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Chrome
    start_chrome()
    time.sleep(3)
    
    # Инициализируем браузер
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_browser())
    
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    # Запускаем поллинг
    logger.info("✅ Бот успешно запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if browser_agent else '❌ Отключен'}")
    logger.info(f"🌐 Браузер статус: {'✅ Подключен' if browser and browser.is_connected else '❌ Отключен'}")
    app.run_polling()

if __name__ == "__main__":
    main()