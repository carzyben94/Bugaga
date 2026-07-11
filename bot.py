import asyncio
import json
import os
import logging
import base64
import aiohttp
import websockets
from typing import Dict, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

class AgnesCDPAgent:
    def __init__(self):
        self.chrome_process = None
        self.websocket = None
        self.message_id = 0
        self.is_running = False
        self.response_queue = {}  # Очередь для ответов
        self.listener_task = None
        
    async def start_chrome(self):
        """Запускает Chrome с CDP портом"""
        chrome_path = "/usr/bin/google-chrome"
        
        if not os.path.exists(chrome_path):
            chrome_path = "/usr/bin/google-chrome-stable"
        
        # Проверяем, что Chrome существует
        if not os.path.exists(chrome_path):
            raise Exception(f"Chrome не найден: {chrome_path}")
        
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
        
        logger.info(f"Запускаю Chrome: {' '.join(cmd)}")
        
        self.chrome_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Ждём запуска Chrome
        for i in range(10):
            await asyncio.sleep(1)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:9222/json") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                break
            except:
                continue
        else:
            raise Exception("Chrome не запустился")
        
        await self.connect_to_cdp()
        self.is_running = True
        
        # Запускаем слушатель событий в фоне
        self.listener_task = asyncio.create_task(self.listen_events())
        
        logger.info("✅ Браузер готов")
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
        
        logger.info("✅ Подключен к CDP")
    
    async def listen_events(self):
        """Слушает события CDP (не блокирует recv)"""
        try:
            while self.is_running:
                try:
                    response = await asyncio.wait_for(
                        self.websocket.recv(), 
                        timeout=0.1
                    )
                    data = json.loads(response)
                    
                    # Если это ответ на команду
                    if "id" in data:
                        msg_id = data["id"]
                        if msg_id in self.response_queue:
                            self.response_queue[msg_id] = data
                            continue
                    
                    # Если это событие
                    if "method" in data:
                        if data["method"] == "Page.loadEventFired":
                            logger.info("✅ Страница загружена")
                        elif data["method"] == "Runtime.consoleAPICalled":
                            args = data["params"].get("args", [])
                            for arg in args:
                                logger.info(f"🖥️ Консоль: {arg.get('value')}")
                        elif data["method"] == "Network.requestWillBeSent":
                            logger.info(f"🌐 Запрос: {data['params'].get('request', {}).get('url')}")
                        
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket закрыт")
                    break
                except Exception as e:
                    logger.error(f"Ошибка listener: {e}")
                    
        except Exception as e:
            logger.error(f"Listener остановлен: {e}")
    
    async def send_cdp_command(self, method: str, params: Dict = None) -> Dict:
        """Отправляет CDP команду и ждёт ответа"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        # Отправляем команду
        await self.websocket.send(json.dumps(message))
        
        # Ждём ответа с этим ID
        for _ in range(50):  # Максимум 5 секунд
            if msg_id in self.response_queue:
                response = self.response_queue.pop(msg_id)
                if "error" in response:
                    raise Exception(f"CDP Error: {response['error']}")
                return response
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Нет ответа на команду {method} (id: {msg_id})")
    
    # ============ МЕТОДЫ ДЛЯ РАБОТЫ ============
    
    async def navigate(self, url: str) -> Dict:
        """Переход по URL"""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return await self.send_cdp_command("Page.navigate", {"url": url})
    
    async def get_document(self) -> Dict:
        """Получить DOM дерево"""
        return await self.send_cdp_command("DOM.getDocument")
    
    async def query_selector(self, selector: str) -> Optional[int]:
        """Поиск элемента по CSS"""
        try:
            doc = await self.get_document()
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
            
            # Клик
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
        """Ввод текста"""
        if selector:
            node_id = await self.query_selector(selector)
            if node_id:
                await self.send_cdp_command("DOM.focus", {"nodeId": node_id})
                await asyncio.sleep(0.1)
        
        return await self.send_cdp_command("Input.insertText", {"text": text})
    
    async def take_screenshot(self, full_page: bool = False) -> Dict:
        """Скриншот"""
        params = {
            "format": "png",
            "captureBeyondViewport": full_page,
            "fromSurface": True
        }
        return await self.send_cdp_command("Page.captureScreenshot", params)
    
    async def get_page_html(self) -> str:
        """Получить HTML"""
        result = await self.send_cdp_command("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True
        })
        return result["result"].get("value", "")
    
    async def get_title(self) -> str:
        """Получить заголовок"""
        result = await self.send_cdp_command("Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True
        })
        return result["result"].get("value", "")
    
    async def execute_js(self, script: str) -> Dict:
        """Выполнить JavaScript"""
        return await self.send_cdp_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
    
    async def emulate_device(self, width: int, height: int, mobile: bool = False, scale: float = 1):
        """Эмуляция устройства"""
        return await self.send_cdp_command("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": scale,
            "mobile": mobile,
            "screenOrientation": {"type": "portraitPrimary", "angle": 0}
        })
    
    async def close(self):
        """Закрытие"""
        self.is_running = False
        
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except:
                pass
        
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
        await update.message.reply_text("✅ Браузер готов!\n\n📋 Команды:\n• открой google.com\n• скриншот\n• нажми на #id\n• введи текст в #input")
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
            await asyncio.sleep(1)
            title = await agent.get_title()
            await update.message.reply_text(f"✅ Открыл: {url}\n📌 Заголовок: {title}")
        
        elif "скрин" in user_input or "сфоткай" in user_input:
            full = "всей" in user_input or "вся" in user_input
            result = await agent.take_screenshot(full_page=full)
            
            if "data" in result.get("result", {}):
                image_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(image_data, caption="📸 Скриншот")
            else:
                await update.message.reply_text("❌ Не удалось сделать скриншот")
        
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
                await update.message.reply_text(f"✅ Нашёл элемент: {selector}")
            else:
                await update.message.reply_text(f"❌ Элемент не найден: {selector}")
        
        elif "html" in user_input:
            html = await agent.get_page_html()
            await update.message.reply_text(f"📄 HTML ({len(html)} символов):\n\n{html[:500]}...")
        
        elif "помощь" in user_input or "help" in user_input:
            await update.message.reply_text(
                "📋 **Команды:**\n\n"
                "🌐 **Навигация:**\n"
                "• открой google.com\n"
                "• назад / вперед\n"
                "• обнови\n\n"
                "🖱️ **Взаимодействие:**\n"
                "• нажми на #id\n"
                "• введи текст в #input\n"
                "• найди #id\n\n"
                "📸 **Скриншоты:**\n"
                "• скриншот\n"
                "• скриншот всей страницы\n\n"
                "📄 **Данные:**\n"
                "• html\n"
                "• заголовок\n"
                "• url"
            )
        
        elif "заголовок" in user_input:
            title = await agent.get_title()
            await update.message.reply_text(f"📌 {title}")
        
        elif "url" in user_input:
            result = await agent.execute_js("window.location.href")
            url = result["result"].get("value", "")
            await update.message.reply_text(f"🔗 {url}")
        
        elif "эмулируй iphone" in user_input:
            await agent.emulate_device(375, 812, True, 3)
            await update.message.reply_text("📱 Эмулирую iPhone")
        
        else:
            await update.message.reply_text(
                "🤔 Не понял. Напиши 'помощь'\n"
                "Или попробуй: 'открой google.com'"
            )
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()