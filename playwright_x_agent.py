# playwright_x_agent.py - Чистая версия для Playwright
"""
Playwright X Agent - Современная автоматизация для X (Twitter)
"""

import os
import sys
import json
import logging
import time
import subprocess
import tempfile
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

print("[PW] Запуск Playwright X Agent...", flush=True)

# === КОНФИГУРАЦИЯ ===
APP_DIR = Path("/app") if os.path.exists("/app") else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = BASE_DIR / "agent.log"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PlaywrightXAgent")

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
_ready = False
_browser_sessions = {}
_playwright_version = None

# === ПРОВЕРКА УСТАНОВКИ ===
def check_installed() -> bool:
    """Проверка наличия Playwright и браузера"""
    global _ready, _playwright_version
    
    try:
        import playwright
        _ready = True
        
        try:
            import pkg_resources
            _playwright_version = pkg_resources.get_distribution("playwright").version
        except:
            _playwright_version = "установлен"
        
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            logger.info("[PW] ✅ Playwright готов к работе")
            return True
        except Exception as e:
            logger.info(f"[PW] ❌ Браузер не найден: {e}")
            _ready = False
            return False
            
    except ImportError:
        _ready = False
        logger.info("[PW] ❌ Playwright не установлен")
        return False

# === УСТАНОВКА ===
def install_playwright() -> bool:
    """Установка Playwright + Chromium"""
    global _ready, _playwright_version
    logger.info("[PW] 📦 Установка Playwright...")
    
    try:
        logger.info("[PW] 📦 pip install playwright...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            check=True,
            capture_output=True,
            timeout=120
        )
        logger.info("[PW] ✅ Playwright установлен")
        
        logger.info("[PW] 🌐 playwright install chromium...")
        subprocess.run(
            ["playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            timeout=300
        )
        logger.info("[PW] ✅ Chromium установлен")
        
        logger.info("[PW] 🐧 playwright install-deps...")
        try:
            subprocess.run(
                ["playwright", "install-deps"],
                check=True,
                capture_output=True,
                timeout=120
            )
            logger.info("[PW] ✅ Зависимости установлены")
        except:
            logger.warning("[PW] ⚠️ Зависимости уже есть или не требуются")
        
        _ready = check_installed()
        
        if _ready:
            logger.info("[PW] ✅ Установка завершена!")
            return True
        else:
            logger.error("[PW] ❌ Установка не удалась")
            return False
            
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"[PW] ❌ Ошибка: {error_msg}")
        return False
    except Exception as e:
        logger.error(f"[PW] ❌ Критическая ошибка: {e}")
        return False

