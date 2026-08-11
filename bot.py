# bot.py - Минимальная версия
import asyncio
import logging
from bsw import StealthBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        # Запуск браузера
        browser = await StealthBrowser.launch(
            headless=True,
            port=9222,
            chrome_path="/usr/bin/chromium"
        )
        logger.info("✅ Браузер запущен")
        
        # Работа
        await StealthBrowser.go_to(browser, "https://example.com")
        text = await StealthBrowser.get_text(browser, "h1")
        logger.info(f"📝 Текст: {text}")
        
        # БЕСКОНЕЧНОЕ ОЖИДАНИЕ С ПРОВЕРКОЙ
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Браузер жив")
            
            # Проверка: жив ли браузер?
            try:
                await StealthBrowser.get_text(browser, "html")
            except:
                logger.warning("⚠️ Браузер упал! Перезапуск...")
                browser = await StealthBrowser.launch(
                    headless=True,
                    port=9222,
                    chrome_path="/usr/bin/chromium"
                )
                logger.info("✅ Браузер перезапущен")
                
    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")
    finally:
        await StealthBrowser.close(browser)

if __name__ == "__main__":
    asyncio.run(main())