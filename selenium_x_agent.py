# selenium_x_agent.py - Полная версия
"""
Selenium X Agent - Полная версия
Поддержка: установка Chrome, статус, браузер, скриншоты, вход через Google
"""

import os
import sys
import json
import logging
import time
import subprocess
import tempfile
import zipfile
import urllib.request
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

print("[SE] Запуск Selenium X Agent...", flush=True)

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
logger = logging.getLogger("SeleniumXAgent")

# === ВЕРСИИ CHROME ===
CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
_installer = None
_browser_sessions = {}

# === КЛАСС УСТАНОВЩИКА ===
class ChromeInstaller:
    """Установка и управление Chrome + Chromedriver"""
    
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
        logger.info(f"[Installer] Статус: {'✅ Готов' if self.ready else '❌ Не готов'}")
    
    def _find_existing(self):
        """Поиск уже установленного Chrome"""
        local_chrome = BASE_DIR / "chrome" / "chrome-linux64" / "chrome"
        local_driver = BASE_DIR / "driver" / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"[Installer] ✅ Локальный Chrome: {self.chrome_path}")
        
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"[Installer] ✅ Локальный Driver: {self.driver_path}")
        
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                try:
                    result = subprocess.run(["which", name], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        self.chrome_path = result.stdout.strip()
                        logger.info(f"[Installer] ✅ Системный Chrome: {self.chrome_path}")
                        break
                except:
                    pass
        
        if not self.driver_path:
            try:
                result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.driver_path = result.stdout.strip()
                    logger.info(f"[Installer] ✅ Системный Driver: {self.driver_path}")
            except:
                pass
    
    @property
    def ready(self):
        return bool(self.chrome_path and self.driver_path)
    
    def status(self) -> Dict:
        return {
            "chrome": {
                "found": bool(self.chrome_path),
                "path": self.chrome_path or "не найден"
            },
            "driver": {
                "found": bool(self.driver_path),
                "path": self.driver_path or "не найден"
            },
            "ready": self.ready,
            "base_dir": str(BASE_DIR)
        }
    
    def install(self) -> bool:
        """Установка Chrome + Driver"""
        logger.info("[Installer] 📦 Начинаю установку...")
        
        # Устанавливаем Selenium
        try:
            import selenium
            logger.info(f"[Installer] ✅ Selenium уже установлен")
        except ImportError:
            logger.info("[Installer] 📦 Устанавливаю selenium...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "selenium", "--quiet"],
                    check=True,
                    timeout=120
                )
                logger.info("[Installer] ✅ Selenium установлен")
            except Exception as e:
                logger.error(f"[Installer] ❌ Ошибка установки Selenium: {e}")
                return False
        
        # Устанавливаем Chrome
        if not self.chrome_path:
            if not self._download_chrome():
                return False
        
        # Устанавливаем Driver
        if not self.driver_path:
            if not self._download_driver():
                return False
        
        logger.info("[Installer] ✅ Установка завершена!")
        return self.ready
    
    def _download_chrome(self) -> bool:
        """Скачивание Chrome"""
        logger.info("[Installer] 📥 Скачиваю Chrome...")
        chrome_dir = BASE_DIR / "chrome"
        chrome_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "chrome.zip"
        url = f"{BASE_URL}/chrome-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("[Installer] 📦 Распаковываю Chrome...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(chrome_dir)
            
            zip_path.unlink()
            
            chrome_bin = chrome_dir / "chrome-linux64" / "chrome"
            if chrome_bin.exists():
                os.chmod(chrome_bin, 0o755)
                self.chrome_path = str(chrome_bin)
                logger.info(f"[Installer] ✅ Chrome установлен: {self.chrome_path}")
                return True
            else:
                logger.error("[Installer] ❌ Chrome не найден после распаковки")
                return False
                
        except Exception as e:
            logger.error(f"[Installer] ❌ Ошибка загрузки Chrome: {e}")
            return False
    
    def _download_driver(self) -> bool:
        """Скачивание Chromedriver"""
        logger.info("[Installer] 📥 Скачиваю Chromedriver...")
        driver_dir = BASE_DIR / "driver"
        driver_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "driver.zip"
        url = f"{BASE_URL}/chromedriver-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("[Installer] 📦 Распаковываю Driver...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(driver_dir)
            
            zip_path.unlink()
            
            driver_bin = driver_dir / "chromedriver-linux64" / "chromedriver"
            if driver_bin.exists():
                os.chmod(driver_bin, 0o755)
                self.driver_path = str(driver_bin)
                logger.info(f"[Installer] ✅ Driver установлен: {self.driver_path}")
                return True
            else:
                logger.error("[Installer] ❌ Driver не найден после распаковки")
                return False
                
        except Exception as e:
            logger.error(f"[Installer] ❌ Ошибка загрузки Driver: {e}")
            return False

# === КЛАСС БРАУЗЕРА ===
class BrowserSession:
    """Управление сессией браузера"""
    
    def __init__(self, headless: bool = True, mobile: bool = False):
        self.driver = None
        self.headless = headless
        self.mobile = mobile
        self._is_active = False
    
    @property
    def is_active(self) -> bool:
        return self._is_active and self.driver is not None
    
    def create(self):
        """Создание браузера"""
        if not _installer.ready:
            raise Exception("Chrome не установлен. Используй /se_install")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            raise Exception("Selenium не установлен. Используй /se_install")
        
        options = Options()
        
        # User-Agent
        if self.mobile:
            ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            window_size = "--window-size=390,844"
        else:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            window_size = "--window-size=1280,720"
        
        options.add_argument(f"--user-agent={ua}")
        options.add_argument(window_size)
        
        # Headless
        if self.headless:
            options.add_argument("--headless")
        
        # Анти-детект
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Путь к Chrome
        if _installer.chrome_path:
            options.binary_location = _installer.chrome_path
        
        # User data dir
        user_data_dir = BASE_DIR / "chrome_user_data"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")
        
        # Создаем драйвер
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Маскировка webdriver
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
        self._is_active = True
        logger.info("[Browser] ✅ Браузер создан")
        return self.driver
    
    def quit(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("[Browser] Браузер закрыт")
            except Exception as e:
                logger.warning(f"[Browser] Ошибка при закрытии: {e}")
            finally:
                self.driver = None
                self._is_active = False
    
    def screenshot(self, name: str = "screenshot") -> Optional[str]:
        """Создание скриншота"""
        if not self.is_active:
            logger.warning("[Browser] Браузер не активен")
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            self.driver.save_screenshot(str(filepath))
            logger.info(f"[Browser] 📸 Скриншот: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка скриншота: {e}")
            return None
    
    def open_url(self, url: str) -> bool:
        """Открытие URL"""
        if not self.is_active:
            logger.warning("[Browser] Браузер не активен")
            return False
        
        try:
            self.driver.get(url)
            time.sleep(2)
            logger.info(f"[Browser] Открыт URL: {url}")
            return True
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка открытия URL: {e}")
            return False
    
    def get_page_source(self) -> str:
        """Получение HTML страницы"""
        if not self.is_active:
            return ""
        try:
            return self.driver.page_source
        except:
            return ""
    
    def get_title(self) -> str:
        """Получение заголовка страницы"""
        if not self.is_active:
            return ""
        try:
            return self.driver.title
        except:
            return ""

# === ГЛОБАЛЬНЫЙ ИНСТАНС ===
_installer = ChromeInstaller()

# === ФУНКЦИИ СТАТУСА ===
def get_status() -> Dict:
    """Получение полного статуса"""
    st = _installer.status()
    
    try:
        import selenium
        selenium_installed = True
        selenium_version = selenium.__version__
    except ImportError:
        selenium_installed = False
        selenium_version = None
    
    st["selenium"] = {
        "installed": selenium_installed,
        "version": selenium_version
    }
    
    cookies_file = BASE_DIR / "cookies.json"
    st["cookies"] = cookies_file.exists()
    st["active_sessions"] = len([s for s in _browser_sessions.values() if s.is_active])
    
    # Для совместимости с bot.py
    st["agent_ready"] = _installer.ready
    st["auth_info"] = get_auth_info()
    st["selenium_dir"] = str(BASE_DIR)
    st["chrome_browser"] = {
        "found": _installer.chrome_path is not None,
        "path": _installer.chrome_path or "не найден"
    }
    st["chromedriver"] = {
        "ready": _installer.driver_path is not None,
        "path": _installer.driver_path or "не найден"
    }
    st["selenium_pip"] = {
        "installed": selenium_installed,
        "version": selenium_version
    }
    st["cookies_exist"] = cookies_file.exists()
    
    return st

def get_full_status() -> Dict:
    """Алиас для get_status()"""
    return get_status()

def AGENT_READY() -> bool:
    """Проверка готовности агента"""
    return _installer.ready if _installer else False

# === ФУНКЦИИ ДЛЯ АВТОРИЗАЦИИ ===
def get_auth_info() -> Optional[Dict]:
    """Получение информации об авторизации"""
    auth_file = BASE_DIR / "x_auth.json"
    if not auth_file.exists():
        return None
    try:
        with open(auth_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[Auth] Ошибка чтения: {e}")
        return None

def save_auth_info(username: str, email: str = None, extra: Dict = None) -> bool:
    """Сохранение информации об авторизации"""
    try:
        data = {
            "username": str(username),
            "email": email,
            "authorized_at": datetime.now().isoformat(),
        }
        if extra:
            data.update(extra)
        
        auth_file = BASE_DIR / "x_auth.json"
        with open(auth_file, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"[Auth] ✅ Сохранена авторизация для {username}")
        return True
    except Exception as e:
        logger.error(f"[Auth] ❌ Ошибка сохранения: {e}")
        return False

def clear_auth_info() -> bool:
    """Очистка авторизации"""
    try:
        auth_file = BASE_DIR / "x_auth.json"
        cookies_file = BASE_DIR / "x_cookies.json"
        
        if auth_file.exists():
            auth_file.unlink()
        if cookies_file.exists():
            cookies_file.unlink()
        
        logger.info("[Auth] ✅ Авторизация очищена")
        return True
    except Exception as e:
        logger.error(f"[Auth] ❌ Ошибка очистки: {e}")
        return False

# === ФУНКЦИЯ ВХОДА ЧЕРЕЗ GOOGLE ===
def google_login(email: str, password: str, bot=None, chat_id=None) -> tuple:
    """Вход через Google OAuth"""
    login_logger = logging.getLogger(f"Login_{email[:3]}")
    
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        return False, "Selenium не установлен"
    
    session = BrowserSession(headless=True, mobile=False)
    
    def report(text):
        login_logger.info(f"[Chat] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    try:
        report("⏳ Запускаю браузер...")
        session.create()
        
        report("📥 Открываю x.com...")
        session.open_url("https://x.com")
        time.sleep(3)
        
        # Ищем кнопку входа
        report("🔍 Ищу кнопку входа...")
        try:
            sign_in = WebDriverWait(session.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@href='/i/flow/login'] | //span[contains(text(), 'Sign in')]/ancestor::a"))
            )
            sign_in.click()
            time.sleep(3)
        except:
            session.open_url("https://x.com/login")
            time.sleep(3)
        
        # Ищем кнопку Google
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        
        # Поиск через JavaScript
        google_btn = session.driver.execute_script("""
            function findBtn() {
                const spans = document.querySelectorAll('span');
                for (let s of spans) {
                    const txt = s.textContent.trim().toLowerCase();
                    if (txt.includes('continue with google') || txt.includes('sign in with google')) {
                        let el = s;
                        while (el && el.tagName !== 'BUTTON' && el.tagName !== 'A') {
                            el = el.parentElement;
                        }
                        if (el) return el;
                    }
                }
                const btns = document.querySelectorAll('button, a');
                for (let b of btns) {
                    const lbl = (b.getAttribute('aria-label') || '').toLowerCase();
                    if (lbl.includes('google')) return b;
                }
                return null;
            }
            return findBtn();
        """)
        
        if not google_btn:
            # Поиск через XPath
            try:
                google_btn = WebDriverWait(session.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Continue with Google')]/ancestor::button"))
                )
            except:
                pass
        
        if not google_btn:
            report("❌ Кнопка Google не найдена")
            session.quit()
            return False, "Кнопка Google не найдена"
        
        # Клик по кнопке Google
        report("🖱️ Кликаю по Google...")
        try:
            session.driver.execute_script("arguments[0].click();", google_btn)
        except:
            try:
                google_btn.click()
            except:
                report("❌ Не удалось кликнуть")
                session.quit()
                return False, "Не удалось кликнуть по кнопке Google"
        
        time.sleep(5)
        
        # Проверка перехода на Google
        current_url = session.driver.current_url
        if "accounts.google.com" not in current_url:
            report("⚠️ Не удалось перейти на Google")
            session.quit()
            return False, "Не удалось перейти на Google"
        
        report("✅ Перешли на Google!")
        
        # Ввод email
        try:
            email_field = WebDriverWait(session.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="email"]'))
            )
            email_field.send_keys(email)
            report("✅ Email введён")
            
            next_btn = WebDriverWait(session.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Next')]"))
            )
            next_btn.click()
            time.sleep(3)
        except Exception as e:
            report(f"❌ Ошибка ввода email: {e}")
            session.quit()
            return False, f"Ошибка ввода email: {e}"
        
        # Ввод пароля
        try:
            pass_field = WebDriverWait(session.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="password"]'))
            )
            pass_field.send_keys(password)
            report("✅ Пароль введён")
            
            next_btn = WebDriverWait(session.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Next')]"))
            )
            next_btn.click()
            time.sleep(5)
        except Exception as e:
            report(f"❌ Ошибка ввода пароля: {e}")
            session.quit()
            return False, f"Ошибка ввода пароля: {e}"
        
        # Проверка 2FA
        current_url = session.driver.current_url
        if "challenge" in current_url:
            report("⚠️ Google требует капчу/2FA")
            session.quit()
            return False, "Google требует дополнительную проверку (капча/2FA)"
        
        # Ждем возврат на X
        report("⏳ Жду редирект на X...")
        x_reached = False
        for i in range(15):
            time.sleep(2)
            url = session.driver.current_url
            if "x.com" in url and "login" not in url:
                x_reached = True
                break
        
        if not x_reached:
            report("⚠️ Не удалось вернуться на X")
            session.quit()
            return False, "Не удалось войти в X"
        
        # Проверка авторизации
        session.open_url("https://x.com/home")
        time.sleep(3)
        
        html = session.driver.page_source.lower()
        auth_indicators = ["home", "following", "for you", "notifications"]
        found = [ind for ind in auth_indicators if ind in html]
        
        if found:
            report(f"✅ Авторизация подтверждена! Индикаторы: {found}")
            session.save_cookies()
            save_auth_info("google_user", email)
            session.quit()
            return True, None
        else:
            report("❌ Не удалось подтвердить авторизацию")
            session.quit()
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        session.quit()
        return False, str(e)

def create_browser(headless: bool = True, mobile: bool = False, chat_id: int = None) -> BrowserSession:
    """Создание новой сессии браузера"""
    session = BrowserSession(headless=headless, mobile=mobile)
    try:
        session.create()
        if chat_id:
            _browser_sessions[chat_id] = session
        return session
    except Exception as e:
        logger.error(f"[Browser] ❌ Ошибка создания: {e}")
        raise

# === РЕГИСТРАЦИЯ КОМАНД ДЛЯ БОТА ===
def register_selenium_bot(bot):
    """Регистрация команд для Telegram бота"""
    logger.info("[Bot] Регистрация команд Selenium...")
    
    @bot.message_handler(commands=["se_status"])
    def cmd_status(message):
        st = get_status()
        
        chrome_icon = "✅" if st['chrome']['found'] else "❌"
        driver_icon = "✅" if st['driver']['found'] else "❌"
        ready_icon = "🟢" if st['ready'] else "🔴"
        selenium_icon = "✅" if st['selenium']['installed'] else "❌"
        
        text = f"""🚗 <b>Selenium X Agent</b>

{chrome_icon} Chrome: <code>{st['chrome']['path']}</code>
{driver_icon} Driver: <code>{st['driver']['path']}</code>
{selenium_icon} Selenium: {'v' + st['selenium']['version'] if st['selenium']['installed'] else 'не установлен'}
{ready_icon} Готов: {"Да" if st['ready'] else "Нет"}

🍪 Cookies: {"есть" if st['cookies'] else "нет"}
🌐 Активных сессий: {st['active_sessions']}

📁 {st['base_dir']}"""
        
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def cmd_install(message):
        if _installer.ready:
            bot.reply_to(message, "✅ Уже установлено!", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Установка Chrome + Driver...\nЭто займет 1-2 минуты", parse_mode="HTML")
        
        try:
            success = _installer.install()
            
            if success:
                bot.edit_message_text(
                    f"✅ <b>Установка завершена!</b>\n\n"
                    f"🌐 Chrome: <code>{_installer.chrome_path}</code>\n"
                    f"🔧 Driver: <code>{_installer.driver_path}</code>",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    "❌ <b>Ошибка установки</b>\n"
                    f"Проверь логи: /se_logs",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Критическая ошибка: {e}",
                chat_id=msg.chat.id,
                message_id=msg.message_id
            )
    
    @bot.message_handler(commands=["se_clear"])
    def cmd_clear(message):
        try:
            log_file = BASE_DIR / "agent.log"
            if log_file.exists():
                log_file.write_text("")
                bot.reply_to(message, "🧹 Логи очищены", parse_mode="HTML")
            else:
                bot.reply_to(message, "❌ Лог-файл не найден", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

# === ЭКСПОРТ ===
__all__ = [
    'register_selenium_bot',
    'get_status',
    'get_full_status',
    'get_auth_info',
    'save_auth_info',
    'clear_auth_info',
    'AGENT_READY',
    'create_browser',
    'BrowserSession',
    'google_login',
    '_installer',
    'BASE_DIR'
]

# === ИНИЦИАЛИЗАЦИЯ ===
logger.info("=" * 50)
logger.info("🚗 Selenium X Agent v2.0")
logger.info(f"📁 Директория: {BASE_DIR}")
logger.info(f"🔧 Статус: {'✅ Готов' if _installer.ready else '❌ Не готов'}")
logger.info("=" * 50)

print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🚗 Selenium X Agent v2.0                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Статус: {'✅ Готов' if _installer.ready else '❌ Не готов'}                         ║
║  Директория: {BASE_DIR} ║
║                                                              ║
║  Команды:                                                    ║
║  /se_status — Статус                                        ║
║  /se_install — Установка                                    ║
║  /se_clear — Очистить логи                                  ║
║  /se_logs — Логи                                            ║
║  /se_google — Вход через Google                             ║
║  /se_logout — Выйти                                         ║
║  /se_browser — Запустить браузер                            ║
║  /se_screenshot — Скриншот                                  ║
║  /se_close — Закрыть браузер                                ║
║  /se_ping — Пинг                                            ║
║  /se_test — Тест                                            ║
║  /se_help — Помощь                                          ║
╚══════════════════════════════════════════════════════════════╝
""")