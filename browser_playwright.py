import asyncio
import os
import sys
import random
import logging
import time
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, ElementHandle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AntiDetectBrowser:
    def __init__(self, headless=False, screenshot_callback=None, log_callback=None):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.screenshot_callback = screenshot_callback
        self.log_callback = log_callback
        self.step = 0
        self.email = None
        self.playwright = None
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        if self.log_callback:
            self.log_callback(log_entry, level)
        
        return log_entry
        
    async def take_step_screenshot(self, name="step"):
        try:
            self.step += 1
            filename = f"step_{self.step}_{name}.png"
            await self.page.screenshot(path=filename, full_page=True)
            self.log(f"📸 Скриншот: {name}", "STEP")
            if self.screenshot_callback:
                self.screenshot_callback(filename, f"Шаг {self.step}: {name}")
            return filename
        except Exception as e:
            self.log(f"❌ Ошибка скриншота: {e}", "ERROR")
            return None
    
    async def setup_driver(self):
        self.log("🔧 Настройка Playwright...", "INFO")
        
        self.playwright = await async_playwright().start()
        
        # Запускаем браузер
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-setuid-sandbox',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-popup-blocking',
                '--disable-notifications',
                '--disable-infobars',
                '--disable-extensions',
                '--remote-debugging-port=9222'
            ]
        )
        
        # Контекст с максимальной маскировкой
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation', 'notifications'],
            geolocation={'longitude': -74.006, 'latitude': 40.7128},
            java_script_enabled=True,
            bypass_csp=True,
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
        
        # Маскировка под реального пользователя
        await self.context.add_init_script("""
            // Удаляем следы автоматизации
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Маскируем plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Маскируем languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Добавляем Chrome объект
            if (!window.chrome) {
                window.chrome = { runtime: {} };
            }
            
            // Маскируем permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        self.page = await self.context.new_page()
        
        # Устанавливаем таймауты
        self.page.set_default_timeout(60000)
        self.page.set_default_navigation_timeout(60000)
        
        self.log("✅ Playwright готов", "SUCCESS")
        return self.page
    
    def random_delay(self, min_sec=0.3, max_sec=1.0):
        time.sleep(random.uniform(min_sec, max_sec))
    
    async def click_element(self, element, method_name="стандартный"):
        """Универсальный клик с несколькими попытками"""
        try:
            # Пробуем стандартный клик
            await element.click(timeout=5000)
            self.log(f"   ✅ Клик {method_name}", "SUCCESS")
            return True
        except:
            pass
        
        try:
            # Пробуем через JavaScript
            await self.page.evaluate("el => el.click()", element)
            self.log(f"   ✅ Клик {method_name} (JS)", "SUCCESS")
            return True
        except:
            pass
        
        try:
            # Пробуем с принудительным скроллом
            await element.scroll_into_view_if_needed()
            await element.click(force=True, timeout=5000)
            self.log(f"   ✅ Клик {method_name} (force)", "SUCCESS")
            return True
        except:
            pass
        
        return False
    
    async def mega_click(self, text="Continue as", selector=None):
        """
        МЕГА-КЛИК — пробует все методы
        """
        self.log("💣 МЕГА-КЛИК — пробую все методы...", "INFO")
        self.log("=" * 60, "INFO")
        
        # 1. Поиск по тексту
        if text:
            try:
                elements = await self.page.get_by_text(text).all()
                for elem in elements:
                    if await elem.is_visible():
                        self.log(f"🔍 Найден элемент по тексту: '{text}'", "SUCCESS")
                        if await self.click_element(elem, "по тексту"):
                            await self.take_step_screenshot("mega_click_success")
                            return True
            except:
                pass
        
        # 2. Поиск по CSS селектору
        if selector:
            try:
                elements = await self.page.query_selector_all(selector)
                for elem in elements:
                    if await elem.is_visible():
                        self.log(f"🔍 Найден элемент по селектору: '{selector}'", "SUCCESS")
                        if await self.click_element(elem, "по селектору"):
                            await self.take_step_screenshot("mega_click_success")
                            return True
            except:
                pass
        
        # 3. Поиск всех кнопок
        try:
            buttons = await self.page.query_selector_all("button, input[type='submit'], [role='button']")
            for btn in buttons:
                if await btn.is_visible() and await btn.is_enabled():
                    btn_text = await btn.text_content() or ""
                    if text.lower() in btn_text.lower() or "continue" in btn_text.lower():
                        self.log(f"🔍 Найдена кнопка: '{btn_text[:30]}'", "SUCCESS")
                        if await self.click_element(btn, "кнопка"):
                            await self.take_step_screenshot("mega_click_success")
                            return True
        except:
            pass
        
        # 4. Клик по координатам (центр экрана)
        try:
            viewport = self.page.viewport_size
            if viewport:
                x = viewport['width'] // 2
                y = viewport['height'] // 2
                await self.page.mouse.click(x, y)
                self.log(f"   ✅ Клик по центру ({x}, {y})", "SUCCESS")
                await self.take_step_screenshot("mega_click_success")
                return True
        except:
            pass
        
        # 5. Клик по координатам (указанным)
        try:
            # Пробуем кликнуть в несколько точек
            for x, y in [(960, 380), (800, 400), (1100, 380)]:
                await self.page.mouse.click(x, y)
                self.log(f"   ✅ Клик по координатам ({x}, {y})", "SUCCESS")
                await self.take_step_screenshot("mega_click_success")
                return True
        except:
            pass
        
        # 6. Поиск в iframe
        try:
            frames = self.page.frames
            for frame in frames:
                if frame != self.page.main_frame:
                    elements = await frame.get_by_text(text).all()
                    for elem in elements:
                        if await elem.is_visible():
                            self.log("🔍 Найден элемент в iframe", "SUCCESS")
                            if await self.click_element(elem, "iframe"):
                                await self.take_step_screenshot("mega_click_success")
                                return True
        except:
            pass
        
        self.log("❌ МЕГА-КЛИК не сработал ни одним методом", "ERROR")
        await self.take_step_screenshot("mega_click_failed")
        return False
    
    async def wait_for_page_load(self, timeout=60):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout*1000)
            self.log("✅ Страница полностью загружена", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"⚠️ Таймаут загрузки: {e}", "WARNING")
            return False
    
    async def scroll_to_load(self):
        try:
            # Плавная прокрутка
            for i in range(0, 1000, 100):
                await self.page.evaluate(f"window.scrollTo(0, {i});")
                time.sleep(0.2)
            
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            await self.page.evaluate("window.scrollTo(0, 0);")
            time.sleep(2)
            self.log("✅ Прокрутка выполнена", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"⚠️ Ошибка прокрутки: {e}", "WARNING")
            return False
    
    async def login_google(self, email, password):
        self.email = email
        self.log(f"🚀 Вход в Google: {email}", "INFO")
        
        try:
            self.log("🌐 Открытие Google...", "INFO")
            await self.page.goto("https://accounts.google.com/")
            self.random_delay(2, 3)
            await self.take_step_screenshot("google_login")
            self.log("✅ Google открыт", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            return False
        
        # Ввод email
        try:
            email_field = await self.page.wait_for_selector("#identifierId", timeout=10000)
            await email_field.click()
            await email_field.fill(email)
            await self.take_step_screenshot("google_email")
            self.log("✅ Email введен", "SUCCESS")
        except:
            self.log("❌ Поле email не найдено", "ERROR")
            return False
        
        self.random_delay(1, 2)
        
        # Нажатие "Далее"
        try:
            next_btn = await self.page.wait_for_selector("#identifierNext, button:has-text('Далее'), button:has-text('Next')", timeout=5000)
            await next_btn.click()
            await self.take_step_screenshot("google_next")
            self.log("✅ 'Далее' нажата", "SUCCESS")
        except:
            self.log("⚠️ Кнопка не найдена", "WARNING")
        
        self.random_delay(2, 4)
        
        # Ввод пароля
        self.log("🔍 Поиск поля пароля...", "INFO")
        
        try:
            password_field = await self.page.wait_for_selector("input[type='password']", timeout=10000)
            await password_field.click()
            await password_field.fill(password)
            await self.take_step_screenshot("google_password")
            self.log("✅ Пароль введен", "SUCCESS")
        except:
            self.log("❌ Поле пароля не найдено", "ERROR")
            return False
        
        self.random_delay(1, 2)
        
        # Нажатие "Войти"
        self.log("🔍 Кнопка входа...", "INFO")
        
        try:
            login_btn = await self.page.wait_for_selector(
                "#passwordNext, button:has-text('Далее'), button:has-text('Next'), button:has-text('Войти')",
                timeout=5000
            )
            await login_btn.click()
            await self.take_step_screenshot("google_login_final")
            self.log("✅ Кнопка входа нажата", "SUCCESS")
        except:
            self.log("⚠️ Кнопка не найдена, пробую Enter", "WARNING")
            await self.page.keyboard.press("Enter")
        
        self.random_delay(3, 5)
        
        current_url = self.page.url
        self.log(f"📍 URL: {current_url[:80]}...", "INFO")
        
        if "challenge" in current_url or "verify" in current_url.lower():
            self.log("🔐 2FA — ожидание подтверждения", "INFO")
            await self.take_step_screenshot("google_2fa")
            
            for i in range(12):
                time.sleep(5)
                new_url = self.page.url
                if "challenge" not in new_url and "verify" not in new_url.lower():
                    self.log("✅ 2FA пройдена!", "SUCCESS")
                    break
                self.log(f"⏳ Ожидание... {i+1}/12", "INFO")
        
        self.log("✅ Вход в Google выполнен!", "SUCCESS")
        await self.take_step_screenshot("google_done")
        return True
    
    async def go_to_xcom(self):
        self.log("🌐 ПЕРЕХОД НА X.COM", "INFO")
        
        try:
            await self.page.goto("https://x.com", timeout=60000)
            self.log("✅ X.com открыт", "SUCCESS")
            
            await self.wait_for_page_load(timeout=60)
            time.sleep(3)
            await self.scroll_to_load()
            await self.take_step_screenshot("xcom_loaded")
            
            current_url = self.page.url
            self.log(f"📍 URL: {current_url}", "INFO")
            
            if "home" in current_url or "x.com/home" in current_url:
                self.log("🎉 Уже на главной", "SUCCESS")
                return True
            
            # === ЗАПУСКАЕМ МЕГА-КЛИК ===
            result = await self.mega_click(text="Continue as")
            
            if result:
                self.log("🎉 МЕГА-КЛИК сработал!", "SUCCESS")
                time.sleep(3)
                await self.take_step_screenshot("xcom_mega_click_success")
                
                current_url = self.page.url
                if "home" in current_url or "x.com/home" in current_url:
                    self.log("🎉 ВХОД ВЫПОЛНЕН!", "SUCCESS")
                    return True
            else:
                self.log("⚠️ МЕГА-КЛИК не сработал", "WARNING")
                await self.take_step_screenshot("xcom_mega_click_failed")
            
            self.log("🔄 Используйте ручное управление", "INFO")
            return True
            
        except Exception as e:
            self.log(f"❌ ОШИБКА: {e}", "ERROR")
            return False
    
    async def close(self):
        if self.browser:
            try:
                await self.browser.close()
                self.log("✅ Браузер закрыт", "SUCCESS")
            except:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass


async def main():
    """Пример использования"""
    browser = AntiDetectBrowser(headless=False)
    
    try:
        await browser.setup_driver()
        
        # Вход в Google
        await browser.login_google("your_email@gmail.com", "your_password")
        
        # Переход на X
        await browser.go_to_xcom()
        
        # Ждем для просмотра результата
        input("Нажмите Enter для завершения...")
        
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())