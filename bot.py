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

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

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
            "--remote-debugging-port=9222"
        ])
        logger.info("✅ Chrome/Chromium запущен (debug port: 9222)")
        return True
    except FileNotFoundError:
        logger.error("❌ Chrome не найден по пути: %s", CHROME_PATH)
        return False
    except Exception as e:
        logger.error("❌ Ошибка запуска Chrome: %s", e)
        return False

# ==================== ПОЛУЧЕНИЕ WEBSOCKET URL ====================
async def get_websocket_url(max_retries=10, delay=1):
    """Получает WebSocket URL с повторными попытками"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:9222/json/list", timeout=3.0)
                pages = resp.json()
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    logger.info(f"✅ WebSocket URL получен: {ws_url}")
                    return ws_url
                else:
                    logger.warning(f"⚠️ Нет страниц (попытка {attempt + 1}/{max_retries})")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка подключения (попытка {attempt + 1}/{max_retries}): {e}")
        
        await asyncio.sleep(delay)
    
    logger.error("❌ Не удалось получить WebSocket URL")
    return None

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ CDP ====================
async def execute_cdp_command(method: str, params: dict = None):
    """Выполняет CDP команду через WebSocket"""
    ws_url = await get_websocket_url()
    if not ws_url:
        return None
    
    try:
        async with websockets.connect(ws_url) as websocket:
            cmd_id = int(time.time() * 1000) % 100000
            command = {"id": cmd_id, "method": method}
            if params:
                command["params"] = params
            
            await websocket.send(json.dumps(command))
            response = await websocket.recv()
            return json.loads(response)
    except Exception as e:
        logger.error(f"❌ CDP ошибка: {e}")
        return None

# ==================== DSPy АДАПТЕР ДЛЯ AGNES AI ====================
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
    """Ты агент с доступом к браузеру через CDP (Chrome DevTools Protocol).
    Используй инструменты для выполнения задач пользователя.
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ==================== ИНСТРУМЕНТЫ ДЛЯ DSPy ====================
def make_tool(func):
    """Декоратор для создания синхронных инструментов"""
    return Tool(func)

# Синхронные обертки для асинхронных функций
def goto_url(url: str) -> str:
    """Перейти на URL"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # Если уже есть event loop, создаем задачу
        future = asyncio.run_coroutine_threadsafe(execute_cdp_command("Page.navigate", {"url": url}), loop)
        result = future.result(timeout=30)
    else:
        # Если нет event loop, запускаем новый
        result = asyncio.run(execute_cdp_command("Page.navigate", {"url": url}))
    
    if result and "result" in result:
        return f"✅ Перешел на {url}"
    return f"❌ Ошибка навигации: {result}"

def capture_screenshot() -> str:
    """Сделать скриншот страницы"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(execute_cdp_command("Page.captureScreenshot"), loop)
        result = future.result(timeout=30)
    else:
        result = asyncio.run(execute_cdp_command("Page.captureScreenshot"))
    
    if result and "result" in result and "data" in result["result"]:
        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        
        # Декодируем base64 и сохраняем
        image_data = base64.b64decode(result["result"]["data"])
        with open(filename, "wb") as f:
            f.write(image_data)
        
        return f"✅ Скриншот сохранен: {filename}"
    return "❌ Не удалось сделать скриншот"

def execute_js(expression: str) -> str:
    """Выполнить JavaScript на странице"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(
            execute_cdp_command("Runtime.evaluate", {"expression": expression}), loop
        )
        result = future.result(timeout=30)
    else:
        result = asyncio.run(execute_cdp_command("Runtime.evaluate", {"expression": expression}))
    
    if result and "result" in result:
        value = result["result"].get("result", {}).get("value", "✅ JS выполнен")
        return str(value)
    return "❌ Ошибка выполнения JS"

def page_info() -> str:
    """Получить информацию о странице"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        url_future = asyncio.run_coroutine_threadsafe(
            execute_cdp_command("Runtime.evaluate", {"expression": "window.location.href"}), loop
        )
        title_future = asyncio.run_coroutine_threadsafe(
            execute_cdp_command("Runtime.evaluate", {"expression": "document.title"}), loop
        )
        url_result = url_future.result(timeout=30)
        title_result = title_future.result(timeout=30)
    else:
        url_result = asyncio.run(execute_cdp_command("Runtime.evaluate", {"expression": "window.location.href"}))
        title_result = asyncio.run(execute_cdp_command("Runtime.evaluate", {"expression": "document.title"}))
    
    url = "unknown"
    title = "unknown"
    
    if url_result and "result" in url_result:
        url = url_result["result"].get("result", {}).get("value", "unknown")
    if title_result and "result" in title_result:
        title = title_result["result"].get("result", {}).get("value", "unknown")
    
    return f"URL: {url}\nTitle: {title}"

# Создаем инструменты
tools = [
    Tool(goto_url),
    Tool(capture_screenshot),
    Tool(execute_js),
    Tool(page_info),
]

# ==================== СОЗДАНИЕ АГЕНТА ====================
def create_browser_agent():
    """Создать ReActV2 агента"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания ReActV2 агента: {e}")
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
        if browser_agent:
            logger.info("✅ BrowserAgent инициализирован")
        else:
            logger.warning("⚠️ Не удалось создать агента")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации DSPy: {e}")
        browser_agent = None
else:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /start"""
    ws_url = await get_websocket_url()
    status = "✅ Chrome готов к работе" if ws_url else "❌ Chrome не доступен"
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"👋 Привет! Бот запущен и работает.\n\n"
        f"{status}\n"
        f"{dspy_status}\n\n"
        f"📌 Доступные команды:\n"
        f"/dspy <запрос> — выполнить задачу через агента\n"
        f"/start — показать это сообщение"
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
            "📝 **Пример использования:**\n"
            "/dspy открыть google.com и сделать скриншот\n"
            "/dspy перейти на youtube.com и показать заголовок",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} запросил: {query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        # Вызываем агента
        result = browser_agent(question=query)
        
        # Обрабатываем результат
        if isinstance(result, list):
            answer = result[0] if result else "Пустой ответ"
        elif hasattr(result, 'answer'):
            answer = result.answer
        else:
            answer = str(result)
        
        if answer and answer.strip():
            from telegram.helpers import escape_markdown
            answer_escaped = escape_markdown(answer[:4000], version=2)
            await status_msg.edit_text(
                f"✅ **Результат:**\n{answer_escaped}",
                parse_mode='MarkdownV2'
            )
        else:
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ЗАПУСК БОТА ====================
def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Chrome
    start_chrome()
    
    # Даём время на запуск
    logger.info("⏳ Ожидание запуска Chrome...")
    time.sleep(3)
    
    # Создаём и настраиваем приложение
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    # Запускаем поллинг
    logger.info("✅ Бот успешно запущен! Ожидание команд...")
    logger.info(f"🧠 DSPy статус: {'✅ Активен (ReActV2)' if browser_agent else '❌ Отключен'}")
    app.run_polling()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    main()