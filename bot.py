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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ============= КЛАСС AGNES CDP АГЕНТ =============
class AgnesCDPAgent:
    """AGNES AI агент, работающий напрямую с Chrome DevTools Protocol"""
    
    def __init__(self):
        self.chrome_process = None
        self.websocket = None
        self.tab_id = None
        self.message_id = 0
        self.pending_commands = {}
        self.memory = []
        self.is_running = False
        
    async def start_chrome(self):
        """Запускает Chrome с открытым CDP портом"""
        chrome_path = "/usr/bin/google-chrome"
        
        # Проверяем, существует ли Chrome
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
        
        # Ждём запуска
        await asyncio.sleep(3)
        
        # Подключаемся к CDP
        await self.connect_to_cdp()
        
        self.is_running = True
        logger.info("✅ Chrome запущен с CDP портом 9222")
        return True
    
    async def connect_to_cdp(self):
        """Подключается к CDP через WebSocket"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:9222/json") as resp:
                    data = await resp.json()
                    if not data:
                        raise Exception("Chrome не ответил на /json")
                    ws_url = data[0]["webSocketDebuggerUrl"]
                    self.tab_id = data[0]["id"]
            
            # Подключаемся по WebSocket
            self.websocket = await websockets.connect(ws_url)
            logger.info(f"✅ Подключен к CDP: {ws_url}")
            
            # Включаем необходимые домены
            await self.send_cdp_command("Page.enable")
            await self.send_cdp_command("Runtime.enable")
            await self.send_cdp_command("Network.enable")
            await self.send_cdp_command("DOM.enable")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
            raise
    
    async def send_cdp_command(self, method: str, params: Dict = None) -> Dict:
        """Отправляет прямую CDP команду"""
        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }
        
        # Отправляем
        await self.websocket.send(json.dumps(message))
        
        # Ждём ответ
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            
            # Проверяем, что это ответ на наш запрос
            if data.get("id") == self.message_id:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data
    
    # ============ ОСНОВНЫЕ ДЕЙСТВИЯ ============
    
    async def navigate(self, url: str) -> Dict:
        """Переход по URL"""
        return await self.send_cdp_command("Page.navigate", {"url": url})
    
    async def get_document(self) -> Dict:
        """Получить DOM дерево"""
        return await self.send_cdp_command("DOM.getDocument")
    
    async def query_selector(self, selector: str) -> Optional[int]:
        """Поиск элемента по CSS селектору"""
        try:
            doc = await self.get_document()
            root_id = doc["result"]["root"]["nodeId"]
            
            result = await self.send_cdp_command("DOM.querySelector", {
                "nodeId": root_id,
                "selector": selector
            })
            
            node_id = result["result"].get("nodeId")
            if node_id and node_id != 0:
                return node_id
            return None
            
        except Exception as e:
            logger.error(f"Ошибка поиска элемента: {e}")
            return None
    
    async def query_selector_all(self, selector: str) -> List[int]:
        """Поиск всех элементов по CSS селектору"""
        doc = await self.get_document()
        root_id = doc["result"]["root"]["nodeId"]
        
        result = await self.send_cdp_command("DOM.querySelectorAll", {
            "nodeId": root_id,
            "selector": selector
        })
        
        return result["result"].get("nodeIds", [])
    
    async def get_element_text(self, node_id: int) -> str:
        """Получить текст элемента"""
        result = await self.send_cdp_command("DOM.getOuterHTML", {"nodeId": node_id})
        return result["result"].get("outerHTML", "")
    
    async def click_element(self, node_id: int) -> Dict:
        """Клик по элементу"""
        try:
            # Получаем координаты элемента
            rect = await self.send_cdp_command("DOM.getBoxModel", {"nodeId": node_id})
            box = rect["result"]["model"]
            
            # Вычисляем центр
            content = box["content"]
            x = (content[0] + content[4]) / 2
            y = (content[1] + content[5]) / 2
            
            # Отправляем события мыши
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
                # Фокусируемся на элементе
                await self.send_cdp_command("DOM.focus", {"nodeId": node_id})
        
        # Вводим текст
        return await self.send_cdp_command("Input.insertText", {"text": text})
    
    async def take_screenshot(self, full_page: bool = False) -> Dict:
        """Скриншот страницы"""
        params = {"format": "png"}
        if full_page:
            params["captureBeyondViewport"] = True
        
        return await self.send_cdp_command("Page.captureScreenshot", params)
    
    async def execute_js(self, script: str, return_by_value: bool = True) -> Dict:
        """Выполнить JavaScript"""
        return await self.send_cdp_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": return_by_value
        })
    
    async def scroll_to_bottom(self) -> Dict:
        """Прокрутка вниз"""
        return await self.execute_js("window.scrollTo(0, document.body.scrollHeight)")
    
    async def scroll_to_top(self) -> Dict:
        """Прокрутка вверх"""
        return await self.execute_js("window.scrollTo(0, 0)")
    
    async def go_back(self) -> Dict:
        """Назад"""
        return await self.execute_js("window.history.back()")
    
    async def go_forward(self) -> Dict:
        """Вперед"""
        return await self.execute_js("window.history.forward()")
    
    async def reload_page(self) -> Dict:
        """Обновить страницу"""
        return await self.send_cdp_command("Page.reload")
    
    async def get_title(self) -> str:
        """Получить заголовок страницы"""
        result = await self.execute_js("document.title")
        return result["result"].get("value", "")
    
    async def get_url(self) -> str:
        """Получить текущий URL"""
        result = await self.execute_js("window.location.href")
        return result["result"].get("value", "")
    
    async def get_cookies(self) -> Dict:
        """Получить cookies"""
        return await self.send_cdp_command("Network.getCookies")
    
    async def set_cookie(self, name: str, value: str, url: str = None) -> Dict:
        """Установить cookie"""
        return await self.send_cdp_command("Network.setCookie", {
            "name": name,
            "value": value,
            "url": url
        })
    
    async def get_page_html(self) -> str:
        """Получить HTML страницы"""
        result = await self.execute_js("document.documentElement.outerHTML")
        return result["result"].get("value", "")
    
    async def find_element_by_text(self, text: str) -> Optional[int]:
        """Найти элемент по тексту через XPath"""
        script = f"""
        function findElementByText(text) {{
            const xpath = `//*[contains(text(), '{text}')]`;
            const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            return result.singleNodeValue;
        }}
        return findElementByText('{text}');
        """
        result = await self.execute_js(script, return_by_value=False)
        # Здесь нужна дополнительная обработка для получения nodeId
        return result
    
    async def emulate_device(self, width: int, height: int, mobile: bool = False) -> Dict:
        """Эмуляция устройства"""
        return await self.send_cdp_command("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": mobile,
            "screenOrientation": {"type": "portraitPrimary", "angle": 0}
        })
    
    async def emulate_geolocation(self, latitude: float, longitude: float) -> Dict:
        """Эмуляция геолокации"""
        return await self.send_cdp_command("Emulation.setGeolocationOverride", {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": 100
        })
    
    async def network_offline(self, offline: bool = True) -> Dict:
        """Эмуляция оффлайн режима"""
        return await self.send_cdp_command("Network.emulateNetworkConditions", {
            "offline": offline,
            "latency": 0,
            "downloadThroughput": 0,
            "uploadThroughput": 0
        })
    
    async def close(self):
        """Закрывает браузер"""
        self.is_running = False
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
        if self.chrome_process:
            try:
                self.chrome_process.terminate()
                await asyncio.sleep(1)
                if self.chrome_process.returncode is None:
                    self.chrome_process.kill()
            except:
                pass
        logger.info("Браузер закрыт")

# ============= ТЕЛЕГРАМ БОТ =============
agent = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск бота"""
    global agent
    
    await update.message.reply_text(
        "🧠 **AGNES CDP Агент**\n\n"
        "Запускаю браузер с Chrome DevTools Protocol...\n"
        "Это даст полный контроль над браузером!",
        parse_mode='Markdown'
    )
    
    try:
        agent = AgnesCDPAgent()
        await agent.start_chrome()
        
        await update.message.reply_text(
            "✅ **Браузер готов!**\n\n"
            "Что умею:\n"
            "• 🌐 Открывать сайты\n"
            "• 🖱️ Кликать, вводить текст\n"
            "• 📸 Делать скриншоты\n"
            "• 🔍 Искать элементы\n"
            "• 📜 Парсить данные\n"
            "• 📱 Эмулировать устройства\n"
            "• 🌍 Менять геолокацию\n"
            "• 📶 Работать оффлайн\n"
            "• и многое другое!\n\n"
            "Просто напиши, что нужно сделать!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка запуска: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
    global agent
    
    if not agent or not agent.is_running:
        await update.message.reply_text("⚠️ Браузер не запущен. Используй /start")
        return
    
    user_input = update.message.text.lower()
    await update.message.reply_text("⏳ AGNES выполняет команду...")
    
    try:
        # ============ ОСНОВНЫЕ КОМАНДЫ ============
        
        # Открыть сайт
        if user_input.startswith("открой "):
            url = user_input[7:].strip()
            if not url.startswith("http"):
                url = "https://" + url
            await agent.navigate(url)
            title = await agent.get_title()
            await update.message.reply_text(f"✅ Открыл: {url}\n📌 Заголовок: {title}")
        
        # Скриншот
        elif "скриншот" in user_input:
            full = "всей" in user_input or "вся" in user_input
            result = await agent.take_screenshot(full_page=full)
            
            if "data" in result.get("result", {}):
                image_data = base64.b64decode(result["result"]["data"])
                await update.message.reply_photo(image_data, caption=f"📸 Скриншот {'всей страницы' if full else 'страницы'}")
            else:
                await update.message.reply_text("❌ Не удалось сделать скриншот")
        
        # Нажми на элемент
        elif "нажми" in user_input and "на " in user_input:
            selector = user_input.split("на ")[1].strip()
            node_id = await agent.query_selector(selector)
            if node_id:
                await agent.click_element(node_id)
                await update.message.reply_text(f"✅ Кликнул по: {selector}")
            else:
                await update.message.reply_text(f"❌ Элемент не найден: {selector}")
        
        # Найти элемент
        elif "найди" in user_input:
            selector = user_input.split("найди ")[1].strip()
            node_id = await agent.query_selector(selector)
            if node_id:
                text = await agent.get_element_text(node_id)
                await update.message.reply_text(f"✅ Нашёл элемент:\n📄 {text[:500]}...")
            else:
                await update.message.reply_text(f"❌ Элемент не найден: {selector}")
        
        # Ввести текст
        elif "введи" in user_input:
            if "в " in user_input:
                parts = user_input.split("в ")
                text = parts[0].replace("введи", "").strip()
                selector = parts[1].strip()
            else:
                text = user_input.replace("введи", "").strip()
                selector = None
            
            await agent.type_text(text, selector)
            await update.message.reply_text(f"✅ Ввёл текст: {text}")
        
        # Прокрутка
        elif "вниз" in user_input or "вниз" in user_input:
            await agent.scroll_to_bottom()
            await update.message.reply_text("⬇️ Прокрутил вниз")
        
        elif "вверх" in user_input:
            await agent.scroll_to_top()
            await update.message.reply_text("⬆️ Прокрутил вверх")
        
        # Назад/Вперед
        elif "назад" in user_input:
            await agent.go_back()
            await update.message.reply_text("⬅️ Назад")
        
        elif "вперед" in user_input or "вперёд" in user_input:
            await agent.go_forward()
            await update.message.reply_text("➡️ Вперед")
        
        # Обновить
        elif "обнов" in user_input or "refresh" in user_input:
            await agent.reload_page()
            await update.message.reply_text("🔄 Обновил страницу")
        
        # Заголовок
        elif "заголовок" in user_input or "title" in user_input:
            title = await agent.get_title()
            await update.message.reply_text(f"📌 Заголовок: {title}")
        
        # URL
        elif "url" in user_input or "адрес" in user_input:
            url = await agent.get_url()
            await update.message.reply_text(f"🔗 URL: {url}")
        
        # HTML
        elif "html" in user_input or "код" in user_input:
            html = await agent.get_page_html()
            await update.message.reply_text(f"📄 HTML получен ({len(html)} символов)\n\n{html[:500]}...")
        
        # Куки
        elif "куки" in user_input or "cookies" in user_input:
            cookies = await agent.get_cookies()
            if cookies.get("result", {}).get("cookies"):
                text = "🍪 Cookies:\n"
                for c in cookies["result"]["cookies"][:5]:
                    text += f"• {c['name']} = {c['value']}\n"
                await update.message.reply_text(text)
            else:
                await update.message.reply_text("🍪 Куки не найдены")
        
        # Эмуляция устройства
        elif "эмулируй" in user_input or "эмуляция" in user_input:
            if "iphone" in user_input or "телефон" in user_input:
                await agent.emulate_device(375, 812, True)
                await update.message.reply_text("📱 Эмулирую iPhone 15")
            elif "ipad" in user_input or "планшет" in user_input:
                await agent.emulate_device(1024, 1366, True)
                await update.message.reply_text("📱 Эмулирую iPad Pro")
            else:
                await agent.emulate_device(1920, 1080, False)
                await update.message.reply_text("🖥️ Эмулирую Desktop")
        
        # JavaScript
        elif "js" in user_input or "javascript" in user_input:
            script = user_input.split("js ")[1] if "js " in user_input else user_input.split("javascript ")[1]
            result = await agent.execute_js(script)
            value = result.get("result", {}).get("value")
            await update.message.reply_text(f"✅ Результат:\n{value}")
        
        # Помощь
        elif "помощь" in user_input or "help" in user_input:
            help_text = """
🤖 **Доступные команды:**

🌐 **Навигация:**
• `открой google.com`
• `назад` / `вперед`
• `обнови`

🖱️ **Взаимодействие:**
• `найди #id` - найти элемент
• `нажми на #button` - кликнуть
• `введи текст в #input`

📸 **Скриншоты:**
• `скриншот` - обычный
• `скриншот всей страницы`

🔍 **Парсинг:**
• `заголовок`
• `url`
• `html`
• `куки`

📱 **Эмуляция:**
• `эмулируй iphone`
• `эмулируй ipad`
• `эмулируй desktop`

⚡ **Продвинутые:**
• `js document.title` - выполнить JS
• `вниз` / `вверх` - скролл

💡 **Примеры:**
• открой github.com
• найди header
• нажми на button.login
• скриншот всей страницы
• js alert('Hello')
"""
            await update.message.reply_text(help_text, parse_mode='Markdown')
        
        else:
            await update.message.reply_text(
                "🤔 Не понял команду.\n"
                "Напиши /help для списка команд\n"
                "Или просто 'открой google.com'"
            )
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановка бота"""
    global agent
    
    if agent:
        await agent.close()
        agent = None
    
    await update.message.reply_text("🛑 Браузер остановлен. Агент отключен.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус агента"""
    global agent
    
    if agent and agent.is_running:
        url = await agent.get_url() if agent.websocket else "Неизвестно"
        status_text = f"""
📊 **Статус AGNES CDP Агента**

Браузер: ✅ Активен
CDP: ✅ Подключен
Текущий URL: {url}
Память: {len(agent.memory)} действий
        """
    else:
        status_text = "❌ Агент не активен. Используй /start"
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ Произошла внутренняя ошибка")

# ============= ЗАПУСК =============
def main():
    """Главная функция"""
    try:
        app = Application.builder().token(TOKEN).build()
        
        # Команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stop", stop))
        app.add_handler(CommandHandler("status", status))
        app.add_handler(CommandHandler("help", handle_message))
        
        # Обработчик сообщений
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        app.add_error_handler(error_handler)
        
        logger.info("🚀 AGNES CDP Агент запущен!")
        logger.info("💡 Используй /start для запуска браузера")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()