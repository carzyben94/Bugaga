# selenium_x_agent.py — Selenium X/Twitter агент с расширенным логированием
import os
import sys
import subprocess
import json
import re
import threading
import time
import tempfile
import urllib.request
import zipfile
import stat
import queue
import logging
import traceback
from datetime import datetime

# === НАСТРОЙКА ПУТЕЙ ===
if os.path.exists("/app") and os.access("/app", os.W_OK):
    SELENIUM_DIR = os.environ.get("SELENIUM_DIR", "/app/selenium_agent")
else:
    SELENIUM_DIR = os.environ.get("SELENIUM_DIR", os.path.join(tempfile.gettempdir(), "selenium_agent"))

os.makedirs(SELENIUM_DIR, exist_ok=True)

CHROME_DIR = os.path.join(SELENIUM_DIR, "chrome")
DRIVER_DIR = os.path.join(SELENIUM_DIR, "driver")
COOKIES_FILE = os.path.join(SELENIUM_DIR, "x_cookies.json")
AUTH_FILE = os.path.join(SELENIUM_DIR, "x_auth.json")
SCREENSHOT_DIR = os.path.join(SELENIUM_DIR, "screenshots")
LOG_FILE = os.path.join(SELENIUM_DIR, "debug.log")

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(CHROME_DIR, exist_ok=True)
os.makedirs(DRIVER_DIR, exist_ok=True)

# === НАСТРОЙКА ЛОГГЕРА ===
logger = logging.getLogger("SeleniumXAgent")
logger.setLevel(logging.DEBUG)

# Файловый обработчик
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Консольный обработчик
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

print(f"[SE] === INIT ===")
print(f"[SE] SELENIUM_DIR: {SELENIUM_DIR}")
print(f"[SE] AUTH_FILE: {AUTH_FILE}")
print(f"[SE] COOKIES_FILE: {COOKIES_FILE}")
print(f"[SE] LOG_FILE: {LOG_FILE}")

logger.info("="*60)
logger.info("SELENIUM X AGENT INITIALIZED")
logger.info(f"Time: {datetime.now().isoformat()}")
logger.info(f"SELENIUM_DIR: {SELENIUM_DIR}")
logger.info("="*60)

# === ГЛОБАЛЬНЫЕ ФЛАГИ ===
SELENIUM_INSTALLED = False
CHROME_BROWSER_READY = False
DRIVER_READY = False
AGENT_READY = False

# === Версии Chrome for Testing ===
CHROME_VERSION = "126.0.6478.126"
CHROME_DOWNLOAD_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64/chrome-linux64.zip"
DRIVER_DOWNLOAD_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64/chromedriver-linux64.zip"

# === Хранилище сессий авторизации ===
login_sessions = {}

# === Очередь для прогресса ===
progress_queue = queue.Queue()


def _run_subprocess(cmd, timeout=120, cwd=None):
    try:
        logger.debug(f"Running subprocess: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        success = result.returncode == 0
        logger.debug(f"Subprocess result: success={success}, stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)}")
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Subprocess timeout: {' '.join(cmd)}")
        return False, "", "Timeout"
    except Exception as e:
        logger.error(f"Subprocess error: {e}")
        return False, "", str(e)


def _download_file(url, dest):
    try:
        logger.info(f"Downloading: {url} -> {dest}")
        urllib.request.urlretrieve(url, dest)
        logger.info(f"Download complete: {dest} ({os.path.getsize(dest)} bytes)")
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


def _extract_zip(zip_path, dest_dir):
    try:
        logger.info(f"Extracting: {zip_path} -> {dest_dir}")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(dest_dir)
        logger.info(f"Extraction complete")
        return True
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return False


def _make_executable(path):
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC)
        logger.info(f"Made executable: {path}")
        return True
    except Exception as e:
        logger.error(f"Chmod error: {e}")
        return False


def check_selenium_pip():
    global SELENIUM_INSTALLED
    try:
        import selenium
        SELENIUM_INSTALLED = True
        logger.info(f"Selenium installed: v{selenium.__version__}")
        return True, selenium.__version__
    except ImportError:
        SELENIUM_INSTALLED = False
        logger.warning("Selenium not installed")
        return False, None


def install_selenium_pip():
    global SELENIUM_INSTALLED
    logger.info("Installing selenium via pip...")
    ok, _, err = _run_subprocess([sys.executable, "-m", "pip", "install", "selenium"], timeout=120)
    if not ok:
        logger.error(f"Pip install failed: {err}")
        return False
    
    import importlib
    if "selenium" in sys.modules:
        importlib.reload(sys.modules["selenium"])
    
    SELENIUM_INSTALLED = True
    logger.info("Selenium installed successfully")
    return True


def check_chrome_binary():
    global CHROME_BROWSER_READY
    chrome_path = os.path.join(CHROME_DIR, "chrome-linux64", "chrome")
    if os.path.exists(chrome_path):
        CHROME_BROWSER_READY = True
        logger.info(f"Chrome found at: {chrome_path}")
        return True, chrome_path
    
    for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
        ok, out, _ = _run_subprocess(["which", name], timeout=5)
        if ok and out.strip():
            CHROME_BROWSER_READY = True
            logger.info(f"Chrome found at: {out.strip()}")
            return True, out.strip()
    
    CHROME_BROWSER_READY = False
    logger.warning("Chrome not found")
    return False, None


def download_chrome_portable():
    global CHROME_BROWSER_READY
    logger.info("Downloading Chrome portable...")
    zip_path = os.path.join(SELENIUM_DIR, "chrome.zip")
    if not _download_file(CHROME_DOWNLOAD_URL, zip_path):
        return False
    if not _extract_zip(zip_path, CHROME_DIR):
        return False
    chrome_path = os.path.join(CHROME_DIR, "chrome-linux64", "chrome")
    if os.path.exists(chrome_path):
        _make_executable(chrome_path)
        CHROME_BROWSER_READY = True
        logger.info(f"Chrome ready: {chrome_path}")
        return True
    return False


def check_driver():
    global DRIVER_READY
    driver_path = os.path.join(DRIVER_DIR, "chromedriver-linux64", "chromedriver")
    if os.path.exists(driver_path):
        DRIVER_READY = True
        logger.info(f"ChromeDriver found at: {driver_path}")
        return True, driver_path
    
    ok, out, _ = _run_subprocess(["which", "chromedriver"], timeout=5)
    if ok and out.strip():
        DRIVER_READY = True
        logger.info(f"ChromeDriver found at: {out.strip()}")
        return True, out.strip()
    
    DRIVER_READY = False
    logger.warning("ChromeDriver not found")
    return False, None


