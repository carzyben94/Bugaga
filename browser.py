import asyncio
from playwright.async_api import async_playwright

# Конфигурация эмуляции
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1920, "height": 1080}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

async def get_browser_page():
    """Создаёт полностью эмульгированный браузер"""
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-gpu',
            '--disable-accelerated-2d-canvas',
            '--disable-pdf-viewer',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--mute-audio',
            '--no-first-run',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
    )
    
    await context.set_geolocation({"latitude": 55.7558, "longitude": 37.6173})
    await context.grant_permissions(["geolocation"])
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
        window.chrome = {
            runtime: {}
        };
    """)
    
    return page, browser, context

async def take_screenshot(url: str) -> bytes:
    """Делает полный скриншот страницы"""
    page, browser, context = await get_browser_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(resolve => setTimeout(resolve, 1000));
            window.scrollTo(0, 0);
        """)
        
        await page.wait_for_timeout(1000)
        
        screenshot = await page.screenshot(full_page=True, type="png")
        return screenshot
    
    except Exception as e:
        print(f"❌ Ошибка скриншота: {e}")
        try:
            screenshot = await page.screenshot(full_page=True, type="png")
            return screenshot
        except:
            return None
    
    finally:
        await browser.close()

async def get_page_content(url: str) -> str:
    """Получает HTML-код страницы"""
    page, browser, context = await get_browser_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        content = await page.content()
        return content
    except Exception as e:
        print(f"❌ Ошибка получения контента: {e}")
        return None
    finally:
        await browser.close()

async def execute_js(url: str, script: str):
    """Выполняет JS на странице"""
    page, browser, context = await get_browser_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        result = await page.evaluate(script)
        return result
    except Exception as e:
        print(f"❌ Ошибка выполнения JS: {e}")
        return None
    finally:
        await browser.close()