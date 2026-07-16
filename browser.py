import asyncio
import logging
import subprocess
import time
import requests
import pychrome

logger = logging.getLogger(__name__)

class CDPBrowserManager:
    def __init__(self, port=9222):
        self.port = port
        self.process = None
        self.browser = None

    async def start(self):
        """Запуск процесса Chromium и подключение к CDP"""
        logger.info("🌐 Запуск Chromium (прямой CDP)...")
        
        # Запускаем Chromium как subprocess
        # Важно: --no-sandbox обязателен для Docker/Railway
        self.process = subprocess.Popen([
            "chromium", # На Railway пакет обычно называется chromium. Если не сработает, попробовать "google-chrome" или "chrome"
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={self.port}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Ждем, пока порт отдаст CDP JSON
        await self._wait_for_cdp()

        # Подключаемся через pychrome
        try:
            self.browser = pychrome.Browser(url=f"http://127.0.0.1:{self.port}")
            logger.info("✅ Подключено к Chromium через CDP.")
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
            await self.stop()

    async def _wait_for_cdp(self, timeout=10):
        """Ожидание готовности CDP endpoint"""
        url = f"http://127.0.0.1:{self.port}/json/version"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=1)
                if response.status_code == 200:
                    return True
            except requests.ConnectionError:
                pass
            await asyncio.sleep(0.5)
            
        raise Exception("Chromium не смог запуститься за отведенное время")

    async def stop(self):
        """Остановка процесса Chromium"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            logger.info("🛑 Chromium остановлен.")

    async def get_page_title(self, url: str) -> str:
        """Пример: получить заголовок страницы через CDP"""
        if not self.browser:
            raise Exception("Браузер не инициализирован!")

        # Запускаем синхронный pychrome в отдельном потоке, чтобы не блокировать асинк-цикл бота
        return await asyncio.to_thread(self._sync_get_title, url)

    def _sync_get_title(self, url: str) -> str:
        """Синхронная работа с CDP"""
        # Создаем новую вкладку
        tab = self.browser.new_tab()
        tab.start()
        
        try:
            # Включаем нужные домены CDP
            tab.Page.enable()
            tab.Runtime.enable()
            
            # Переходим на страницу
            tab.Page.navigate(url=url, _timeout=15)
            
            # Ждем загрузки (упрощенный вариант: просто пауза, в идеале слушать Network.loadingFinished или Page.loadEventFired)
            time.sleep(3) 
            
            # Выполняем JS для получения тайтла
            result = tab.Runtime.evaluate(expression="document.title")
            title = result.get('result', {}).get('value', 'Без названия')
            return title
            
        except Exception as e:
            logger.error(f"Ошибка CDP: {e}")
            return f"Ошибка: {e}"
        finally:
            # Обязательно закрываем вкладку, чтобы не копился мусор в памяти
            tab.stop()
            self.browser.close_tab(tab)

# Экземпляр менеджера
browser_manager = CDPBrowserManager()