def download_driver():
    global DRIVER_READY
    logger.info("Downloading ChromeDriver...")
    zip_path = os.path.join(SELENIUM_DIR, "driver.zip")
    if not _download_file(DRIVER_DOWNLOAD_URL, zip_path):
        return False
    if not _extract_zip(zip_path, DRIVER_DIR):
        return False
    driver_path = os.path.join(DRIVER_DIR, "chromedriver-linux64", "chromedriver")
    if os.path.exists(driver_path):
        _make_executable(driver_path)
        DRIVER_READY = True
        logger.info(f"ChromeDriver ready: {driver_path}")
        return True
    return False


def get_full_status():
    pip_ok, pip_ver = check_selenium_pip()
    browser_ok, browser_path = check_chrome_binary()
    driver_ok, driver_path = check_driver()
    global AGENT_READY
    AGENT_READY = pip_ok and browser_ok and driver_ok
    
    auth_info = get_auth_info()
    logger.debug(f"get_full_status: auth_info={auth_info}")
    
    return {
        "selenium_pip": {"installed": pip_ok, "version": pip_ver},
        "chrome_browser": {"found": browser_ok, "path": browser_path},
        "chromedriver": {"ready": driver_ok, "path": driver_path},
        "agent_ready": AGENT_READY,
        "cookies_exist": os.path.exists(COOKIES_FILE),
        "auth_info": auth_info,
        "selenium_dir": SELENIUM_DIR,
    }


def get_auth_info():
    """Получить информацию об авторизованном аккаунте"""
    logger.debug(f"get_auth_info: checking {AUTH_FILE}")
    if not os.path.exists(AUTH_FILE):
        logger.debug("AUTH_FILE does not exist")
        return None
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
        logger.debug(f"get_auth_info read: {data}")
        
        if not data.get("username"):
            logger.warning("get_auth_info: username is empty in file!")
            return None
        
        return data
    except Exception as e:
        logger.error(f"Error reading AUTH_FILE: {e}")
        return None


