import asyncio
from playwright.async_api import async_playwright


class Browser:
    def __init__(self, headless=False, log_callback=None):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.log_callback = log_callback
    
    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    async def start(self):
        self.log("🔧 Запуск браузера...")
        
        self.playwright = await async_playwright().start()
        self.log("✅ Playwright запущен")
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        self.log("✅ Браузер запущен")
        
        self.page = await self.browser.new_page(
            viewport={'width': 1920, 'height': 1080}
        )
        self.log("✅ Страница создана")
        
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        self.log("✅ Маскировка установлена")
        
        return self.page
    
    async def close(self):
        self.log("🔧 Закрытие браузера...")
        if self.browser:
            await self.browser.close()
            self.log("✅ Браузер закрыт")
        if self.playwright:
            await self.playwright.stop()
            self.log("✅ Playwright остановлен")
    
    async def screenshot(self, filename="screen.png"):
        self.log(f"📸 Скриншот: {filename}")
        await self.page.screenshot(path=filename, full_page=True)
        self.log("✅ Скриншот сохранен")
        return filename
    
    async def goto(self, url):
        if not url.startswith('http'):
            url = 'https://' + url
        
        self.log(f"🌐 Открываю: {url}")
        
        try:
            self.log("⏳ Этап 1: Подключение...")
            await self.page.goto(url, timeout=60000, wait_until='commit')
            self.log("✅ Подключение установлено")
            
            self.log("⏳ Этап 2: Загрузка DOM...")
            await self.page.wait_for_load_state('domcontentloaded', timeout=30000)
            self.log("✅ DOM загружен")
            
            self.log("⏳ Этап 3: Загрузка страницы (load)...")
            await self.page.wait_for_load_state('load', timeout=60000)
            self.log("✅ Страница загружена")
            
            self.log("⏳ Этап 4: Ожидание дополнительных элементов...")
            await asyncio.sleep(5)
            self.log("✅ Дополнительные элементы загружены")
            
            current_url = self.page.url
            self.log(f"📍 Текущий URL: {current_url}")
            
            return True
            
        except asyncio.TimeoutError:
            self.log("⚠️ Таймаут, но страница открыта")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка: {e}")
            return False
    
    async def get_url(self):
        return self.page.url
    
    async def mega_click(self, x=None, y=None, text=None, selector=None):
        """
        СУПЕР-МЕГА-КЛИК - пробует ВСЕ возможные способы
        """
        self.log("💣 СУПЕР-МЕГА-КЛИК")
        
        # Даем странице время
        await asyncio.sleep(1)
        
        # === 1. Клик по координатам ===
        if x is not None and y is not None:
            self.log(f"   🔄 1. Клик по координатам ({x}, {y})")
            try:
                await self.page.mouse.click(x, y)
                self.log("   ✅ Клик по координатам успешен")
                await asyncio.sleep(1)
                return True
            except Exception as e:
                self.log(f"   ❌ Ошибка: {e}")
        
        # === 2. Поиск по тексту ===
        if text:
            self.log(f"   🔄 2. Клик по тексту '{text}'")
            try:
                await self.page.get_by_text(text, exact=True).first.click(timeout=3000)
                self.log("   ✅ Точное совпадение")
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            try:
                await self.page.get_by_text(text).first.click(timeout=3000)
                self.log("   ✅ Частичное совпадение")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        # === 3. Поиск кнопок ===
        if text:
            self.log(f"   🔄 3. Поиск кнопки с текстом '{text}'")
            try:
                await self.page.locator(f"button:has-text('{text}')").click(timeout=3000)
                self.log("   ✅ Кнопка найдена")
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            try:
                await self.page.locator(f"button:has-text('{text}')").first.click(timeout=3000, force=True)
                self.log("   ✅ Кнопка (force)")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        # === 4. Поиск div/span с текстом ===
        if text:
            self.log(f"   🔄 4. Поиск элемента с текстом '{text}'")
            try:
                await self.page.locator(f"div:has-text('{text}')").first.click(timeout=3000)
                self.log("   ✅ Div найден")
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            try:
                await self.page.locator(f"span:has-text('{text}')").first.click(timeout=3000)
                self.log("   ✅ Span найден")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        # === 5. JavaScript клик ===
        if text:
            self.log(f"   🔄 5. JavaScript клик по тексту '{text}'")
            try:
                await self.page.evaluate(f"""
                    const elements = document.querySelectorAll('*');
                    for (let el of elements) {{
                        if (el.textContent && el.textContent.includes('{text}')) {{
                            el.click();
                            return true;
                        }}
                    }}
                """)
                self.log("   ✅ JavaScript клик успешен")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        # === 6. Клик по селектору ===
        if selector:
            self.log(f"   🔄 6. Клик по селектору '{selector}'")
            try:
                await self.page.click(selector, timeout=3000)
                self.log("   ✅ Клик по селектору")
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            try:
                await self.page.click(selector, timeout=3000, force=True)
                self.log("   ✅ Клик по селектору (force)")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        # === 7. Клик по центру экрана ===
        self.log("   🔄 7. Клик по центру экрана")
        try:
            viewport = self.page.viewport_size
            await self.page.mouse.click(viewport['width'] // 2, viewport['height'] // 2)
            self.log("   ✅ Клик по центру")
            await asyncio.sleep(1)
            return True
        except Exception as e:
            self.log(f"   ❌ Ошибка: {e}")
        
        # === 8. Клик по первому элементу с ролью button ===
        self.log("   🔄 8. Поиск любой кнопки")
        try:
            await self.page.locator("[role='button']").first.click(timeout=3000)
            self.log("   ✅ Кнопка (role)")
            await asyncio.sleep(1)
            return True
        except:
            pass
        
        self.log("❌ СУПЕР-МЕГА-КЛИК не сработал")
        return False