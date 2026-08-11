# bot.py - bsw запускает браузер с маскировкой, Harness подключается
import os
import sys
import asyncio
import logging
import time

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness (только то, что есть)
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, capture_screenshot,
    click_at_xy, wait_for_element, close_tab, js,
    page_info, current_tab
)
from browser_harness.admin import ensure_daemon
from browser_harness.daemon import Daemon

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
        self.daemon = None
        self.page = None
        self.is_ready = False
    
    async def start(self):
        """Запуск браузера через bsw + подключение Harness"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        
        # 1. Запускаем браузер через bsw (с маскировкой)
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # 2. Устанавливаем переменные для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        os.environ["BU_BROWSER"] = "chrome"
        
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Запуск Browser Harness...")
        
        # 3. Запускаем daemon Harness'а
        try:
            self.daemon = ensure_daemon()
            logger.info("✅ Daemon запущен")
        except Exception as e:
            logger.warning(f"⚠️ ensure_daemon: {e}")
            # Пробуем альтернативный способ
            self.daemon = Daemon()
            logger.info("✅ Daemon создан через Daemon()")
        
        # 4. Создаём вкладку (синхронно)
        try:
            self.page = new_tab("https://example.com")
            logger.info(f"✅ Вкладка создана: {self.page}")
        except Exception as e:
            logger.error(f"❌ Ошибка new_tab: {e}")
            # Пробуем без URL
            self.page = new_tab()
            logger.info(f"✅ Вкладка создана (без URL): {self.page}")
        
        # 5. Ждём загрузки
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
        
        # 1. Информация о странице
        info = page_info()
        logger.info(f"📄 Информация: {info}")
        
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
                current = current_tab()
                logger.info(f"📌 Текущая вкладка: {current}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки: {e}")
                
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