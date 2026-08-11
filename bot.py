# bot.py - Правильное подключение
import os
import sys
import asyncio
import logging

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, capture_screenshot,
    click_at_xy, wait_for_element, close_tab, js
)
from browser_harness.admin import ensure_daemon

# Импортируем маскировку
from bsw import StealthBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HarnessBot:
    def __init__(self):
        self.browser = None
        self.page = None
        self.is_ready = False
    
    async def start(self):
        """Запуск браузера через bsw + подключение Harness"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        
        # 1. Запускаем браузер через bsw
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # 2. Получаем CDP URL
        cdp_url = self.browser["cdp_url"]
        logger.info(f"🔗 CDP URL: {cdp_url}")
        
        # 3. Устанавливаем переменную для Harness
        os.environ["BU_CDP_URL"] = f"http://localhost:9222"
        # или для WebSocket:
        # os.environ["BU_CDP_WS"] = cdp_url
        
        await asyncio.sleep(1)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 4. Запускаем Harness
        self.daemon = ensure_daemon()
        logger.info("✅ Browser Harness подключен")
        
        # 5. Создаем вкладку
        self.page = await new_tab()
        self.is_ready = True
        
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def go_to(self, url: str):
        await goto_url(self.page, url)
        await wait_for_load(self.page)
    
    async def get_text(self, selector: str) -> str:
        result = await js(self.page, f"""
            document.querySelector('{selector}')?.textContent || ''
        """)
        return result.get('result', {}).get('value', '')
    
    async def click(self, selector: str):
        await wait_for_element(self.page, selector)
        await click_at_xy(self.page, selector)
    
    async def screenshot(self) -> bytes:
        return await capture_screenshot(self.page)
    
    async def close(self):
        if self.page:
            try:
                await close_tab(self.page)
            except:
                pass
        if self.browser:
            await StealthBrowser.close(self.browser)
        self.is_ready = False


async def main():
    bot = HarnessBot()
    
    try:
        await bot.start()
        
        # Работа
        await bot.go_to("https://example.com")
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # Скриншот
        img = await bot.screenshot()
        with open("screenshot.png", "wb") as f:
            f.write(img)
        logger.info("📸 Скриншот сохранен")
        
        # Бесконечное ожидание
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())