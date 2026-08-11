# bot.py - Полный CDP клиент + Telegram бот
import os
import json
import logging
import asyncio
import subprocess
import requests
import base64
import websockets
import random
import time
from typing import Optional, List, Dict, Any, Callable
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем ТОЛЬКО маскировку из stealth.py
from stealth import (
    Stealth, 
    HumanBehavior, 
    TimingConfig, 
    BrowserPreferences,
    BezierCurve
)

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ============================================================
# CDP КЛИЕНТ (ВЕСЬ ЗДЕСЬ)
# ============================================================

class CDPConnection:
    """WebSocket соединение с Chrome"""
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.websocket = None
        self.message_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._listener_task = None
        self._event_handlers: Dict[str, List[Callable]] = {}
        
    async def connect(self):
        self.websocket = await websockets.connect(self.ws_url)
        self._listener_task = asyncio.create_task(self._listen())
        return self
    
    async def _listen(self):
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_id = data.get('id')
                    method = data.get('method')
                    
                    if msg_id and msg_id in self._callbacks:
                        future = self._callbacks.pop(msg_id)
                        if 'error' in data:
                            future.set_exception(Exception(data['error'].get('message', 'CDP Error')))
                        else:
                            future.set_result(data)
                    
                    if method and method in self._event_handlers:
                        for handler in self._event_handlers[method]:
                            asyncio.create_task(handler(data.get('params', {})))
                except Exception as e:
                    logging.error(f"Ошибка обработки: {e}")
        except websockets.exceptions.ConnectionClosed:
            logging.warning("Соединение закрыто")
    
    async def send_command(self, method: str, params: Dict = None) -> Dict:
        self.message_id += 1
        msg_id = self.message_id
        message = {"id": msg_id, "method": method, "params": params or {}}
        future = asyncio.get_event_loop().create_future()
        self._callbacks[msg_id] = future
        await self.websocket.send(json.dumps(message))
        return await future
    
    def on(self, event_name: str, handler: Callable):
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)
    
    async def close(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self.websocket:
            await self.websocket.close()


class Element:
    """DOM элемент"""
    def __init__(self, page: 'CDPPage', node_id: int, object_id: str = None):
        self.page = page
        self.node_id = node_id
        self.object_id = object_id
        
    async def click(self, humanize: bool = True, config: TimingConfig = None):
        return await self.page.click_selector(f"nodeId:{self.node_id}", humanize, config)
    
    async def type_text(self, text: str, humanize: bool = True, config: TimingConfig = None):
        return await self.page.type_selector(f"nodeId:{self.node_id}", text, humanize, config)
    
    async def get_text(self) -> str:
        if self.object_id:
            result = await self.page.connection.send_command("Runtime.callFunctionOn", {
                "functionDeclaration": "function() { return this.textContent; }",
                "objectId": self.object_id,
                "returnByValue": True
            })
            return result.get('result', {}).get('value', '')
        return None


class Mouse:
    """Управление мышью"""
    def __init__(self, page: 'CDPPage'):
        self.page = page
        self.x = 0
        self.y = 0
        
    async def move(self, x: int, y: int, humanize: bool = True, config: TimingConfig = None):
        if config is None:
            config = TimingConfig()
        
        if humanize:
            points = BezierCurve.generate_points(
                (self.x, self.y),
                (x, y),
                num_points=random.randint(20, 40),
                spread=30
            )
            for px, py in points:
                await self.page.connection.send_command("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": px,
                    "y": py
                })
                await asyncio.sleep(random.uniform(config.mouse_speed_min, config.mouse_speed_max))
        else:
            await self.page.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y
            })
        self.x = x
        self.y = y
    
    async def click(self, x: int = None, y: int = None, button: str = "left",
                    humanize: bool = True, config: TimingConfig = None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y
        
        if humanize:
            await HumanBehavior.human_click(self.page, x, y, button, config)
        else:
            await self.page.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": 1
            })
            await asyncio.sleep(0.05)
            await self.page.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": 1
            })


class Keyboard:
    """Управление клавиатурой"""
    def __init__(self, page: 'CDPPage'):
        self.page = page
    
    async def press(self, key: str):
        await self.page.connection.send_command("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key
        })
        await asyncio.sleep(random.uniform(0.02, 0.05))
        await self.page.connection.send_command("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key
        })
    
    async def type_text(self, text: str, humanize: bool = True, config: TimingConfig = None):
        if humanize:
            await HumanBehavior.human_type_global(self.page, text, config)
        else:
            await self.page.connection.send_command("Input.insertText", {"text": text})


