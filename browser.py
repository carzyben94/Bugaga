# browser.py - с указанием пути к Chrome
import asyncio
import subprocess
import time
from typing import Optional, Dict, Any, List
from cdp_use.client import CDPClient
from cdp_use.cdp.runtime.commands import Evaluate
import logging

logger = logging.getLogger(__name__)

class BrowserManager:
    """Управление Chrome через CDP"""
    
    def __init__(self, ws_url: str = "ws://localhost:9222", chrome_path: str = "/usr/bin/google-chrome"):
        """
        Args:
            ws_url: WebSocket URL для подключения к Chrome
            chrome_path: путь к исполняемому файлу Chrome
        """
        self.ws_url = ws_url
        self.chrome_path = chrome_path
        self.client: Optional[CDPClient] = None
        self.current_session = None
        self.target_id: Optional[str] = None
        self._console_logs: List[str] = []
        self.chrome_process = None
        
    async def launch_chrome(self, headless: bool = True, port: int = 9222):
        """Запустить Chrome с открытым портом для отладки"""
        try:
            cmd = [
                self.chrome_path,
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check"
            ]
            
            if headless:
                cmd.append("--headless")
            
            # Запускаем Chrome
            self.chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Ждём пока Chrome запустится
            time.sleep(2)
            
            self.ws_url = f"ws://localhost:{port}/devtools/browser/..."
            logger.info(f"✅ Chrome запущен на порту {port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            return False
    
    async def close_chrome(self):
        """Закрыть Chrome"""
        try:
            if self.chrome_process:
                self.chrome_process.terminate()
                self.chrome_process = None
                logger.info("✅ Chrome закрыт")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия Chrome: {e}")
            return False
    
    async def connect(self):
        """Подключение к Chrome"""
        try:
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
            self.current_session = await self.client.attach_target(target_id)
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
            result = await self.current_session.send.Runtime.evaluate(
                Evaluate(
                    expression="document.documentElement.outerHTML",
                    returnByValue=True
                )
            )
            return result["result"]["value"]
        except Exception as e:
            logger.error(f"❌ Ошибка получения HTML: {e}")
            return None
    
    async def get_title(self) -> Optional[str]:
        """Получить заголовок страницы"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Runtime.evaluate(
                Evaluate(
                    expression="document.title",
                    returnByValue=True
                )
            )
            return result["result"]["value"]
        except Exception as e:
            logger.error(f"❌ Ошибка получения заголовка: {e}")
            return None
    
    async def execute_js(self, script: str) -> Optional[Any]:
        """Выполнить JavaScript на странице"""
        try:
            if not self.current_session:
                raise Exception("Нет активной сессии")
            result = await self.current_session.send.Runtime.evaluate(
                Evaluate(
                    expression=script,
                    returnByValue=True
                )
            )
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


# Функция для быстрого использования
async def quick_browser_action(ws_url: str, action: str, **kwargs):
    """Быстрое выполнение одного действия"""
    browser = BrowserManager(ws_url)
    
    try:
        await browser.connect()
        
        target_id = await browser.create_tab()
        if not target_id:
            raise Exception("Не удалось создать вкладку")
        
        await browser.attach_to_tab(target_id)
        
        if action == "get_html":
            if "url" in kwargs:
                await browser.navigate(kwargs["url"])
            return await browser.get_html()
        
        elif action == "get_title":
            if "url" in kwargs:
                await browser.navigate(kwargs["url"])
            return await browser.get_title()
        
        elif action == "screenshot":
            if "url" in kwargs:
                await browser.navigate(kwargs["url"])
            return await browser.screenshot()
        
        elif action == "execute_js":
            if "url" in kwargs:
                await browser.navigate(kwargs["url"])
            return await browser.execute_js(kwargs["script"])
        
        elif action == "navigate":
            return await browser.navigate(kwargs["url"])
        
        else:
            raise ValueError(f"Неизвестное действие: {action}")
    
    finally:
        if browser.target_id:
            await browser.close_tab(browser.target_id)
        await browser.disconnect()


if __name__ == "__main__":
    # Тест
    async def test():
        browser = BrowserManager(chrome_path="/usr/bin/google-chrome")
        await browser.launch_chrome(headless=True)
        await browser.connect()
        
        target_id = await browser.create_tab()
        await browser.attach_to_tab(target_id)
        await browser.navigate("https://example.com")
        
        title = await browser.get_title()
        print(f"Заголовок: {title}")
        
        await browser.close_tab(target_id)
        await browser.disconnect()
        await browser.close_chrome()
    
    asyncio.run(test())