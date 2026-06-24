from cloakbrowser import launch_async

class CloakBrowserManager:
    def __init__(self):
        self.browser = None
        self.page = None

    async def start(self, proxy=None):
        """Запуск браузера через launch_async"""
        self.browser = await launch_async(
            headless=True,
            proxy=proxy,
            humanize=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.page = await self.browser.new_page()
        return self.page

    async def get_page_content(self, url):
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until='networkidle')
        return await self.page.content()

    async def screenshot(self, url):
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until='networkidle')
        return await self.page.screenshot(full_page=True)

    async def get_cookies(self, url=None):
        if not self.page:
            await self.start()
        if url:
            await self.page.goto(url, wait_until='networkidle')
        return await self.page.context.cookies()

    async def set_cookies(self, cookies_list):
        if not self.page:
            await self.start()
        await self.page.context.add_cookies(cookies_list)

    async def close(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None