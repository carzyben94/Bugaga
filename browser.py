# browser.py - полная автоматизация с запуском Chrome
import asyncio
import logging
import subprocess
import time
import os
import shutil
from typing import Optional, Dict, Any, List
from cdp_use.client import CDPClient

logger = logging.getLogger(__name__)

class BrowserManager:
    """Управление Chrome через CDP с автоматическим запуском"""
    
    def __init__(self, chrome_path: str = "/usr/bin/google-chrome", port: int = 9222):
        """
        Args:
            chrome_path: путь к Chrome
            port: порт для отладки
        """
        self.chrome_path = chrome_path
        self.port = port
        self.ws_url = f"ws://localhost:{port}/devtools/browser/..."
        self.client: Optional[CDPClient] = None
        self.current_session = None
        self.target_id: Optional[str] = None
        self._console_logs: List[str] = []
        self.chrome_process = None
        self._is_own_chrome = False  # Флаг: мы запустили Chrome или он уже был запущен
    
    def _find_chrome(self) -> Optional[str]:
        """Найти Chrome в системе"""
        # Список возможных путей
        paths = [
            self.chrome_path,
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome-stable",
            "/opt/google/chrome/chrome",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",  # Windows
        ]
        
        for path in paths:
            if os.path.exists(path) or shutil.which(path):
                logger.info(f"✅ Найден Chrome: {path}")
                return path
        
        return None
    
    async def _launch_chrome(self, headless: bool = True) -> bool:
        """Запустить Chrome"""
        try:
            chrome_path = self._find_chrome()
            if not chrome_path:
                logger.error("❌ Chrome не найден в системе")
                return False
            
            # Проверяем, не запущен ли уже Chrome на этом порту
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
                "--no-sandbox",  # Нужно для Docker/Railway
            ]
            
            if headless:
                cmd.append("--headless")
                cmd.append("--window-size=1920,1080")
            
            # Запускаем Chrome
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
                    logger.info(f"✅ Chrome запущен на порту {self.port}")
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
            # Пробуем подключиться к WebSocket
            import websockets
            try:
                async with websockets.connect(self.ws_url, timeout=1):
                    return True
            except:
                pass
            
            # Альтернативная проверка через curl
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
                
                # Ждём завершения
                for _ in range(5):
                    if self.chrome_process.poll() is not None:
                        break
                    time.sleep(1)
                
                # Если не завершился - убиваем
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
            
            # Закрываем Chrome если сами запускали
            if self._is_own_chrome:
                await self._close_chrome()
                
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отключения: {e}")
            return False
    
    async def list_tabs(self) -> List[Dict[str, Any]]:
        """Получить список всех открытых вкладок"""
        try:
            targets = await self.client.send.Target.getTargets()
            tabs = []
            for target in targets.get("targetInfos", []):
                if target.get("type") == "page":
                    tabs.append({
                        "id": target["targetId"],
                        "url": target["url"],
                        "title": target.get("title", ""),
                        "attached": target.get("attached", False)
                    })
            return tabs
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка вкладок: {e}")
            return []
    
    async def create_tab(self, url: str = "about:blank") -> Optional[str]:
        """Создать новую вкладку"""
        try:
            result = await self.client.send.Target.createTarget({"url": url})
            target_id = result["targetId"]
            logger.info(f"✅ Создана вкладка: {target_id}")
            return target_id
        except Exception as e:
            logger.error(f"❌ Ошибка создания вкладки: {e}")
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
    
    async def attach_to_tab(self, target_id: str):
        """Подключиться к вкладке"""
        try:
            self.target_id = target_id
            self.current_session = await self.client.attach_to_target(target_id)
            logger.info(f"✅ Подключен к вкладке: {target_id}")
            return self.current_session
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к вкладке: {e}")
            return None
    
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
    
    async def get_html(self) -> Optional[str]:
        """Получить HTML страницы"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Runtime.evaluate({
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True
            })
            return result["result"]["value"]
        except Exception as e:
            logger.error(f"❌ Ошибка получения HTML: {e}")
            return None
    
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
    
    async def execute_js(self, script: str) -> Optional[Any]:
        """Выполнить JavaScript на странице"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Runtime.evaluate({
                "expression": script,
                "returnByValue": True
            })
            return result["result"]["value"]
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения JS: {e}")
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
        
        # Автоматически запустит Chrome и подключится
        await browser.connect(headless=True)
        
        # Создаём вкладку и работаем
        target_id = await browser.create_tab()
        await browser.attach_to_tab(target_id)
        await browser.navigate("https://example.com")
        
        title = await browser.get_title()
        print(f"Заголовок: {title}")
        
        # Закрываем
        await browser.close_tab(target_id)
        await browser.disconnect()  # Автоматически закроет Chrome
    
    asyncio.run(test())