def save_auth_info(username, email=None, extra=None):
    """Сохранить информацию об авторизованном аккаунте — ГАРАНТИРОВАННО"""
    try:
        if not username or username == "unknown":
            logger.error("save_auth_info: CRITICAL ERROR — username is empty!")
            return False
        
        data = {
            "username": str(username),
            "email": email,
            "authorized_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            data.update(extra)
        
        logger.info(f"save_auth_info: writing username={username} to {AUTH_FILE}")
        logger.debug(f"save_auth_info: full data={data}")
        
        tmp_file = AUTH_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        os.replace(tmp_file, AUTH_FILE)
        
        if os.path.exists(AUTH_FILE):
            size = os.path.getsize(AUTH_FILE)
            logger.info(f"AUTH_FILE created, size: {size}")
            with open(AUTH_FILE, "r") as f:
                verify = json.load(f)
            logger.debug(f"Verification: verify={verify}")
            if verify.get("username") == username:
                logger.info("✅ Username matches!")
                return True
            else:
                logger.error(f"❌ Username mismatch! Expected {username}, got {verify.get('username')}")
                return False
        else:
            logger.error("CRITICAL ERROR: AUTH_FILE not created!")
            return False
    except Exception as e:
        logger.error(f"Auth save CRITICAL ERROR: {e}")
        traceback.print_exc()
        return False


def clear_auth_info():
    """Очистить информацию об авторизации"""
    try:
        if os.path.exists(AUTH_FILE):
            os.remove(AUTH_FILE)
            logger.info("AUTH_FILE deleted")
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            logger.info("COOKIES_FILE deleted")
        return True
    except Exception as e:
        logger.error(f"Clear auth error: {e}")
        return False


def full_install():
    global SELENIUM_INSTALLED, CHROME_BROWSER_READY, DRIVER_READY, AGENT_READY
    logger.info("Starting full installation...")
    
    if not SELENIUM_INSTALLED:
        if not install_selenium_pip():
            return False
    
    if not CHROME_BROWSER_READY:
        browser_ok, _ = check_chrome_binary()
        if not browser_ok:
            if not download_chrome_portable():
                check_chrome_binary()
    
    if not DRIVER_READY:
        driver_ok, _ = check_driver()
        if not driver_ok:
            if not download_driver():
                check_driver()
    
    AGENT_READY = SELENIUM_INSTALLED and CHROME_BROWSER_READY and DRIVER_READY
    logger.info(f"Full install completed: AGENT_READY={AGENT_READY}")
    return AGENT_READY


# === Selenium Agent ===

class SeleniumXAgent:
    def __init__(self):
        self.driver = None
        self._cookies_valid = False
        self._progress_callback = None
        logger.info("SeleniumXAgent initialized")
    
    def set_progress_callback(self, callback):
        self._progress_callback = callback
    
    def _report(self, step, message):
        print(f"[SE] [{step}] {message}")
        logger.info(f"[{step}] {message}")
        if self._progress_callback:
            try:
                self._progress_callback(step, message)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def _get_chrome_options(self):
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        options.add_argument("--lang=en-US")
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        browser_ok, browser_path = check_chrome_binary()
        if browser_ok and browser_path and "chrome-linux64" in browser_path:
            options.binary_location = browser_path
            logger.debug(f"Using Chrome binary: {browser_path}")
        return options
    
    def _create_driver(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        options = self._get_chrome_options()
        driver_ok, driver_path = check_driver()
        if driver_ok and driver_path:
            service = Service(driver_path)
            logger.debug(f"Using ChromeDriver: {driver_path}")
        else:
            service = Service()
            logger.warning("Using default ChromeDriver service")
        
        logger.info("Creating Chrome driver...")
        self.driver = webdriver.Chrome(service=service, options=options)
        logger.info(f"Chrome driver created. Session ID: {self.driver.session_id}")
        
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        logger.debug("CDP command executed")
        return self.driver
    
    def _screenshot(self, name):
        try:
            path = os.path.join(SCREENSHOT_DIR, f"{name}_{int(time.time())}.png")
            self.driver.save_screenshot(path)
            logger.info(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None
    
    def _load_cookies(self):
        if not os.path.exists(COOKIES_FILE):
            logger.warning(f"Cookies file not found: {COOKIES_FILE}")
            return False
        try:
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            logger.info(f"Loading {len(cookies)} cookies")
            for cookie in cookies:
                cookie.pop("sameSite", None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Failed to add cookie: {e}")
            logger.info("Cookies loaded")
            return True
        except Exception as e:
            logger.error(f"Cookie load error: {e}")
            return False
    
    def _save_cookies(self):
        try:
            if not self.driver:
                logger.error("No driver for saving cookies")
                return False
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            self._cookies_valid = True
            logger.info(f"Cookies saved: {len(cookies)} cookies to {COOKIES_FILE}")
            return True
        except Exception as e:
            logger.error(f"Cookie save error: {e}")
            return False
    
    def _smart_fill(self, selectors, value, field_name="поле"):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        for i, selector in enumerate(selectors):
            try:
                logger.debug(f"Trying to fill {field_name} with selector {i}: {selector}")
                elem = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if elem.is_displayed() and elem.is_enabled():
                    elem.clear()
                    elem.send_keys(value)
                    logger.info(f"Filled {field_name}: {selector}")
                    time.sleep(0.5)
                    return True
                else:
                    logger.debug(f"Element not displayed/enabled: {selector}")
            except Exception as e:
                logger.debug(f"Failed to fill {selector}: {e}")
                continue
        logger.warning(f"Could not fill {field_name} with any selector")
        return False
    
    def _smart_click(self, selectors, button_name="кнопка"):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        for i, selector in enumerate(selectors):
            try:
                logger.debug(f"Trying to click {button_name} with selector {i}: {selector}")
                elem = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                elem.click()
                logger.info(f"Clicked {button_name}: {selector}")
                time.sleep(0.5)
                return True
            except Exception as e:
                logger.debug(f"Failed to click {selector}: {e}")
                continue
        logger.warning(f"Could not click {button_name} with any selector")
        return False
    
    def login(self, username, password, email=None):
        """Авторизация с ГАРАНТИРОВАННЫМ сохранением username и ДЕТАЛЬНЫМ логированием"""
        
        logger.info("="*60)
        logger.info("START LOGIN")
        logger.info(f"Username: {username}")
        logger.info(f"Email provided: {bool(email)}")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info("="*60)
        
        target_username = username.strip().lstrip("@") if username else "unknown"
        logger.info(f"Target username normalized: {target_username}")
        
        # Детальная диагностика окружения
        logger.info(f"SELENIUM_DIR: {SELENIUM_DIR}")
        logger.info(f"CHROME_DIR: {CHROME_DIR}")
        logger.info(f"DRIVER_DIR: {DRIVER_DIR}")
        logger.info(f"COOKIES_FILE: {COOKIES_FILE}")
        logger.info(f"AUTH_FILE: {AUTH_FILE}")
        
        # Проверка прав на запись
        for path in [SELENIUM_DIR, CHROME_DIR, DRIVER_DIR, SCREENSHOT_DIR]:
            if os.path.exists(path):
                logger.info(f"Directory exists: {path}, writable: {os.access(path, os.W_OK)}")
            else:
                logger.warning(f"Directory does NOT exist: {path}")
        
        try:
            self._report("start", f"🚀 Начинаю авторизацию как @{target_username}")
            logger.info("Step 1: Starting browser...")
            
            self._report("browser", "🌐 Запускаю Chrome...")
            self._create_driver()
            logger.info(f"Browser started. Driver: {self.driver}")
            self._report("browser", "✅ Chrome запущен")
            
            self._report("page", "📄 Открываю страницу входа...")
            self.driver.get("https://x.com/i/flow/login")
            logger.info(f"Page loaded. Current URL: {self.driver.current_url}")
            logger.info(f"Page title: {self.driver.title}")
            logger.info(f"Page source length: {len(self.driver.page_source)}")
            
            # ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА СТРАНИЦЫ
            from selenium.webdriver.common.by import By
            
            # Проверяем наличие основных элементов на странице
            page_elements = {
                "login_form": self.driver.find_elements(By.CSS_SELECTOR, 'form[action*="login"]'),
                "username_field": self.driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="username"]'),
                "password_field": self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'),
                "login_button": self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]'),
            }
            
            for name, elements in page_elements.items():
                logger.info(f"Page elements - {name}: found {len(elements)}")
                if elements:
                    try:
                        logger.info(f"  First element: display={elements[0].is_displayed()}, enabled={elements[0].is_enabled()}")
                    except:
                        logger.info(f"  First element: could not check status")
            
            # Сохраняем HTML для анализа
            debug_html_path = os.path.join(SELENIUM_DIR, f"debug_login_page_{int(time.time())}.html")
            try:
                with open(debug_html_path, "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.info(f"Saved page HTML to: {debug_html_path}")
            except Exception as e:
                logger.error(f"Failed to save HTML: {e}")
            
            time.sleep(4)
            self._screenshot("login_start")
            logger.info(f"Screenshot saved: login_start")
            
            self._report("page", f"📄 Страница загружена: {self.driver.title}")
            
            # === ВВОД USERNAME ===
            self._report("username", "⌨️ Ввожу username...")
            username_selectors = [
                'input[autocomplete="username"]',
                'input[name="text"]',
                'input[type="text"]',
                'input[autocapitalize="none"]',
                'input[inputmode="text"]',
            ]
            
            logger.info(f"Looking for username field with selectors: {username_selectors}")
            username_found = False
            
            for i, selector in enumerate(username_selectors):
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        elem = elements[0]
                        if elem.is_displayed() and elem.is_enabled():
                            logger.info(f"Found username field with selector {i}: {selector}")
                            logger.info(f"  Tag: {elem.tag_name}, Type: {elem.get_attribute('type')}")
                            logger.info(f"  Display: {elem.is_displayed()}, Enabled: {elem.is_enabled()}")
                            username_found = True
                            break
                except Exception as e:
                    logger.warning(f"Error checking selector {selector}: {e}")
            
            if not username_found:
                logger.error("Username field NOT found on page!")
                # Ищем любые input поля
                all_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input")
                logger.info(f"All inputs on page: {len(all_inputs)}")
                for i, inp in enumerate(all_inputs[:5]):
                    try:
                        logger.info(f"  Input {i}: type={inp.get_attribute('type')}, name={inp.get_attribute('name')}")
                    except:
                        pass
            
            if not self._smart_fill(username_selectors, target_username, "username"):
                self._screenshot("login_no_username")
                error_msg = "❌ Поле username не найдено"
                logger.error(error_msg)
                return False, error_msg
            
            logger.info(f"Username entered: {target_username}")
            self._report("username", f"✅ Username введён: @{target_username}")
            
            time.sleep(1)
            
            # === НАЖАТИЕ NEXT ===
            self._report("next", "➡️ Нажимаю Next...")
            next_selectors = [
                'button[type="submit"]',
                'button:has-text("Next")',
                'button:has-text("Далее")',
                'div[role="button"]:has-text("Next")',
            ]
            
            logger.info("Attempting to click Next button...")
            next_clicked = self._smart_click(next_selectors, "Next")
            logger.info(f"Next clicked: {next_clicked}")
            
            time.sleep(3)
            self._screenshot("login_after_username")
            logger.info(f"After Next - URL: {self.driver.current_url}")
            logger.info(f"After Next - Title: {self.driver.title}")
            
            self._report("next", "✅ Перешли к следующему шагу")
            
            # === ПРОВЕРКА ВЕРИФИКАЦИИ ===
            self._report("verify", "🔍 Проверяю дополнительную верификацию...")
            verify_selectors = [
                'input[name="email"]',
                'input[name="phone"]',
                'input[data-testid="ocfEnterTextTextInput"]',
            ]
            
            verification_required = False
            for selector in verify_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem.is_displayed():
                        verification_required = True
                        logger.info(f"Verification field found: {selector}")
                        if email:
                            logger.info(f"Filling verification with email: {email}")
                            elem.clear()
                            elem.send_keys(email)
                            time.sleep(1)
                            self._smart_click(['button[type="submit"]'], "Next after verify")
                            time.sleep(3)
                            self._report("verify", "✅ Email принят")
                        else:
                            logger.warning("Verification required but NO email provided!")
                            return False, "❌ Требуется email/телефон для верификации"
                except Exception as e:
                    logger.debug(f"No verification field for {selector}: {e}")
            
            if not verification_required:
                logger.info("No verification required")
                self._report("verify", "✅ Дополнительной верификации нет")
            
            # === ВВОД ПАРОЛЯ ===
            self._report("password", "⌨️ Ввожу пароль...")
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
            ]
            
            logger.info("Looking for password field...")
            password_found = False
            for i, selector in enumerate(password_selectors):
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        elem = elements[0]
                        if elem.is_displayed() and elem.is_enabled():
                            logger.info(f"Found password field with selector {i}: {selector}")
                            password_found = True
                            break
                except Exception as e:
                    logger.warning(f"Error checking password selector {selector}: {e}")
            
            if not password_found:
                logger.error("Password field NOT found!")
                # Проверяем, не вернулись ли мы на username
                try:
                    username_field = self.driver.find_element(By.CSS_SELECTOR, 'input[autocomplete="username"]')
                    if username_field.is_displayed():
                        logger.error("Still on username step! Need to click Next again or different flow")
                except:
                    pass
            
            if not self._smart_fill(password_selectors, password, "password"):
                error_msg = "❌ Поле пароля не найдено"
                logger.error(error_msg)
                return False, error_msg
            
            logger.info("Password entered")
            self._report("password", "✅ Пароль введён")
            
            time.sleep(1)
            
            # === НАЖАТИЕ LOGIN ===
            self._report("submit", "🔓 Нажимаю Log in...")
            login_selectors = [
                'button[data-testid="LoginForm_Login_Button"]',
                'button:has-text("Log in")',
                'button:has-text("Войти")',
                'button[type="submit"]',
            ]
            
            logger.info("Attempting to click Login button...")
            login_clicked = self._smart_click(login_selectors, "Log in")
            logger.info(f"Login clicked: {login_clicked}")
            
            self._report("submit", "⏳ Жду ответа сервера...")
            
            # ОЖИДАНИЕ С ДИАГНОСТИКОЙ
            for i in range(10):
                time.sleep(1)
                current_url = self.driver.current_url
                logger.info(f"Wait {i+1}s: URL={current_url}")
                
                # Проверяем появление ошибок
                error_selectors = [
                    'span:has-text("Wrong password")',
                    'span:has-text("Incorrect")',
                    'span:has-text("неверный")',
                    '[role="alert"]',
                    '[data-testid="toast"]',
                ]
                
                for selector in error_selectors:
                    try:
                        err = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if err.is_displayed():
                            err_text = err.text
                            logger.error(f"Error found: {err_text}")
                            return False, f"❌ Ошибка входа: {err_text}"
                    except:
                        pass
                
                # Проверяем капчу
                try:
                    captcha = self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="captcha"], iframe[src*="recaptcha"]')
                    if captcha and len(captcha) > 0:
                        logger.warning("Captcha detected!")
                        return False, "❌ Обнаружена капча"
                except:
                    pass
            
            self._screenshot("login_after_submit")
            logger.info(f"After login attempt - URL: {self.driver.current_url}")
            logger.info(f"After login attempt - Title: {self.driver.title}")
            
            # === ПРОВЕРКА УСПЕШНОСТИ ===
            current_url = self.driver.current_url
            logger.info(f"Final URL: {current_url}")
            
            # Проверка на редирект на домашнюю страницу
            if "home" in current_url or current_url == "https://x.com/" or current_url == "https://x.com":
                logger.info("✅ SUCCESS: Redirected to home page!")
            else:
                logger.warning(f"⚠️ Not on home page. Current: {current_url}")
            
            # === ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: ЕСТЬ ЛИ ДОСТУП ===
            self._report("check", "🔍 Проверяю доступ к контенту...")
            
            # Пытаемся получить свою страницу
            self.driver.get(f"https://x.com/{target_username}")
            time.sleep(3)
            logger.info(f"Profile page URL: {self.driver.current_url}")
            logger.info(f"Profile page Title: {self.driver.title}")
            
            # Проверяем наличие контента
            try:
                tweets = self.driver.find_elements(By.CSS_SELECTOR, 'article')
                logger.info(f"Tweets found on profile: {len(tweets)}")
                
                if len(tweets) == 0:
                    logger.warning("⚠️ No tweets found on profile!")
                    
                    # Проверяем, не требует ли вход
                    login_btn = self.driver.find_elements(By.CSS_SELECTOR, 'a[href="/i/flow/login"]')
                    if login_btn:
                        logger.error("❌ Login button is visible - session NOT working!")
                        return False, "❌ Сессия не работает: профиль требует входа"
                    
                    # Проверяем наличие ошибок
                    error_msg = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="emptyState"]')
                    if error_msg:
                        try:
                            logger.error(f"Empty state found: {error_msg[0].text}")
                        except:
                            pass
            except Exception as e:
                logger.error(f"Error checking profile: {e}")
            
            # === СОХРАНЕНИЕ ===
            self._report("save", "💾 Сохраняю cookies...")
            cookie_ok = self._save_cookies()
            logger.info(f"Cookies saved: {cookie_ok}")
            
            if cookie_ok:
                cookies = self.driver.get_cookies()
                logger.info(f"Number of cookies: {len(cookies)}")
                for i, cookie in enumerate(cookies[:5]):
                    logger.info(f"  Cookie {i}: {cookie.get('name')} - domain: {cookie.get('domain')}")
            
            # === СОХРАНЕНИЕ AUTH ===
            self._report("save_auth", f"💾 Сохраняю auth info для @{target_username}...")
            auth_data = {
                "following_count": None,
                "followers_count": None,
                "profile_title": self.driver.title,
                "home_url": current_url,
                "debug_url": self.driver.current_url,
            }
            
            # Пытаемся получить статистику
            try:
                stats = self.driver.find_elements(By.CSS_SELECTOR, 'a[href$="/following"] span span')
                for stat in stats:
                    if any(c.isdigit() for c in stat.text):
                        auth_data["following_count"] = stat.text
                        break
            except Exception as e:
                logger.warning(f"Could not get following count: {e}")
            
            try:
                stats = self.driver.find_elements(By.CSS_SELECTOR, 'a[href$="/followers"] span span')
                for stat in stats:
                    if any(c.isdigit() for c in stat.text):
                        auth_data["followers_count"] = stat.text
                        break
            except Exception as e:
                logger.warning(f"Could not get followers count: {e}")
            
            auth_saved = save_auth_info(target_username, email, auth_data)
            logger.info(f"Auth info saved: {auth_saved}")
            
            # === ФИНАЛЬНАЯ ПРОВЕРКА ===
            verify_auth = get_auth_info()
            logger.info(f"VERIFICATION - auth_info: {verify_auth}")
            
            if verify_auth and verify_auth.get("username") == target_username:
                logger.info("✅ SUCCESS - auth info verified!")
                self._report("done", "✅ Авторизация завершена и подтверждена!")
                return True, None
            else:
                logger.error(f"❌ FAILED - username mismatch. Expected: {target_username}, Got: {verify_auth}")
                # Сохраняем еще раз
                save_auth_info(target_username, email, auth_data)
                # Считаем успешным, если cookies сохранены
                if cookie_ok:
                    logger.warning("Cookies saved but auth file issue. Returning success.")
                    return True, None
                return False, "❌ Ошибка сохранения данных"
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR: {e}")
            logger.error(traceback.format_exc())
            self._screenshot("login_exception")
            return False, f"💥 Ошибка авторизации: {e}"
        finally:
            if self.driver:
                logger.info("Closing driver...")
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
                logger.info("Driver closed")
            logger.info("="*60)
            logger.info("END LOGIN")
            logger.info("="*60)
    
    def fetch_timeline(self, username=None, limit=10):
        if not AGENT_READY:
            logger.warning("fetch_timeline: Agent not ready")
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            logger.warning("fetch_timeline: Not authorized")
            return None, "Не авторизован. Сначала /se_login"
        
        logger.info(f"fetch_timeline: username={username}, limit={limit}")
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                logger.warning("fetch_timeline: Could not load cookies")
                return None, "Не удалось загрузить cookies. Авторизуйся заново: /se_login"
            
            url = f"https://x.com/{username}" if username else "https://x.com/home"
            logger.info(f"fetch_timeline: Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)
            
            from selenium.webdriver.common.by import By
            
            current_url = self.driver.current_url
            logger.info(f"fetch_timeline: Current URL: {current_url}")
            if "login" in current_url:
                logger.warning("fetch_timeline: Redirected to login")
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            tweets = []
            last_count = 0
            attempts = 0
            
            while len(tweets) < limit and attempts < 10:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                logger.debug(f"fetch_timeline: Found {len(articles)} articles")
                for article in articles:
                    try:
                        text = article.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
                        user = article.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]').text
                        time_elem = article.find_element(By.CSS_SELECTOR, "time")
                        dt = time_elem.get_attribute("datetime")
                        link = article.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                        url = f"https://x.com{link.get_attribute('href')}"
                        tweet = {
                            "text": text,
                            "author": user.split("\n")[0] if "\n" in user else user,
                            "handle": user.split("\n")[1] if "\n" in user else "",
                            "time": dt,
                            "url": url,
                        }
                        if tweet not in tweets:
                            tweets.append(tweet)
                    except Exception as e:
                        logger.debug(f"fetch_timeline: Error parsing tweet: {e}")
                
                if len(tweets) == last_count:
                    attempts += 1
                else:
                    attempts = 0
                    last_count = len(tweets)
                
                self.driver.execute_script("window.scrollBy(0, 800)")
                time.sleep(1)
            
            self._save_cookies()
            logger.info(f"fetch_timeline: Retrieved {len(tweets)} tweets")
            return tweets[:limit], None
            
        except Exception as e:
            logger.error(f"fetch_timeline error: {e}")
            logger.error(traceback.format_exc())
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def fetch_trends(self, limit=10):
        if not AGENT_READY:
            logger.warning("fetch_trends: Agent not ready")
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            logger.warning("fetch_trends: Not authorized")
            return None, "Не авторизован. Сначала /se_login"
        
        logger.info(f"fetch_trends: limit={limit}")
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                logger.warning("fetch_trends: Could not load cookies")
                return None, "Не удалось загрузить cookies"
            
            self.driver.get("https://x.com/explore/tabs/trending")
            time.sleep(4)
            
            from selenium.webdriver.common.by import By
            
            current_url = self.driver.current_url
            logger.info(f"fetch_trends: Current URL: {current_url}")
            if "login" in current_url:
                logger.warning("fetch_trends: Redirected to login")
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            trends = []
            attempts = 0
            
            while len(trends) < limit and attempts < 5:
                trend_selectors = [
                    '[data-testid="trend"]',
                    '[href*="/search?q="]',
                    'div[dir="ltr"] a[href^="/search"]',
                ]
                for selector in trend_selectors:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elems:
                        try:
                            text = elem.text or elem.get_attribute("aria-label") or ""
                            href = elem.get_attribute("href") or ""
                            if text and "search" in href and text not in [t["text"] for t in trends]:
                                trends.append({
                                    "text": text,
                                    "url": href if href.startswith("http") else f"https://x.com{href}",
                                })
                                if len(trends) >= limit:
                                    break
                        except Exception as e:
                            logger.debug(f"fetch_trends: Error parsing trend: {e}")
                    if len(trends) >= limit:
                        break
                
                if len(trends) == 0:
                    attempts += 1
                else:
                    attempts = 0
                
                self.driver.execute_script("window.scrollBy(0, 600)")
                time.sleep(1)
            
            self._save_cookies()
            logger.info(f"fetch_trends: Retrieved {len(trends)} trends")
            return trends[:limit], None
            
        except Exception as e:
            logger.error(f"fetch_trends error: {e}")
            logger.error(traceback.format_exc())
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def search(self, query, limit=10):
        if not AGENT_READY:
            logger.warning("search: Agent not ready")
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            logger.warning("search: Not authorized")
            return None, "Не авторизован. Сначала /se_login"
        
        logger.info(f"search: query={query}, limit={limit}")
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                logger.warning("search: Could not load cookies")
                return None, "Не удалось загрузить cookies"
            
            encoded = query.replace(" ", "%20")
            url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
            logger.info(f"search: Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)
            
            from selenium.webdriver.common.by import By
            
            current_url = self.driver.current_url
            logger.info(f"search: Current URL: {current_url}")
            if "login" in current_url:
                logger.warning("search: Redirected to login")
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            tweets = []
            attempts = 0
            
            while len(tweets) < limit and attempts < 8:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                logger.debug(f"search: Found {len(articles)} articles")
                for article in articles:
                    try:
                        text = article.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
                        user = article.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]').text
                        time_elem = article.find_element(By.CSS_SELECTOR, "time")
                        dt = time_elem.get_attribute("datetime")
                        link = article.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                        url = f"https://x.com{link.get_attribute('href')}"
                        tweet = {
                            "text": text,
                            "author": user.split("\n")[0] if "\n" in user else user,
                            "handle": user.split("\n")[1] if "\n" in user else "",
                            "time": dt,
                            "url": url,
                        }
                        if tweet not in tweets:
                            tweets.append(tweet)
                    except Exception as e:
                        logger.debug(f"search: Error parsing tweet: {e}")
                
                if len(tweets) == 0:
                    attempts += 1
                
                self.driver.execute_script("window.scrollBy(0, 1000)")
                time.sleep(1.5)
            
            self._save_cookies()
            logger.info(f"search: Retrieved {len(tweets)} tweets")
            return tweets[:limit], None
            
        except Exception as e:
            logger.error(f"search error: {e}")
            logger.error(traceback.format_exc())
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def check_current_auth(self):
        """Проверить сессию через открытие home"""
        logger.info("check_current_auth: Starting")
        
        if not os.path.exists(COOKIES_FILE):
            logger.warning("check_current_auth: No cookies file")
            return False, "Нет cookies файла"
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                logger.warning("check_current_auth: Could not load cookies")
                return False, "Не удалось загрузить cookies"
            
            self.driver.get("https://x.com/home")
            time.sleep(3)
            
            from selenium.webdriver.common.by import By
            
            current_url = self.driver.current_url
            logger.info(f"check_current_auth: Current URL: {current_url}")
            if "home" not in current_url:
                self._screenshot("auth_check_not_home")
                return False, f"Не на домашней странице: {current_url}"
            
            try:
                self.driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
                logger.info("check_current_auth: primaryColumn found")
            except:
                logger.warning("check_current_auth: primaryColumn not found")
                return False, "Лента не найдена"
            
            try:
                login_btn = self.driver.find_element(By.CSS_SELECTOR, 'a[href="/i/flow/login"]')
                if login_btn.is_displayed():
                    logger.warning("check_current_auth: Login button is visible")
                    return False, "Кнопка входа видна — сессия истекла"
            except:
                pass
            
            self._save_cookies()
            logger.info("check_current_auth: Session is valid")
            return True, "Сессия активна"
            
        except Exception as e:
            logger.error(f"check_current_auth error: {e}")
            logger.error(traceback.format_exc())
            return False, f"Ошибка проверки: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None


