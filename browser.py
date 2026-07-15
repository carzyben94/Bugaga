# browser.py - исправленная версия с правильным получением WS URL
import asyncio
import logging
import subprocess
import time
import os
import shutil
import json
import requests
from typing import Optional, Dict, Any, List
from cdp_use.client import CDPClient

logger = logging.getLogger(__name__)

class BrowserManager:
    """Управление Chrome через CDP с автоматическим запуском"""
    
    def __init__(self, chrome_path: str = "/usr/bin/google-chrome", port: int = 9222):
        self.chrome_path = chrome_path
        self.port = port
        self.ws_url: Optional[str] = None
        self.client: Optional[CDPClient] = None
        self.current_session = None
        self.target_id: Optional[str] = None
        self._console_logs: List[str] = []
        self.chrome_process = None
        self._is_own_chrome = False
    
    def _find_chrome(self) -> Optional[str]:
        """Найти Chrome в системе"""
        paths = [
            self.chrome_path,
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome-stable",
            "/opt/google/chrome/chrome",
        ]
        
        for path in paths:
            if os.path.exists(path) or shutil.which(path):
                logger.info(f"✅ Найден Chrome: {path}")
                return path
        
        return None
    
    def _get_websocket_url(self) -> Optional[str]:
        """Получить WebSocket URL из Chrome"""
        try:
            # Получаем список доступных страниц
            response = requests.get(f"http://localhost:{self.port}/json")
            if response.status_code == 200:
                pages = response.json()
                
                # Ищем первую страницу с WebSocket URL
                for page in pages:
                    if "webSocketDebuggerUrl" in page:
                        ws_url = page["webSocketDebuggerUrl"]
                        logger.info(f"✅ Найден WebSocket URL: {ws_url}")
                        return ws_url
                
                # Если страниц нет, создаём новую
                response = requests.get(f"http://localhost:{self.port}/json/new")
                if response.status_code == 200:
                    page = response.json()
                    if "webSocketDebuggerUrl" in page:
                        ws_url = page["webSocketDebuggerUrl"]
                        logger.info(f"✅ Создана новая страница: {ws_url}")
                        return ws_url
            else:
                # Пробуем альтернативный путь
                response = requests.get(f"http://localhost:{self.port}/json/version")
                if response.status_code == 200:
                    data = response.json()
                    if "webSocketDebuggerUrl" in data:
                        ws_url = data["webSocketDebuggerUrl"]
                        logger.info(f"✅ Найден WebSocket URL: {ws_url}")
                        return ws_url
            
            logger.error("❌ Не удалось получить WebSocket URL")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения WebSocket URL: {e}")
            return None
    
    async def _launch_chrome(self, headless: bool = True) -> bool:
        """Запустить Chrome"""
        try:
            chrome_path = self._find_chrome()
            if not chrome_path:
                logger.error("❌ Chrome не найден в системе")
                return False
            
            # Проверяем, не запущен ли уже Chrome
            if await self._is_chrome_running():
                logger.info(f"✅ Chrome уже запущен на порту {self.port}")
                return True
            
            logger.info(f"🚀 Запускаю Chrome: {chrome_path}")
            
            cmd = [
                chrome_path,
                f"--remote-debugging-port={self.port}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-sandbox",
            ]
            
            if headless:
                cmd.append("--headless")
                cmd.append("--window-size=1920,1080")
            
            self.chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            self._is_own_chrome = True
            
            # Ждём запуска
            for i in range(10):
                time.sleep(1)
                if await self._is_chrome_running():
                    # Получаем WebSocket URL
                    self.ws_url = self._get_websocket_url()
                    if self.ws_url:
                        logger.info(f"✅ Chrome готов на порту {self.port}")
                        return True
                logger.debug(f"Ожидание запуска Chrome... {i+1}/10")
            
            logger.error("❌ Chrome не запустился за 10 секунд")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            return False
    
    async def _is_chrome_running(self) -> bool:
        """Проверить, запущен ли Chrome на порту"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', self.port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    async def _close_chrome(self):
        """Закрыть Chrome (если сами запускали)"""
        try:
            if self._is_own_chrome and self.chrome_process:
                logger.info("🛑 Закрываю Chrome...")
                self.chrome_process.terminate()
                
                for _ in range(5):
                    if self.chrome_process.poll() is not None:
                        break
                    time.sleep(1)
                
                if self.chrome_process.poll() is None:
                    self.chrome_process.kill()
                
                self.chrome_process = None
                self._is_own_chrome = False
                logger.info("✅ Chrome закрыт")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия Chrome: {e}")
            return False
    
    async def connect(self, headless: bool = True):
        """Подключение к Chrome (автоматически запускает если нужно)"""
        try:
            # Запускаем Chrome если не запущен
            if not await self._launch_chrome(headless):
                return False
            
            # Подключаемся
            self.client = CDPClient(self.ws_url)
            await self.client.__aenter__()
            logger.info("✅ Подключен к Chrome")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def disconnect(self):
        """Отключение от Chrome"""
        try:
            if self.client:
                await self.client.__aexit__(None, None, None)
                self.client = None
                self.current_session = None
                self.target_id = None
                logger.info("✅ Отключен от Chrome")
            
            if self._is_own_chrome:
                await self._close_chrome()
                
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отключения: {e}")
            return False
    
    async def create_tab(self, url: str = "about:blank") -> Optional[str]:
        """Создать новую вкладку"""
        try:
            # Сначала получаем список вкладок
            targets = await self.client.send.Target.getTargets()
            
            # Создаём новую
            result = await self.client.send.Target.createTarget({"url": url})
            target_id = result["targetId"]
            logger.info(f"✅ Создана вкладка: {target_id}")
            return target_id
        except Exception as e:
            logger.error(f"❌ Ошибка создания вкладки: {e}")
            return None
    
    async def attach_to_tab(self, target_id: str):
        """Подключиться к вкладке"""
        try:
            self.target_id = target_id
            self.current_session = await self.client.attach_target(target_id)
            logger.info(f"✅ Подключен к вкладке: {target_id}")
            return self.current_session
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к вкладке: {e}")
            return None
    
    async def close_tab(self, target_id: str) -> bool:
        """Закрыть вкладку"""
        try:
            await self.client.send.Target.closeTarget({"targetId": target_id})
            logger.info(f"✅ Закрыта вкладка: {target_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия вкладки: {e}")
            return False
    
    async def navigate(self, url: str) -> bool:
        """Перейти по URL"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            await self.current_session.send.Page.navigate({"url": url})
            logger.info(f"✅ Навигация на: {url}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка навигации: {e}")
            return False
    
    async def get_title(self) -> Optional[str]:
        """Получить заголовок страницы"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Runtime.evaluate({
                "expression": "document.title",
                "returnByValue": True
            })
            return result["result"]["value"]
        except Exception as e:
            logger.error(f"❌ Ошибка получения заголовка: {e}")
            return None
    
    async def screenshot(self, format: str = "png") -> Optional[str]:
        """Сделать скриншот страницы"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Page.captureScreenshot({
                "format": format
            })
            return result["data"]
        except Exception as e:
            logger.error(f"❌ Ошибка создания скриншота: {e}")
            return None


if __name__ == "__main__":
    async def test():
        browser = BrowserManager()
        
        await browser.connect(headless=True)
        
        target_id = await browser.create_tab()
        await browser.attach_to_tab(target_id)
        await browser.navigate("https://example.com")
        
        title = await browser.get_title()
        print(f"Заголовок: {title}")
        
        await browser.close_tab(target_id)
        await browser.disconnect()
    
    asyncio.run(test())