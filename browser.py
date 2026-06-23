import asyncio
from playwright.async_api import async_playwright


class Browser:
    def __init__(self, headless=False, log_callback=None):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.log_callback = log_callback
        self.popup = None
    
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
    
    async def screenshot(self, filename="screen.png", page=None):
        """Скриншот (можно указать конкретную страницу)"""
        self.log(f"📸 Скриншот: {filename}")
        if page:
            await page.screenshot(path=filename, full_page=True)
        else:
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
    
    async def get_url(self, page=None):
        if page:
            return page.url
        return self.page.url
    
    async def get_pages(self):
        """Получить все страницы (вкладки)"""
        return self.browser.contexts[0].pages
    
    async def click_with_popup(self, text=None, x=None, y=None):
        """Клик с ожиданием popup окна"""
        self.log("💣 Клик с ожиданием popup...")
        
        # Ожидаем появления нового окна
        async with self.browser.contexts[0].expect_page() as popup_info:
            # Кликаем по тексту
            if text:
                self.log(f"   🔄 Клик по тексту '{text}'")
                try:
                    await self.page.get_by_text(text).first.click(timeout=3000)
                except:
                    try:
                        await self.page.locator(f"button:has-text('{text}')").click(timeout=3000)
                    except:
                        try:
                            await self.page.locator(f"*:has-text('{text}')").first.click(timeout=3000)
                        except:
                            await self.page.mouse.click(x or 960, y or 400)
            
            # Или клик по координатам
            elif x is not None and y is not None:
                self.log(f"   🔄 Клик по координатам ({x}, {y})")
                await self.page.mouse.click(x, y)
        
        # Получаем popup
        try:
            popup = await popup_info.value
            self.log("✅ Popup окно открылось!")
            self.log(f"📍 URL popup: {popup.url}")
            
            # Ждем загрузки popup
            await popup.wait_for_load_state('load', timeout=30000)
            self.log("✅ Popup загружен")
            
            return popup
        except:
            self.log("❌ Popup не открылся")
            return None
    
    async def login_google_via_popup(self, email, password):
        """Вход в Google через popup окно"""
        self.log("🔑 Вход в Google через popup...")
        
        # Кликаем "Continue with Google" и ждем popup
        popup = await self.click_with_popup(text="Continue with Google")
        
        if not popup:
            self.log("❌ Popup не открылся")
            return False
        
        try:
            # Ждем форму входа
            self.log("⏳ Ожидание формы входа...")
            await popup.wait_for_selector('input[type="email"]', timeout=30000)
            self.log("✅ Форма входа найдена")
            
            # Ввод email
            self.log("📧 Ввод email...")
            await popup.fill('input[type="email"]', email)
            await asyncio.sleep(1)
            
            # Нажимаем "Далее"
            self.log("🔄 Нажатие 'Далее'...")
            await popup.click('button:has-text("Далее"), button:has-text("Next")')
            await asyncio.sleep(3)
            
            # Ожидаем поле пароля
            self.log("⏳ Ожидание поля пароля...")
            await popup.wait_for_selector('input[type="password"]', timeout=30000)
            self.log("✅ Поле пароля найдено")
            
            # Ввод пароля
            self.log("🔑 Ввод пароля...")
            await popup.fill('input[type="password"]', password)
            await asyncio.sleep(1)
            
            # Нажимаем "Далее" или "Войти"
            self.log("🔄 Нажатие входа...")
            try:
                await popup.click('button:has-text("Далее"), button:has-text("Next"), button:has-text("Войти")')
            except:
                await popup.keyboard.press("Enter")
            
            await asyncio.sleep(5)
            
            # Проверяем URL popup
            current_url = popup.url
            self.log(f"📍 URL после входа: {current_url}")
            
            # Закрываем popup
            await popup.close()
            self.log("✅ Popup закрыт")
            
            # Возвращаемся к основной странице
            self.log("🔄 Возврат к основной странице")
            await self.page.bring_to_front()
            
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка входа: {e}")
            try:
                await popup.close()
            except:
                pass
            return False
    
    async def mega_click(self, x=None, y=None, text=None):
        self.log("💣 МЕГА-КЛИК")
        
        await asyncio.sleep(1)
        
        if x is not None and y is not None:
            self.log(f"   🔄 Клик по координатам ({x}, {y})")
            try:
                await self.page.mouse.click(x, y)
                self.log("   ✅ Клик по координатам")
                await asyncio.sleep(1)
                return True
            except Exception as e:
                self.log(f"   ❌ Ошибка: {e}")
        
        if text:
            self.log(f"   🔄 Поиск текста '{text}'")
            
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
            
            try:
                await self.page.locator(f"button:has-text('{text}')").click(timeout=3000)
                self.log("   ✅ Кнопка")
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            try:
                await self.page.locator(f"*:has-text('{text}')").first.click(timeout=3000)
                self.log("   ✅ Элемент")
                await asyncio.sleep(1)
                return True
            except:
                pass
        
        self.log("❌ МЕГА-КЛИК не сработал")
        return False