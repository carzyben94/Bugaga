import subprocess
import time
import json 
import asyncio
import httpx
import websockets
import base64
from typing import Optional, Dict, Any

class ChromiumBrowser:
    def __init__(self, port: int = 9222):
        self.port = port
        self.process = None
        self.websocket = None
        self.ws_url = None
        self.page_id = None
        self.viewport_width = 1280
        self.viewport_height = 720
        
    def launch(self, headless: bool = True):
        """Запускает Chromium с открытым портом для отладки"""
        cmd = [
            "chromium-browser",
            f"--remote-debugging-port={self.port}",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ]
        if headless:
            cmd.append("--headless=new")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("⏳ Ожидание запуска браузера...")
        time.sleep(2)
        print("✅ Браузер запущен")
        
    async def get_ws_url(self) -> str:
        """Получает WebSocket URL первой вкладки через /json/list"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:{self.port}/json/list")
            pages = resp.json()
            
            if not pages:
                raise Exception("Нет открытых вкладок. Запусти браузер с --remote-debugging-port")
            
            self.page_id = pages[0]["id"]
            ws_url = pages[0]["webSocketDebuggerUrl"]
            print(f"📄 Найдена страница: {self.page_id}")
            return ws_url
            
    async def connect(self):
        """Подключается к браузеру через WebSocket"""
        if not self.ws_url:
            self.ws_url = await self.get_ws_url()
        self.websocket = await websockets.connect(self.ws_url)
        print("🔗 WebSocket подключен")
        
        # Включаем необходимые домены
        await self.send_command("Page.enable")
        await self.send_command("Runtime.enable")
        
    async def send_command(self, method: str, params: Dict[str, Any] = None) -> Dict:
        """Отправляет CDP-команду и возвращает ответ"""
        if not self.websocket:
            await self.connect()
            
        msg_id = int(time.time() * 1000)
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        await self.websocket.send(json.dumps(msg))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def set_viewport(self, width: int = 1280, height: int = 720):
        """Устанавливает размер окна для избежания ошибок с размерами скриншотов"""
        self.viewport_width = width
        self.viewport_height = height
        
        params = {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
            "scale": 1,
            "screenWidth": width,
            "screenHeight": height,
            "positionX": 0,
            "positionY": 0
        }
        
        result = await self.send_command("Emulation.setDeviceMetricsOverride", params)
        print(f"📐 Установлен размер окна: {width}x{height}")
        return result
    
    async def navigate(self, url: str) -> Dict:
        """Переходит по URL"""
        print(f"🌐 Переход на {url}")
        result = await self.send_command("Page.navigate", {"url": url})
        
        # Ждём загрузки страницы
        await asyncio.sleep(1)
        return result
    
    async def evaluate(self, expression: str) -> Any:
        """Выполняет JavaScript и возвращает результат"""
        result = await self.send_command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True}
        )
        
        if "exceptionDetails" in result:
            raise Exception(f"JS Error: {result['exceptionDetails']}")
        
        return result.get("result", {}).get("result", {}).get("value")
    
    async def screenshot(self, format: str = "png", full_page: bool = False) -> bytes:
        """Делает скриншот с корректными размерами"""
        # Устанавливаем размер перед скриншотом
        await self.set_viewport(self.viewport_width, self.viewport_height)
        
        params = {
            "format": format,
            "captureBeyondViewport": False  # ✅ Ключевой параметр!
        }
        
        if full_page:
            # Для полной страницы нужно знать высоту контента
            height = await self.evaluate("document.documentElement.scrollHeight")
            if height and height > self.viewport_height:
                await self.set_viewport(self.viewport_width, min(int(height), 10000))
        
        result = await self.send_command("Page.captureScreenshot", params)
        return base64.b64decode(result["result"]["data"])
    
    async def click(self, selector: str):
        """Клик по элементу"""
        # Находим элемент
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{
                x: rect.left + rect.width/2,
                y: rect.top + rect.height/2
            }};
        }})()
        """
        pos = await self.evaluate(js_code)
        if not pos:
            raise Exception(f"Элемент {selector} не найден")
        
        # Кликаем через CDP
        params = {
            "x": pos["x"],
            "y": pos["y"],
            "button": "left",
            "clickCount": 1
        }
        await self.send_command("Input.dispatchMouseEvent", {"type": "mouseMoved", **params})
        await self.send_command("Input.dispatchMouseEvent", {"type": "mousePressed", **params})
        await self.send_command("Input.dispatchMouseEvent", {"type": "mouseReleased", **params})
        print(f"🖱️ Клик по {selector}")
    
    async def type_text(self, text: str):
        """Вводит текст"""
        for char in text:
            params = {"text": char}
            await self.send_command("Input.insertText", params)
        print(f"⌨️ Введён текст: {text}")
    
    async def disconnect(self):
        """Закрывает WebSocket-соединение"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print("🔌 WebSocket отключен")
            
    def close(self):
        """Закрывает браузер"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            print("🛑 Браузер закрыт")


# === ТЕСТ ===
async def test_browser():
    print("🚀 Запуск теста браузера")
    
    browser = ChromiumBrowser()
    browser.launch(headless=True)
    
    try:
        await browser.connect()
        print("✅ Подключение успешно!")
        
        # Устанавливаем размер вьюпорта
        await browser.set_viewport(1280, 720)
        
        # Открываем сайт
        await browser.navigate("https://example.com")
        
        # Получаем заголовок
        title = await browser.evaluate("document.title")
        print(f"📄 Заголовок: {title}")
        
        # Делаем скриншот
        img = await browser.screenshot()
        with open("screenshot.png", "wb") as f:
            f.write(img)
        print("📸 Скриншот сохранён (1280x720)")
        
        # Проверяем клик
        await browser.click("h1")
        print("✅ Клик по h1 выполнен")
        
        # Проверяем ввод текста
        await browser.type_text("Привет, мир!")
        print("✅ Текст введён")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.disconnect()
        browser.close()

if __name__ == "__main__":
    asyncio.run(test_browser())