import os
import json
import logging
import asyncio
import subprocess
import requests
import base64
import websockets
from typing import Optional, List, Dict, Any, Callable
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ============ CDP КЛИЕНТ В СТИЛЕ Pydoll ============

class CDPConnection:
    """Управление WebSocket соединением"""
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.websocket = None
        self.message_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._listener_task = None
        
    async def connect(self):
        """Подключиться к Chrome"""
        self.websocket = await websockets.connect(self.ws_url)
        self._listener_task = asyncio.create_task(self._listen())
        return self
    
    async def _listen(self):
        """Слушать входящие сообщения"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_id = data.get('id')
                    if msg_id and msg_id in self._callbacks:
                        future = self._callbacks.pop(msg_id)
                        if 'error' in data:
                            future.set_exception(Exception(data['error'].get('message', 'CDP Error')))
                        else:
                            future.set_result(data)
                except Exception as e:
                    logging.error(f"Ошибка обработки: {e}")
        except websockets.exceptions.ConnectionClosed:
            logging.warning("Соединение закрыто")
    
    async def send_command(self, method: str, params: Dict = None) -> Dict:
        """Отправить CDP команду и получить ответ"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        future = asyncio.get_event_loop().create_future()
        self._callbacks[msg_id] = future
        
        await self.websocket.send(json.dumps(message))
        return await future
    
    async def close(self):
        """Закрыть соединение"""
        if self._listener_task:
            self._listener_task.cancel()
        if self.websocket:
            await self.websocket.close()


class CDPPage:
    """Управление страницей (вкладкой)"""
    def __init__(self, page_id: str, ws_url: str):
        self.id = page_id
        self.ws_url = ws_url
        self.connection = CDPConnection(ws_url)
        self._is_connected = False
        
    async def connect(self):
        """Подключиться к странице"""
        await self.connection.connect()
        # Включаем необходимые домены
        await self.connection.send_command("Page.enable")
        await self.connection.send_command("DOM.enable")
        await self.connection.send_command("Runtime.enable")
        await self.connection.send_command("Network.enable")
        
        # Устанавливаем размер
        await self.connection.send_command("Emulation.setDeviceMetricsOverride", {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "mobile": False
        })
        
        self._is_connected = True
        return self
    
    async def navigate(self, url: str) -> Dict:
        """Перейти по URL"""
        return await self.connection.send_command("Page.navigate", {"url": url})
    
    async def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        """Выполнить JavaScript"""
        result = await self.connection.send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value
        })
        return result.get('result', {}).get('value')
    
    async def screenshot(self, format: str = "png", full_page: bool = False) -> bytes:
        """Сделать скриншот"""
        result = await self.connection.send_command("Page.captureScreenshot", {
            "format": format,
            "quality": 100,
            "captureBeyondViewport": full_page,
            "fromSurface": True
        })
        img_data = base64.b64decode(result.get('result', {}).get('data', ''))
        return img_data
    
    async def click(self, selector: str) -> bool:
        """Кликнуть по элементу"""
        # Ищем элемент
        result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
        root = result.get('root', {}).get('nodeId')
        
        # Получаем элемент по селектору
        result = await self.connection.send_command("DOM.querySelector", {
            "nodeId": root,
            "selector": selector
        })
        node_id = result.get('nodeId')
        
        if not node_id:
            return False
        
        # Получаем координаты
        result = await self.connection.send_command("DOM.getBoxModel", {"nodeId": node_id})
        content = result.get('model', {}).get('content')
        
        if not content:
            return False
        
        # Центр элемента
        x = (content[0] + content[4]) / 2
        y = (content[1] + content[5]) / 2
        
        # Клик
        await self.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        
        await self.connection.send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        
        return True
    
    async def type_text(self, selector: str, text: str) -> bool:
        """Ввести текст в поле"""
        # Аналогично click, но с добавлением type
        result = await self.connection.send_command("DOM.getDocument", {"depth": 0})
        root = result.get('root', {}).get('nodeId')
        
        result = await self.connection.send_command("DOM.querySelector", {
            "nodeId": root,
            "selector": selector
        })
        node_id = result.get('nodeId')
        
        if not node_id:
            return False
        
        # Фокусируемся на элементе
        await self.connection.send_command("DOM.focus", {"nodeId": node_id})
        
        # Вводим текст
        await self.connection.send_command("Input.insertText", {"text": text})
        
        return True
    
    async def get_html(self) -> str:
        """Получить HTML код страницы"""
        html = await self.evaluate("document.documentElement.outerHTML")
        return html
    
    async def get_title(self) -> str:
        """Получить заголовок страницы"""
        return await self.evaluate("document.title")
    
    async def get_url(self) -> str:
        """Получить URL страницы"""
        return await self.evaluate("location.href")
    
    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> bool:
        """Ожидать появление элемента"""
        js = f"""
            new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve(true);
                    }} else if (Date.now() - start > {timeout}) {{
                        resolve(false);
                    }} else {{
                        setTimeout(check, 100);
                    }}
                }};
                check();
            }})
        """
        return await self.evaluate(js)
    
    async def close(self):
        """Закрыть страницу"""
        await self.connection.close()