se_agent = SeleniumXAgent()


def run_sync_task(func, *args, **kwargs):
    result = [None, None]
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            result[1] = str(e)
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=120)
    if t.is_alive():
        return None, "Таймаут (120 сек)"
    if result[1]:
        return None, result[1]
    return result[0], None


# === РЕГИСТРАЦИЯ КОМАНД БОТА ===

def register_selenium_bot(bot):
    print("[SE] === REGISTER SELENIUM BOT ===")
    logger.info("Registering Selenium bot commands")
    
    @bot.message_handler(commands=["se_status"])
    def se_status_command(message):
        status = get_full_status()
        auth = status.get("auth_info")
        
        def icon(flag):
            return "✅" if flag else "❌"
        
        if auth:
            extra = auth.get("following_count") or auth.get("followers_count")
            extra_line = ""
            if extra:
                extra_line = f"   📊 Подписок: {auth.get('following_count', '?')}\n"
                extra_line += f"   📊 Подписчиков: {auth.get('followers_count', '?')}\n"
            
            auth_status = (
                f"👤 <b>Аккаунт:</b> <code>@{auth['username']}</code>\n"
                f"🕐 <b>Авторизован:</b> {auth['authorized_at']}\n"
                f"{extra_line}"
            )
        else:
            auth_status = "👤 <b>Аккаунт:</b> <i>не подключён</i>\n"
        
        msg = (
            "🚗 <b>Selenium X Agent — Статус</b>\n\n"
            f"{auth_status}\n"
            f"{icon(status['selenium_pip']['installed'])} <b>Selenium pip:</b> "
            f"{'v' + status['selenium_pip']['version'] if status['selenium_pip']['version'] else 'не установлен'}\n"
            f"{icon(status['chrome_browser']['found'])} <b>Chrome браузер:</b> "
            f"<code>{status['chrome_browser']['path'] or 'не найден'}</code>\n"
            f"{icon(status['chromedriver']['ready'])} <b>ChromeDriver:</b> "
            f"<code>{status['chromedriver']['path'] or 'не готов'}</code>\n\n"
            f"{'🟢' if status['agent_ready'] else '🔴'} <b>Agent готов:</b> "
            f"{'Да' if status['agent_ready'] else 'Нет'}\n"
            f"🍪 <b>Cookies:</b> {'есть' if status['cookies_exist'] else 'нет'}\n"
            f"📁 <b>Директория:</b> <code>{status['selenium_dir']}</code>\n\n"
        )
        
        if not status['agent_ready']:
            msg += "⚠️ Нажми /se_install для установки\n"
        elif not auth:
            msg += "⚠️ Авторизуйся: /se_login\n"
        else:
            msg += "✅ Готов! Используй команды ниже ⬇️"
        
        bot.reply_to(message, msg, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logs"])
    def se_logs_command(message):
        """Показать последние логи авторизации"""
        log_file = LOG_FILE
        
        if not os.path.exists(log_file):
            bot.reply_to(message, "❌ Лог-файл не найден")
            return
        
        try:
            # Читаем последние 100 строк
            with open(log_file, "r", encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
            
            log_text = "".join(last_lines)
            
            # Если слишком длинно, отправляем файлом
            if len(log_text) > 4000:
                with open(log_file, "rb") as f:
                    bot.send_document(message.chat.id, f, caption="📋 Логи авторизации")
            else:
                bot.reply_to(message, f"📋 <b>Последние логи</b>\n\n<code>{log_text}</code>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"se_logs error: {e}")
            bot.reply_to(message, f"❌ Ошибка чтения логов: {e}")
    
    @bot.message_handler(commands=["se_check_auth"])
    def se_check_auth_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install", parse_mode="HTML")
            return
        
        auth = get_auth_info()
        logger.debug(f"se_check_auth: auth from file={auth}")
        
        if not auth:
            bot.reply_to(message, "❌ Нет данных об авторизации. Сначала /se_login", parse_mode="HTML")
            return
        
        username = auth.get("username", "?")
        logger.info(f"se_check_auth: Checking auth for @{username}")
        
        bot.reply_to(message, f"🔍 Проверяю сессию для @{username}...", parse_mode="HTML")
        valid, msg = run_sync_task(se_agent.check_current_auth)
        
        if valid:
            bot.reply_to(message, 
                f"✅ <b>Сессия активна</b>\n"
                f"👤 @{username}\n"
                f"📊 Подписок: {auth.get('following_count', '?')}\n"
                f"📊 Подписчиков: {auth.get('followers_count', '?')}\n\n"
                f"Можно пользоваться командами.",
                parse_mode="HTML"
            )
        else:
            bot.reply_to(message, 
                f"❌ <b>Сессия недействительна</b>\n"
                f"{msg}\n\n"
                f"Авторизуйся: /se_login",
                parse_mode="HTML"
            )
    
    @bot.message_handler(commands=["se_logout"])
    def se_logout_command(message):
        clear_auth_info()
        bot.reply_to(message, "🚪 <b>Сессия очищена</b>\nCookies и данные авторизации удалены.\nТеперь можно авторизоваться заново: /se_login", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def se_install_command(message):
        bot.reply_to(message, "⏳ Начинаю установку Selenium...\n<i>Это может занять 1-2 минуты</i>", parse_mode="HTML")
        success = full_install()
        status = get_full_status()
        
        if success:
            bot.reply_to(message,
                "✅ <b>Selenium установлен!</b>\n\n"
                f"📦 pip: v{status['selenium_pip']['version']}\n"
                f"🌐 Chrome: <code>{status['chrome_browser']['path']}</code>\n"
                f"🚗 Driver: <code>{status['chromedriver']['path']}</code>\n\n"
                "Теперь /se_login",
                parse_mode="HTML"
            )
        else:
            msg = (
                "❌ <b>Установка не завершена</b>\n\n"
                f"pip: {'✅' if status['selenium_pip']['installed'] else '❌'}\n"
                f"Chrome: {'✅' if status['chrome_browser']['found'] else '❌'}\n"
                f"Driver: {'✅' if status['chromedriver']['ready'] else '❌'}\n\n"
                "💡 Попробуй ещё раз: /se_install"
            )
            bot.reply_to(message, msg, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_login"])
    def se_login_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. Сначала /se_install", parse_mode="HTML")
            return
        
        auth = get_auth_info()
        if auth:
            bot.reply_to(message,
                f"⚠️ Уже авторизован как <code>@{auth['username']}</code>\n\n"
                f"📊 Подписок: {auth.get('following_count', '?')}\n"
                f"🕐 Авторизован: {auth['authorized_at']}\n\n"
                f"Используй /se_logout чтобы сменить аккаунт\n"
                f"Или /se_check_auth чтобы проверить сессию",
                parse_mode="HTML"
            )
            return
        
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
        
        bot.reply_to(message,
            "🔐 <b>Авторизация в X (Selenium)</b>\n\n"
            "Введи <b>username</b> (без @):",
            parse_mode="HTML"
        )
        login_sessions[chat_id] = {"step": "username", "method": "selenium"}
        logger.info(f"Login dialog started for chat {chat_id}")
    
    @bot.message_handler(commands=["se_timeline"])
    def se_timeline_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install")
            return
        
        auth = get_auth_info()
        if not auth:
            bot.reply_to(message, "❌ Не авторизован. Сначала /se_login", parse_mode="HTML")
            return
        
        args = message.text.split()
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        target = f"@{username}" if username else f"@{auth['username']} (Home)"
        bot.reply_to(message, f"🐦 Загружаю ленту {target}...")
        
        tweets, error = run_sync_task(se_agent.fetch_timeline, username, limit)
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not tweets:
            bot.reply_to(message, "📭 Твиты не найдены")
            return
        
        lines = [f"🐦 <b>{target}</b>\n"]
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:180]
            if len(t.get("text", "")) > 180:
                text += "..."
            lines.append(
                f"{i}. <b>{t.get('author', '')}</b> <code>{t.get('handle', '')}</code>\n"
                f"   <i>{text}</i>\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n<i>...обрезано</i>"
        bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)
    
    @bot.message_handler(commands=["se_trends"])
    def se_trends_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install")
            return
        
        auth = get_auth_info()
        if not auth:
            bot.reply_to(message, "❌ Не авторизован. Сначала /se_login", parse_mode="HTML")
            return
        
        limit = 10
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            limit = int(args[1])
        
        bot.reply_to(message, "📈 Загружаю тренды...")
        
        trends, error = run_sync_task(se_agent.fetch_trends, limit)
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not trends:
            bot.reply_to(message, "📭 Тренды не найдены")
            return
        
        lines = ["📈 <b>Тренды X</b>\n"]
        for i, t in enumerate(trends, 1):
            text = t.get("text", "")[:100]
            lines.append(f"{i}. <a href='{t.get('url', '')}'>{text}</a>")
        
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n<i>...обрезано</i>"
        bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)
    
    @bot.message_handler(commands=["se_search"])
    def se_search_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install")
            return
        
        auth = get_auth_info()
        if not auth:
            bot.reply_to(message, "❌ Не авторизован. Сначала /se_login", parse_mode="HTML")
            return
        
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи запрос: <code>/se_search python</code>", parse_mode="HTML")
            return
        
        query = args[1]
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🔍 Ищу: <i>{query}</i>...", parse_mode="HTML")
        
        tweets, error = run_sync_task(se_agent.search, query, limit)
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not tweets:
            bot.reply_to(message, "📭 Ничего не найдено")
            return
        
        lines = [f"🔍 <b>{query}</b>\n"]
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:160]
            if len(t.get("text", "")) > 160:
                text += "..."
            lines.append(
                f"{i}. <b>{t.get('author', '')}</b> <code>{t.get('handle', '')}</code>\n"
                f"   <i>{text}</i>\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    
    @bot.message_handler(commands=["se_screenshot"])
    def se_screenshot_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install")
            return
        
        auth = get_auth_info()
        if not auth:
            bot.reply_to(message, "❌ Не авторизован. Сначала /se_login", parse_mode="HTML")
            return
        
        args = message.text.split()
        url = args[1] if len(args) > 1 else "https://x.com/home"
        
        bot.reply_to(message, f"📸 Делаю скриншот {url}...")
        
        def take_screenshot():
            se_agent._create_driver()
            se_agent._load_cookies()
            se_agent.driver.get(url)
            time.sleep(3)
            path = se_agent._screenshot("manual")
            se_agent.driver.quit()
            se_agent.driver = None
            return path
        
        path, error = run_sync_task(take_screenshot)
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        try:
            with open(path, "rb") as f:
                bot.send_photo(message.chat.id, f, caption=f"📸 {url}")
        except Exception as e:
            bot.reply_to(message, f"❌ Не удалось отправить скриншот: {e}")
    
    @bot.message_handler(commands=["se_help"])
    def se_help_command(message):
        auth = get_auth_info()
        if auth:
            auth_line = f"👤 Аккаунт: <code>@{auth['username']}</code>\n"
            auth_line += f"   📊 Подписок: {auth.get('following_count', '?')}\n"
            auth_line += f"   🕐 Авторизован: {auth['authorized_at']}\n"
        else:
            auth_line = "👤 Аккаунт: <i>не подключён</i>\n"
        
        msg = (
            "🚗 <b>Selenium X Agent</b>\n\n"
            f"{auth_line}\n"
            "🔧 <b>Настройка</b>\n"
            "  /se_status — Полный статус системы\n"
            "  /se_install — Установить Selenium + Chrome + Driver\n"
            "  /se_check_auth — Проверить сессию\n"
            "  /se_logout — Выйти и очистить сессию\n\n"
            "📋 <b>Диагностика</b>\n"
            "  /se_logs — Показать логи авторизации\n\n"
            "🔐 <b>Авторизация</b>\n"
            "  /se_login — Войти в X\n\n"
            "📰 <b>Контент</b>\n"
            "  /se_timeline [user] [N] — Лента (своя или чужая)\n"
            "  /se_trends [N] — 🔥 Тренды X\n"
            "  /se_search [запрос] [N] — Поиск твитов\n"
            "  /se_screenshot [url] — Скриншот страницы\n\n"
            "⚠️ <b>Особенности:</b>\n"
            "• Chrome скачивается автоматически (~150MB)\n"
            "• Работает без apt-get на Render\n"
            "• Cookies сохраняются между сессиями\n"
            "• Полное логирование в debug.log"
        )
        bot.reply_to(message, msg, parse_mode="HTML")
    
    # === ДИАЛОГ АВТОРИЗАЦИИ ===
    
    def is_se_login_dialog(chat_id, step):
        if chat_id not in login_sessions:
            return False
        session = login_sessions[chat_id]
        if session.get("method") != "selenium":
            return False
        if session.get("step") != step:
            return False
        return True
    
    @bot.message_handler(func=lambda m: is_se_login_dialog(m.chat.id, "username"))
    def se_login_username(message):
        chat_id = message.chat.id
        text = message.text.strip()
        
        if text.startswith("/"):
            if text.lower() == "/se_cancel":
                del login_sessions[chat_id]
                bot.reply_to(message, "❌ Ввод отменён")
                return
            return
        
        username = text.lstrip("@")
        if not username:
            bot.reply_to(message, "❌ Username не может быть пустым. Введи username или /se_cancel")
            return
        
        login_sessions[chat_id]["username"] = username
        login_sessions[chat_id]["step"] = "password"
        bot.reply_to(message,
            f"✅ Username: <code>{username}</code>\n\n"
            f"Теперь введи <b>пароль</b>:",
            parse_mode="HTML"
        )
    
    @bot.message_handler(func=lambda m: is_se_login_dialog(m.chat.id, "password"))
    def se_login_password(message):
        chat_id = message.chat.id
        text = message.text
        
        if text.startswith("/"):
            if text.lower() == "/se_cancel":
                del login_sessions[chat_id]
                bot.reply_to(message, "❌ Ввод отменён")
                return
            return
        
        login_sessions[chat_id]["password"] = text
        login_sessions[chat_id]["step"] = "email"
        bot.reply_to(message,
            "✅ Пароль получен\n\n"
            "Если нужен email для верификации — введи сейчас.\n"
            "Или отправь <code>skip</code>:",
            parse_mode="HTML"
        )
    
    @bot.message_handler(func=lambda m: is_se_login_dialog(m.chat.id, "email"))
    def se_login_email(message):
        chat_id = message.chat.id
        text = message.text.strip()
        
        if text.startswith("/"):
            if text.lower() == "/se_cancel":
                del login_sessions[chat_id]
                bot.reply_to(message, "❌ Ввод отменён")
                return
            return
        
        email = None if text.lower() == "skip" else text
        creds = login_sessions[chat_id]
        username = creds["username"]
        password = creds["password"]
        
        try:
            bot.delete_message(chat_id, message.message_id - 1)
            bot.delete_message(chat_id, message.message_id)
        except:
            pass
        
        progress_msg = bot.send_message(chat_id,
            f"🔐 <b>Авторизация @{username}</b>\n\n"
            f"⏳ Подготовка...",
            parse_mode="HTML"
        )
        
        progress_q = queue.Queue()
        
        def update_progress(step, msg_text):
            progress_q.put((step, msg_text))
        
        def progress_worker():
            last_text = ""
            while True:
                try:
                    step, msg_text = progress_q.get(timeout=0.5)
                    if step == "done":
                        break
                    new_text = (
                        f"🔐 <b>Авторизация @{username}</b>\n\n"
                        f"{msg_text}\n\n"
                        f"<i>Шаг: {step}</i>"
                    )
                    if new_text != last_text:
                        try:
                            bot.edit_message_text(
                                new_text,
                                chat_id=chat_id,
                                message_id=progress_msg.message_id,
                                parse_mode="HTML"
                            )
                            last_text = new_text
                        except Exception as e:
                            logger.error(f"Progress edit error: {e}")
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Progress worker error: {e}")
        
        progress_thread = threading.Thread(target=progress_worker)
        progress_thread.start()
        
        se_agent.set_progress_callback(update_progress)
        
        def do_login():
            result = se_agent.login(username, password, email)
            progress_q.put(("done", ""))
            return result
        
        success, error = run_sync_task(do_login)
        progress_thread.join(timeout=5)
        se_agent.set_progress_callback(None)
        del login_sessions[chat_id]
        
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        
        auth_after = get_auth_info()
        logger.info(f"After login auth_info: {auth_after}")
        
        if error:
            bot.reply_to(message, f"❌ {error}")
        elif success and auth_after and auth_after.get("username") == username:
            msg = (
                f"✅ <b>Авторизация УСПЕШНА!</b>\n\n"
                f"👤 Аккаунт: <code>@{auth_after['username']}</code>\n"
                f"🕐 Время: {auth_after['authorized_at']}\n"
            )
            if auth_after.get('following_count'):
                msg += f"📊 Подписок: {auth_after['following_count']}\n"
            if auth_after.get('followers_count'):
                msg += f"📊 Подписчиков: {auth_after['followers_count']}\n"
            
            msg += (
                f"\n"
                f"Теперь можно использовать:\n"
                f"/se_timeline — лента\n"
                f"/se_trends — тренды\n"
                f"/se_search — поиск"
            )
            bot.reply_to(message, msg, parse_mode="HTML")
        elif success and auth_after:
            bot.reply_to(message, 
                f"⚠️ <b>Авторизация прошла, но username не совпадает!</b>\n"
                f"Ожидалось: @{username}\n"
                f"Сохранено: @{auth_after.get('username', '?')}\n\n"
                f"Попробуй /se_check_auth",
                parse_mode="HTML"
            )
        elif success and not auth_after:
            bot.reply_to(message, 
                "⚠️ <b>Авторизация прошла, но данные НЕ сохранились!</b>\n"
                "Попробуй /se_check_auth\n"
                "Или /se_login ещё раз.\n\n"
                "💡 Возможно, проблема с правами на диск. Проверь /se_status",
                parse_mode="HTML"
            )
        else:
            bot.reply_to(message, "❌ Авторизация не удалась")
    
    @bot.message_handler(commands=["se_cancel"])
    def se_cancel_command(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Ввод отменён")
        else:
            bot.reply_to(message, "Нет активного ввода")
    
    logger.info("Selenium bot commands registered")
    print("[SE] === REGISTER END ===")


# === ИНИЦИАЛИЗАЦИЯ ===
check_selenium_pip()
check_chrome_binary()
check_driver()

logger.info("Selenium X Agent initialization complete")