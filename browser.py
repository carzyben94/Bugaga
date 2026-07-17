import subprocess
import time
import json
import asyncio
import httpx
import websockets
import base64
import shutil
import os
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
        self.chrome_path = self._find_chrome()
        
    def _find_chrome(self) -> str:
        """Ищет Chromium/Chrome по множеству путей"""
        
        # Список возможных имён
        possible_names = [
            "chromium",
            "chromium-browser",
            "chrome",
            "google-chrome",
            "google-chrome-stable",
            "chrome-browser"
        ]
        
        # Список возможных путей
        possible_paths = [
            # Стандартные пути
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chrome-browser",
            # Snap
            "/snap/bin/chromium",
            "/snap/bin/chrome",
            # Пользовательские
            "/usr/local/bin/chromium",
            "/usr/local/bin/chrome",
            "/opt/google/chrome/chrome",
            "/opt/chromium/chrome",
            # Дополнительные
            "/usr/lib/chromium-browser/chromium-browser",
            "/usr/lib/chromium/chromium",
            "/app/chromium/chrome",
            # Вендорские
            "/usr/lib/google-chrome/chrome",
            "/usr/lib64/google-chrome/chrome"
        ]
        
        # 1. Проверяем через which (поиск в PATH)
        for name in possible_names:
            path = shutil.which(name)
            if path:
                print(f"✅ Найден Chrome (which): {path}")
                return path
        
        # 2. Проверяем конкретные пути
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"✅ Найден Chrome (путь): {path}")
                return path
        
        # 3. Ищем через find (на всякий случай)
        try:
            result = subprocess.run(
                ["find", "/", "-name", "chromium", "-type", "f", "-executable", "2>/dev/null"],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line and os.access(line, os.X_OK):
                    print(f"✅ Найден Chrome (find): {line}")
                    return line
        except:
            pass
        
        # 4. Пробуем через dpkg (Debian/Ubuntu)
        try:
            result = subprocess.run(
                ["dpkg", "-L", "chromium", "2>/dev/null"],
                capture_output=True,
                text=True,
                timeout=3
            )
            for line in result.stdout.split('\n'):
                if line.endswith("/chromium") and os.access(line, os.X_OK):
                    print(f"✅ Найден Chrome (dpkg): {line}")
                    return line
        except:
            pass
        
        raise Exception(
            "Chromium/Chrome не найден!\n"
            "Установи через: apt-get install chromium\n"
            "Или укажи путь вручную в CHROME_PATH переменной окружения"
        )
    
    def launch(self, headless: bool = True):
        """Запускает Chromium"""
        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={self.port}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
        if headless:
            cmd.append("--headless=new")
            cmd.append("--disable-software-rasterizer")
        
        print(f"🚀 Запуск браузера: {self.chrome_path}")
        print(f"📋 Команда: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Ждём запуска
        time.sleep(3)
        
        # Проверяем, что процесс жив
        if self.process.poll() is not None:
            raise Exception(f"Браузер упал при запуске (код: {self.process.returncode})")
        
        print("✅ Браузер запущен")
        
    async def get_ws_url(self) -> str:
        """Получает WebSocket URL первой вкладки через /json/list"""
        async with httpx.AsyncClient() as client:
            # Пробуем несколько раз, пока браузер не запустится
            for attempt in range(5):
                try:
                    resp = await client.get(f"http://localhost:{self.port}/json/list")
                    pages = resp.json()
                    
                    if not pages:
                        raise Exception("Нет открытых вкладок")
                    
                    self.page_id = pages[0]["id"]
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    print(f"📄 Найдена страница: {self.page_id}")
                    return ws_url
                except Exception as e:
                    if attempt < 4:
                        print(f"⏳ Ожидание браузера (попытка {attempt+1}/5)...")
                        await asyncio.sleep(1)
                    else:
                        raise Exception(f"Не удалось подключиться к браузеру: {e}")
    
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
        """Устанавливает размер окна"""
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
        
        # Ждём загрузки
        await asyncio.sleep(1)
        return result
    
    async def evaluate(self, expression: str) -> Any:
        """Выполняет JavaScript"""
        result = await self.send_command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True}
        )
        
        if "exceptionDetails" in result:
            raise Exception(f"JS Error: {result['exceptionDetails']}")
        
        return result.get("result", {}).get("result", {}).get("value")
    
    async def screenshot(self, format: str = "png", full_page: bool = False) -> bytes:
        """Делает скриншот"""
        await self.set_viewport(self.viewport_width, self.viewport_height)
        
        params = {
            "format": format,
            "captureBeyondViewport": False
        }
        
        if full_page:
            height = await self.evaluate("document.documentElement.scrollHeight")
            if height and height > self.viewport_height:
                await self.set_viewport(self.viewport_width, min(int(height), 10000))
        
        result = await self.send_command("Page.captureScreenshot", params)
        return base64.b64decode(result["result"]["data"])
    
    async def click(self, selector: str):
        """Кликает по элементу"""
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
        """Закрывает WebSocket"""
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
        
        await browser.set_viewport(1280, 720)
        await browser.navigate("https://example.com")
        
        title = await browser.evaluate("document.title")
        print(f"📄 Заголовок: {title}")
        
        img = await browser.screenshot()
        with open("screenshot.png", "wb") as f:
            f.write(img)
        print("📸 Скриншот сохранён")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await browser.disconnect()
        browser.close()

if __name__ == "__main__":
    asyncio.run(test_browser())