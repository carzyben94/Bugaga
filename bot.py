# bot.py - bsw запускает браузер с маскировкой, работа через CDP
import os
import sys
import asyncio
import logging
import base64
import json

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

# Импорты Browser Harness (только для управления вкладками)
from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
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
        self.ws = None    # WebSocket для CDP
        self.is_ready = False
        self._id = 0
    
    async def start(self):
        """Запуск браузера через bsw + подключение через CDP"""
        logger.info("🚀 Шаг 1: Запуск браузера через bsw...")
        
        # 1. Запускаем браузер через bsw
        self.browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен через bsw")
        
        # Сохраняем WebSocket для прямого CDP
        self.ws = self.browser["ws"]
        self._id = self.browser["_id"]
        
        await asyncio.sleep(2)
        
        logger.info("🔗 Шаг 2: Подключение Browser Harness...")
        
        # 2. Устанавливаем переменные для Harness
        os.environ["BU_CDP_URL"] = "http://localhost:9222"
        
        # 3. Запускаем daemon
        self.daemon = ensure_daemon()
        logger.info("✅ Daemon запущен")
        
        # 4. Создаём вкладку через Harness
        self.page = new_tab("https://example.com")
        logger.info(f"✅ Вкладка создана: {self.page}")
        
        # 5. Ждём загрузки
        wait_for_load()
        logger.info("✅ Страница загружена")
        
        self.is_ready = True
        logger.info(f"✅ Текущая вкладка: {current_tab()}")
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def _cdp_send(self, method: str, params: dict = None) -> dict:
        """Отправить CDP команду через WebSocket"""
        self._id += 1
        msg = {
            "id": self._id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        return json.loads(response)
    
    async def get_text(self, selector: str) -> str:
        """Получение текста через CDP"""
        try:
            # Выполняем JS через CDP
            result = await self._cdp_send("Runtime.evaluate", {
                "expression": f"document.querySelector('{selector}')?.textContent || ''",
                "returnByValue": True
            })
            
            if result and "result" in result and "result" in result["result"]:
                return result["result"]["result"].get("value", "")
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка получения текста: {e}")
            return ""
    
    async def screenshot(self, path: str = None) -> bytes:
        """Скриншот через CDP"""
        try:
            result = await self._cdp_send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            })
            
            if result and "result" in result and "data" in result["result"]:
                data = base64.b64decode(result["result"]["data"])
                if path:
                    with open(path, "wb") as f:
                        f.write(data)
                    logger.info(f"📸 Скриншот сохранён в {path}")
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    async def click(self, selector: str):
        """Клик через CDP"""
        try:
            # Находим элемент
            result = await self._cdp_send("Runtime.evaluate", {
                "expression": f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        return {{
                            x: rect.left + rect.width/2,
                            y: rect.top + rect.height/2
                        }};
                    }})()
                """,
                "returnByValue": True
            })
            
            if result and "result" in result and "result" in result["result"]:
                pos = result["result"]["result"].get("value")
                if pos:
                    # Клик через CDP
                    await self._cdp_send("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": pos["x"],
                        "y": pos["y"]
                    })
                    await asyncio.sleep(0.1)
                    await self._cdp_send("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    await asyncio.sleep(0.1)
                    await self._cdp_send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": pos["x"],
                        "y": pos["y"],
                        "button": "left",
                        "clickCount": 1
                    })
                    logger.info(f"🖱️ Клик на {selector}")
                    return True
            logger.warning(f"⚠️ Элемент {selector} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            return False
    
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
        
        # 2. Получение текста (через CDP)
        text = await bot.get_text("h1")
        logger.info(f"📝 Текст: {text}")
        
        # 3. Скриншот (через CDP)
        os.makedirs("/app/screenshots", exist_ok=True)
        img = await bot.screenshot("/app/screenshots/page.png")
        if img:
            logger.info(f"📸 Скриншот сохранён (размер: {len(img)} байт)")
        else:
            logger.warning("⚠️ Скриншот не получен")
        
        # === БЕСКОНЕЧНОЕ ОЖИДАНИЕ ===
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
            
            # Простая проверка
            try:
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
    os.makedirs("/app/screenshots", exist_ok=True)
    asyncio.run(main())