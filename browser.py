from cloakbrowser import launch_async

class CloakBrowserManager:
    def __init__(self):
        self.browser = None
        self.page = None

    async def start(self, proxy=None):
        """Запуск браузера с улучшенной эмуляцией"""
        self.browser = await launch_async(
            headless=True,
            proxy=proxy,
            humanize=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-web-security',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--disable-features=OutOfBlinkCors',
                '--disable-gpu',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-features=TranslateUI',
                '--disable-ipc-flooding-protection',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows',
                '--disable-background-timer-throttling',
                '--disable-client-side-phishing-detection',
                '--disable-crash-reporter',
                '--disable-hang-monitor',
                '--disable-prompt-on-repost',
                '--disable-sync',
                '--no-first-run'
            ]
        )
        
        self.page = await self.browser.new_page(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Скрываем следы автоматизации
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ru-RU', 'ru', 'en-US', 'en']
            });
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0
            });
            window.chrome = {
                runtime: {}
            };
        """)
        
        return self.page
    
    # ... остальные методы без изменений