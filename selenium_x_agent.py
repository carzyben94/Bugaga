
fixed_script = '''# selenium_x_agent.py — Исправленный вход через Google в X
import os
import sys
import time
import json
import logging
import zipfile
import urllib.request
import subprocess
import tempfile
import traceback
import threading
import re
from pathlib import Path

print("[SE] Начало модуля", flush=True)

APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_FILE = BASE_DIR / "x_cookies.json"
AUTH_FILE = BASE_DIR / "x_auth.json"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
LOG_FILE = BASE_DIR / "agent.log"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SeleniumXAgent")

CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"
CHROME_ZIP = f"{BASE_URL}/chrome-linux64.zip"
DRIVER_ZIP = f"{BASE_URL}/chromedriver-linux64.zip"

login_sessions = {}


class ChromeInstaller:
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
        print(f"[SE] Installer ready={self.ready}", flush=True)
    
    def _find_existing(self):
        CHROME_DIR = BASE_DIR / "chrome"
        DRIVER_DIR = BASE_DIR / "driver"
        
        local_chrome = CHROME_DIR / "chrome-linux64" / "chrome"
        local_driver = DRIVER_DIR / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
        if local_driver.exists():
            self.driver_path = str(local_driver)
        
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                try:
                    result = subprocess.run(["which", name], capture_output=True, text=True, timeout=5, check=True)
                    self.chrome_path = result.stdout.strip()
                    break
                except:
                    pass
        
        if not self.driver_path:
            try:
                result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True, timeout=5, check=True)
                self.driver_path = result.stdout.strip()
            except:
                pass
    
    @property
    def ready(self):
        return bool(self.chrome_path and self.driver_path)
    
    def status(self):
        return {
            "chrome": {"found": bool(self.chrome_path), "path": self.chrome_path},
            "driver": {"found": bool(self.driver_path), "path": self.driver_path},
            "ready": self.ready,
            "base_dir": str(BASE_DIR)
        }
    
    def install(self):
        logger.info("Начинаю установку...")
        self._install_selenium_pip()
        success = True
        if not self.chrome_path:
            success = self._download_chrome() and success
        if not self.driver_path:
            success = self._download_driver() and success
        return success
    
    def _install_selenium_pip(self):
        try:
            import selenium
            print(f"[SE] Selenium уже установлен: v{selenium.__version__}", flush=True)
            return True
        except ImportError:
            print("[SE] Устанавливаю selenium...", flush=True)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "selenium"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print("[SE] Selenium установлен", flush=True)
                    import importlib
                    if "selenium" in sys.modules:
                        importlib.reload(sys.modules["selenium"])
                    return True
                else:
                    print(f"[SE] Ошибка: {result.stderr[:200]}", flush=True)
                    return False
            except Exception as e:
                print(f"[SE] Ошибка установки: {e}", flush=True)
                return False
    
    def _download(self, url, dest):
        try:
            urllib.request.urlretrieve(url, dest)
            return True
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False
    
    def _extract(self, zip_path, dest_dir):
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(dest_dir)
            zip_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Extract error: {e}")
            return False
    
    def _make_executable(self, path):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
        except:
            pass
    
    def _download_chrome(self):
        CHROME_DIR = BASE_DIR / "chrome"
        CHROME_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = BASE_DIR / "chrome.zip"
        if not self._download(CHROME_ZIP, zip_path):
            return False
        if not self._extract(zip_path, CHROME_DIR):
            return False
        chrome_bin = CHROME_DIR / "chrome-linux64" / "chrome"
        if chrome_bin.exists():
            self._make_executable(chrome_bin)
            self.chrome_path = str(chrome_bin)
            return True
        return False
    
    def _download_driver(self):
        DRIVER_DIR = BASE_DIR / "driver"
        DRIVER_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = BASE_DIR / "driver.zip"
        if not self._download(DRIVER_ZIP, zip_path):
            return False
        if not self._extract(zip_path, DRIVER_DIR):
            return False
        driver_bin = DRIVER_DIR / "chromedriver-linux64" / "chromedriver"
        if driver_bin.exists():
            self._make_executable(driver_bin)
            self.driver_path = str(driver_bin)
            return True
        return False


_installer = ChromeInstaller()


def get_full_status():
    auth = get_auth_info()
    selenium_ok = False
    try:
        import selenium
        selenium_ok = True
    except:
        pass
    
    return {
        "selenium_pip": {"installed": selenium_ok, "version": None},
        "chrome_browser": {"found": _installer.status()["chrome"]["found"], "path": _installer.chrome_path},
        "chromedriver": {"ready": _installer.status()["driver"]["found"], "path": _installer.driver_path},
        "agent_ready": _installer.ready,
        "cookies_exist": COOKIES_FILE.exists(),
        "auth_info": auth,
        "selenium_dir": str(BASE_DIR),
    }


def get_auth_info():
    if not AUTH_FILE.exists():
        return None
    try:
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def save_auth_info(username, email=None, extra=None):
    try:
        data = {
            "username": str(username),
            "email": email,
            "authorized_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            data.update(extra)
        with open(AUTH_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False


def clear_auth_info():
    try:
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
        if COOKIES_FILE.exists():
            COOKIES_FILE.unlink()
        return True
    except:
        return False


def icon(flag):
    return "✅" if flag else "❌"


def run_sync_task(func, *args, **kwargs):
    result = [None, None]
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            result[1] = str(e)
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=300)
    if t.is_alive():
        return None, "Таймаут (300 сек)"
    if result[1]:
        return None, result[1]
    return result[0], None


# === BROWSER SESSION ===
class BrowserSession:
    def __init__(self):
        self.driver = None
        self._chat_id = None
        self._bot = None
    
    def set_chat(self, bot, chat_id):
        self._bot = bot
        self._chat_id = chat_id
    
    def _report(self, text):
        logger.info(text)
        if self._bot and self._chat_id:
            try:
                self._bot.send_message(self._chat_id, text, parse_mode="HTML")
            except:
                pass
    
    def _screenshot(self, name, caption=None):
        try:
            path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
            self.driver.save_screenshot(str(path))
            if self._bot and self._chat_id and path.exists():
                with open(path, "rb") as f:
                    self._bot.send_photo(self._chat_id, f, caption=caption or f"📸 {name}")
            return str(path)
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None
    
    def _save_html(self, name):
        try:
            html = self.driver.page_source
            html_path = BASE_DIR / f"{name}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"HTML saved: {html_path}")
            return str(html_path)
        except Exception as e:
            logger.error(f"HTML save error: {e}")
            return None
    
    def _get_options(self):
        from selenium.webdriver.chrome.options import Options
        options = Options()
        
        # === КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ДЛЯ ОБХОДА БЛОКИРОВКИ ===
        
        # 1. Desktop User-Agent вместо мобильного (меньше подозрений)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        options.add_argument(f"--user-agent={ua}")
        
        # 2. НЕ headless! Используем виртуальный дисплей
        # options.add_argument("--headless")  # УБРАНО!
        
        # 3. Окно нормального размера
        options.add_argument("--window-size=1366,768")
        
        # 4. Основные sandbox-аргументы
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # 5. Отключаем флаги автоматизации
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 6. Дополнительные анти-детект настройки
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-US,en")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        
        # 7. Притворяемся обычным пользователем
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_settings.popups": 0,
        }
        options.add_experimental_option("prefs", prefs)
        
        if _installer.chrome_path and "chrome-linux64" in _installer.chrome_path:
            options.binary_location = _installer.chrome_path
        
        return options
    
    def create(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        
        # Проверяем/запускаем виртуальный дисплей
        display = None
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=0, size=(1366, 768))
            display.start()
            logger.info("Виртуальный дисплей запущен")
        except ImportError:
            logger.warning("pyvirtualdisplay не установлен, пробуем установить...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "pyvirtualdisplay"], 
                              capture_output=True, timeout=60)
                from pyvirtualdisplay import Display
                display = Display(visible=0, size=(1366, 768))
                display.start()
                logger.info("Виртуальный дисплей запущен после установки")
            except Exception as e:
                logger.error(f"Не удалось запустить виртуальный дисплей: {e}")
                # Пробуем xvfb напрямую
                try:
                    os.environ['DISPLAY'] = ':99'
                    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1366x768x24", "-ac"])
                    time.sleep(2)
                    logger.info("Xvfb запущен напрямую")
                except:
                    pass
        
        self._display = display
        
        options = self._get_options()
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        
        # Дополнительные опции для обхода детекта
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--disable-site-isolation-trials")
        
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Скрываем webdriver
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
            """
        })
        
        return self.driver
    
    def save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            return True
        except:
            return False
    
    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        # Останавливаем виртуальный дисплей
        if hasattr(self, '_display') and self._display:
            try:
                self._display.stop()
            except:
                pass


def _send_log_file(bot, chat_id, prefix=""):
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "rb") as f:
                caption = f"{prefix}\\n📄 Логи: {LOG_FILE.name}" if prefix else f"📄 Логи: {LOG_FILE.name}"
                bot.send_document(chat_id, f, caption=caption)
    except Exception as e:
        logger.error(f"Failed to send log: {e}")


# === GOOGLE LOGIN ===
def google_login(email, password, bot=None, chat_id=None):
    try:
        import selenium
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        _installer._install_selenium_pip()
        try:
            import selenium
            from selenium.webdriver.common.keys import Keys
        except ImportError:
            return False, "Selenium не удалось установить"
    
    session = BrowserSession()
    if bot and chat_id:
        session.set_chat(bot, chat_id)
    
    def report(text):
        logger.info(text)
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Report send error: {e}")
    
    def report_error(text, send_log=True):
        logger.error(text)
        if bot and chat_id:
            try:
                bot.send_message(chat_id, f"❌ {text}", parse_mode="HTML")
                if send_log:
                    _send_log_file(bot, chat_id, prefix=f"❌ {text[:100]}")
            except Exception as e:
                logger.error(f"Error report failed: {e}")
    
    try:
        report("⏳ Запускаю браузер...")
        logger.info(f"Starting login for email: {email[:3]}***")
        session.create()
        logger.info(f"Browser created, title: {session.driver.title}")
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # === ШАГ 1: Заходим напрямую на страницу входа X ===
        report("📥 Открываю страницу входа X...")
        logger.info("Navigating to https://x.com/i/flow/login")
        session.driver.get("https://x.com/i/flow/login")
        time.sleep(8)  # Даём больше времени на загрузку
        
        current_url = session.driver.current_url
        title = session.driver.title
        logger.info(f"After login page load - URL: {current_url}, Title: {title}")
        report(f"📍 URL: {current_url}")
        report(f"📰 Title: {title}")
        
        session._screenshot("step1_login_page", "📸 Шаг 1: Страница входа")
        session._save_html("step1_login_page")
        
        # === ШАГ 2: Ищем и кликаем "Continue with Google" ===
        report("🔍 Ищу кнопку Google...")
        time.sleep(3)
        
        google_btn = None
        
        # Множественные стратегии поиска
        strategies = [
            # По тексту
            ("//span[contains(text(), 'Continue with Google')]", "text"),
            ("//span[contains(text(), 'Sign in with Google')]", "text"),
            ("//div[contains(text(), 'Continue with Google')]", "text"),
            ("//div[contains(text(), 'Sign in with Google')]", "text"),
            # По aria-label
            ("//div[@aria-label='Sign in with Google']", "aria"),
            ("//button[@aria-label='Sign in with Google']", "aria"),
            # По роли
            ("//div[@role='button' and contains(., 'Google')]", "role"),
            ("//button[contains(., 'Google')]", "button"),
            # По SVG/иконке Google
            ("//svg[contains(@class, 'google')]", "svg"),
            # По data-testid
            ("//div[@data-testid='googleLoginButton']", "testid"),
            # Общий поиск по partial text
            ("//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]", "partial"),
        ]
        
        for xpath, strategy in strategies:
            try:
                elements = session.driver.find_elements(By.XPATH, xpath)
                logger.debug(f"Strategy '{strategy}' found: {len(elements)} elements")
                if elements:
                    # Берём самый видимый элемент
                    for el in elements:
                        try:
                            if el.is_displayed() and el.is_enabled():
                                google_btn = el
                                logger.info(f"Found Google button via strategy: {strategy}")
                                report(f"✅ Найдено через: {strategy}")
                                break
                        except:
                            continue
                    if google_btn:
                        break
            except Exception as e:
                logger.debug(f"Strategy '{strategy}' failed: {e}")
        
        # Если XPath не сработал, ищем по всем кнопкам
        if not google_btn:
            logger.info("XPath search failed, trying all interactive elements...")
            report("🔍 Перебираю все элементы...")
            
            all_elements = session.driver.find_elements(By.XPATH, 
                "//button | //div[@role='button'] | //a | //div[contains(@class, 'button')]")
            logger.info(f"Total interactive elements: {len(all_elements)}")
            
            for idx, el in enumerate(all_elements[:30]):
                try:
                    text = (el.text or el.get_attribute("aria-label") or 
                           el.get_attribute("title") or "")
                    href = el.get_attribute("href") or ""
                    
                    if text or href:
                        report(f"   [{idx}] {text[:50]} | href={href[:50]}")
                        
                        if any(kw in (text + href).lower() for kw in ['google', 'gmail', 'continue with g']):
                            if el.is_displayed():
                                google_btn = el
                                logger.info(f"Found Google button at index {idx}")
                                report(f"   ✅ Это Google!")
                                break
                except Exception as e:
                    logger.debug(f"Element [{idx}] error: {e}")
        
        if not google_btn:
            logger.error("Google button not found")
            report_error("❌ Кнопка Google не найдена! Проверь скриншот.")
            session._screenshot("no_google_found", "📸 Нет кнопки Google")
            return False, "Кнопка Google не найдена"
        
        # Кликаем по Google
        report("🖱️ Кликаю по Google...")
        logger.info("Clicking Google button")
        
        try:
            # Скроллим к элементу
            session.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", google_btn)
            time.sleep(1)
            
            # Пробуем обычный клик
            google_btn.click()
            logger.info("Normal click succeeded")
        except Exception as e:
            logger.warning(f"Normal click failed: {e}, trying JS click")
            try:
                session.driver.execute_script("arguments[0].click();", google_btn)
                logger.info("JS click succeeded")
            except Exception as e2:
                logger.error(f"JS click also failed: {e2}")
                # Пробуем найти href и перейти
                href = google_btn.get_attribute("href")
                if href:
                    logger.info(f"Navigating to href: {href[:100]}")
                    session.driver.get(href)
                else:
                    raise Exception("All click methods failed")
        
        time.sleep(8)
        session._screenshot("after_google_click", "📸 После клика Google")
        logger.info(f"After Google click - URL: {session.driver.current_url}")
        
        # === ШАГ 3: Google Auth Flow ===
        current_url = session.driver.current_url
        logger.info(f"Current URL before Google auth: {current_url}")
        report(f"📍 URL: {current_url[:80]}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            logger.info("On Google auth page")
            report("✅ На странице Google!")
            
            # Ждём загрузки формы
            time.sleep(3)
            
            try:
                logger.info("Looking for email field")
                email_field = WebDriverWait(session.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"], input[name="identifier"], #identifierId'))
                )
                email_field.clear()
                email_field.send_keys(email)
                logger.info("Email entered")
                report("✅ Email введён")
                time.sleep(1)
                
                # Ищем кнопку Next или жмём Enter
                try:
                    next_btn = session.driver.find_element(By.XPATH, "//button[contains(., 'Next')] | //span[contains(., 'Next')]//ancestor::button")
                    next_btn.click()
                except:
                    email_field.send_keys(Keys.RETURN)
                
                time.sleep(5)
                logger.info(f"After email - URL: {session.driver.current_url}")
            except Exception as e:
                logger.error(f"Email input failed: {e}")
                report(f"⚠️ Email: {e}")
                session._screenshot("email_error", "📸 Ошибка ввода email")
            
            # Проверяем, не попали ли на страницу с выбором аккаунта
            try:
                account_elements = session.driver.find_elements(By.XPATH, 
                    "//div[@data-email] | //div[contains(@class, 'account')]")
                if account_elements:
                    logger.info("Account selection page detected")
                    report("🔀 Страница выбора аккаунта")
                    # Ищем аккаунт с нужным email
                    for acc in account_elements:
                        acc_email = acc.get_attribute("data-email") or acc.text
                        if email.lower() in (acc_email or "").lower():
                            acc.click()
                            logger.info(f"Selected account: {acc_email}")
                            report(f"✅ Выбран аккаунт: {acc_email}")
                            time.sleep(5)
                            break
            except:
                pass
            
            try:
                logger.info("Looking for password field")
                pass_field = WebDriverWait(session.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"], input[name="password"]'))
                )
                pass_field.clear()
                pass_field.send_keys(password)
                logger.info("Password entered")
                report("✅ Пароль введён")
                time.sleep(1)
                
                # Ищем кнопку Next/Sign in или жмём Enter
                try:
                    next_btn = session.driver.find_element(By.XPATH, 
                        "//button[contains(., 'Next')] | //span[contains(., 'Next')]//ancestor::button | "
                        "//button[contains(., 'Sign in')] | //span[contains(., 'Sign in')]//ancestor::button")
                    next_btn.click()
                except:
                    pass_field.send_keys(Keys.RETURN)
                
                time.sleep(8)
                logger.info(f"After password - URL: {session.driver.current_url}")
            except Exception as e:
                logger.error(f"Password input failed: {e}")
                report(f"⚠️ Password: {e}")
                session._screenshot("password_error", "📸 Ошибка ввода пароля")
            
            # Обработка 2FA / подтверждения
            for attempt in range(10):
                time.sleep(3)
                url = session.driver.current_url
                logger.info(f"2FA check [{attempt+1}/10]: {url}")
                
                if "accounts.google.com" not in url:
                    logger.info("Left Google auth page")
                    break
                
                # Проверяем, не запросили ли код 2FA
                try:
                    code_inputs = session.driver.find_elements(By.CSS_SELECTOR, 
                        'input[type="tel"], input[aria-label*="code"], input[name="idvPin"]')
                    if code_inputs:
                        report("🔐 Требуется 2FA код! Введи код в чат командой /code <код>")
                        # Здесь можно добавить логику ожидания кода от пользователя
                        session._screenshot("2fa_required", "📸 Требуется 2FA")
                        break
                except:
                    pass
                
                # Проверяем подтверждение "Да, это я"
                try:
                    confirm_btn = session.driver.find_element(By.XPATH, 
                        "//button[contains(., 'Yes')] | //span[contains(., 'Yes')]//ancestor::button")
                    confirm_btn.click()
                    report("✅ Подтверждение 'Да, это я'")
                    time.sleep(5)
                    break
                except:
                    pass
            
            session._screenshot("google_done", "📸 После Google login")
        
        # === ШАГ 4: Ждём редиректа на X ===
        report("⏳ Жду редирект на X...")
        final_url = None
        for i in range(20):
            time.sleep(3)
            url = session.driver.current_url
            final_url = url
            logger.info(f"Redirect wait [{i+1}/20]: {url}")
            report(f"  [{i+1}/20] {url[:70]}")
            
            if "x.com/home" in url:
                logger.info("Home page detected")
                report("✅ Домашняя страница!")
                break
            if "x.com" in url and "login" not in url and "flow" not in url and "onboarding" not in url:
                logger.info("X detected without login")
                report("✅ Вошли в X!")
                break
            
            # Проверяем, не попали ли на onboarding
            if "onboarding" in url:
                logger.info("Onboarding detected, trying to skip")
                report("🔀 Обнаружен onboarding, пропускаю...")
                try:
                    skip_btns = session.driver.find_elements(By.XPATH, 
                        "//span[contains(text(), 'Skip')] | //span[contains(text(), 'Next')] | //div[@role='button']")
                    for btn in skip_btns[:3]:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(2)
                except:
                    pass
        
        # === ШАГ 5: Получаем информацию о пользователе ===
        username = None
        display_name = None
        followers = None
        following = None
        
        try:
            logger.info("Navigating to /home for user info")
            session.driver.get("https://x.com/home")
            time.sleep(6)
            session._screenshot("home_for_info", "📸 Home для получения информации")
            session._save_html("home_for_info")
            
            html = session.driver.page_source
            logger.info(f"Home HTML length: {len(html)}")
            
            # Способ 1: Парсим JSON в HTML
            screen_name_match = re.search(r'"screen_name":"([^"]+)"', html)
            if screen_name_match:
                username = screen_name_match.group(1)
                logger.info(f"Found screen_name: @{username}")
                report(f"✅ Имя из HTML: @{username}")
            
            name_match = re.search(r'"name":"([^"]+)"', html)
            if name_match:
                display_name = name_match.group(1)
                logger.info(f"Found display_name: {display_name}")
                report(f"✅ Display name: {display_name}")
            
            followers_match = re.search(r'"followers_count":(\d+)', html)
            if followers_match:
                followers = int(followers_match.group(1))
                logger.info(f"Found followers: {followers}")
                report(f"✅ Подписчики: {followers}")
            
            following_match = re.search(r'"friends_count":(\d+)', html)
            if following_match:
                following = int(following_match.group(1))
                logger.info(f"Found following: {following}")
                report(f"✅ Подписки: {following}")
            
            # Способ 2: Из cookies
            if not username:
                try:
                    cookies = session.driver.get_cookies()
                    for cookie in cookies:
                        if "twid" in cookie.get("name", "").lower():
                            val = cookie.get("value", "")
                            if val.startswith("u%3D"):
                                username = val.replace("u%3D", "").replace("%40", "@")
                                logger.info(f"Found username from twid: @{username}")
                                report(f"✅ Имя из cookie: @{username}")
                                break
                except:
                    pass
            
            # Способ 3: Переходим на профиль
            if username:
                logger.info(f"Navigating to profile: @{username}")
                report(f"🔍 Перехожу на профиль @{username}...")
                session.driver.get(f"https://x.com/{username}")
                time.sleep(5)
                session._screenshot("profile_page", f"📸 Профиль @{username}")
                
                profile_html = session.driver.page_source
                
                if not followers:
                    f_match = re.search(r'"followers_count":(\d+)', profile_html)
                    if f_match:
                        followers = int(f_match.group(1))
                        report(f"✅ Подписчики из профиля: {followers}")
                
                if not following:
                    fr_match = re.search(r'"friends_count":(\d+)', profile_html)
                    if fr_match:
                        following = int(fr_match.group(1))
                        report(f"✅ Подписки из профиля: {following}")
        
        except Exception as e:
            logger.error(f"User info extraction failed: {e}", exc_info=True)
            report(f"⚠️ Не удалось получить информацию: {e}")
        
        # Финальная проверка
        session._screenshot("final_check", "📸 Финальная проверка")
        
        html = session.driver.page_source.lower()
        auth_confirmed = any(k in html for k in ["home", "following", "for you", "для вас", "главная", "logout", "sign out"])
        
        # Дополнительная проверка через URL
        current_url = session.driver.current_url
        url_auth = "x.com" in current_url and "login" not in current_url and "flow" not in current_url
        
        logger.info(f"Auth confirmed (HTML): {auth_confirmed}, (URL): {url_auth}")
        
        if auth_confirmed or url_auth:
            report("✅ Авторизация подтверждена!")
            session.save_cookies()
            
            extra = {}
            if display_name:
                extra["display_name"] = display_name
            if followers is not None:
                extra["followers"] = followers
            if following is not None:
                extra["following"] = following
            
            save_auth_info(username or "unknown", email, extra if extra else None)
            logger.info(f"Saved auth: username={username}, followers={followers}, following={following}")
            
            report(f"👤 @{username or 'unknown'} | 📧 {email}")
            if display_name:
                report(f"📝 {display_name}")
            if followers:
                report(f"👥 Подписчики: {followers}")
            if following:
                report(f"📌 Подписки: {following}")
            
            return True, None
        else:
            logger.error("Auth not confirmed")
            report_error("❌ Авторизация не подтверждена. Проверь скриншоты.")
            return False, "Не удалось войти"
            
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        report_error(f"❌ Ошибка: {str(e)[:300]}")
        return False, str(e)
    finally:
        logger.info("Closing browser session")
        session.quit()


# === AGENT_READY ===
def AGENT_READY():
    return _installer.ready


# === РЕГИСТРАЦИЯ КОМАНД ===
def register_selenium_bot(bot):
    print("[SE] Регистрация команд...", flush=True)
    
    @bot.message_handler(commands=["se_status"])
    def se_status(message):
        st = get_full_status()
        auth = st.get("auth_info")
        auth_line = f"👤 <code>@{auth['username']}</code>\\n" if auth else "👤 <i>не подключён</i>\\n"
        
        display_line = ""
        followers_line = ""
        following_line = ""
        if auth:
            if auth.get("display_name"):
                display_line = f"📝 <code>{auth['display_name']}</code>\\n"
            if auth.get("followers"):
                followers_line = f"👥 Подписчики: <code>{auth['followers']}</code>\\n"
            if auth.get("following"):
                following_line = f"📌 Подписки: <code>{auth['following']}</code>\\n"
        
        text = (
            "🚗 <b>Selenium X Agent</b>\\n\\n"
            f"{auth_line}"
            f"{display_line}"
            f"{followers_line}"
            f"{following_line}"
            f"{icon(st['chrome_browser']['found'])} Chrome: <code>{st['chrome_browser']['path'] or 'не найден'}</code>\\n"
            f"{icon(st['chromedriver']['ready'])} Driver: <code>{st['chromedriver']['path'] or 'не найден'}</code>\\n"
            f"{icon(st['selenium_pip']['installed'])} Selenium pip: {'установлен' if st['selenium_pip']['installed'] else 'не установлен'}\\n"
            f"{'🟢' if st['agent_ready'] else '🔴'} Готов: {'Да' if st['agent_ready'] else 'Нет'}\\n"
            f"🍪 Cookies: {'есть' if st['cookies_exist'] else 'нет'}\\n"
            f"📁 {st['selenium_dir']}"
        )
        if not st['agent_ready']:
            text += "\\n\\n⚠️ /se_install"
        elif not auth:
            text += "\\n\\n⚠️ /se_google — войти"
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def se_install(message):
        if _installer.ready:
            try:
                import selenium
                bot.reply_to(message, "🟢 Уже установлено!", parse_mode="HTML")
                return
            except ImportError:
                pass
        
        msg = bot.reply_to(message, "⏳ Скачиваю Chrome + Driver + Selenium...", parse_mode="HTML")
        success = _installer.install()
        
        if success:
            bot.edit_message_text(
                f"✅ Установлено!\\n🌐 <code>{_installer.chrome_path}</code>\\n🔧 <code>{_installer.driver_path}</code>",
                chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="HTML"
            )
        else:
            bot.edit_message_text(
                f"❌ Ошибка. Логи: <code>{LOG_FILE}</code>",
                chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="HTML"
            )
    
    @bot.message_handler(commands=["se_google"])
    def se_google(message):
        if not _installer.ready:
            bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
            return
        
        chat_id = message.chat.id
        bot.reply_to(message, "🔐 <b>Вход через Google</b>\\n\\nВведи <b>email</b> от Google:", parse_mode="HTML")
        login_sessions[chat_id] = {"step": "google_email", "method": "google"}
    
    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "google_email")
    def se_google_email(message):
        chat_id = message.chat.id
        email = message.text.strip()
        if email.startswith("/"):
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
            return
        
        login_sessions[chat_id]["email"] = email
        login_sessions[chat_id]["step"] = "google_password"
        bot.reply_to(message, f"✅ Email: <code>{email}</code>\\n\\nТеперь введи <b>пароль</b>:", parse_mode="HTML")
    
    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "google_password")
    def se_google_password(message):
        chat_id = message.chat.id
        password = message.text
        if password.startswith("/"):
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
            return
        
        email = login_sessions[chat_id]["email"]
        del login_sessions[chat_id]
        
        msg = bot.reply_to(message, "⏳ Вхожу через Google...\\n<i>60-90 сек</i>", parse_mode="HTML")
        
        success, error = run_sync_task(google_login, email, password, bot, chat_id)
        
        try:
            bot.delete_message(chat_id, msg.message_id)
        except:
            pass
        
        if error:
            bot.reply_to(message, f"❌ {error}", parse_mode="HTML")
            try:
                _send_log_file(bot, chat_id, prefix="❌ Ошибка входа")
            except:
                pass
        elif success:
            auth = get_auth_info()
            username = auth.get("username", "?") if auth else "?"
            display_name = auth.get("display_name", "")
            followers = auth.get("followers", "")
            following = auth.get("following", "")
            
            extra_lines = ""
            if display_name:
                extra_lines += f"\\n📝 <code>{display_name}</code>"
            if followers:
                extra_lines += f"\\n👥 Подписчики: <code>{followers}</code>"
            if following:
                extra_lines += f"\\n📌 Подписки: <code>{following}</code>"
            
            bot.reply_to(message, f"✅ <b>Вход успешен!</b>\\n👤 @{username}\\n📧 {email}{extra_lines}", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Вход не удался", parse_mode="HTML")
            try:
                _send_log_file(bot, chat_id, prefix="❌ Вход не удался")
            except:
                pass
    
    @bot.message_handler(commands=["se_log"])
    def se_log(message):
        try:
            _send_log_file(bot, message.chat.id, prefix="📄 Запрошены логи")
            bot.reply_to(message, "📄 Логи отправлены", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"❌ Не удалось отправить логи: {e}", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logout"])
    def se_logout(message):
        clear_auth_info()
        bot.reply_to(message, "🚪 Сессия очищена", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_help"])
    def se_help(message):
        bot.reply_to(message, (
            "🚗 <b>Selenium X Agent</b>\\n\\n"
            "/se_status — Статус\\n"
            "/se_install — Установить Chrome\\n"
            "/se_google — Войти через Google\\n"
            "/se_log — Получить логи\\n"
            "/se_logout — Выйти\\n"
            "/se_help — Помощь"
        ), parse_mode="HTML")
    
    @bot.message_handler(commands=["se_cancel"])
    def se_cancel(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
    
    print("[SE] Команды зарегистрированы", flush=True)


print(f"[SE] Модуль загружен. ready={_installer.ready}", flush=True)
'''

# Сохраняем исправленный скрипт
output_path = "/mnt/agents/output/selenium_x_agent_fixed.py"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(fixed_script)

print(f"✅ Исправленный скрипт сохранён: {output_path}")
print(f"📊 Размер: {len(fixed_script)} символов")