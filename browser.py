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
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()
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
        await self.page.goto(url)
    
    async def click(self, selector):
        """Клик по селектору"""
        await self.page.click(selector)
    
    async def fill(self, selector, text):
        """Ввод текста"""
        await self.page.fill(selector, text)