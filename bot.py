# bot.py - Cloud Browser + DSPy (без Browser Harness)
import os
import sys
import asyncio
import logging
import base64
import json
import time
import httpx
import websockets

# ============================================================
# 1. НАСТРОЙКА ЛОГГЕРА
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. ПАПКИ
# ============================================================

SCREENSHOTS_DIR = '/app/screenshots'
LOGS_DIR = '/app/logs'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ============================================================
# 3. ИМПОРТ КУК
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"🍪 Загружено {len(COOKIES)} кук")
except ImportError:
    logger.warning("⚠️ cookies.py не найден, куки не загружены")
    COOKIES = []

# ============================================================
# 4. ТОКЕНЫ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

BROWSER_USE_API_KEY = os.environ.get("BROWSER_USE_API_KEY")
if not BROWSER_USE_API_KEY:
    raise ValueError("❌ BROWSER_USE_API_KEY не задан!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")

# ============================================================
# 5. DSPy ИНТЕГРАЦИЯ
# ============================================================

import warnings
import dspy
from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool

warnings.filterwarnings("ignore")


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
                
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)


# ============================================================
# 6. КЛАСС ДЛЯ РАБОТЫ С ОБЛАЧНЫМ БРАУЗЕРОМ (ПРАВИЛЬНЫЙ API)
# ============================================================

