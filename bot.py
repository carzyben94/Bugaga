import os
import json
import asyncio
import logging
import base64
import subprocess
import aiohttp
import websockets
from typing import Dict, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.DEBUG)  # Включаем детальное логирование
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
        self.response_queue = {}
        self.listener_task = None
        
    async def start_chrome(self):
        """Запускает Chrome с CDP портом"""
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium"
        ]
        
        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_path = path
                break
        
        if not chrome_path:
            raise Exception("Chrome не найден! Установите: apt-get install -y google-chrome-stable")
        
        logger.info(f"🔍 Использую Chrome: {chrome_path}")
        
        cmd = [
            chrome_path,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--remote-debugging-port=9222",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080",
            "--user-data-dir=/tmp/chrome-profile"
        ]
        
        logger.info(f"🚀 Запускаю Chrome: {' '.join(cmd)}")
        
        self.chrome_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Ждём запуска Chrome с проверкой
        for i in range(20):  # 20 секунд
            await asyncio.sleep(1)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:9222/json/version") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            logger.info(f"✅ Chrome запущен: {data.get('Browser', 'Unknown')}")
                            break
            except Exception as e:
                logger.debug(f"Ожидание Chrome... {i+1}/20")
        else:
            # Проверяем вывод ошибок
            stderr = await self.chrome_process.stderr.read()
            stdout = await self.chrome_process.stdout.read()
            logger.error(f"Chrome stderr: {stderr.decode() if stderr else 'Нет'}")
            logger.error(f"Chrome stdout: {stdout.decode() if stdout else 'Нет'}")
            raise Exception("Chrome не запустился за 20 секунд")
        
        await self.connect_to_cdp()
        self.is_running = True
        
        # Запускаем слушатель
        self.listener_task = asyncio.create_task(self.listen_events())
        
        logger.info("✅ Агент готов")
        return True
    
    async def connect_to_cdp(self):
        """Подключается к CDP"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:9222/json") as resp:
                    if resp.status != 200:
                        raise Exception(f"CDP не отвечает: {resp.status}")
                    data = await resp.json()
                    if not data:
                        raise Exception("Нет активных страниц")
                    
                    ws_url = data[0]["webSocketDebuggerUrl"]
                    logger.info(f"🔗 WebSocket URL: {ws_url}")
            
            self.websocket = await websockets.connect(
                ws_url,
                max_size=10**7,
                ping_interval=20,
                ping_timeout=60
            )
            logger.info("✅ WebSocket подключен")
            
            # Включаем домены с таймаутом
            await self.send_cdp_command("Page.enable", timeout=10)
            await self.send_cdp_command("Runtime.enable", timeout=10)
            await self.send_cdp_command("Network.enable", timeout=10)
            await self.send_cdp_command("DOM.enable", timeout=10)
            
            logger.info("✅ Домены включены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к CDP: {e}")
            raise
    
    async def send_cdp_command(self, method: str, params: Dict = None, timeout: int = 5) -> Dict:
        """Отправляет CDP команду с таймаутом"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        logger.debug(f"📤 Отправка: {method} (id: {msg_id})")
        
        try:
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            raise Exception(f"Ошибка отправки: {e}")
        
        # Ждём ответа
        for _ in range(timeout * 10):  # timeout * 0.1 секунды
            if msg_id in self.response_queue:
                response = self.response_queue.pop(msg_id)
                logger.debug(f"📥 Ответ: {method} (id: {msg_id})")
                if "error" in response:
                    raise Exception(f"CDP Error: {response['error']}")
                return response
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Нет ответа на команду {method} (id: {msg_id}) за {timeout}с")
    
    async def listen_events(self):
        """Слушает события CDP"""
        try:
            while self.is_running and self.websocket:
                try:
                    response = await asyncio.wait_for(
                        self.websocket.recv(), 
                        timeout=1.0
                    )
                    data = json.loads(response)
                    
                    # Ответ на команду
                    if "id" in data:
                        msg_id = data["id"]
                        self.response_queue[msg_id] = data
                        continue
                    
                    # Событие
                    if "method" in data:
                        method = data["method"]
                        if method == "Page.loadEventFired":
                            logger.info("✅ Страница загружена")
                        elif method == "Runtime.consoleAPICalled":
                            args = data["params"].get("args", [])
                            for arg in args:
                                logger.info(f"🖥️ Консоль: {arg.get('value')}")
                        elif method == "Network.requestWillBeSent":
                            url = data["params"].get("request", {}).get("url", "")
                            if url:
                                logger.info(f"🌐 Запрос: {url[:100]}")
                                
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("⚠️ WebSocket закрыт")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка listener: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Listener остановлен: {e}")
    
    # ============ МЕТОДЫ ДЛЯ РАБОТЫ ============
    
    async def navigate(self, url: str) -> Dict:
        """Переход по URL"""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        result = await self.send_cdp_command("Page.navigate", {"url": url})
        
        # Ждём загрузки
        await asyncio.sleep(2)
        
        return result
    
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
    
    async def get_title(self) -> str:
        """Получить заголовок"""
        result = await self.send_cdp_command("Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True
        })
        return result["result"].get("value", "")
    
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
        
        if self.chrome_process:
            try:
                self.chrome_process.terminate()
                await asyncio.sleep(2)
                if self.chrome_process.returncode is None:
                    self.chrome_process.kill()
            except:
                pass
        
        logger.info("🛑 Агент остановлен")

