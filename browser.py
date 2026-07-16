import os
import asyncio
import logging
import subprocess
import json
import requests
import random
import base64
from typing import Optional, Dict, Any
import websockets
from mask import Mask, UserAgentParser
from cookies import X_COOKIES, get_cookies_for_domain, format_cookies_for_cdp

logger = logging.getLogger(__name__)

class CDPClient:
    def __init__(self):
        self.chrome_path = "/usr/bin/google-chrome"
        self.chrome_process = None
        self.debug_port = 9222
        self.ws_url = None
        self.ws = None
        self.msg_id = 0
        self.mask = Mask()
        self._reconnect_attempts = 3
        
    async def start_chrome(self):
        """Запуск Chrome с маскировкой из Mask"""
        try:
            launch_args = self.mask.get_launch_args(
                chrome_path=self.chrome_path,
                debug_port=self.debug_port
            )
            
            logger.info(f"🚀 Запуск Chrome с маскировкой...")
            
            for i, arg in enumerate(launch_args):
                if arg == '--user-agent' and i + 1 < len(launch_args):
                    logger.info(f"📋 User-Agent: {launch_args[i + 1]}")
                    break
            
            self.chrome_process = subprocess.Popen(
                launch_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Ждем запуска Chrome
            await asyncio.sleep(3)
            
            # Получаем WebSocket URL через /json/list
            response = requests.get(f"http://localhost:{self.debug_port}/json/list")
            if response.status_code == 200:
                pages = response.json()
                if pages and len(pages) > 0:
                    self.ws_url = pages[0].get("webSocketDebuggerUrl")
                    logger.info(f"✅ Chrome запущен. CDP: {self.ws_url}")
                    return self.ws_url
                else:
                    raise Exception("Нет активных страниц в Chrome")
            else:
                raise Exception(f"Не удалось получить список страниц: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            raise
    
    async def connect_cdp(self, navigate_to_x: bool = False):
        """Подключение к CDP с полной настройкой"""
        if not self.ws_url:
            await self.start_chrome()
        
        try:
            # Закрываем старый сокет если есть
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None
            
            # Подключаемся с настройками для долгого соединения
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,           # Пинг каждые 30 секунд
                ping_timeout=60,            # Таймаут пинга 60 секунд
                close_timeout=10,           # Таймаут закрытия
                max_size=10 * 1024 * 1024   # 10 MB максимальный размер сообщения
            )
            logger.info("✅ Подключен к CDP")
            
            # 1. Применяем JS маскировку
            await self.apply_js_mask()
            
            # 2. Устанавливаем куки X.com сразу
            await self.set_x_cookies()
            logger.info("🍪 Куки X.com установлены в браузер")
            
            # 3. Если нужно сразу перейти на X.com
            if navigate_to_x:
                await self.navigate_to("https://x.com")
            
            return self.ws
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к CDP: {e}")
            raise
    
    async def apply_js_mask(self):
        """Применяет JS маскировку из mask.py"""
        try:
            js_code = self.mask.get_js_mask()
            
            result = await self.send_command(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": js_code}
            )
            
            logger.info("✅ JS маскировка применена")
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка применения JS маскировки: {e}")
            raise
    
    async def send_command(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Отправка CDP команды с автоматическим переподключением"""
        for attempt in range(self._reconnect_attempts):
            try:
                if not self.ws:
                    await self.connect_cdp()
                
                if not self.ws:
                    raise Exception("Нет соединения с CDP")
                
                self.msg_id += 1
                message = {
                    "id": self.msg_id,
                    "method": method,
                    "params": params or {}
                }
                
                await self.ws.send(json.dumps(message))
                response = await asyncio.wait_for(self.ws.recv(), timeout=60)
                response_data = json.loads(response)
                
                if "error" in response_data:
                    logger.error(f"CDP ошибка: {response_data['error']}")
                    return {"error": response_data["error"]}
                
                return response_data.get("result", {})
                
            except (websockets.ConnectionClosedOK,
                    websockets.ConnectionClosedError,
                    asyncio.TimeoutError,
                    websockets.WebSocketException) as e:
                
                logger.warning(f"⚠️ Ошибка соединения (попытка {attempt + 1}): {e}")
                self.ws = None
                
                if attempt < self._reconnect_attempts - 1:
                    await asyncio.sleep(2)
                    await self.reconnect()
                else:
                    raise Exception(f"Не удалось выполнить команду после {self._reconnect_attempts} попыток: {e}")
            
            except Exception as e:
                logger.error(f"❌ Ошибка отправки CDP команды: {e}")
                raise
        
        raise Exception("Не удалось выполнить команду")
    
    async def reconnect(self):
        """Переподключение к CDP"""
        try:
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None
            
            if self.chrome_process:
                try:
                    self.chrome_process.terminate()
                    self.chrome_process.wait(timeout=3)
                except:
                    pass
                self.chrome_process = None
            
            await self.start_chrome()
            await self.connect_cdp()
            logger.info("✅ Переподключение успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка переподключения: {e}")
            return False
    
    async def ensure_connection(self):
        """Проверяет и восстанавливает соединение если нужно"""
        try:
            if self.ws:
                await self.send_command("Runtime.evaluate", {"expression": "1"})
                return True
        except:
            logger.warning("⚠️ Соединение потеряно, переподключаемся...")
            await self.reconnect()
            return True
        
        if not self.ws:
            await self.connect_cdp()
        
        return True
    
    async def navigate_to(self, url: str):
        """Переход по URL с человеческой задержкой"""
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        result = await self.send_command("Page.navigate", {"url": url})
        
        # Ждем загрузки страницы
        await self.send_command("Page.loadEventFired", {})
        
        logger.info(f"📄 Переход на {url}")
        return result
    
    async def set_x_cookies(self):
        """Устанавливает все куки для X.com одной командой"""
        formatted_cookies = format_cookies_for_cdp(X_COOKIES)
        
        result = await self.send_command("Network.setCookies", {
            "cookies": formatted_cookies
        })
        
        logger.info(f"🍪 Установлено {len(formatted_cookies)} кук для X.com")
        return result
    
    async def set_cookies_for_domain(self, domain: str):
        """Устанавливает куки для любого домена"""
        cookies = get_cookies_for_domain(domain)
        if not cookies:
            logger.warning(f"⚠️ Нет кук для домена: {domain}")
            return
        
        formatted_cookies = format_cookies_for_cdp(cookies)
        
        result = await self.send_command("Network.setCookies", {
            "cookies": formatted_cookies
        })
        
        logger.info(f"🍪 Установлено {len(formatted_cookies)} кук для {domain}")
        return result
    
    async def set_viewport(self, width: int = 1280, height: int = 720):
        """Устанавливает размер вьюпорта для скриншотов"""
        await self.ensure_connection()
        
        result = await self.send_command("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
            "fitWindow": False
        })
        
        logger.info(f"📐 Вьюпорт установлен: {width}x{height}")
        return result

    async def take_screenshot(
        self, 
        width: int = 1280, 
        height: int = 720,
        format: str = "png",
        quality: Optional[int] = None,
        full_page: bool = False
    ) -> str:
        """Делает скриншот с повторными попытками"""
        try:
            await self.ensure_connection()
            
            # Проверяем, что страница загружена
            try:
                ready_state = await self.send_command("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                if ready_state.get("result", {}).get("value") != "complete":
                    await asyncio.sleep(2)
            except:
                pass
            
            # Устанавливаем вьюпорт
            await self.set_viewport(width, height)
            
            await asyncio.sleep(0.5)
            
            # Параметры скриншота
            params = {
                "format": format,
                "captureBeyondViewport": full_page
            }
            
            if format == "jpeg" and quality:
                params["quality"] = quality
            
            # Делаем скриншот с повторной попыткой
            result = None
            for attempt in range(3):
                try:
                    result = await self.send_command("Page.captureScreenshot", params)
                    if result and result.get("data"):
                        break
                except Exception as e:
                    logger.warning(f"⚠️ Попытка {attempt + 1} скриншота: {e}")
                    await asyncio.sleep(0.5)
                    if attempt < 2:
                        await self.ensure_connection()
            
            if not result or not result.get("data"):
                raise Exception("Не удалось получить скриншот (пустые данные)")
            
            logger.info(f"📸 Скриншот сделан: {width}x{height}, {format}")
            return result.get("data", "")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания скриншота: {e}")
            raise
    
    async def get_page_content(self) -> str:
        """Получение HTML страницы"""
        await self.ensure_connection()
        
        result = await self.send_command("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML"
        })
        return result.get("result", {}).get("value", "")
    
    async def execute_script(self, script: str) -> Any:
        """Выполнение JavaScript"""
        await self.ensure_connection()
        
        result = await self.send_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
        return result.get("result", {}).get("value")
    
    async def human_click(self, selector: str) -> bool:
        """Человеческий клик (из mask.py)"""
        await self.ensure_connection()
        
        js_code = self.mask.get_human_click_js(selector)
        result = await self.execute_script(js_code)
        return result
    
    async def human_type(self, selector: str, text: str) -> bool:
        """Человеческий ввод (из mask.py)"""
        await self.ensure_connection()
        
        js_code = self.mask.get_human_type_js(selector, text)
        result = await self.execute_script(js_code)
        return result
    
    async def human_scroll(self, distance: int) -> bool:
        """Человеческий скролл (из mask.py)"""
        await self.ensure_connection()
        
        js_code = self.mask.get_human_scroll_js(distance)
        result = await self.execute_script(js_code)
        return result
    
    async def close(self):
        """Закрытие Chrome"""
        try:
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None
                
            if self.chrome_process:
                self.chrome_process.terminate()
                self.chrome_process.wait(timeout=5)
                self.chrome_process = None
                
            logger.info("✅ Chrome закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия Chrome: {e}")

# Глобальный экземпляр
cdp_client = CDPClient()