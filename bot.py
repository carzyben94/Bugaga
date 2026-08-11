# bot.py - bsw запускает браузер с маскировкой, Harness подключается
import os
import sys
import asyncio
import logging
import base64

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness (по документации)
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, capture_screenshot,
    click_at_xy, wait_for_element, close_tab, js,
    page_info, current_tab
)
from browser_harness.admin import ensure_daemon

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
        self.page = None  # Это target_id (строка)
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
        
        # 2. Устанавливаем переменные для Harness (по документации)
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 3. Запускаем daemon (по документации - без аргументов)
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # 4. Создаём вкладку (синхронно, возвращает target_id)
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 5. Ждём загрузки (синхронно)
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        goto_url(self.page, url)
        wait_for_load()
        logger.info(f"✅ Страница {url} загружена")
    
    async def get_text(self, selector: str) -> str:
        """Получение текста (по документации)"""
        try:
            # js(target_id, expression) - синхронный вызов
            result = js(self.page, f"""
                document.querySelector('{selector}')?.textContent || ''
            """)
            # По документации: результат в result['result']['value']
            if result and 'result' in result:
                return result['result'].get('value', '')
            return ''
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
    async def click(self, selector: str):
        """Клик по элементу"""
        wait_for_element(self.page, selector)
        click_at_xy(self.page, selector)
        logger.info(f"🖱️ Клик на {selector}")
    
    async def screenshot(self, path: str = None) -> bytes:
        """
        Скриншот (по документации)
        Если path указан - сохраняет в файл и возвращает путь
        Если path не указан - возвращает base64 строку
        """
        try:
            if path:
                # По документации: capture_screenshot(path) сохраняет в файл
                result = capture_screenshot(self.page, path)
                logger.info(f"📸 Скриншот сохранён в {path}")
                return result
            else:
                # Без пути возвращает base64 строку
                result = capture_screenshot(self.page)
                if isinstance(result, str):
                    # Декодируем base64 в bytes
                    return base64.b64decode(result)
                return result
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        return page_info()
    
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
        
        # === РАБОТА ПО ДОКУМЕНТАЦИИ ===
        
        # 1. Информация о странице
        info = await bot.get_page_info()
        logger.info(f"📄 Информация: {info}")
        
        # 2. Получение текста
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Скриншот в файл (по документации)
        await bot.screenshot("/app/screenshots/page.png")
        
        # 4. Скриншот в память (base64 → bytes)
        img = await bot.screenshot()
        if img:
            with open("/app/screenshots/memory.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот в память (размер: {len(img)} байт)")
        
        # === БЕСКОНЕЧНОЕ ОЖИДАНИЕ ===
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по Ctrl+C...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())