import asyncio
from cloakbrowser import AsyncCloakBrowser

class CloakBrowserManager:
    def __init__(self):
        self.browser = None
        self.page = None
    
    async def start(self, proxy=None):
        """Запуск браузера"""
        self.browser = await AsyncCloakBrowser.launch(
            headless=True,
            proxy=proxy,
            humanize=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.page = await self.browser.new_page()
        return self.page
    
    async def get_page_content(self, url):
        """Получить HTML страницы"""
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until='networkidle')
        return await self.page.content()
    
    async def screenshot(self, url):
        """Сделать скриншот"""
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until='networkidle')
        return await self.page.screenshot(full_page=True)
    
    async def get_cookies(self, url=None):
        """Получить куки"""
        if not self.page:
            await self.start()
        if url:
            await self.page.goto(url, wait_until='networkidle')
        return await self.page.context.cookies()
    
    async def set_cookies(self, cookies_list):
        """Установить куки"""
        if not self.page:
            await self.start()
        await self.page.context.add_cookies(cookies_list)
    
    async def close(self):
        """Закрыть браузер"""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None