class CDPBrowser:
    """Управление браузером"""
    def __init__(self):
        self.chrome_process = None
        self.pages: List[CDPPage] = []
        self.current_page: Optional[CDPPage] = None
        
    def get_debugger_url(self) -> Optional[str]:
        """Получить URL отладчика"""
        try:
            resp = requests.get("http://localhost:9222/json/version", timeout=2)
            data = resp.json()
            return data.get("webSocketDebuggerUrl")
        except:
            return None
    
    def get_pages_list(self) -> List[Dict]:
        """Получить список страниц"""
        try:
            resp = requests.get("http://localhost:9222/json/list")
            return resp.json()
        except:
            return []
    
    async def launch(self, headless: bool = True):
        """Запустить браузер"""
        chrome_cmd = '/usr/bin/chromium'
        
        if not os.path.exists(chrome_cmd):
            return False, f"❌ Chromium не найден: {chrome_cmd}"
        
        # Проверяем, не запущен ли уже
        if self.get_debugger_url():
            return True, "✅ Chrome уже запущен"
        
        cmd = [
            chrome_cmd,
            '--remote-debugging-port=9222',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-setuid-sandbox',
            '--no-sandbox',
            '--window-size=1280,720'
        ]
        
        if headless:
            cmd.insert(cmd.index('--remote-debugging-port=9222') + 1, '--headless=new')
        
        self.chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Ждем запуска
        for _ in range(15):
            await asyncio.sleep(1)
            if self.get_debugger_url():
                return True, "✅ Chrome запущен"
        
        return False, "❌ Не удалось запустить Chrome"
    
    async def new_page(self, url: str = "about:blank") -> Optional[CDPPage]:
        """Создать новую страницу"""
        try:
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
    
    async def get_page(self, page_id: str) -> Optional[CDPPage]:
        """Получить страницу по ID"""
        for page in self.pages:
            if page.id == page_id:
                return page
        return None
    
    def get_first_page(self) -> Optional[CDPPage]:
        """Получить первую страницу"""
        pages = self.get_pages_list()
        if pages:
            page_id = pages[0].get('id')
            ws_url = pages[0].get('webSocketDebuggerUrl')
            page = CDPPage(page_id, ws_url)
            return page
        return None
    
    async def close(self):
        """Закрыть браузер"""
        for page in self.pages:
            await page.close()
        if self.chrome_process:
            self.chrome_process.terminate()


# ============ БОТ ============

browser = CDPBrowser()
current_page: Optional[CDPPage] = None

