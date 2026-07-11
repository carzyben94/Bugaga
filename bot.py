import os
import json
import asyncio
import logging
import base64
import subprocess
import websockets
import aiohttp
from typing import Dict, Any, List, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============= НАСТРОЙКИ =============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ============= AGNES CDP АГЕНТ =============
class AgnesCDPAgent:
    def __init__(self):
        self.chrome_process = None
        self.websocket = None
        self.message_id = 0
        self.is_running = False
        
    async def start_chrome(self):
        """Запускает Chrome с CDP портом"""
        chrome_path = "/usr/bin/google-chrome"
        
        if not os.path.exists(chrome_path):
            chrome_path = "/usr/bin/google-chrome-stable"
        
        cmd = [
            chrome_path,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--remote-debugging-port=9222",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080"
        ]
        
        self.chrome_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.sleep(3)
        await self.connect_to_cdp()
        self.is_running = True
        
        # Запускаем слушатель событий
        asyncio.create_task(self.listen_events())
        
        return True
    
    async def connect_to_cdp(self):
        """Подключается к CDP"""
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:9222/json") as resp:
                data = await resp.json()
                ws_url = data[0]["webSocketDebuggerUrl"]
        
        self.websocket = await websockets.connect(ws_url)
        
        # Включаем домены
        await self.send_cdp_command("Page.enable")
        await self.send_cdp_command("Runtime.enable")
        await self.send_cdp_command("Network.enable")
        await self.send_cdp_command("DOM.enable")
    
    async def send_cdp_command(self, method: str, params: Dict = None) -> Dict:
        """Отправляет CDP команду"""
        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }
        
        await self.websocket.send(json.dumps(message))
        
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            if data.get("id") == self.message_id:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data
    
    async def listen_events(self):
        """Слушает события CDP"""
        try:
            while self.is_running:
                response = await self.websocket.recv()
                data = json.loads(response)
                if "method" in data:
                    if data["method"] == "Page.loadEventFired":
                        logger.info("✅ Страница загружена")
        except Exception as e:
            logger.error(f"Ошибка listener: {e}")
    
    # ============ ИСПРАВЛЕННЫЕ МЕТОДЫ ============
    
    async def navigate(self, url: str) -> Dict:
        """Переход по URL"""
        # Проверяем URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return await self.send_cdp_command("Page.navigate", {"url": url})
    
    async def take_screenshot(self, full_page: bool = False, format: str = "png", quality: int = 80):
        """Скриншот по документации"""
        params = {
            "format": format,
            "captureBeyondViewport": full_page,
            "fromSurface": True
        }
        if format == "jpeg":
            params["quality"] = quality
        
        # Убираем None значения
        params = {k: v for k, v in params.items() if v is not None}
        return await self.send_cdp_command("Page.captureScreenshot", params)
    
    async def query_selector(self, selector: str) -> Optional[int]:
        """Поиск элемента по CSS"""
        try:
            doc = await self.send_cdp_command("DOM.getDocument")
            root_id = doc["result"]["root"]["nodeId"]
            
            result = await self.send_cdp_command("DOM.querySelector", {
                "nodeId": root_id,
                "selector": selector
            })
            
            node_id = result["result"].get("nodeId")
            return node_id if node_id and node_id != 0 else None
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return None
    
    async def click_element(self, node_id: int) -> Dict:
        """Клик по элементу"""
        try:
            # Получаем координаты
            rect = await self.send_cdp_command("DOM.getBoxModel", {"nodeId": node_id})
            box = rect["result"]["model"]
            content = box["content"]
            
            x = (content[0] + content[4]) / 2
            y = (content[1] + content[5]) / 2
            
            # Эмуляция мыши
            await self.send_cdp_command("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            
            await self.send_cdp_command("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            
            return {"success": True}
        except Exception as e:
            logger.error(f"Ошибка клика: {e}")
            return {"success": False, "error": str(e)}
    
    async def type_text(self, text: str, selector: str = None) -> Dict:
        """Ввод текста с фокусом"""
        if selector:
            node_id = await self.query_selector(selector)
            if node_id:
                await self.send_cdp_command("DOM.focus", {"nodeId": node_id})
                await asyncio.sleep(0.1)
        
        return await self.send_cdp_command("Input.insertText", {"text": text})
    
    async def emulate_device(self, width: int, height: int, mobile: bool = False, scale: float = 1):
        """Эмуляция устройства по документации"""
        return await self.send_cdp_command("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": scale,
            "mobile": mobile,
            "screenOrientation": {"type": "portraitPrimary", "angle": 0}
        })
    
    async def emulate_geolocation(self, latitude: float, longitude: float, accuracy: int = 100):
        """Эмуляция геолокации"""
        return await self.send_cdp_command("Emulation.setGeolocationOverride", {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy
        })
    
    async def get_page_html(self) -> str:
        """Получение HTML с проверкой загрузки"""
        try:
            # Проверяем статус загрузки
            ready = await self.send_cdp_command("Runtime.evaluate", {
                "expression": "document.readyState",
                "returnByValue": True
            })
            
            if ready.get("result", {}).get("value") != "complete":
                await asyncio.sleep(1)
            
            result = await self.send_cdp_command("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True
            })
            return result["result"].get("value", "")
        except Exception as e:
            logger.error(f"Ошибка получения HTML: {e}")
            return ""
    
    async def close(self):
        """Корректное закрытие"""
        self.is_running = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
        
        try:
            await self.send_cdp_command("Browser.close")
        except:
            pass
        
        if self.chrome_process:
            try:
                self.chrome_process.terminate()
                try:
                    await asyncio.wait_for(self.chrome_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.chrome_process.kill()
            except:
                pass

# ============ ТЕЛЕГРАМ БОТ ============
agent = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global agent
    await update.message.reply_text("🧠 Запускаю AGNES CDP Агент...")
    
    try:
        agent = AgnesCDPAgent()
        await agent.start_chrome()
        await update.message.reply_text("✅ Браузер готов!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global agent
    
    if not agent or not agent.is_running:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /start")
        return
    
    user_input = update.message.text.lower()
    await update.message.reply_text("⏳ Выполняю...")
    
    try:
        if "открой" in user_input:
            url = user_input.replace("открой", "").strip()
            await agent.navigate(url)
            await update.message.reply_text(f"✅ Открыл: {url}")
        
        elif "скрин" in user_input or "сфоткай" in user_input:
            full = "всей" in user_input or "вся" in user_input
            result = await agent.take_screenshot(full_page=full)
            
            if "data" in result.get("result", {}):
                image_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(image_data, caption="📸 Скриншот")
        
        elif "нажми" in user_input and "на " in user_input:
            selector = user_input.split("на ")[1].strip()
            node_id = await agent.query_selector(selector)
            if node_id:
                await agent.click_element(node_id)
                await update.message.reply_text(f"✅ Кликнул: {selector}")
            else:
                await update.message.reply_text(f"❌ Элемент не найден: {selector}")
        
        elif "введи" in user_input:
            if "в " in user_input:
                parts = user_input.split("в ")
                text = parts[0].replace("введи", "").strip()
                selector = parts[1].strip()
            else:
                text = user_input.replace("введи", "").strip()
                selector = None
            
            await agent.type_text(text, selector)
            await update.message.reply_text(f"✅ Ввёл: {text}")
        
        elif "найди" in user_input:
            selector = user_input.split("найди ")[1].strip()
            node_id = await agent.query_selector(selector)
            if node_id:
                html = await agent.get_page_html()
                await update.message.reply_text(f"✅ Нашёл элемент")
            else:
                await update.message.reply_text(f"❌ Элемент не найден")
        
        elif "эмулируй iphone" in user_input:
            await agent.emulate_device(375, 812, True, 3)
            await update.message.reply_text("📱 Эмулирую iPhone")
        
        elif "помощь" in user_input:
            await update.message.reply_text(
                "📋 **Команды:**\n"
                "• открой google.com\n"
                "• скриншот\n"
                "• нажми на #id\n"
                "• введи текст в #input\n"
                "• найди #id\n"
                "• эмулируй iphone"
            )
        
        else:
            await update.message.reply_text("🤔 Не понял. Напиши 'помощь'")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()