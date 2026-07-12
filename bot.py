
import os
import asyncio
import json
import websockets
import requests
import subprocess
import time
import base64
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHROME_PATH = "/usr/bin/google-chrome"
CHROME_PORT = 9222

# ==================== УПРАВЛЕНИЕ БРАУЗЕРОМ ====================
class ChromeManager:
    def __init__(self, chrome_path=CHROME_PATH, port=CHROME_PORT):
        self.chrome_path = chrome_path
        self.port = port
        self.process = None
        self.ws_endpoint = None
    
    def start(self):
        """Запускает Chrome с CDP"""
        if self.is_running():
            print("✅ Chrome уже запущен")
            self.ws_endpoint = self.get_ws_endpoint()
            return True
        
        print("🚀 Запускаю Chrome...")
        
        cmd = [
            self.chrome_path,
            "--headless",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            f"--remote-debugging-port={self.port}",
            "--window-size=1920,1080"
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            
            time.sleep(3)
            
            self.ws_endpoint = self.get_ws_endpoint()
            if self.ws_endpoint:
                print(f"✅ Chrome запущен: {self.ws_endpoint}")
                return True
            else:
                print("❌ Не удалось получить WebSocket endpoint")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка запуска Chrome: {e}")
            return False
    
    def is_running(self):
        """Проверяет, запущен ли Chrome"""
        try:
            response = requests.get(f"http://localhost:{self.port}/json/version", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_ws_endpoint(self):
        """Получает WebSocket endpoint от Chrome"""
        try:
            response = requests.get(f"http://localhost:{self.port}/json/version", timeout=2)
            return response.json()["webSocketDebuggerUrl"]
        except:
            return None
    
    def stop(self):
        """Останавливает Chrome"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
            print("🛑 Chrome остановлен")

# ==================== CDP КЛИЕНТ ====================
class CDPClient:
    def __init__(self, ws_endpoint):
        self.ws_endpoint = ws_endpoint
        self.websocket = None
        self.msg_id = 0
        self.targets = {}
        self.session_id = None
    
    async def connect(self):
        if not self.ws_endpoint:
            raise Exception("WebSocket endpoint не указан")
        self.websocket = await websockets.connect(self.ws_endpoint)
        print(f"✅ Подключено к Chrome: {self.ws_endpoint}")
    
    async def send(self, method, params=None, session_id=None):
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        
        await self.websocket.send(json.dumps(msg))
        
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            if data.get("id") == self.msg_id:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data
    
    async def create_tab(self):
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        target_id = result["result"]["targetId"]
        
        result = await self.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = result["result"]["sessionId"]
        
        await self.send("Page.enable", session_id=session_id)
        await self.send("Runtime.enable", session_id=session_id)
        await self.send("DOM.enable", session_id=session_id)
        
        self.targets[session_id] = target_id
        self.session_id = session_id
        return session_id, target_id
    
    async def navigate(self, session_id, url):
        return await self.send("Page.navigate", {"url": url}, session_id=session_id)
    
    async def wait_for_load(self, session_id, timeout=30):
        for _ in range(timeout):
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=1)
                data = json.loads(response)
                if data.get("method") == "Page.loadEventFired":
                    return True
                if data.get("method") == "Page.frameStoppedLoading":
                    return True
                if data.get("id") and data.get("error"):
                    return False
            except asyncio.TimeoutError:
                continue
        return False
    
    async def get_accessibility_tree(self, session_id):
        result = await self.send("Accessibility.getFullAXTree", session_id=session_id)
        return result["result"]["nodes"]
    
    async def get_element_by_selector(self, session_id, selector):
        result = await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {{
                        id: el.id || '',
                        className: el.className || '',
                        tagName: el.tagName,
                        x: rect.x + rect.width/2,
                        y: rect.y + rect.height/2,
                        width: rect.width,
                        height: rect.height
                    }};
                }})()
            """
        }, session_id=session_id)
        
        if result.get("result", {}).get("result", {}).get("value"):
            return result["result"]["result"]["value"]
        return None
    
    async def click_element(self, session_id, selector):
        coords = await self.get_element_by_selector(session_id, selector)
        if not coords:
            raise Exception("Элемент не найден")
        
        await self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
            "modifiers": 0
        }, session_id=session_id)
        
        await asyncio.sleep(0.1)
        
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
            "modifiers": 0
        }, session_id=session_id)
        
        return coords
    
    async def fill_input(self, session_id, selector, text):
        await self.send("Runtime.evaluate", {
            "expression": f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.focus();
                        el.value = '';
                        return true;
                    }}
                    return false;
                }})()
            """
        }, session_id=session_id)
        
        await asyncio.sleep(0.1)
        
        for char in text:
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char
            }, session_id=session_id)
            await asyncio.sleep(0.01)
            await self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "text": char
            }, session_id=session_id)
            await asyncio.sleep(0.01)
        
        return True
    
    async def screenshot(self, session_id):
        result = await self.send("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True
        }, session_id=session_id)
        return base64.b64decode(result["result"]["data"])
    
    async def close_tab(self, session_id):
        if session_id in self.targets:
            target_id = self.targets[session_id]
            await self.send("Target.closeTarget", {"targetId": target_id})
            del self.targets[session_id]
    
    async def close(self):
        if self.websocket:
            await self.websocket.close()

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
chrome_manager = ChromeManager()

if not chrome_manager.start():
    print("❌ Не удалось запустить Chrome")
    exit(1)

cdp = CDPClient(chrome_manager.ws_endpoint)

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Я бот для автоматизации браузера.\n\n"
        "📌 Отправь мне URL, и я покажу все элементы.\n"
        "📌 Используй /click <селектор> для клика.\n"
        "📌 Используй /fill <селектор> <текст> для заполнения.\n"
        "📌 Используй /screenshot для скриншота."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Отправь корректный URL")
        return
    
    await update.message.reply_text(f"🔄 Анализирую {url}...")
    
    try:
        if not cdp.websocket:
            await cdp.connect()
        
        session_id, target_id = await cdp.create_tab()
        context.user_data['session_id'] = session_id
        
        await cdp.navigate(session_id, url)
        await update.message.reply_text("⏳ Ожидаю загрузку страницы...")
        await cdp.wait_for_load(session_id)
        
        nodes = await cdp.get_accessibility_tree(session_id)
        
        interactive = []
        for node in nodes:
            role = node.get("role", {}).get("value", "")
            if role in ["button", "link", "textbox", "checkbox", "combobox", "radio"]:
                name = node.get("name", {}).get("value", "")
                node_id = node.get("nodeId")
                interactive.append({
                    "id": node_id,
                    "role": role,
                    "name": name[:100]
                })
        
        context.user_data['elements'] = interactive
        
        if interactive:
            msg = "🔍 Найдены интерактивные элементы:\n\n"
            for i, el in enumerate(interactive[:20], 1):
                name = el['name'] if el['name'] else "(без названия)"
                msg += f"{i}. [{el['role']}] {name}\n"
            
            if len(interactive) > 20:
                msg += f"\n... и ещё {len(interactive) - 20} элементов"
            
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ Интерактивных элементов не найдено")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        print(f"Error: {e}")

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.split()
        if len(args) < 2:
            await update.message.reply_text("❌ Использование: /click <селектор>")
            return
        
        selector = args[1]
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text(f"🖱️ Кликаю по '{selector}'...")
        coords = await cdp.click_element(session_id, selector)
        await update.message.reply_text(f"✅ Клик выполнен по координатам ({coords['x']:.0f}, {coords['y']:.0f})")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def fill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.split()
        if len(args) < 3:
            await update.message.reply_text("❌ Использование: /fill <селектор> <текст>")
            return
        
        selector = args[1]
        text = " ".join(args[2:])
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text(f"✍️ Заполняю '{selector}' текстом: {text}")
        await cdp.fill_input(session_id, selector, text)
        await update.message.reply_text("✅ Поле заполнено")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        session_id = context.user_data.get('session_id')
        
        if not session_id:
            await update.message.reply_text("❌ Сначала отправь URL для анализа")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        image_data = await cdp.screenshot(session_id)
        await update.message.reply_photo(
            photo=BytesIO(image_data),
            caption="📸 Скриншот страницы"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get('session_id')
    if session_id:
        await cdp.close_tab(session_id)
        context.user_data.clear()
        await update.message.reply_text("🧹 Сессия очищена")
    else:
        await update.message.reply_text("Активной сессии нет")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Доступные команды:\n\n"
        "/start - Начать работу\n"
        "/help - Эта справка\n"
        "/click <селектор> - Кликнуть по элементу\n"
        "/fill <селектор> <текст> - Заполнить поле\n"
        "/screenshot - Сделать скриншот\n"
        "/clear - Очистить сессию\n\n"
        "🔹 Просто отправь URL для анализа страницы"
    )

# ==================== ЗАПУСК БОТА ====================
def main():
    print("🚀 Запуск бота...")
    print(f"🔗 Chrome: {chrome_manager.ws_endpoint}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("click", click_command))
    app.add_handler(CommandHandler("fill", fill_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("✅ Бот запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()