# ============ ТЕЛЕГРАМ БОТ ============
agent = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global agent
    await update.message.reply_text("🧠 Запускаю AGNES CDP Агент...\n⏳ Это может занять 5-10 секунд...")
    
    try:
        agent = AgnesCDPAgent()
        await agent.start_chrome()
        
        await update.message.reply_text(
            "✅ **Браузер готов!**\n\n"
            "📋 **Команды:**\n"
            "• открой google.com\n"
            "• скриншот\n"
            "• нажми на #id\n"
            "• введи текст в #input\n"
            "• найди #id\n"
            "• заголовок\n"
            "• url\n\n"
            "💡 Напиши 'помощь' для полного списка",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        error_msg = str(e)
        if "Chrome" in error_msg:
            await update.message.reply_text(
                "❌ **Chrome не установлен!**\n\n"
                "На Railway добавьте в настройки:\n"
                "```\n"
                "apt-get update && apt-get install -y google-chrome-stable\n"
                "```",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Ошибка: {error_msg}")

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
            if not url:
                await update.message.reply_text("❌ Укажи URL: открой google.com")
                return
            
            await agent.navigate(url)
            await asyncio.sleep(1)
            title = await agent.get_title()
            await update.message.reply_text(f"✅ Открыл: {url}\n📌 Заголовок: {title}")
        
        elif "скрин" in user_input or "сфоткай" in user_input:
            full = "всей" in user_input or "вся" in user_input
            result = await agent.take_screenshot(full_page=full)
            
            if "data" in result.get("result", {}):
                image_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(
                    image_data, 
                    caption=f"📸 Скриншот {'всей страницы' if full else 'страницы'}"
                )
            else:
                await update.message.reply_text("❌ Не удалось сделать скриншот")
        
        elif "нажми" in user_input and "на " in user_input:
            selector = user_input.split("на ")[1].strip()
            if not selector:
                await update.message.reply_text("❌ Укажи селектор: нажми на #button")
                return
            
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
            
            if not text:
                await update.message.reply_text("❌ Укажи текст: введи привет")
                return
            
            await agent.type_text(text, selector)
            await update.message.reply_text(f"✅ Ввёл: {text}")
        
        elif "найди" in user_input:
            selector = user_input.split("найди ")[1].strip()
            if not selector:
                await update.message.reply_text("❌ Укажи селектор: найди #id")
                return
            
            node_id = await agent.query_selector(selector)
            if node_id:
                await update.message.reply_text(f"✅ Нашёл элемент: {selector}")
            else:
                await update.message.reply_text(f"❌ Элемент не найден: {selector}")
        
        elif "заголовок" in user_input or "title" in user_input:
            title = await agent.get_title()
            await update.message.reply_text(f"📌 {title}")
        
        elif "url" in user_input or "адрес" in user_input:
            result = await agent.send_cdp_command("Runtime.evaluate", {
                "expression": "window.location.href",
                "returnByValue": True
            })
            url = result["result"].get("value", "")
            await update.message.reply_text(f"🔗 {url}")
        
        elif "html" in user_input or "код" in user_input:
            result = await agent.send_cdp_command("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True
            })
            html = result["result"].get("value", "")
            await update.message.reply_text(f"📄 HTML ({len(html)} символов):\n\n{html[:500]}...")
        
        elif "назад" in user_input:
            await agent.send_cdp_command("Runtime.evaluate", {
                "expression": "window.history.back()"
            })
            await update.message.reply_text("⬅️ Назад")
        
        elif "вперед" in user_input or "вперёд" in user_input:
            await agent.send_cdp_command("Runtime.evaluate", {
                "expression": "window.history.forward()"
            })
            await update.message.reply_text("➡️ Вперед")
        
        elif "обнови" in user_input or "refresh" in user_input:
            await agent.send_cdp_command("Page.reload")
            await update.message.reply_text("🔄 Обновил страницу")
        
        elif "куки" in user_input or "cookies" in user_input:
            result = await agent.send_cdp_command("Network.getCookies")
            cookies = result.get("result", {}).get("cookies", [])
            if cookies:
                text = "🍪 **Cookies:**\n\n"
                for c in cookies[:10]:
                    text += f"• {c.get('name')} = {c.get('value')}\n"
                await update.message.reply_text(text, parse_mode='Markdown')
            else:
                await update.message.reply_text("🍪 Куки не найдены")
        
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
                "• url\n"
                "• куки\n\n"
                "💡 **Примеры:**\n"
                "• открой google.com\n"
                "• найди button\n"
                "• нажми на a[href*='login']\n"
                "• введи привет в #search",
                parse_mode='Markdown'
            )
        
        else:
            await update.message.reply_text(
                "🤔 Не понял. Напиши 'помощь' для списка команд\n\n"
                "💡 Попробуй: 'открой google.com'"
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()