import asyncio
import json
import logging
import requests
import websockets
from subprocess import Popen, PIPE, TimeoutExpired
import os

from mask import Mask
from cookies import X_COOKIES

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
        self._keepalive_task = None
        self._is_closing = False
    
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
        try:
            if not self._is_chrome_running():
                args = Mask.get_launch_args(self.chrome_path, self.debug_port)
                logger.info("🚀 Запуск Chrome с маскировкой...")
                self.process = Popen(args, stdout=PIPE, stderr=PIPE)
                await asyncio.sleep(3)
                if self.process.poll() is not None:
                    raise RuntimeError("Chrome не запустился")
            
            self.ws_url = self._get_websocket_url()
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=15,
                ping_timeout=30,
                close_timeout=10,
                max_size=10 * 1024 * 1024,
                max_queue=64
            )
            
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            await self.set_viewport(self.viewport_width, self.viewport_height)
            
            await self.set_cookies(X_COOKIES)
            
            js_mask = Mask.get_js_mask()
            await self.eval_js(js_mask)
            self._masked = True
            
            self._start_keepalive()
            
            logger.info("✅ Браузер готов (маскировка + куки + keepalive, max_size=10MB)")
            
            return self
        except Exception as e:
            logger.error(f"❌ Ошибка запуска: {e}")
            await self.close()
            raise
    
    def _start_keepalive(self):
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            logger.info("🔁 Keepalive задача запущена")
    
    async def _keepalive_loop(self):
        try:
            while not self._is_closing and self.ws is not None:
                await asyncio.sleep(20)
                
                if self.ws is None:
                    continue
                
                try:
                    # Просто отправляем ping, если ошибка — переподключаемся
                    await self.send("Runtime.evaluate", {
                        "expression": "1+1",
                        "returnByValue": True
                    })
                    logger.debug("💓 Keepalive ping отправлен")
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("⚠️ WebSocket закрыт, переподключение...")
                    await self._reconnect()
                except Exception as e:
                    logger.warning(f"⚠️ Keepalive ping failed: {e}")
                    await self._reconnect()
                    
        except asyncio.CancelledError:
            logger.info("⏹️ Keepalive задача остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка в keepalive: {e}")
    
    async def _reconnect(self):
        logger.info("🔄 Переподключение к CDP...")
        try:
            if self.ws:
                await self.ws.close()
            self.ws_url = self._get_websocket_url()
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=15,
                ping_timeout=30,
                close_timeout=10,
                max_size=10 * 1024 * 1024,
                max_queue=64
            )
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            await self.set_viewport(self.viewport_width, self.viewport_height)
            logger.info("✅ Переподключение успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка переподключения: {e}")
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
    
    async def set_cookies(self, cookies_list):
        if not cookies_list:
            return
        await self.send("Network.setCookies", {
            "cookies": cookies_list
        })
        logger.info(f"🍪 Установлено {len(cookies_list)} кук")
    
    async def send(self, method, params=None):
        if params is None:
            params = {}
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method, "params": params}
        
        try:
            await self.ws.send(json.dumps(msg))
            
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=60)
                data = json.loads(response)
                if "id" in data and data["id"] == msg_id:
                    if "error" in data:
                        raise RuntimeError(f"CDP Error: {data['error']}")
                    if "result" in data:
                        return data["result"]
                    return data
        except asyncio.TimeoutError:
            logger.error("⏱️ Таймаут ожидания ответа от CDP")
            raise RuntimeError("CDP timeout")
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"🔌 WebSocket закрыт: {e}")
            if not self._is_closing:
                await self._reconnect()
            raise
        except websockets.exceptions.MessageTooLarge as e:
            logger.error(f"📦 Сообщение слишком большое: {e}")
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=15,
                ping_timeout=30,
                close_timeout=10,
                max_size=20 * 1024 * 1024,
                max_queue=128
            )
            raise
    
    async def eval_js(self, js_code):
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
        js = Mask.get_human_click_js(selector)
        return await self.eval_js(js)
    
    async def human_type(self, selector, text):
        js = Mask.get_human_type_js(selector, text)
        return await self.eval_js(js)
    
    async def human_scroll(self, distance):
        js = Mask.get_human_scroll_js(distance)
        return await self.eval_js(js)
    
    async def close(self):
        self._is_closing = True
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                if self.process.poll() is None:
                    self.process.kill()
            except:
                pass
        logger.info("🛑 Браузер закрыт")
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, *args):
        await self.close()