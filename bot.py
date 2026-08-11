# bot.py - bsw запускает браузер с маскировкой, Harness подключается
import os
import sys
import asyncio
import logging

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
)
from browser_harness.admin import ensure_daemon

# Импортируем маскировку
from bsw import StealthBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HarnessBot:
    """bsw запускает браузер → Harness подключается через CDP"""
    
    def __init__(self):
        self.browser = None      # от bsw
        self.daemon = None       # от Harness
        self.page = None
        self.is_ready = False
    
    async def start(self):
        """Шаг 1: bsw запускает браузер → Шаг 2: Harness подключается"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw (с маскировкой)...")
        
        # bsw запускает браузер с полной маскировкой
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # Ждем, пока браузер полностью инициализируется
        await asyncio.sleep(1)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness к браузеру...")
        
        # Harness подключается к уже запущенному браузеру
        self.daemon = await ensure_daemon(
            browser_url="http://localhost:9222",
            headless=True
        )
        logger.info("✅ Browser Harness подключен")
        
        # Создаем вкладку через Harness
        self.page = await new_tab()
        self.is_ready = True
        
        logger.info("✅ HarnessBot готов!")
        return self
    
    # ========== МЕТОДЫ С ПРИОРИТЕТОМ HARNESS ==========
    
    async def go_to(self, url: str):
        """Переход через Harness"""
        logger.info(f"🌐 Перехожу на {url}")
        await goto_url(self.page, url)
        await wait_for_load(self.page)
    
    async def get_text(self, selector: str) -> str:
        """Получение текста через Harness"""
        result = await js(self.page, f"""
            document.querySelector('{selector}')?.textContent || ''
        """)
        return result.get('result', {}).get('value', '')
    
    async def click(self, selector: str):
        """Клик через Harness"""
        await wait_for_element(self.page, selector)
        await click_at_xy(self.page, selector)
    
    async def type(self, selector: str, text: str):
        """Ввод через Harness"""
        await fill_input(self.page, selector, text)
    
    async def screenshot(self) -> bytes:
        """Скриншот через Harness"""
        return await capture_screenshot(self.page)
    
    async def wait(self, selector: str, timeout: int = 10):
        """Ожидание элемента через Harness"""
        await wait_for_element(self.page, selector, timeout=timeout)
    
    async def scroll(self, x: int = 0, y: int = 100):
        """Скролл через Harness"""
        await scroll(self.page, x, y)
    
    async def press(self, key: str):
        """Нажатие клавиши через Harness"""
        await press_key(self.page, key)
    
    # ========== МЕТОДЫ ДЛЯ ПРЯМОГО ДОСТУПА К CDP ==========
    
    async def cdp_send(self, method: str, params: dict = None):
        """Прямой CDP запрос через Harness"""
        return await cdp(self.page, method, params or {})
    
    async def js_eval(self, expression: str) -> dict:
        """Выполнение JS через Harness"""
        return await js(self.page, expression)
    
    # ========== УПРАВЛЕНИЕ ВКЛАДКАМИ ==========
    
    async def new_tab(self):
        """Новая вкладка"""
        self.page = await new_tab()
        return self.page
    
    async def close_tab(self):
        """Закрыть текущую вкладку"""
        await close_tab(self.page)
    
    async def list_tabs(self):
        """Список вкладок"""
        return await list_tabs()
    
    async def switch_tab(self, index: int):
        """Переключить вкладку"""
        self.page = await switch_tab(index)
        return self.page
    
    # ========== ЗАКРЫТИЕ ==========
    
    async def close(self):
        """Закрытие: сначала Harness, потом bsw"""
        logger.info("🔚 Закрываю...")
        
        # Закрываем вкладки через Harness
        if self.page:
            try:
                await close_tab(self.page)
            except:
                pass
        
        # Закрываем браузер через bsw
        if self.browser:
            await StealthBrowser.close(self.browser)
        
        self.is_ready = False
        logger.info("✅ Закрыто")


# ============================================
# ЗАПУСК
# ============================================

async def main():
    bot = HarnessBot()
    
    try:
        # Запуск (bsw → Harness)
        await bot.start()
        
        # Работа через Harness
        await bot.go_to("https://example.com")
        
        # Получаем текст
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # Скриншот
        img = await bot.screenshot()
        with open("screenshot.png", "wb") as f:
            f.write(img)
        logger.info("📸 Скриншот сохранен")
        
        # Пример: прямой CDP запрос
        info = await bot.cdp_send("Browser.getVersion")
        logger.info(f"ℹ️ Браузер: {info}")
        
        # Бесконечное ожидание
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())