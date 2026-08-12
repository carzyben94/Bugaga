# bot_working.py - рабочий код без Browser Use API
import os
import sys
import asyncio
import logging
import time

# ============================================================
# 1. НАСТРОЙКА
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. BROWSER HARNESS (без start_remote_daemon)
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    capture_screenshot,
    js,
    page_info,
)
from browser_harness.admin import ensure_daemon

# ============================================================
# 3. CDP URL
# ============================================================

CDP_URL = "https://9d683906-74b6-44a1-a138-c33b957fb907.cdp.browser-use.com"

# ============================================================
# 4. ОСНОВНОЙ КОД
# ============================================================

def main():
    logger.info("🚀 Запуск Browser Harness...")
    
    # ВАЖНО: Устанавливаем переменную ДО вызова ensure_daemon()
    os.environ["BU_CDP_URL"] = CDP_URL
    logger.info(f"🔗 BU_CDP_URL: {CDP_URL}")
    
    # ensure_daemon() подключится к существующему браузеру
    ensure_daemon()
    logger.info("✅ Демон подключен к браузеру")
    
    # Создаём вкладку
    logger.info("🌐 Создаю вкладку...")
    tab = new_tab("https://example.com")
    wait_for_load()
    logger.info(f"✅ Вкладка создана: {tab}")
    
    # Информация о странице
    info = page_info()
    logger.info(f"📄 URL: {info.get('url')}")
    logger.info(f"📌 Title: {info.get('title')}")
    
    # Скриншот
    path = f"/app/screenshots/test_{int(time.time())}.png"
    capture_screenshot(path=path)
    logger.info(f"📸 Скриншот: {path}")
    
    # Получаем текст
    text = js('document.body.innerText')
    logger.info(f"📝 Текст: {str(text)[:200]}...")
    
    logger.info("✅ Всё работает!")

if __name__ == "__main__":
    main()