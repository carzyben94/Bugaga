import asyncio
import json
import logging
import requests
import websockets
from subprocess import Popen, PIPE, TimeoutExpired
import os

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
    
    def _find_chrome(self):
        """Найти Chrome в системе"""
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome-stable",
        ]
        
        for path in paths:
            if os.path.exists(path):
                logger.info(f"✅ Chrome найден: {path}")
                return path
        
        logger.error("❌ Chrome не найден в системе!")
        return "/usr/bin/google-chrome"
    
    async def start(self):
        """Запуск Chrome с открытым CDP"""
        try:
            logger.info("🚀 Запуск Chrome...")
            
            if not self._is_chrome_running():
                self.process = Popen([
                    self.chrome_path,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--use-gl=angle",
                    "--disable-dev-shm-usage",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-setuid-sandbox",
                    "--hide-scrollbars",
                    "--mute-audio",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-client-side-phishing-detection",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-default-apps",
                    "--disable-features=TranslateUI",
                    "--disable-hang-monitor",
                    "--disable-ipc-flooding-protection",
                    "--disable-popup-blocking",
                    "--disable-prompt-on-repost",
                    "--disable-renderer-backgrounding",
                    "--disable-sync",
                    "--force-color-profile=srgb",
                    "--metrics-recording-only",
                    "--enable-features=NetworkService,NetworkServiceInProcess",
                    "--window-size=1280,720",
                    "--window-position=0,0",
                    "--disable-blink-features=AutomationControlled",
                    f"--remote-debugging-port={self.debug_port}",
                    "about:blank"
                ], stdout=PIPE, stderr=PIPE)
                
                logger.info("⏳ Ожидание запуска Chrome...")
                await asyncio.sleep(3)
                
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate(timeout=2)
                    logger.error(f"Chrome упал при запуске: {stderr.decode()}")
                    raise RuntimeError(f"Chrome не запустился: {stderr.decode()}")
            else:
                logger.info("ℹ️ Chrome уже запущен")
            
            self.ws_url = self._get_websocket_url()
            logger.info(f"🔗 Подключение к CDP: {self.ws_url}")
            
            self.ws = await websockets.connect(self.ws_url)
            
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            
            await self.set_viewport(self.viewport_width, self.viewport_height)
            
            logger.info("✅ Браузер готов к работе!")
            return self
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска браузера: {e}")
            await self.close()
            raise
    
    def _is_chrome_running(self):
        """Проверяет, запущен ли Chrome на порту 9222"""
        try:
            resp = requests.get(f"http://localhost:{self.debug_port}/json/version", timeout=2)
            return resp.status_code == 200
        except:
            return False
    
    def _get_websocket_url(self):
        """Получить WebSocket URL из /json/list"""
        try:
            resp = requests.get(f"http://localhost:{self.debug_port}/json/list", timeout=5)
            resp.raise_for_status()
            pages = resp.json()
            
            if not pages:
                logger.warning("Нет активных страниц, создаю новую...")
                resp = requests.get(f"http://localhost:{self.debug_port}/json/new", timeout=5)
                resp.raise_for_status()
                return resp.json()["webSocketDebuggerUrl"]
            
            return pages[0]["webSocketDebuggerUrl"]
            
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Не удалось подключиться к Chrome на порту {self.debug_port}")
        except Exception as e:
            raise RuntimeError(f"Ошибка получения WebSocket URL: {e}")
    
    async def send(self, method, params=None):
        """Отправить CDP-команду с целочисленным id"""
        if params is None:
            params = {}
        
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "method": method,
            "params": params
        }
        
        try:
            await self.ws.send(json.dumps(msg))
            response = await self.ws.recv()
            data = json.loads(response)
            
            # Логируем полный ответ для диагностики
            logger.info(f"📨 Ответ CDP на {method}: {json.dumps(data)[:500]}")
            
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown CDP error")
                error_code = data["error"].get("code", "N/A")
                logger.error(f"CDP Error ({method}): [{error_code}] {error_msg}")
                raise RuntimeError(f"CDP Error: {error_msg}")
            
            if "result" in data:
                return data["result"]
            return data
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("WebSocket соединение закрыто")
            raise RuntimeError("Соединение с браузером потеряно")
        except Exception as e:
            logger.error(f"Ошибка отправки CDP команды {method}: {e}")
            raise
    
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
        logger.info(f"🖥️ Viewport: {width}x{height}")
    
    async def goto(self, url):
        """Навигация (CDP) с ожиданием полной загрузки"""
        logger.info(f"📍 Переход: {url}")
        
        # Отправляем навигацию
        result = await self.send("Page.navigate", {"url": url})
        
        # Ждём событие загрузки
        logger.info("⏳ Ожидание загрузки страницы...")
        
        # Ждём Page.loadEventFired
        for _ in range(30):  # максимум 30 секунд
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=1)
                data = json.loads(response)
                
                if data.get("method") == "Page.loadEventFired":
                    logger.info("✅ Страница загружена")
                    break
                    
            except asyncio.TimeoutError:
                continue
        else:
            logger.warning("⏱️ Таймаут ожидания загрузки")
        
        # Дополнительная задержка для рендера
        await asyncio.sleep(1)
        
        return result
    
    async def screenshot(self):
        """Скриншот через CDP с диагностикой"""
        logger.info("📸 Делаю скриншот...")
        result = await self.send("Page.captureScreenshot")
        
        # Подробная диагностика
        logger.info(f"🔍 Тип ответа: {type(result)}")
        logger.info(f"🔍 Ключи ответа: {result.keys() if isinstance(result, dict) else 'не словарь'}")
        
        if isinstance(result, dict) and "data" in result:
            logger.info("✅ data найдена в result")
            return result["data"]
        elif isinstance(result, dict) and "result" in result and "data" in result["result"]:
            logger.info("✅ data найдена в result.result")
            return result["result"]["data"]
        else:
            # Если data нет — показываем что пришло
            logger.error(f"❌ Неизвестный формат ответа: {result}")
            raise RuntimeError(f"Поле 'data' не найдено. Получено: {result}")
    
    async def close(self):
        """Закрыть браузер"""
        try:
            if self.ws:
                await self.ws.close()
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except TimeoutExpired:
                    self.process.kill()
            logger.info("🛑 Браузер закрыт")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии браузера: {e}")
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, *args):
        await self.close()