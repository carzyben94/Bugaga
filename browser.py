import asyncio
from playwright.async_api import async_playwright


class Browser:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
    
    async def start(self):
        """Запуск браузера"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        self.page = await self.browser.new_page(
            viewport={'width': 1920, 'height': 1080}
        )
        
        # Маскировка
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        return self.page
    
    async def close(self):
        """Закрытие браузера"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def screenshot(self, filename="screen.png"):
        """Скриншот"""
        await self.page.screenshot(path=filename, full_page=True)
        return filename
    
    async def goto(self, url):
        """Переход на URL"""
        if not url.startswith('http'):
            url = 'https://' + url
        await self.page.goto(url, timeout=30000)
        await self.page.wait_for_load_state("networkidle")
    
    async def click(self, selector):
        """Клик по селектору"""
        await self.page.click(selector)
    
    async def click_by_text(self, text):
        """Клик по тексту"""
        try:
            await self.page.get_by_text(text).click(timeout=3000)
            return True
        except:
            return False
    
    async def mega_click(self, x=None, y=None, text=None):
        """Мега-клик - пробует все методы"""
        
        # 1. Клик по координатам
        if x is not None and y is not None:
            try:
                await self.page.mouse.click(x, y)
                return True
            except:
                pass
        
        # 2. Клик по тексту
        if text:
            try:
                await self.page.get_by_text(text).click(timeout=2000)
                return True
            except:
                pass
            
            try:
                await self.page.locator(f"button:has-text('{text}')").click(timeout=2000)
                return True
            except:
                pass
            
            try:
                await self.page.locator(f"*:has-text('{text}')").first.click(timeout=2000)
                return True
            except:
                pass
        
        # 3. Клик по центру
        try:
            viewport = self.page.viewport_size
            await self.page.mouse.click(viewport['width'] // 2, viewport['height'] // 2)
            return True
        except:
            pass
        
        # 4. JavaScript клик
        try:
            await self.page.evaluate("""
                document.querySelector('*:contains("Continue")')?.click()
            """)
            return True
        except:
            pass
        
        return False