class Scroll:
    """Управление скроллом"""
    def __init__(self, page: 'CDPPage'):
        self.page = page
    
    async def to_bottom(self, humanize: bool = True):
        height = await self.page.evaluate("document.body.scrollHeight")
        viewport_height = await self.page.evaluate("window.innerHeight")
        
        if humanize:
            steps = random.randint(15, 25)
            for i in range(steps):
                progress = (i + 1) / steps
                eased = progress * progress * (3 - 2 * progress)
                current_height = min(height * eased, height - viewport_height)
                await self.page.connection.send_command("Runtime.evaluate", {
                    "expression": f"window.scrollTo(0, {current_height})",
                    "returnByValue": False
                })
                await asyncio.sleep(random.uniform(0.03, 0.08))
        else:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    
    async def to_top(self, humanize: bool = True):
        if humanize:
            current = await self.page.evaluate("window.scrollY")
            steps = random.randint(10, 20)
            for i in range(steps):
                progress = 1 - (i + 1) / steps
                eased = progress * progress * (3 - 2 * progress)
                current_height = max(0, current * eased)
                await self.page.connection.send_command("Runtime.evaluate", {
                    "expression": f"window.scrollTo(0, {current_height})",
                    "returnByValue": False
                })
                await asyncio.sleep(random.uniform(0.02, 0.06))
        else:
            await self.page.evaluate("window.scrollTo(0, 0)")


class CDPPage:
    """Управление страницей"""
    def __init__(self, page_id: str, ws_url: str):
        self.id = page_id
        self.ws_url = ws_url
        self.connection = CDPConnection(ws_url)
        self._is_connected = False
        
        self.mouse = Mouse(self)
        self.keyboard = Keyboard(self)
        self.scroll = Scroll(self)
        
    async def connect(self):
        await self.connection.connect()
        await self.connection.send_command("Page.enable")
        await self.connection.send_command("DOM.enable")
        await self.connection.send_command("Runtime.enable")
        await self.connection.send_command("Network.enable")
        
        # Применяем маскировку (из stealth.py)
        for script in Stealth.get_stealth_scripts():
            await self.connection.send_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": False
            })
        
        self._is_connected = True
        return self
    
    async def goto(self, url: str):
        # Добавляем referrer маскировку
        await self.connection.send_command("Page.addScriptToEvaluateOnNewDocument", {
            "source": Stealth.get_referrer_script()
        })
        return await self.connection.send_command("Page.navigate", {"url": url})
    
    async def click_selector(self, selector: str, humanize: bool = True, config: TimingConfig = None) -> bool:
        if selector.startswith("nodeId:"):
            node_id = int(selector.split(":")[1])
        else:
            result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
            root = result.get('root', {}).get('nodeId')
            result = await self.connection.send_command("DOM.querySelector", {
                "nodeId": root,
                "selector": selector
            })
            node_id = result.get('nodeId')
        
        if not node_id:
            return False
        
        result = await self.connection.send_command("DOM.getBoxModel", {"nodeId": node_id})
        content = result.get('model', {}).get('content')
        if not content:
            return False
        
        x = (content[0] + content[4]) / 2 + random.uniform(-10, 10)
        y = (content[1] + content[5]) / 2 + random.uniform(-10, 10)
        
        if humanize:
            await HumanBehavior.human_click(self, x, y, "left", config)
        else:
            await self.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            await asyncio.sleep(0.05)
            await self.connection.send_command("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
        return True
    
    async def type_selector(self, selector: str, text: str, humanize: bool = True, config: TimingConfig = None) -> bool:
        if selector.startswith("nodeId:"):
            node_id = int(selector.split(":")[1])
        else:
            result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
            root = result.get('root', {}).get('nodeId')
            result = await self.connection.send_command("DOM.querySelector", {
                "nodeId": root,
                "selector": selector
            })
            node_id = result.get('nodeId')
        
        if not node_id:
            return False
        
        await self.connection.send_command("DOM.focus", {"nodeId": node_id})
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if humanize:
            await HumanBehavior.human_type_global(self, text, config)
        else:
            await self.connection.send_command("Input.insertText", {"text": text})
        return True
    
    async def evaluate(self, expression: str) -> Any:
        result = await self.connection.send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        if 'exceptionDetails' in result:
            raise Exception(f"JS Error: {result['exceptionDetails']}")
        return result.get('result', {}).get('value')
    
    async def screenshot(self) -> bytes:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        result = await self.connection.send_command("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True
        })
        return base64.b64decode(result.get('result', {}).get('data', ''))
    
    async def html(self) -> str:
        return await self.evaluate("document.documentElement.outerHTML")
    
    async def text(self) -> str:
        return await self.evaluate("document.body.textContent")
    
    async def url(self) -> str:
        return await self.evaluate("location.href")
    
    async def title(self) -> str:
        return await self.evaluate("document.title")
    
    async def cookies(self) -> List[Dict]:
        result = await self.connection.send_command("Network.getCookies")
        return result.get('cookies', [])
    
    async def close(self):
        await self.connection.close()


