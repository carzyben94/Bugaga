# bot.py - bsw запускает браузер с маскировкой, Harness подключается
import os
import sys
import asyncio
import logging
import time

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, capture_screenshot,
    click_at_xy, wait_for_element, close_tab, js,
    page_info, current_tab
)

# Импортируем маскировку
from bsw import StealthBrowser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HarnessBot:
    def __init__(self):
        self.browser = None
        self.page = None
        self.is_ready = False
    
    async def start(self):
        """Запуск браузера через bsw + подключение Harness"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        
        # 1. Запускаем браузер через bsw
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # 2. Получаем CDP URL
        cdp_url = self.browser["cdp_url"]
        logger.info(f"🔗 CDP URL: {cdp_url}")
        
        # 3. Устанавливаем переменную для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        # Ждём, пока браузер полностью инициализируется
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 4. Создаём вкладку с навигацией (синхронный вызов)
        try:
            self.page = new_tab("https://example.com")
            logger.info("✅ Вкладка создана через new_tab(url)")
        except Exception as e:
            logger.error(f"❌ Ошибка new_tab: {e}")
            # Если не работает, пробуем создать пустую вкладку
            try:
                self.page = new_tab()
                logger.info("✅ Вкладка создана через new_tab()")
            except Exception as e2:
                logger.error(f"❌ Ошибка new_tab(): {e2}")
                raise
        
        # Ждём загрузки страницы
        try:
            wait_for_load()
            logger.info("✅ Страница загружена")
        except Exception as e:
            logger.warning(f"⚠️ wait_for_load: {e}")
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        try:
            goto_url(self.page, url)
            wait_for_load()
            logger.info(f"✅ Страница {url} загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка перехода: {e}")
            raise
    
    async def get_text(self, selector: str) -> str:
        """Получение текста"""
        try:
            result = js(self.page, f"""
                document.querySelector('{selector}')?.textContent || ''
            """)
            return result.get('result', {}).get('value', '')
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
    async def click(self, selector: str):
        """Клик по элементу"""
        try:
            wait_for_element(self.page, selector)
            click_at_xy(self.page, selector)
            logger.info(f"🖱️ Клик на {selector}")
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            raise
    
    async def screenshot(self) -> bytes:
        """Скриншот"""
        try:
            return capture_screenshot(self.page)
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        try:
            return page_info()
        except Exception as e:
            logger.error(f"❌ Ошибка page_info: {e}")
            return {}
    
    async def close(self):
        """Закрытие"""
        logger.info("🔚 Закрываю...")
        
        if self.page:
            try:
                close_tab(self.page)
                logger.info("✅ Вкладка закрыта")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка закрытия вкладки: {e}")
        
        if self.browser:
            await StealthBrowser.close(self.browser)
            logger.info("✅ Браузер закрыт")
        
        self.is_ready = False
        logger.info("✅ Закрыто")


async def main():
    bot = HarnessBot()
    
    try:
        # Запуск
        await bot.start()
        
        # === РАБОТА ===
        
        # 1. Переход на сайт
        await bot.go_to("https://example.com")
        
        # 2. Получение текста
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Информация о странице
        info = await bot.get_page_info()
        logger.info(f"📄 Информация: {info}")
        
        # 4. Скриншот
        img = await bot.screenshot()
        if img:
            with open("screenshot.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот сохранён (размер: {len(img)} байт)")
        
        # 5. Пример работы с другой страницей
        # await bot.go_to("https://google.com")
        # await bot.click("input[name='q']")
        # await bot.type_text("input[name='q']", "Hello")
        # await bot.click("button[type='submit']")
        
        # === БЕСКОНЕЧНОЕ ОЖИДАНИЕ ===
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
            # Проверка браузера
            try:
                await bot.get_text("html")
            except Exception as e:
                logger.warning(f"⚠️ Браузер упал: {e}")
                logger.info("🔄 Перезапуск...")
                await bot.close()
                await bot.start()
                await bot.go_to("https://example.com")
                
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по Ctrl+C...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())