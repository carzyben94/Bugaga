import os
import sys
import subprocess
import logging
from playwright.sync_api import sync_playwright, Browser, Page
from pathlib import Path

logger = logging.getLogger(__name__)

class PlaywrightBrowser:
    """Менеджер для управления Playwright браузером"""
    
    def __init__(self, headless=True, browser_type="chromium"):
        self.headless = headless
        self.browser_type = browser_type
        self.playwright = None
        self.browser = None
        self.context = None
        self._ensure_browser_installed()
    
    def _ensure_browser_installed(self):
        """Проверяет наличие браузера и устанавливает если отсутствует"""
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "--version"],
                capture_output=True,
                check=True
            )
            logger.info("Playwright уже установлен")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Playwright не найден, устанавливаю...")
            self._install_playwright()
        
        browser_path = Path.home() / ".cache" / "ms-playwright"
        browser_installed = False
        
        if browser_path.exists():
            browsers = list(browser_path.glob(f"{self.browser_type}-*"))
            if browsers:
                browser_installed = True
                logger.info(f"Браузер {self.browser_type} уже установлен")
        
        if not browser_installed:
            logger.info(f"Устанавливаю браузер {self.browser_type}...")
            self._install_browser()
    
    def _install_playwright(self):
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
                capture_output=True
            )
            logger.info("Playwright успешно установлен")
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка установки Playwright: {e.stderr.decode()}")
            raise
    
    def _install_browser(self):
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", self.browser_type],
                check=True,
                capture_output=True
            )
            logger.info(f"Браузер {self.browser_type} успешно установлен")
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка установки браузера: {e.stderr.decode()}")
            raise
    
    def start(self):
        try:
            self.playwright = sync_playwright().start()
            
            if self.browser_type == "chromium":
                browser_launcher = self.playwright.chromium
            elif self.browser_type == "firefox":
                browser_launcher = self.playwright.firefox
            elif self.browser_type == "webkit":
                browser_launcher = self.playwright.webkit
            else:
                raise ValueError(f"Неподдерживаемый тип браузера: {self.browser_type}")
            
            self.browser = browser_launcher.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            logger.info(f"Браузер {self.browser_type} успешно запущен")
            return self
            
        except Exception as e:
            logger.error(f"Ошибка запуска браузера: {e}")
            raise
    
    def new_page(self) -> Page:
        if not self.context:
            raise RuntimeError("Браузер не запущен. Вызовите start()")
        return self.context.new_page()
    
    def close(self):
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Браузер закрыт")
        except Exception as e:
            logger.error(f"Ошибка закрытия браузера: {e}")
    
    def screenshot(self, url: str, selector: str = None, full_page: bool = False) -> bytes:
        page = self.new_page()
        try:
            page.goto(url, wait_until="networkidle")
            
            if selector:
                element = page.query_selector(selector)
                if element:
                    return element.screenshot()
                else:
                    raise ValueError(f"Элемент не найден: {selector}")
            else:
                return page.screenshot(full_page=full_page)
        finally:
            page.close()
    
    def get_content(self, url: str) -> str:
        page = self.new_page()
        try:
            page.goto(url, wait_until="networkidle")
            return page.content()
        finally:
            page.close()
    
    def __enter__(self):
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_browser_info():
    """Возвращает информацию об установленных браузерах"""
    cache_path = Path.home() / ".cache" / "ms-playwright"
    if cache_path.exists():
        browsers = [d.name for d in cache_path.iterdir() if d.is_dir()]
        return {
            "installed": len(browsers) > 0,
            "browsers": browsers
        }
    return {"installed": False, "browsers": []}