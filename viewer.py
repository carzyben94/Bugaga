import base64
import os
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PageViewer:
    """
    Окно просмотра страницы — показывает скриншот в реальном времени.
    """
    
    def __init__(self, browser, eval):
        self.browser = browser
        self.eval = eval
        self.is_active = False
        self.current_screenshot = None
        self.last_update = None
    
    async def capture(self) -> Dict[str, Any]:
        """Сделать скриншот текущей страницы"""
        try:
            screenshot_base64 = await self.browser.screenshot()
            self.current_screenshot = screenshot_base64
            self.last_update = datetime.now()
            
            # Сохраняем
            screenshots_dir = "screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            filename = f"{screenshots_dir}/viewer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(screenshot_base64))
            
            return {
                "success": True,
                "screenshot": screenshot_base64,
                "filename": filename,
                "timestamp": self.last_update.isoformat(),
                "url": await self.eval.get_url(),
                "title": await self.eval.get_title()
            }
        except Exception as e:
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
        return await self.capture()