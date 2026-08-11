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
        
        # 2. Устанавливаем переменные для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 3. Запускаем daemon
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # 4. Создаём вкладку (синхронно)
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 5. Ждём загрузки
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
        """Получение текста"""
        try:
            # Используем page как target_id
            result = js(self.page, f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    return el ? el.textContent : '';
                }})()
            """)
            # Извлекаем значение
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
        """
        try:
            if path:
                # Сохраняем в файл
                result = capture_screenshot(self.page, path)
                logger.info(f"📸 Скриншот сохранён в {path}")
                return result
            else:
                # Получаем скриншот (может вернуть base64)
                result = capture_screenshot(self.page)
                if isinstance(result, str):
                    # Декодируем base64
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
        
        # === РАБОТА ===
        
        # 1. Информация о странице
        info = await bot.get_page_info()
        logger.info(f"📄 Информация: {info}")
        
        # 2. Получение текста (с обновлённым target_id)
        # Получаем актуальный target_id
        current = current_tab()
        if current and 'target_id' in current:
            bot.page = current['target_id']
            logger.info(f"🔄 Обновлён target_id: {bot.page}")
        
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Скриншот в память
        img = await bot.screenshot()
        if img:
            with open("/app/screenshots/memory.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот в память (размер: {len(img)} байт)")
        
        # 4. Скриншот в файл
        await bot.screenshot("/app/screenshots/page.png")
        
        # === БЕСКОНЕЧНОЕ ОЖИДАНИЕ ===
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
            # Обновляем target_id при каждой проверке
            try:
                current = current_tab()
                if current and 'target_id' in current:
                    bot.page = current['target_id']
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки: {e}")
                
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