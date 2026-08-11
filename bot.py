# bot.py - bsw запускает браузер с маскировкой, Harness подключается
import os
import sys
import asyncio
import logging
import base64

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness
from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    capture_screenshot,
    click_at_xy,
    wait_for_element,
    close_tab,
    js,
    page_info,
    current_tab,
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
        self.page = None  # target_id
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
        
        # 4. Создаём вкладку (синхронно, возвращает target_id)
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 5. Ждём загрузки
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    def _get_target_id(self):
        """Получить актуальный target_id"""
        # Если self.page уже строка - используем её
        if self.page and isinstance(self.page, str):
            return self.page
        
        # Иначе получаем из current_tab()
        try:
            info = current_tab()
            if info and isinstance(info, dict):
                target_id = info.get('target_id') or info.get('targetId')
                if target_id:
                    self.page = target_id
                    return target_id
        except Exception as e:
            logger.warning(f"⚠️ Ошибка получения target_id: {e}")
        
        return self.page
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        goto_url(self.page, url)
        wait_for_load()
        logger.info(f"✅ Страница {url} загружена")
    
    async def get_text(self, selector: str) -> str:
        """Получение текста"""
        try:
            target_id = self._get_target_id()
            if not target_id:
                logger.warning("⚠️ Нет target_id для get_text")
                return ""
            
            # js(target_id, expression) - первый аргумент target_id
            result = js(target_id, f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    return el ? el.textContent : '';
                }})()
            """)
            
            # Извлекаем значение
            if result and isinstance(result, dict):
                if 'result' in result:
                    return result['result'].get('value', '')
                if 'value' in result:
                    return result.get('value', '')
            return ''
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
    async def click(self, selector: str):
        """Клик по элементу"""
        target_id = self._get_target_id()
        if not target_id:
            return
        wait_for_element(target_id, selector)
        click_at_xy(target_id, selector)
        logger.info(f"🖱️ Клик на {selector}")
    
    async def screenshot(self, path: str = None) -> bytes:
        """Скриншот"""
        try:
            target_id = self._get_target_id()
            if not target_id:
                logger.warning("⚠️ Нет target_id для скриншота")
                return None
            
            if path:
                # Сохраняем в файл
                result = capture_screenshot(target_id, path)
                logger.info(f"📸 Скриншот сохранён в {path}")
                return result
            else:
                # Получаем скриншот
                result = capture_screenshot(target_id)
                
                # Если результат это строка - пробуем декодировать base64
                if isinstance(result, str):
                    try:
                        return base64.b64decode(result)
                    except:
                        return result.encode()
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
        
        # 2. Получение текста
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Скриншот
        img = await bot.screenshot()
        if img and len(img) > 100:
            os.makedirs("/app/screenshots", exist_ok=True)
            with open("/app/screenshots/page.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот сохранён (размер: {len(img)} байт)")
        else:
            logger.warning(f"⚠️ Скриншот не получен или повреждён (размер: {len(img) if img else 0})")
        
        # === БЕСКОНЕЧНОЕ ОЖИДАНИЕ ===
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
            # Проверка браузера
            try:
                target_id = bot._get_target_id()
                if target_id:
                    # Простая проверка через page_info
                    info = page_info()
                    logger.info(f"📌 Страница: {info.get('title', 'unknown')}")
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
    # Создаём папку для скриншотов
    os.makedirs("/app/screenshots", exist_ok=True)
    asyncio.run(main())