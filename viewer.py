import base64
import os
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PageViewer:
    """
    Окно просмотра страницы — показывает скриншот в реальном времени.
    """
    
    def __init__(self, browser, eval):
        self.browser = browser
        self.eval = eval
        self.is_active = True
        self.current_screenshot = None
        self.last_update = None
        self.chat_id = None
        self.message_id = None
        self._updating = False
        logger.info("🖥️ Окно просмотра создано")
    
    async def capture(self) -> Dict[str, Any]:
        """Сделать скриншот текущей страницы (без сохранения)"""
        try:
            screenshot_base64 = await self.browser.screenshot()
            self.current_screenshot = screenshot_base64
            self.last_update = datetime.now()
            
            return {
                "success": True,
                "screenshot": screenshot_base64,
                "timestamp": self.last_update.isoformat(),
                "url": await self.eval.get_url(),
                "title": await self.eval.get_title()
            }
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота окна: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_view(self) -> Dict[str, Any]:
        """Получить текущий вид"""
        if not self.current_screenshot:
            return await self.capture()
        
        return {
            "success": True,
            "screenshot": self.current_screenshot,
            "timestamp": self.last_update.isoformat() if self.last_update else None
        }
    
    async def update(self) -> Dict[str, Any]:
        """Обновить скриншот"""
        if self._updating:
            logger.info("⏳ Окно уже обновляется, пропускаем")
            return {"success": False, "error": "already_updating"}
        
        self._updating = True
        try:
            logger.info("🔄 Обновление окна просмотра")
            return await self.capture()
        finally:
            self._updating = False