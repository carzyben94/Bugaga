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
from mask import Mask

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
        self._msg_id = 0
        self.mask = Mask()
        self._keep_alive_task = None  # ← задача keep-alive
        
    def _find_chrome(self) -> str:
        possible_names = [
            "chromium", "chromium-browser", "chrome", "google-chrome",
            "google-chrome-stable", "chrome-browser"
        ]
        possible_paths = [
            "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/chrome",
            "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium", "/snap/bin/chrome",
            "/usr/local/bin/chromium", "/usr/local/bin/chrome",
            "/opt/google/chrome/chrome", "/opt/chromium/chrome",
            "/usr/lib/chromium-browser/chromium-browser",
            "/usr/lib/chromium/chromium", "/app/chromium/chrome",
            "/usr/lib/google-chrome/chrome", "/usr/lib64/google-chrome/chrome"
        ]
        
        for name in possible_names:
            path = shutil.which(name)
            if path:
                print(f"✅ Найден Chrome (which): {path}")
                return path
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"✅ Найден Chrome (путь): {path}")
                return path
        
        try:
            result = subprocess.run(
                ["find", "/", "-name", "chromium", "-type", "f", "-executable"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if line and os.access(line, os.X_OK):
                    print(f"✅ Найден Chrome (find): {line}")
                    return line
        except:
            pass
        
        raise Exception("Chromium/Chrome не найден! Установи через: apt-get install chromium")
    
    def launch(self, headless: bool = True):
        cmd = Mask.get_launch_args(self.chrome_path, self.port)
        
        print(f"🚀 Запуск браузера с маскировкой: {self.chrome_path}")
        print(f"📋 Команда: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        
        if self.process.poll() is not None:
            raise Exception(f"Браузер упал при запуске (код: {self.process.returncode})")
        print("✅ Браузер запущен с маскировкой")
        
    async def get_ws_url(self) -> str:
        async with httpx.AsyncClient() as client:
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
    
    async def _keep_alive(self):
        """Отправляет пинг каждые 10 секунд, чтобы сохранить WebSocket"""
        while self.websocket and not self.websocket.closed:
            try:
                await asyncio.sleep(10)
                await self.websocket.ping()
                print("💓 WebSocket ping отправлен")
            except Exception as e:
                print(f"⚠️ Keep-alive ошибка: {e}")
                break
    
    async def connect(self):
        if not self.ws_url:
            self.ws_url = await self.get_ws_url()
        
        # ✅ WebSocket с лимитом 10 МБ
        self.websocket = await websockets.connect(
            self.ws_url,
            max_size=10 * 1024 * 1024  # 10 МБ
        )
        print("🔗 WebSocket подключен (макс. размер: 10 МБ)")
        
        # Запускаем keep-alive в фоне
        if self._keep_alive_task is None or self._keep_alive_task.done():
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        
        await self.send_command("Page.enable")
        await self.send_command("Runtime.enable")
        
        print("🕵️ Применяю JS-маскировку...")
        js_mask = Mask.get_js_mask()
        await self.send_command("Page.addScriptToEvaluateOnNewDocument", {"source": js_mask})
        print("✅ JS-маскировка применена")
        
    async def send_command(self, method: str, params: Dict[str, Any] = None) -> Dict:
        if not self.websocket:
            await self.connect()
        
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        
        print(f"📤 Отправка: {method} (id={self._msg_id})")
        await self.websocket.send(json.dumps(msg))
        
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            if "id" in data:
                if "error" in data:
                    raise Exception(f"CDP Error: {data['error']}")
                return data
            print(f"📡 Событие: {data.get('method')}")
    
    async def set_viewport(self, width: int = 1280, height: int = 720):
        self.viewport_width = width
        self.viewport_height = height
        params = {
            "width": width, "height": height, "deviceScaleFactor": 1,
            "mobile": False, "scale": 1, "screenWidth": width,
            "screenHeight": height, "positionX": 0, "positionY": 0
        }
        await self.send_command("Emulation.setDeviceMetricsOverride", params)
        print(f"📐 Установлен размер окна: {width}x{height}")
    
    async def navigate(self, url: str) -> Dict:
        print(f"🌐 Переход на {url}")
        
        await self.send_command("Page.enable")
        result = await self.send_command("Page.navigate", {"url": url})
        
        for attempt in range(30):
            await asyncio.sleep(0.5)
            try:
                ready_state = await self.evaluate("document.readyState")
                if ready_state == "complete":
                    print(f"✅ Страница загружена (попытка {attempt+1})")
                    break
            except Exception as e:
                print(f"⏳ Ожидание загрузки... ({attempt+1}/30)")
        
        await asyncio.sleep(1)
        return result
    
    async def evaluate(self, expression: str) -> Any:
        result = await self.send_command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True}
        )
        if "exceptionDetails" in result:
            raise Exception(f"JS Error: {result['exceptionDetails']}")
        return result.get("result", {}).get("result", {}).get("value")
    
    async def screenshot(self, format: str = "png") -> bytes:
        await self.set_viewport(self.viewport_width, self.viewport_height)
        result = await self.send_command(
            "Page.captureScreenshot",
            {"format": format, "captureBeyondViewport": False}
        )
        if "result" in result and "data" in result["result"]:
            return base64.b64decode(result["result"]["data"])
        elif "data" in result:
            return base64.b64decode(result["data"])
        else:
            raise Exception(f"Неизвестный ответ CDP: {result}")
    
    async def click_human(self, selector: str):
        print(f"🖱️ Человеческий клик по {selector}")
        js_code = Mask.get_human_click_js(selector)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception(f"Не удалось кликнуть по {selector}")
        await asyncio.sleep(0.5)
    
    async def type_human(self, selector: str, text: str):
        print(f"⌨️ Человеческий ввод: {text}")
        js_code = Mask.get_human_type_js(selector, text)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception(f"Не удалось ввести текст в {selector}")
        await asyncio.sleep(0.5)
    
    async def scroll_human(self, distance: int):
        print(f"📜 Человеческий скролл: {distance}px")
        js_code = Mask.get_human_scroll_js(distance)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception("Не удалось выполнить скролл")
        await asyncio.sleep(0.3)
    
    async def disconnect(self):
        # Останавливаем keep-alive
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except:
                pass
            self._keep_alive_task = None
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print("🔌 WebSocket отключен")
            
    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            print("🛑 Браузер закрыт")