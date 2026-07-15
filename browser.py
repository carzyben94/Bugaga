# browser.py - исправленная версия
import asyncio
import logging
from typing import Optional, Dict, Any, List
from cdp_use.client import CDPClient

logger = logging.getLogger(__name__)

class BrowserManager:
    """Управление Chrome через CDP"""
    
    def __init__(self, ws_url: str = "ws://localhost:9222"):
        self.ws_url = ws_url
        self.client: Optional[CDPClient] = None
        self.current_session = None
        self.target_id: Optional[str] = None
        self._console_logs: List[str] = []
    
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
    async def test():
        browser = BrowserManager("ws://localhost:9222/devtools/browser/...")
        await browser.connect()
        
        target_id = await browser.create_tab()
        await browser.attach_to_tab(target_id)
        await browser.navigate("https://example.com")
        
        title = await browser.get_title()
        print(f"Заголовок: {title}")
        
        await browser.close_tab(target_id)
        await browser.disconnect()
    
    asyncio.run(test())