# bot.py - Cloud Browser Use с правильными API v2/v3
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
# 3. ТОКЕНЫ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

BROWSER_USE_API_KEY = os.environ.get("BROWSER_USE_API_KEY")
if not BROWSER_USE_API_KEY:
    raise ValueError("❌ BROWSER_USE_API_KEY не задан!")

# ============================================================
# 4. КЛАСС ДЛЯ РАБОТЫ С ОБЛАЧНЫМ БРАУЗЕРОМ (v3 API)
# ============================================================

class CloudBrowser:
    """Клиент для облачного браузера Browser Use (v3 API)"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws = None
        self.browser_id = None
        self.cdp_id = 0
        self._connected = False
        self.base_url = "https://api.browser-use.com"  # Правильный домен!
    
    async def create(self) -> dict:
        """Создать браузер в облаке (v3 API)"""
        logger.info("☁️ Создаю браузер в облаке Browser Use (v3)...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v3/browsers",  # Правильный эндпоинт
                headers={
                    "X-Browser-Use-API-Key": self.api_key,  # Правильный заголовок!
                    "Content-Type": "application/json"
                },
                json={
                    "headless": True,
                    "stealth": True,
                    "proxy": True,
                    "keep_alive": True
                }
            )
            
            if response.status_code == 401:
                raise ValueError("❌ Неверный API ключ Browser Use")
            
            response.raise_for_status()
            data = response.json()
            
            self.browser_id = data.get("id") or data.get("browser_id")
            ws_url = data.get("ws_url") or data.get("webSocketDebuggerUrl")
            
            if not ws_url:
                # Пробуем получить через отдельный эндпоинт
                ws_response = await client.get(
                    f"{self.base_url}/api/v3/browsers/{self.browser_id}/ws",
                    headers={"X-Browser-Use-API-Key": self.api_key}
                )
                ws_data = ws_response.json()
                ws_url = ws_data.get("ws_url")
            
            if not ws_url:
                raise ValueError("Не получен WebSocket URL")
            
            logger.info(f"✅ Браузер создан: {self.browser_id}")
            logger.info(f"🔗 WebSocket: {ws_url[:60]}...")
            
            await self._connect(ws_url)
            
            return {
                "browser_id": self.browser_id,
                "ws_url": ws_url
            }
    
    async def create_task(self, task: str) -> dict:
        """Создать задачу (v2 API) - альтернативный способ"""
        logger.info(f"📝 Создаю задачу: {task[:50]}...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v2/tasks",
                headers={
                    "X-Browser-Use-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "task": task,
                    "headless": True,
                    "stealth": True,
                    "proxy": True
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"✅ Задача создана: {data.get('id')}")
            return data
    
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
        
        # Включаем CDP домены
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
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(response)
                if data.get("id") == self.cdp_id:
                    if "error" in data:
                        raise RuntimeError(f"CDP ошибка: {data['error']}")
                    return data.get("result", {})
            except asyncio.TimeoutError:
                raise RuntimeError("Таймаут CDP")
    
    async def goto(self, url: str) -> dict:
        """Перейти на URL"""
        logger.info(f"🌐 Перехожу на {url}")
        
        result = await self.send_cdp("Page.navigate", {"url": url})
        
        # Ждем загрузки
        for _ in range(20):
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
        
        logger.info(f"✅ Страница загружена")
        return result
    
    async def get_text(self) -> str:
        """Получить текст"""
        try:
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": "document.body ? document.body.innerText : ''",
                "returnByValue": True
            })
            return result.get("result", {}).get("value", "")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
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
                    logger.info(f"📸 Скриншот: {path}")
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    async def click(self, selector: str) -> bool:
        """Кликнуть"""
        try:
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        return {{ x: rect.left + rect.width/2, y: rect.top + rect.height/2 }};
                    }})()
                """,
                "returnByValue": True
            })
            
            pos = result.get("result", {}).get("value")
            if pos:
                await self.send_cdp("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": pos["x"], "y": pos["y"],
                    "button": "left", "clickCount": 1
                })
                await asyncio.sleep(0.1)
                await self.send_cdp("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": pos["x"], "y": pos["y"],
                    "button": "left", "clickCount": 1
                })
                logger.info(f"🖱️ Клик на {selector}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def fill(self, selector: str, text: str) -> bool:
        """Заполнить поле"""
        try:
            safe_text = text.replace("'", "\\'").replace('"', '\\"')
            await self.send_cdp("Runtime.evaluate", {
                "expression": f"""
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.focus();
                        el.value = '{safe_text}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                """
            })
            logger.info(f"⌨️ Заполнено: {selector}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    async def js(self, expression: str) -> any:
        """Выполнить JS"""
        try:
            result = await self.send_cdp("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True
            })
            return result.get("result", {}).get("value")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        try:
            url = await self.js("document.URL")
            title = await self.js("document.title")
            return {"url": url or "unknown", "title": title or "unknown"}
        except Exception as e:
            return {"url": "unknown", "title": "unknown"}
    
    async def close(self):
        """Закрыть браузер"""
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        
        if self.browser_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        f"{self.base_url}/api/v3/browsers/{self.browser_id}",
                        headers={"X-Browser-Use-API-Key": self.api_key}
                    )
                logger.info(f"✅ Браузер {self.browser_id} закрыт")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка: {e}")
        
        self._connected = False


