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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness к браузеру...")
        
        # Browser Harness автоматически подключается к localhost:9222
        self.daemon = ensure_daemon()
        logger.info("✅ Browser Harness подключен")
        
        # Создаем вкладку через Harness
        self.page = await new_tab()
        self.is_ready = True
        
        logger.info("✅ HarnessBot готов!")
        return self
    
    # ========== МЕТОДЫ УПРАВЛЕНИЯ ==========
    
    async def go_to(self, url: str):
        """Переход на страницу"""
        logger.info(f"🌐 Перехожу на {url}")
        await goto_url(self.page, url)
        await wait_for_load(self.page)
    
    async def get_text(self, selector: str) -> str:
        """Получение текста по селектору"""
        result = await js(self.page, f"""
            document.querySelector('{selector}')?.textContent || ''
        """)
        return result.get('result', {}).get('value', '')
    
    async def click(self, selector: str):
        """Клик по элементу"""
        await wait_for_element(self.page, selector)
        await click_at_xy(self.page, selector)
    
    async def type_text(self, selector: str, text: str):
        """Ввод текста"""
        await fill_input(self.page, selector, text)
    
    async def screenshot(self) -> bytes:
        """Скриншот страницы"""
        return await capture_screenshot(self.page)
    
    async def wait_for_element(self, selector: str, timeout: int = 10):
        """Ожидание элемента"""
        await wait_for_element(self.page, selector, timeout=timeout)
    
    async def scroll(self, x: int = 0, y: int = 100):
        """Скролл страницы"""
        await scroll(self.page, x, y)
    
    async def press_key(self, key: str):
        """Нажатие клавиши"""
        await press_key(self.page, key)
    
    async def get_page_info(self) -> dict:
        """Информация о странице"""
        return await page_info(self.page)
    
    # ========== ПРЯМОЙ ДОСТУП К CDP ==========
    
    async def cdp_send(self, method: str, params: dict = None):
        """Прямой CDP запрос"""
        return await cdp(self.page, method, params or {})
    
    async def js_eval(self, expression: str) -> dict:
        """Выполнение JavaScript"""
        return await js(self.page, expression)
    
    # ========== УПРАВЛЕНИЕ ВКЛАДКАМИ ==========
    
    async def new_tab(self, url: str = None):
        """Создать новую вкладку"""
        self.page = await new_tab(url)
        return self.page
    
    async def close_current_tab(self):
        """Закрыть текущую вкладку"""
        await close_tab(self.page)
    
    async def list_tabs(self):
        """Список всех вкладок"""
        return await list_tabs()
    
    async def switch_tab(self, index: int):
        """Переключиться на вкладку по индексу"""
        self.page = await switch_tab(index)
        return self.page
    
    async def get_current_tab(self):
        """Получить текущую вкладку"""
        return await current_tab()
    
    # ========== ЗАКРЫТИЕ ==========
    
    async def close(self):
        """Закрытие браузера"""
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
        
        # ===== РАБОТА С БРАУЗЕРОМ =====
        
        # 1. Переход на сайт
        await bot.go_to("https://example.com")
        
        # 2. Получение текста
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Скриншот
        img = await bot.screenshot()
        with open("screenshot.png", "wb") as f:
            f.write(img)
        logger.info("📸 Скриншот сохранен (размер: {len(img)} байт)")
        
        # 4. Пример: прямой CDP запрос
        info = await bot.cdp_send("Browser.getVersion")
        logger.info(f"ℹ️ Версия браузера: {info}")
        
        # 5. Получение информации о странице
        page_info = await bot.get_page_info()
        logger.info(f"📄 Информация: {page_info}")
        
        # ===== БЕСКОНЕЧНОЕ ОЖИДАНИЕ =====
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
            # Проверка: жив ли браузер?
            try:
                await bot.get_text("html")
            except Exception as e:
                logger.warning(f"⚠️ Браузер упал! {e}")
                logger.info("🔄 Перезапуск браузера...")
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