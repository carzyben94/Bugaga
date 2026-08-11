# bot.py - по документации Browser Harness
import os
import sys
import asyncio
import logging
import base64

sys.path.insert(0, "browser-harness/src")

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
    ensure_real_tab,
)
from browser_harness.admin import ensure_daemon

from bsw import StealthBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HarnessBot:
    def __init__(self):
        self.browser = None
        self.page = None  # target_id
        self.is_ready = False

    async def start(self):
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        self.browser = await StealthBrowser.launch(
            headless=True, port=9222, chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")

        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        await asyncio.sleep(2)

        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        ensure_daemon()
        logger.info("✅ Daemon запущен")

        # ✅ Первая навигация ВСЕГДА через new_tab(url)
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")

        wait_for_load()
        logger.info("✅ Страница загружена")

        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self

    def _get_page(self):
        """Получить актуальный target_id"""
        try:
            # ✅ Используем ensure_real_tab() для проверки
            ensure_real_tab()
            info = current_tab()
            if info and isinstance(info, dict):
                target_id = info.get("target_id") or info.get("targetId")
                if target_id:
                    self.page = target_id
                    return target_id
        except Exception as e:
            logger.warning(f"⚠️ Ошибка получения target_id: {e}")
        return self.page

    async def go_to(self, url: str):
        logger.info(f"🌐 Перехожу на {url}")
        # ✅ goto_url работает только после new_tab
        goto_url(self.page, url)
        wait_for_load()
        logger.info(f"✅ Страница {url} загружена")

    async def get_text(self, selector: str) -> str:
        try:
            page = self._get_page()
            if not page:
                return ""

            # ✅ js() принимает target_id как второй аргумент
            result = js(
                page,
                f"""document.querySelector('{selector}')?.textContent || ''""",
            )

            if result and isinstance(result, dict):
                if "result" in result:
                    return result["result"].get("value", "")
                if "value" in result:
                    return result.get("value", "")
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""

    async def click(self, selector: str):
        page = self._get_page()
        if not page:
            return
        wait_for_element(page, selector)
        click_at_xy(page, selector)
        logger.info(f"🖱️ Клик на {selector}")

    async def screenshot(self, path: str = None, full: bool = False) -> bytes:
        """Скриншот по документации"""
        try:
            page = self._get_page()
            if not page:
                return None

            if path:
                # ✅ capture_screenshot принимает full=True для полностраничного
                result = capture_screenshot(page, path, full=full)
                logger.info(f"📸 Скриншот сохранён в {path}")
                return result
            else:
                result = capture_screenshot(page, full=full)
                if isinstance(result, str):
                    try:
                        return base64.b64decode(result)
                    except:
                        return result.encode()
                return result
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None

    async def close(self):
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
        await bot.start()

        logger.info(f"📄 Информация: {page_info()}")

        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")

        # ✅ Полностраничный скриншот
        img = await bot.screenshot(full=True)
        if img and len(img) > 100:
            os.makedirs("/app/screenshots", exist_ok=True)
            with open("/app/screenshots/memory.png", "wb") as f:
                f.write(img)
            logger.info(f"📸 Скриншот (размер: {len(img)} байт)")

        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            ensure_real_tab()  # ✅ Проверка вкладки

    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())