# ============================================================
# 5. ОСНОВНОЙ КЛАСС БОТА
# ============================================================

class HarnessBot:
    def __init__(self):
        self.browser = None
        self.is_ready = False
    
    async def start(self):
        """Запуск"""
        logger.info("☁️ Подключение к облачному браузеру Browser Use...")
        
        self.browser = CloudBrowser(BROWSER_USE_API_KEY)
        await self.browser.create()
        
        # Переходим на страницу
        await self.browser.goto("https://example.com")
        
        self.is_ready = True
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def ask(self, question: str) -> str:
        """Выполнить задачу"""
        if not self.browser:
            return "❌ Браузер не готов"
        
        logger.info(f"🧠 Выполняю: {question}")
        
        try:
            q_lower = question.lower()
            
            if "скриншот" in q_lower:
                timestamp = int(time.time())
                path = f"/app/screenshots/result_{timestamp}.png"
                await self.browser.screenshot(path)
                return f"✅ Скриншот: result_{timestamp}.png"
            
            if "перейти" in q_lower or "открыть" in q_lower:
                import re
                url_match = re.search(r'(https?://[^\s]+)', question)
                if url_match:
                    url = url_match.group(1)
                    await self.browser.goto(url)
                    return f"✅ Перешел на {url}"
                return "❌ URL не найден"
            
            if "текст" in q_lower:
                text = await self.browser.get_text()
                return f"📄 Текст:\n\n{text[:2000]}..." if text else "❌ Текст не найден"
            
            if "инфо" in q_lower or "информация" in q_lower:
                info = await self.browser.get_page_info()
                return f"URL: {info.get('url')}\nTitle: {info.get('title')}"
            
            return "❌ Команды: скриншот, перейти <url>, текст, информация"
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return f"❌ Ошибка: {str(e)[:200]}"
    
    async def close(self):
        if self.browser:
            await self.browser.close()
        self.is_ready = False


# ============================================================
# 6. TELEGRAM
# ============================================================

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

bot = None

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message:
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 **Команды:**\n"
            "`/ask перейти https://example.com`\n"
            "`/ask скриншот`\n"
            "`/ask текст`\n"
            "`/ask информация`",
            parse_mode='Markdown'
        )
        return
    
    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text("🔄 Выполняю...")
    
    try:
        if not bot or not bot.is_ready:
            await status_msg.edit_text("❌ Бот не готов")
            return
        
        answer = await bot.ask(user_query)
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# 7. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("ask", ask_command))
    
    logger.info("🚀 Бот запущен! Команда: /ask")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(60)
        logger.info("💓 Bot alive")


if __name__ == "__main__":
    asyncio.run(main())