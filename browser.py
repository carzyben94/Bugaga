import asyncio
import json
import logging
import requests
import websockets
from subprocess import Popen, PIPE
import time

# Настройка логирования для этого модуля
logger = logging.getLogger(__name__)

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
        logger.info("🚀 Запуск Chrome...")
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
        logger.info(f"🔗 Подключение к WebSocket: {ws_url}")
        self.ws = await websockets.connect(ws_url)
        
        # Включаем необходимые домены
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Network.enable")
        
        # Устанавливаем размер окна
        await self.set_viewport(self.viewport_width, self.viewport_height)
        logger.info("✅ Браузер готов")
        return self
    
    def _get_websocket_url(self):
        """Получить WebSocket URL из /json/list"""
        try:
            resp = requests.get(f"http://localhost:{self.debug_port}/json/list")
            resp.raise_for_status()
            pages = resp.json()
            
            if not pages:
                logger.warning("Нет активных страниц, создаю новую...")
                resp = requests.get(f"http://localhost:{self.debug_port}/json/new")
                resp.raise_for_status()
                return resp.json()["webSocketDebuggerUrl"]
            
            return pages[0]["webSocketDebuggerUrl"]
        except Exception as e:
            logger.error(f"Ошибка получения WebSocket URL: {e}")
            raise
    
    async def send(self, method, params=None):
        """
        Отправить CDP-команду и вернуть РАСПАРСЕННЫЙ ответ.
        Всегда возвращает словарь. Если есть поле 'result' - возвращает его,
        иначе возвращает весь ответ.
        """
        if params is None:
            params = {}
        
        msg = {
            "id": int(time.time() * 1000),
            "method": method,
            "params": params
        }
        
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        data = json.loads(response)
        
        # Логируем структуру ответа для отладки
        logger.debug(f"Ответ CDP на {method}: {list(data.keys())}")
        
        # Если в ответе есть поле 'result' - возвращаем его, иначе весь ответ
        if "result" in data:
            return data["result"]
        return data
    
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
        logger.info(f"🖥️ Viewport установлен: {width}x{height}")
    
    async def goto(self, url):
        """Навигация (CDP)"""
        logger.info(f"📍 Переход на {url}")
        result = await self.send("Page.navigate", {"url": url})
        return result
    
    async def screenshot(self):
        """Скриншот через CDP с правильной обработкой ответа"""
        logger.info("📸 Запрос скриншота...")
        response = await self.send("Page.captureScreenshot")
        
        # Диагностика: выводим структуру ответа
        logger.info(f"Структура ответа screenshot: {list(response.keys())}")
        
        # Пытаемся извлечь data отовсюду
        if "data" in response:
            return response["data"]
        elif isinstance(response, dict) and "result" in response and "data" in response["result"]:
            return response["result"]["data"]
        else:
            logger.error(f"Не удалось найти 'data' в ответе: {response}")
            raise KeyError(f"Поле 'data' не найдено в ответе CDP. Получено: {list(response.keys())}")
    
    async def close(self):
        """Закрыть браузер"""
        if self.ws:
            await self.ws.close()
        if self.process:
            self.process.terminate()
        logger.info("🛑 Браузер закрыт")
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, *args):
        await self.close()