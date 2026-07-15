import asyncio
import json
import logging
import requests
import websockets
from subprocess import Popen, PIPE, TimeoutExpired
import os

from mask import Mask

logger = logging.getLogger(__name__)

class Browser:
    def __init__(self):
        self.ws = None
        self.process = None
        self.debug_port = 9222
        self.chrome_path = self._find_chrome()
        self.viewport_width = 1280
        self.viewport_height = 720
        self.ws_url = None
        self._msg_id = 0
        self._masked = False
    
    def _find_chrome(self):
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome-stable",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return "/usr/bin/google-chrome"
    
    async def start(self):
        """Запуск Chrome с маскировкой из mask.py"""
        try:
            if not self._is_chrome_running():
                args = Mask.get_launch_args(self.chrome_path, self.debug_port)
                logger.info("🚀 Запуск Chrome с маскировкой...")
                self.process = Popen(args, stdout=PIPE, stderr=PIPE)
                await asyncio.sleep(3)
                if self.process.poll() is not None:
                    raise RuntimeError("Chrome не запустился")
            
            self.ws_url = self._get_websocket_url()
            self.ws = await websockets.connect(self.ws_url)
            
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            await self.set_viewport(self.viewport_width, self.viewport_height)
            
            # Применяем JS-маскировку из mask.py
            js_mask = Mask.get_js_mask()
            await self.eval_js(js_mask)
            self._masked = True
            logger.info("✅ Браузер готов (маскировка применена)")
            
            return self
        except Exception as e:
            logger.error(f"❌ Ошибка запуска: {e}")
            await self.close()
            raise
    
    def _is_chrome_running(self):
        try:
            requests.get(f"http://localhost:{self.debug_port}/json/version", timeout=2)
            return True
        except:
            return False
    
    def _get_websocket_url(self):
        resp = requests.get(f"http://localhost:{self.debug_port}/json/list", timeout=5)
        pages = resp.json()
        if not pages:
            resp = requests.get(f"http://localhost:{self.debug_port}/json/new")
            return resp.json()["webSocketDebuggerUrl"]
        return pages[0]["webSocketDebuggerUrl"]
    
    async def send(self, method, params=None):
        if params is None:
            params = {}
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method, "params": params}
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            response = await self.ws.recv()
            data = json.loads(response)
            if "id" in data and data["id"] == msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP Error: {data['error']}")
                if "result" in data:
                    return data["result"]
                return data
    
    async def eval_js(self, js_code):
        """Выполнить JavaScript на странице"""
        result = await self.send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True
        })
        return result
    
    async def set_viewport(self, width=1280, height=720):
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
        result = await self.send("Page.navigate", {"url": url})
        for _ in range(30):
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=1)
                data = json.loads(response)
                if data.get("method") == "Page.loadEventFired":
                    break
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(1)
        return result
    
    async def screenshot(self):
        result = await self.send("Page.captureScreenshot")
        if "data" in result:
            return result["data"]
        raise RuntimeError(f"data не найдена: {result}")
    
    async def human_click(self, selector):
        """Человеческий клик через mask.py"""
        js = Mask.get_human_click_js(selector)
        return await self.eval_js(js)
    
    async def human_type(self, selector, text):
        """Человеческий ввод через mask.py"""
        js = Mask.get_human_type_js(selector, text)
        return await self.eval_js(js)
    
    async def human_scroll(self, distance):
        """Человеческий скролл через mask.py"""
        js = Mask.get_human_scroll_js(distance)
        return await self.eval_js(js)
    
    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.process:
            self.process.terminate()
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, *args):
        await self.close()