async def ensure_browser():
    """Убедиться что браузер запущен"""
    global current_page
    
    # Проверяем подключение
    if current_page and current_page._is_connected:
        try:
            await current_page.evaluate("1")
            return True, "✅ Уже подключен"
        except:
            current_page = None
    
    # Запускаем браузер
    success, msg = await browser.launch(headless=True)
    if not success:
        return False, msg
    
    # Получаем первую страницу
    page = browser.get_first_page()
    if page:
        await page.connect()
        current_page = page
        browser.current_page = page
        return True, "✅ Подключен"
    
    # Или создаем новую
    page = await browser.new_page()
    if page:
        current_page = page
        return True, "✅ Создана новая страница"
    
    return False, "❌ Не удалось получить страницу"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CDP Client (Pydoll Style)\n\n"
        "Команды:\n"
        "/screenshot - скриншот\n"
        "/newpage <url> - новая страница\n"
        "/navigate <url> - перейти\n"
        "/evaluate <js> - выполнить JS\n"
        "/click <selector> - клик\n"
        "/type <selector> <text> - ввод\n"
        "/html - получить HTML\n"
        "/tabs - список страниц\n"
        "/status - статус"
    )

async def new_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новую страницу"""
    global current_page
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    url = context.args[0] if context.args else "about:blank"
    page = await browser.new_page(url)
    
    if page:
        current_page = page
        await update.message.reply_text(f"✅ Новая страница: {url}")
    else:
        await update.message.reply_text("❌ Не удалось создать страницу")

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    
    if not context.args:
        await update.message.reply_text("❌ /navigate https://example.com")
        return
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    url = context.args[0]
    await current_page.navigate(url)
    await update.message.reply_text(f"✅ Переход на {url}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    await update.message.reply_text("🔄 Делаю скриншот...")
    img_data = await current_page.screenshot()
    await update.message.reply_photo(photo=img_data, caption="📸 Скриншот 1280x720")

async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    
    if not context.args:
        await update.message.reply_text("❌ /evaluate document.title")
        return
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    js = ' '.join(context.args)
    result = await current_page.evaluate(js)
    await update.message.reply_text(f"✅ {str(result)[:1000]}")

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
    result = await current_page.click(selector)
    
    if result:
        await update.message.reply_text(f"✅ Клик по: {selector}")
    else:
        await update.message.reply_text(f"❌ Не найден: {selector}")

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
    result = await current_page.type_text(selector, text)
    
    if result:
        await update.message.reply_text(f"✅ Введено: {text}")
    else:
        await update.message.reply_text(f"❌ Не найден: {selector}")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_page
    
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    html = await current_page.get_html()
    # Отправляем кусок HTML
    await update.message.reply_text(f"📄 HTML:\n{html[:1000]}")

async def list_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success, msg = await ensure_browser()
    if not success:
        await update.message.reply_text(f"❌ {msg}")
        return
    
    pages = browser.get_pages_list()
    
    if not pages:
        await update.message.reply_text("📭 Нет страниц")
        return
    
    msg = "📄 Страницы:\n\n"
    for i, page in enumerate(pages, 1):
        title = page.get('title', 'Без названия')[:30]
        url = page.get('url', '')[:50]
        msg += f"{i}. {title}\n   {url}\n\n"
    
    await update.message.reply_text(msg[:4000])

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = "📊 Статус:\n"
    status_msg += f"Страница: {'✅' if current_page else '❌'}\n"
    
    if current_page and current_page._is_connected:
        try:
            url = await current_page.get_url()
            title = await current_page.get_title()
            status_msg += f"URL: {url[:60]}\n"
            status_msg += f"Title: {title[:30]}\n"
        except:
            status_msg += "❌ Ошибка получения данных\n"
    
    status_msg += f"Страниц: {len(browser.pages)}"
    await update.message.reply_text(status_msg)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newpage", new_page))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(CommandHandler("click", click))
    app.add_handler(CommandHandler("type", type_text))
    app.add_handler(CommandHandler("html", get_html))
    app.add_handler(CommandHandler("tabs", list_pages))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 CDP Client (Pydoll Style) запущен")
    print("📁 Chromium: /usr/bin/chromium")
    print("🎯 Режим: Headless New")
    app.run_polling()

if __name__ == "__main__":
    main()