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
        """Логирование"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    async def start(self):
        """Запуск браузера"""
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
        
        # Маскировка
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        self.log("✅ Маскировка установлена")
        
        return self.page
    
    async def close(self):
        """Закрытие браузера"""
        self.log("🔧 Закрытие браузера...")
        if self.browser:
            await self.browser.close()
            self.log("✅ Браузер закрыт")
        if self.playwright:
            await self.playwright.stop()
            self.log("✅ Playwright остановлен")
    
    async def screenshot(self, filename="screen.png"):
        """Скриншот"""
        self.log(f"📸 Скриншот: {filename}")
        await self.page.screenshot(path=filename, full_page=True)
        self.log("✅ Скриншот сохранен")
        return filename
    
    async def goto(self, url):
        """Переход на URL с полной загрузкой"""
        if not url.startswith('http'):
            url = 'https://' + url
        
        self.log(f"🌐 Открываю: {url}")
        
        try:
            # Этап 1: Начальная загрузка
            self.log("⏳ Этап 1: Подключение...")
            await self.page.goto(url, timeout=60000, wait_until='commit')
            self.log("✅ Подключение установлено")
            
            # Этап 2: DOM загружен
            self.log("⏳ Этап 2: Загрузка DOM...")
            await self.page.wait_for_load_state('domcontentloaded', timeout=30000)
            self.log("✅ DOM загружен")
            
            # Этап 3: Полная загрузка
            self.log("⏳ Этап 3: Полная загрузка страницы...")
            await self.page.wait_for_load_state('networkidle', timeout=60000)
            self.log("✅ Страница полностью загружена")
            
            # Этап 4: Дополнительная загрузка (для тяжелых сайтов)
            self.log("⏳ Этап 4: Ожидание дополнительных элементов...")
            await asyncio.sleep(5)
            self.log("✅ Дополнительные элементы загружены")
            
            return True
            
        except asyncio.TimeoutError:
            self.log("⚠️ Таймаут, но страница открыта")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка: {e}")
            return False
    
    async def get_url(self):
        """Получить текущий URL"""
        return self.page.url
    
    async def click(self, selector):
        """Клик по селектору"""
        self.log(f"🖱️ Клик: {selector}")
        await self.page.click(selector)
        self.log("✅ Клик выполнен")
    
    async def click_by_text(self, text):
        """Клик по тексту"""
        self.log(f"🖱️ Поиск текста: {text}")
        try:
            await self.page.get_by_text(text).click(timeout=5000)
            self.log("✅ Клик по тексту выполнен")
            return True
        except:
            self.log("❌ Текст не найден")
            return False
    
    async def mega_click(self, x=None, y=None, text=None):
        """Мега-клик - пробует все методы"""
        self.log("💣 МЕГА-КЛИК")
        
        # 1. Клик по координатам
        if x is not None and y is not None:
            self.log(f"   🔄 Метод 1: Клик по координатам ({x}, {y})")
            try:
                await self.page.mouse.click(x, y)
                self.log("   ✅ Клик по координатам успешен")
                return True
            except Exception as e:
                self.log(f"   ❌ Ошибка: {e}")
        
        # 2. Клик по тексту
        if text:
            self.log(f"   🔄 Метод 2: Клик по тексту '{text}'")
            try:
                await self.page.get_by_text(text).first.click(timeout=3000)
                self.log("   ✅ Клик по тексту успешен")
                return True
            except:
                pass
            
            self.log("   🔄 Метод 3: Поиск кнопки с текстом")
            try:
                await self.page.locator(f"button:has-text('{text}')").click(timeout=3000)
                self.log("   ✅ Клик по кнопке успешен")
                return True
            except:
                pass
            
            self.log("   🔄 Метод 4: Поиск любого элемента с текстом")
            try:
                await self.page.locator(f"*:has-text('{text}')").first.click(timeout=3000)
                self.log("   ✅ Клик по элементу успешен")
                return True
            except:
                pass
        
        # 3. Клик по центру
        self.log("   🔄 Метод 5: Клик по центру экрана")
        try:
            viewport = self.page.viewport_size
            await self.page.mouse.click(viewport['width'] // 2, viewport['height'] // 2)
            self.log("   ✅ Клик по центру успешен")
            return True
        except Exception as e:
            self.log(f"   ❌ Ошибка: {e}")
        
        self.log("❌ МЕГА-КЛИК не сработал ни одним методом")
        return False