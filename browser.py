import asyncio
import json
import requests
import websockets
from subprocess import Popen, PIPE
import time

class Browser:
    def __init__(self):
        self.ws = None
        self.process = None
        self.debug_port = 9222
        self.chrome_path = "/usr/bin/google-chrome"
        self.viewport_width = 1280
        self.viewport_height = 720
    
    async def start(self):
        """Запуск Chrome с открытым CDP"""
        self.process = Popen([
            self.chrome_path,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={self.debug_port}"
        ], stdout=PIPE, stderr=PIPE)
        
        await asyncio.sleep(2)
        
        ws_url = self._get_websocket_url()
        self.ws = await websockets.connect(ws_url)
        
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        
        # Устанавливаем размер окна 1280x720
        await self.set_viewport(self.viewport_width, self.viewport_height)
        
        return self
    
    def _get_websocket_url(self):
        """Получить WebSocket URL из /json/list"""
        resp = requests.get(f"http://localhost:{self.debug_port}/json/list")
        pages = resp.json()
        
        if not pages:
            # Создаём новую вкладку, если нет ни одной
            resp = requests.get(f"http://localhost:{self.debug_port}/json/new")
            return resp.json()["webSocketDebuggerUrl"]
        
        return pages[0]["webSocketDebuggerUrl"]
    
    async def send(self, method, params=None):
        """Отправить CDP-команду"""
        if params is None:
            params = {}
        
        msg = {
            "id": int(time.time() * 1000),
            "method": method,
            "params": params
        }
        
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        return json.loads(response)
    
    async def set_viewport(self, width=1280, height=720):
        """Установить размер окна через CDP"""
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
            "screenWidth": width,
            "screenHeight": height,
            "captureBeyondViewport": False
        })
    
    async def goto(self, url):
        """Навигация (CDP)"""
        return await self.send("Page.navigate", {"url": url})
    
    async def screenshot(self):
        """Скриншот через CDP"""
        result = await self.send("Page.captureScreenshot")
        return result["result"]["data"]
    
    async def close(self):
        """Закрыть браузер"""
        if self.ws:
            await self.ws.close()
        if self.process:
            self.process.terminate()
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, *args):
        await self.close()