# === БРАУЗЕР ===
class Browser:
    """Управление браузером через Playwright"""
    
    def __init__(self, headless: bool = True, mobile: bool = False):
        self.headless = headless
        self.mobile = mobile
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_active = False
    
    def start(self):
        """Запуск браузера"""
        if not _ready:
            raise Exception("Playwright не установлен. Используй /se_install")
        
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Exception("Playwright не найден")
        
        try:
            self._playwright = sync_playwright().start()
            
            viewport = {"width": 390, "height": 844} if self.mobile else {"width": 1280, "height": 720}
            
            user_agent = (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                if self.mobile else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            self.browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            
            user_data = BASE_DIR / "playwright_data"
            user_data.mkdir(parents=True, exist_ok=True)
            
            self.context = self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                user_data_dir=str(user_data),
                locale="en-US"
            )
            
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            self.page = self.context.new_page()
            self.is_active = True
            
            logger.info("[PW] ✅ Браузер запущен")
            return self.page
            
        except Exception as e:
            logger.error(f"[PW] ❌ Ошибка запуска: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Остановка браузера"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self._playwright:
                self._playwright.stop()
            self.is_active = False
            logger.info("[PW] Браузер остановлен")
        except Exception as e:
            logger.warning(f"[PW] Ошибка остановки: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self._playwright = None
    
    def screenshot(self, name: str = "screenshot") -> Optional[str]:
        """Скриншот"""
        if not self.is_active:
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            self.page.screenshot(path=str(filepath), full_page=True)
            logger.info(f"[PW] 📸 {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[PW] ❌ Ошибка скриншота: {e}")
            return None
    
    def goto(self, url: str) -> bool:
        """Переход на URL"""
        if not self.is_active:
            return False
        
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            logger.info(f"[PW] 🌐 {url}")
            return True
        except Exception as e:
            logger.error(f"[PW] ❌ Ошибка перехода: {e}")
            return False
    
    def title(self) -> str:
        """Заголовок страницы"""
        try:
            return self.page.title() if self.is_active else ""
        except:
            return ""

# === ФУНКЦИИ СТАТУСА ===
def get_full_status() -> Dict:
    """Полный статус"""
    return {
        "ready": _ready,
        "version": _playwright_version,
        "base_dir": str(BASE_DIR),
        "cookies": (BASE_DIR / "cookies.json").exists(),
        "sessions": len([s for s in _browser_sessions.values() if s.is_active]),
        "auth": get_auth()
    }

def get_status() -> Dict:
    return get_full_status()

def is_ready() -> bool:
    return _ready

# === АВТОРИЗАЦИЯ ===
def get_auth() -> Optional[Dict]:
    """Получить данные авторизации"""
    auth_file = BASE_DIR / "auth.json"
    if not auth_file.exists():
        return None
    try:
        with open(auth_file, "r") as f:
            return json.load(f)
    except:
        return None

def get_auth_info() -> Optional[Dict]:
    """Алиас для get_auth"""
    return get_auth()

def save_auth(username: str, email: str = None) -> bool:
    """Сохранить авторизацию"""
    try:
        data = {
            "username": username,
            "email": email,
            "date": datetime.now().isoformat()
        }
        with open(BASE_DIR / "auth.json", "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"[PW] ❌ Ошибка сохранения: {e}")
        return False

def clear_auth() -> bool:
    """Очистить авторизацию"""
    try:
        for f in [BASE_DIR / "auth.json", BASE_DIR / "cookies.json"]:
            if f.exists():
                f.unlink()
        logger.info("[PW] ✅ Авторизация очищена")
        return True
    except Exception as e:
        logger.error(f"[PW] ❌ Ошибка очистки: {e}")
        return False

def clear_auth_info() -> bool:
    """Алиас для clear_auth"""
    return clear_auth()

# === ВХОД ЧЕРЕЗ GOOGLE ===
def google_login(email: str, password: str, bot=None, chat_id=None) -> tuple:
    """Вход через Google"""
    
    def report(text):
        logger.info(f"[Login] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    browser = Browser(headless=True)
    
    try:
        report("⏳ Запускаю браузер...")
        page = browser.start()
        
        report("📥 Открываю x.com...")
        browser.goto("https://x.com")
        time.sleep(2)
        
        report("🔍 Ищу вход...")
        try:
            sign = page.locator('a[href="/i/flow/login"]').first
            if sign.count() == 0:
                sign = page.locator('span:has-text("Sign in")').first
            if sign.count() > 0:
                sign.click()
                time.sleep(2)
            else:
                browser.goto("https://x.com/login")
                time.sleep(2)
        except:
            browser.goto("https://x.com/login")
            time.sleep(2)
        
        report("🔍 Ищу Google...")
        google = None
        
        for selector in [
            'button:has-text("Continue with Google")',
            'span:has-text("Continue with Google")',
            'button[aria-label*="Google"]'
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    google = el
                    break
            except:
                pass
        
        if not google:
            report("❌ Google не найден")
            browser.stop()
            return False, "Кнопка Google не найдена"
        
        report("🖱️ Кликаю...")
        google.click()
        time.sleep(3)
        
        try:
            page.wait_for_url(lambda u: "accounts.google.com" in u, timeout=15000)
        except:
            pass
        
        if "accounts.google.com" not in page.url:
            report("❌ Не перешли на Google")
            browser.stop()
            return False, "Не удалось перейти на Google"
        
        report("✅ На Google")
        
        try:
            page.locator('input[type="email"]').first.fill(email)
            report("✅ Email")
            page.locator('span:has-text("Next")').first.click()
            time.sleep(2)
        except Exception as e:
            report(f"❌ Email: {e}")
            browser.stop()
            return False, f"Ошибка email: {e}"
        
        try:
            page.locator('input[type="password"]').first.fill(password)
            report("✅ Пароль")
            page.locator('span:has-text("Next")').first.click()
            time.sleep(3)
        except Exception as e:
            report(f"❌ Пароль: {e}")
            browser.stop()
            return False, f"Ошибка пароля: {e}"
        
        if "challenge" in page.url:
            report("⚠️ Требуется 2FA")
            browser.stop()
            return False, "Требуется 2FA"
        
        report("⏳ Возврат на X...")
        try:
            page.wait_for_url(lambda u: "x.com" in u and "login" not in u, timeout=30000)
        except:
            pass
        
        browser.goto("https://x.com/home")
        time.sleep(2)
        
        html = page.content().lower()
        if any(w in html for w in ["home", "following", "notifications"]):
            report("✅ Вход выполнен!")
            cookies = page.context.cookies()
            with open(BASE_DIR / "cookies.json", "w") as f:
                json.dump(cookies, f)
            save_auth("google_user", email)
            browser.stop()
            return True, None
        else:
            report("❌ Вход не подтвержден")
            browser.stop()
            return False, "Не удалось войти"
            
    except Exception as e:
        report(f"❌ Ошибка: {e}")
        logger.error(traceback.format_exc())
        browser.stop()
        return False, str(e)

# === СОЗДАНИЕ БРАУЗЕРА ===
def create_browser(headless: bool = True, mobile: bool = False, chat_id: int = None) -> Browser:
    """Создание браузера"""
    browser = Browser(headless=headless, mobile=mobile)
    browser.start()
    if chat_id:
        _browser_sessions[chat_id] = browser
    return browser

# === ИНИЦИАЛИЗАЦИЯ ===
_ready = check_installed()

logger.info("=" * 50)
logger.info("🚗 Playwright X Agent")
logger.info(f"📁 {BASE_DIR}")
logger.info(f"🔧 {'✅ Готов' if _ready else '❌ Не готов'}")
logger.info("=" * 50)

print(f"""
╔════════════════════════════════════════════════╗
║  🚗 Playwright X Agent                        ║
╠════════════════════════════════════════════════╣
║  Статус: {'✅ Готов' if _ready else '❌ Не готов'}           ║
║  Версия: {_playwright_version or '?'}                     ║
║                                                ║
║  Команды:                                      ║
║  /se_status  /se_install                      ║
║  /se_google  /se_browser                     ║
║  /se_screenshot  /se_logs                    ║
║  /se_help                                    ║
╚════════════════════════════════════════════════╝
""")

# Экспорт
__all__ = [
    'register_commands',
    'get_full_status',
    'get_status',
    'get_auth',
    'get_auth_info',
    'is_ready',
    'create_browser',
    'Browser',
    'google_login',
    'clear_auth',
    'clear_auth_info',
    'install_playwright',
    'BASE_DIR',
    '_ready'
]