class CloudBrowser:
    """Клиент для облачного браузера Browser Use"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws = None
        self.browser_id = None
        self.cdp_id = 0
        self._connected = False
        self.session_id = None
    
    async def create(self) -> dict:
        """Создать браузер в облаке"""
        logger.info("☁️ Создаю браузер в облаке Browser Use...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Правильный эндпоинт для Browser Use Cloud
            response = await client.post(
                "https://cloud.browser-use.com/api/v1/browser",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "headless": True,
                    "stealth": True,
                    "proxy": True
                }
            )
            
            if response.status_code == 401:
                raise ValueError("❌ Неверный API ключ Browser Use. Проверьте BROWSER_USE_API_KEY")
            
            response.raise_for_status()
            data = response.json()
            
            self.browser_id = data.get("id") or data.get("browser_id")
            self.session_id = data.get("session_id")
            
            # Получаем WebSocket URL
            ws_url = data.get("ws_url") or data.get("webSocketDebuggerUrl")
            
            if not ws_url:
                # Пробуем получить через отдельный эндпоинт
                ws_response = await client.get(
                    f"https://cloud.browser-use.com/api/v1/browser/{self.browser_id}/ws",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                ws_data = ws_response.json()
                ws_url = ws_data.get("ws_url") or ws_data.get("webSocketDebuggerUrl")
            
            if not ws_url:
                raise ValueError("Не получен WebSocket URL")
            
            logger.info(f"✅ Браузер создан: {self.browser_id}")
            logger.info(f"🔗 WebSocket: {ws_url[:50]}...")
            
            # Подключаемся к WebSocket
            await self._connect(ws_url)
            
            return {
                "browser_id": self.browser_id,
                "ws_url": ws_url,
                "session_id": self.session_id
            }
    
    async def _connect(self, ws_url: str):
        """Подключиться к WebSocket"""
        logger.info("🔗 Подключаюсь к WebSocket...")
        self.ws = await websockets.connect(
            ws_url,
            max_size=100 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=60
        )
        self._connected = True
        logger.info("✅ WebSocket подключен")
        
        # Включаем необходимые домены
        await self.send_cdp("Page.enable")
        await self.send_cdp("Runtime.enable")
        await self.send_cdp("Network.enable")
    
    async def send_cdp(self, method: str, params: dict = None) -> dict:
        """Отправить CDP команду"""
        if not self._connected or not self.ws:
            raise RuntimeError("WebSocket не подключен")
        
        self.cdp_id += 1
        msg = {
            "id": self.cdp_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(msg))
        
        # Ждем ответ
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(response)
                if data.get("id") == self.cdp_id:
                    if "error" in data:
                        raise RuntimeError(f"CDP ошибка: {data['error']}")
                    return data.get("result", {})
            except asyncio.TimeoutError:
                raise RuntimeError("Таймаут ожидания CDP ответа")
    
    async def goto(self, url: str) -> dict:
        """Перейти на URL"""
        logger.info(f"🌐 Перехожу на {url}")
        
        try:
            result = await self.send_cdp("Page.navigate", {"url": url})
            
            # Ждем загрузки
            await asyncio.sleep(2)
            
            # Ждем, пока загрузка завершится
            for _ in range(10):
                try:
                    load_result = await self.send_cdp("Runtime.evaluate", {
                        "expression": "document.readyState",
                        "returnByValue": True
                    })
                    state = load_result.get("result", {}).get("value", "")
                    if state == "complete":
                        break
                except:
                    pass
                await asyncio.sleep(0.5)
            
            logger.info(f"✅ Страница загружена: {url}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка перехода: {e}")
            raise
    
    async def get_text(self) -> str:
        """Получить текст страницы"""
        try:
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": "document.body ? document.body.innerText : ''",
                "returnByValue": True
            })
            
            if result and "result" in result and "result" in result["result"]:
                return result["result"]["result"].get("value", "")
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
    async def screenshot(self, path: str = None) -> bytes:
        """Сделать скриншот"""
        try:
            result = await self.send_cdp("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            })
            
            if result and "data" in result:
                data = base64.b64decode(result["data"])
                
                if path:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(data)
                    logger.info(f"📸 Скриншот сохранён в {path}")
                
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    async def click(self, selector: str) -> bool:
        """Кликнуть на элемент"""
        try:
            # Находим координаты элемента
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        return {{
                            x: rect.left + rect.width/2,
                            y: rect.top + rect.height/2
                        }};
                    }})()
                """,
                "returnByValue": True
            })
            
            if result and "result" in result and "result" in result["result"]:
                pos = result["result"]["result"].get("value")
                if pos:
                    await self.send_cdp("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    await asyncio.sleep(0.1)
                    await self.send_cdp("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    logger.info(f"🖱️ Клик на {selector}")
                    return True
            
            logger.warning(f"⚠️ Элемент {selector} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            return False
    
    async def fill(self, selector: str, text: str) -> bool:
        """Заполнить поле"""
        try:
            # Экранируем кавычки
            safe_text = text.replace("'", "\\'").replace('"', '\\"')
            
            await self.send_cdp("Runtime.evaluate", {
                "expression": f"""
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.focus();
                        el.value = '{safe_text}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                """
            })
            logger.info(f"⌨️ Заполнено: {selector} -> {text[:30]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения: {e}")
            return False
    
    async def js(self, expression: str) -> any:
        """Выполнить JavaScript"""
        try:
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True
            })
            
            if result and "result" in result and "result" in result["result"]:
                return result["result"]["result"].get("value")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка JS: {e}")
            return None
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        try:
            url_result = await self.js("document.URL")
            title_result = await self.js("document.title")
            return {
                "url": url_result or "unknown",
                "title": title_result or "unknown"
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации: {e}")
            return {"url": "unknown", "title": "unknown"}
    
    async def close(self):
        """Закрыть браузер"""
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
        
        if self.browser_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        f"https://cloud.browser-use.com/api/v1/browser/{self.browser_id}",
                        headers={"Authorization": f"Bearer {self.api_key}"}
                    )
                logger.info(f"✅ Браузер {self.browser_id} закрыт")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка закрытия браузера: {e}")
        
        self._connected = False


# ============================================================
# 7. ОСНОВНОЙ КЛАСС HarnessBot
# ============================================================

class HarnessBot:
    def __init__(self):
        self.browser = None
        self.is_ready = False
        self.dspy_agent = None
        self.dspy_lm = None
    
    async def start(self):
        """Запуск через облачный браузер Browser Use"""
        logger.info("☁️ Подключение к облачному браузеру Browser Use...")
        
        # Создаем браузер
        self.browser = CloudBrowser(BROWSER_USE_API_KEY)
        await self.browser.create()
        
        # Переходим на страницу
        await self.browser.goto("https://example.com")
        logger.info("✅ Страница загружена")
        
        # Инициализация DSPy
        await self._init_dspy()
        
        self.is_ready = True
        logger.info("✅ HarnessBot готов (облачный режим)!")
        return self
    
    async def _init_dspy(self):
        """Инициализация DSPy с инструментами"""
        if not AGNES_API_KEY:
            logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
            return
        
        try:
            # Инструменты для DSPy
            def tool_goto_url(url: str) -> str:
                """Перейти на URL"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.goto(url),
                        loop
                    )
                    future.result(timeout=30)
                    return f"✅ Перешел на {url}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_screenshot(filename: str = None) -> str:
                """Сделать скриншот"""
                try:
                    if not filename:
                        timestamp = int(time.time())
                        filename = f"screenshot_{timestamp}.png"
                    full_path = os.path.join(SCREENSHOTS_DIR, filename)
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.screenshot(full_path),
                        loop
                    )
                    future.result(timeout=30)
                    return f"✅ Скриншот: {filename}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_page_info() -> str:
                """Информация о странице"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.get_page_info(),
                        loop
                    )
                    info = future.result(timeout=10)
                    return f"URL: {info.get('url')}\nTitle: {info.get('title')}"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_text() -> str:
                """Получить текст страницы"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.get_text(),
                        loop
                    )
                    text = future.result(timeout=10)
                    if text and len(text) > 10:
                        return text[:5000]
                    return "❌ Текст не найден"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_click(selector: str) -> str:
                """Кликнуть на элемент"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.click(selector),
                        loop
                    )
                    result = future.result(timeout=10)
                    return f"✅ Клик на {selector}" if result else f"❌ Элемент {selector} не найден"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_fill(selector: str, text: str) -> str:
                """Заполнить поле"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.fill(selector, text),
                        loop
                    )
                    result = future.result(timeout=10)
                    return f"✅ Заполнено: {selector} -> {text}" if result else f"❌ Элемент {selector} не найден"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_js(expression: str) -> str:
                """Выполнить JavaScript"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.js(expression),
                        loop
                    )
                    result = future.result(timeout=10)
                    return str(result) if result is not None else "✅ JS выполнен"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_links() -> str:
                """Получить ссылки"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.js('Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)'),
                        loop
                    )
                    result = future.result(timeout=10)
                    if isinstance(result, list) and result:
                        links = [str(item) for item in result if item]
                        return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
                    return "❌ Ссылок не найдено"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_get_buttons() -> str:
                """Получить кнопки"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.js('Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())'),
                        loop
                    )
                    result = future.result(timeout=10)
                    if isinstance(result, list) and result:
                        buttons = [str(item).strip() for item in result if item and str(item).strip()]
                        return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
                    return "❌ Кнопок не найдено"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            def tool_scroll(dx: int, dy: int) -> str:
                """Прокрутить"""
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.browser.js(f'window.scrollBy({dx}, {dy})'),
                        loop
                    )
                    future.result(timeout=5)
                    return f"✅ Прокрутка на ({dx}, {dy})"
                except Exception as e:
                    return f"❌ Ошибка: {e}"
            
            tools = [
                Tool(tool_goto_url),
                Tool(tool_screenshot),
                Tool(tool_page_info),
                Tool(tool_get_text),
                Tool(tool_click),
                Tool(tool_fill),
                Tool(tool_js),
                Tool(tool_get_links),
                Tool(tool_get_buttons),
                Tool(tool_scroll),
            ]
            
            # Инициализация DSPy
            lm = AgnesLM(api_key=AGNES_API_KEY, temperature=0.3, max_tokens=2000)
            settings.configure(lm=lm)
            logger.info("✅ DSPy настроен")
            
            # Создаем агента
            try:
                class BrowserSignature(Signature):
                    """Агент с доступом к облачному браузеру"""
                    question = InputField(desc="Задача пользователя")
                    answer = OutputField(desc="Ответ на задачу")
                
                self.dspy_agent = ReActV2(
                    signature=BrowserSignature,
                    tools=tools,
                    max_iters=8,
                )
                logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
            except Exception as e:
                logger.error(f"❌ Ошибка создания агента: {e}")
                self.dspy_agent = None
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации DSPy: {e}")
            self.dspy_agent = None
    
    async def ask_dspy(self, question: str) -> str:
        """Задать вопрос DSPy агенту"""
        if not self.dspy_agent:
            return "❌ DSPy агент не инициализирован"
        
        logger.info(f"🧠 DSPy запрос: {question}")
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.dspy_agent(question=question)
            )
            
            if hasattr(result, 'answer'):
                return result.answer
            return str(result)
            
        except Exception as e:
            logger.error(f"❌ DSPy ошибка: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def close(self):
        """Закрыть браузер"""
        if self.browser:
            await self.browser.close()
        self.is_ready = False


# ============================================================
# 8. TELEGRAM КОМАНДА
# ============================================================

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

bot = None

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /dspy"""
    if not update or not update.message:
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу:\n"
            "`/dspy открыть google.com и сделать скриншот`\n\n"
            "**Примеры:**\n"
            "`/dspy перейти на youtube.com и получить текст`\n"
            "`/dspy нажать на кнопку login`",
            parse_mode='Markdown'
        )
        return
    
    user_query = " ".join(context.args)
    logger.info(f"👤 DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        if not bot or not bot.is_ready:
            await status_msg.edit_text("❌ Бот не готов. Попробуйте позже.")
            return
        
        if not bot.dspy_agent:
            await status_msg.edit_text("❌ DSPy агент не инициализирован. Проверьте AGNES_API_KEY")
            return
        
        answer = await bot.ask_dspy(user_query)
        
        if not answer or not answer.strip():
            await status_msg.edit_text("❌ Пустой ответ от агента")
            return
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# 9. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен! Команда: /dspy")
    logger.info(f"🧠 DSPy: {'✅ Активен' if bot.dspy_agent else '❌ Отключен'}")
    logger.info(f"☁️ Браузер: Облачный Browser Use")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(60)
        logger.info("💓 Bot alive")


if __name__ == "__main__":
    asyncio.run(main())