# bot.py - Правильное подключение через CDP
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
from browser_harness.cdp import connect

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
        
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness через CDP...")
        
        # 3. Подключаемся через CDP напрямую
        try:
            # Устанавливаем соединение с браузером
            connect(cdp_url)  # синхронное подключение
            logger.info("✅ CDP соединение установлено")
            
            # Создаём вкладку
            self.page = new_tab("https://example.com")
            logger.info("✅ Вкладка создана")
            
            # Ждём загрузки
            wait_for_load()
            logger.info("✅ Страница загружена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            raise
        
        self.is_ready = True
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
        
        # 3. Скриншот
        img = await bot.screenshot()
        if img:
            with open("screenshot.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот сохранён (размер: {len(img)} байт)")
        
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