class CDPBrowser:
    """Управление браузером"""
    def __init__(self):
        self.chrome_process = None
        self.pages: List[CDPPage] = []
        self.current_page: Optional[CDPPage] = None
        self._headless = True
        
    def get_debugger_url(self) -> Optional[str]:
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=2)
            data = resp.json()
            return data.get("webSocketDebuggerUrl")
        except:
            return None
    
    def get_pages_list(self) -> List[Dict]:
        try:
            resp = requests.get("http://localhost:9222/json/list")
            return resp.json()
        except:
            return []
    
    async def launch(self, headless: bool = True, user_agent: str = None,
                     proxy: str = None, webrtc_leak_protection: bool = True):
        """Запуск браузера с маскировкой из stealth.py"""
        if self.get_debugger_url():
            return True, "✅ Chrome уже запущен"
        
        self._headless = headless
        
        # Получаем флаги из stealth.py
        cmd = Stealth.get_chrome_flags(headless, user_agent, proxy, webrtc_leak_protection)
        
        self.chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        for _ in range(15):
            await asyncio.sleep(1)
            if self.get_debugger_url():
                return True, f"✅ Chrome запущен (headless={headless})"
        
        return False, "❌ Не удалось запустить Chrome"
    
    def get_first_page(self) -> Optional[CDPPage]:
        pages = self.get_pages_list()
        if pages:
            page_id = pages[0].get('id')
            ws_url = pages[0].get('webSocketDebuggerUrl')
            return CDPPage(page_id, ws_url)
        return None
    
    async def new_page(self, url: str = "about:blank") -> Optional[CDPPage]:
        try:
            await asyncio.sleep(random.uniform(0.1, 0.5))
            resp = requests.get(f"http://localhost:9222/json/new?{url}")
            if resp.status_code == 200:
                data = resp.json()
                page = CDPPage(data.get('id'), data.get('webSocketDebuggerUrl'))
                await page.connect()
                self.pages.append(page)
                self.current_page = page
                return page
        except Exception as e:
            logging.error(f"Ошибка создания страницы: {e}")
        return None
    
    async def close(self):
        for page in self.pages:
            await page.close()
        if self.chrome_process:
            self.chrome_process.terminate()


# ============================================================
# ТЕЛЕГРАМ БОТ
# ============================================================

browser = CDPBrowser()
current_page: Optional[CDPPage] = None
timing_config = TimingConfig()

async def ensure_browser():
    global current_page
    if current_page and current_page._is_connected:
        try:
            await current_page.evaluate("1")
            return True, "✅ Уже подключен"
        except:
            current_page = None
    
    success, msg = await browser.launch(headless=True)
    if not success:
        return False, msg
    
    page = browser.get_first_page()
    if page:
        await page.connect()
        current_page = page
        browser.current_page = page
        return True, "✅ Подключен"
    
    page = await browser.new_page()
    if page:
        current_page = page
        return True, "✅ Создана новая страница"
    
    return False, "❌ Не удалось получить страницу"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client + Stealth\n\n"
        "Команды:\n"
        "/screenshot - скриншот\n"
        "/navigate <url> - перейти\n"
        "/click <selector> - клик\n"
        "/type <selector> <text> - ввод\n"
        "/html - получить HTML\n"
        "/cookies - получить куки\n"
        "/status - статус"
    )

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if not context.args:
        await update.message.reply_text("❌ /navigate https://example.com")
        return
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    await current_page.goto(context.args[0])
    await update.message.reply_text(f"✅ Переход на {context.args[0]}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    await update.message.reply_text("🔄 Делаю скриншот...")
    img_data = await current_page.screenshot()
    await update.message.reply_photo(photo=img_data, caption="📸 Скриншот")

async def click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if not context.args:
        await update.message.reply_text("❌ /click #button")
        return
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    selector = ' '.join(context.args)
    await current_page.click_selector(selector, humanize=True, config=timing_config)
    await update.message.reply_text(f"✅ Клик по: {selector}")

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    if len(context.args) < 2:
        await update.message.reply_text("❌ /type #input text")
        return
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    await current_page.type_selector(selector, text, humanize=True, config=timing_config)
    await update.message.reply_text(f"✅ Введено: {text}")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    html = await current_page.html()
    await update.message.reply_text(f"📄 HTML:\n{html[:1000]}")

async def get_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    cookies = await current_page.cookies()
    if not cookies:
        await update.message.reply_text("🍪 Нет кук")
        return
    
    msg = "🍪 Куки:\n\n"
    for cookie in cookies[:10]:
        msg += f"{cookie.get('name')}: {cookie.get('value')[:30]}\n"
    await update.message.reply_text(msg[:4000])

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = "📊 Статус:\n\n"
    status_msg += f"Страница: {'✅' if current_page else '❌'}\n"
    status_msg += f"Headless: {'✅' if browser._headless else '❌'}\n"
    status_msg += f"Маскировка: ✅\n"
    status_msg += f"Humanize: ✅\n"
    
    if current_page and current_page._is_connected:
        try:
            url = await current_page.url()
            title = await current_page.title()
            status_msg += f"\nURL: {url[:60]}\n"
            status_msg += f"Title: {title[:30]}\n"
        except:
            status_msg += "❌ Ошибка получения данных\n"
    
    await update.message.reply_text(status_msg)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("click", click))
    app.add_handler(CommandHandler("type", type_text))
    app.add_handler(CommandHandler("html", get_html))
    app.add_handler(CommandHandler("cookies", get_cookies))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 CDP Client + Stealth запущен")
    print("📁 Маскировка вынесена в stealth.py")
    print("🎯 bot.py содержит только клиент + бот")
    app.run_polling()

if __name__ == "__main__":
    main()