# selenium_x_agent.py — Полный агент с мониторингом, логированием и запросами в чат
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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
HTML_DIR = os.path.join(SELENIUM_DIR, "html_pages")

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(CHROME_DIR, exist_ok=True)
os.makedirs(DRIVER_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

# === НАСТРОЙКА ЛОГГЕРА ===
logger = logging.getLogger("SeleniumXAgent")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

print(f"[SE] === INIT ===")
print(f"[SE] SELENIUM_DIR: {SELENIUM_DIR}")
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
progress_queue = queue.Queue()


def _run_subprocess(cmd, timeout=120, cwd=None):
    try:
        logger.debug(f"Running subprocess: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        success = result.returncode == 0
        logger.debug(f"Subprocess result: success={success}")
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
        
        tmp_file = AUTH_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        os.replace(tmp_file, AUTH_FILE)
        
        if os.path.exists(AUTH_FILE):
            with open(AUTH_FILE, "r") as f:
                verify = json.load(f)
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


def run_sync_task(func, *args, **kwargs):
    result = [None, None]
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            result[1] = str(e)
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=180)
    if t.is_alive():
        return None, "Таймаут (180 сек)"
    if result[1]:
        return None, result[1]
    return result[0], None


# === Selenium Agent с мониторингом ===

class SeleniumXAgent:
    def __init__(self):
        self.driver = None
        self._cookies_valid = False
        self._progress_callback = None
        self._user_input_callbacks = {}
        logger.info("SeleniumXAgent initialized")
    
    def set_progress_callback(self, callback):
        self._progress_callback = callback
    
    def set_user_input_callback(self, input_type, callback):
        self._user_input_callbacks[input_type] = callback
        logger.info(f"User input callback set for: {input_type}")
    
    def _report(self, step, message):
        print(f"[SE] [{step}] {message}")
        logger.info(f"[{step}] {message}")
        if self._progress_callback:
            try:
                self._progress_callback(step, message)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def _request_user_input(self, input_type, prompt, timeout=120):
        logger.info(f"Requesting {input_type} from user")
        if input_type in self._user_input_callbacks:
            try:
                result = self._user_input_callbacks[input_type](prompt, timeout)
                logger.info(f"Received {input_type}: {result if result else 'None'}")
                return result
            except Exception as e:
                logger.error(f"Error getting {input_type}: {e}")
                return None
        else:
            logger.error(f"No callback for {input_type}")
            return None
    
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
    
    def _analyze_page(self):
        """Анализирует страницу и определяет, что требуется от пользователя"""
        try:
            current_url = self.driver.current_url.lower()
            
            if "home" in current_url or current_url == "https://x.com/" or current_url == "https://x.com":
                return {"status": "success", "message": "Уже на домашней странице"}
            
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, '[role="alert"], [data-testid="toast"], .error, .alert')
            for err in error_elements:
                if err.is_displayed():
                    err_text = err.text.lower()
                    if "wrong" in err_text or "incorrect" in err_text:
                        return {"status": "error", "type": "wrong_password", "message": f"Неверный пароль: {err.text}"}
                    elif "not found" in err_text or "doesn't exist" in err_text:
                        return {"status": "error", "type": "user_not_found", "message": f"Пользователь не найден: {err.text}"}
                    elif "suspended" in err_text or "blocked" in err_text:
                        return {"status": "error", "type": "account_suspended", "message": f"Аккаунт заблокирован: {err.text}"}
            
            captcha_elements = self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="captcha"], iframe[src*="recaptcha"], [data-testid="captcha"]')
            if captcha_elements:
                return {"status": "blocked", "type": "captcha", "message": "🔒 Обнаружена капча! Требуется ручное решение"}
            
            email_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[name="email"], input[placeholder*="email"], input[placeholder*="Email"]')
            for inp in email_inputs:
                if inp.is_displayed() and inp.is_enabled():
                    return {"status": "input_needed", "type": "email", "message": "📧 Требуется email для верификации"}
            
            phone_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="tel"], input[name="phone"], input[placeholder*="phone"], input[placeholder*="Phone"]')
            for inp in phone_inputs:
                if inp.is_displayed() and inp.is_enabled():
                    return {"status": "input_needed", "type": "phone", "message": "📱 Требуется номер телефона для верификации"}
            
            password_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            if password_inputs:
                return {"status": "input_needed", "type": "password", "message": "🔑 Требуется ввести пароль"}
            
            username_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[autocomplete="username"]')
            if username_inputs:
                return {"status": "input_needed", "type": "username", "message": "👤 Требуется ввести username"}
            
            return {"status": "unknown", "type": "unknown", "message": "Неизвестное состояние страницы"}
            
        except Exception as e:
            logger.error(f"Page analysis error: {e}")
            return {"status": "error", "type": "analysis_error", "message": f"Ошибка анализа: {e}"}
    
    def login(self, username, password, email=None, phone=None):
        logger.info("="*60)
        logger.info(f"START LOGIN for {username}")
        logger.info("="*60)
        
        target_username = username.strip().lstrip("@")
        
        try:
            self._report("start", f"🚀 Авторизация @{target_username}")
            self._create_driver()
            
            login_urls = [
                "https://x.com/i/flow/login",
                "https://x.com/login",
                "https://x.com/i/flow/login?force_login=true",
            ]
            
            for login_url in login_urls:
                try:
                    logger.info(f"Пробую URL: {login_url}")
                    self.driver.get(login_url)
                    time.sleep(3)
                    
                    if "home" in self.driver.current_url:
                        logger.info("✅ Уже на home!")
                        self._save_cookies()
                        save_auth_info(target_username, email, {"method": "direct_home"})
                        return True, None
                    
                    inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input')
                    if inputs:
                        logger.info(f"Найдено {len(inputs)} полей ввода")
                        break
                except Exception as e:
                    logger.warning(f"URL {login_url} не работает: {e}")
                    continue
            
            time.sleep(2)
            self._screenshot("login_start")
            
            max_steps = 20
            step = 0
            email_used = email
            phone_used = phone
            
            while step < max_steps:
                step += 1
                logger.info(f"Шаг {step}/{max_steps}")
                
                analysis = self._analyze_page()
                logger.info(f"Анализ: {analysis}")
                self._report("analyze", f"🔍 {analysis.get('message', '')}")
                
                if analysis.get("status") == "success" or "home" in self.driver.current_url:
                    logger.info("✅ Авторизация успешна!")
                    self._save_cookies()
                    save_auth_info(target_username, email_used, {"method": "success", "steps": step})
                    return True, None
                
                if analysis.get("status") == "error":
                    error_msg = analysis.get("message", "Неизвестная ошибка")
                    self._screenshot("login_error")
                    return False, f"❌ {error_msg}"
                
                if analysis.get("type") == "captcha":
                    self._report("captcha", "🔒 Обнаружена капча!")
                    screenshot_path = self._screenshot("captcha_required")
                    captcha_result = self._request_user_input(
                        "captcha",
                        f"🔒 Обнаружена капча!\n\nСкриншот: {screenshot_path}\n\nПосле решения отправь 'done':",
                        timeout=300
                    )
                    if captcha_result and captcha_result.lower() in ["done", "готово", "ok"]:
                        self._report("captcha", "✅ Капча решена")
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    else:
                        return False, "❌ Капча не решена"
                
                if analysis.get("type") == "email":
                    if email_used:
                        email_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[name="email"], input[placeholder*="email"]')
                        for inp in email_inputs:
                            if inp.is_displayed() and inp.is_enabled():
                                inp.clear()
                                inp.send_keys(email_used)
                                time.sleep(1)
                                next_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                                for btn in next_btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        btn.click()
                                        time.sleep(2)
                                        break
                                break
                    else:
                        email_used = self._request_user_input(
                            "email",
                            "📧 Требуется email для верификации!\nВведи email:",
                            timeout=120
                        )
                        if email_used:
                            logger.info(f"Получен email: {email_used}")
                            continue
                        else:
                            return False, "❌ Email не указан"
                
                if analysis.get("type") == "phone":
                    if phone_used:
                        phone_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="tel"], input[name="phone"], input[placeholder*="phone"]')
                        for inp in phone_inputs:
                            if inp.is_displayed() and inp.is_enabled():
                                inp.clear()
                                inp.send_keys(phone_used)
                                time.sleep(1)
                                next_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                                for btn in next_btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        btn.click()
                                        time.sleep(2)
                                        break
                                break
                    else:
                        phone_used = self._request_user_input(
                            "phone",
                            "📱 Требуется номер телефона!\nВведи номер (с кодом страны):",
                            timeout=120
                        )
                        if phone_used:
                            logger.info(f"Получен телефон: {phone_used}")
                            continue
                        else:
                            return False, "❌ Телефон не указан"
                
                if analysis.get("type") == "password":
                    password_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                    for inp in password_inputs:
                        if inp.is_displayed() and inp.is_enabled():
                            logger.info("Ввожу пароль")
                            inp.clear()
                            inp.send_keys(password)
                            time.sleep(1)
                            login_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"], button[data-testid="LoginForm_Login_Button"]')
                            if login_btns:
                                for btn in login_btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        btn.click()
                                        time.sleep(2)
                                        break
                            else:
                                inp.send_keys(Keys.RETURN)
                                time.sleep(2)
                            break
                
                if analysis.get("type") == "username":
                    username_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[autocomplete="username"]')
                    for inp in username_inputs:
                        if inp.is_displayed() and inp.is_enabled():
                            logger.info(f"Ввожу username: {target_username}")
                            inp.clear()
                            inp.send_keys(target_username)
                            time.sleep(1)
                            next_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                            for btn in next_btns:
                                if btn.is_displayed() and btn.is_enabled():
                                    btn.click()
                                    time.sleep(2)
                                    break
                            break
                
                time.sleep(2)
                if step % 3 == 0:
                    self._screenshot(f"step_{step}")
            
            self._screenshot("login_timeout")
            return False, "⏰ Превышено максимальное количество шагов"
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            logger.error(traceback.format_exc())
            self._screenshot("login_exception")
            return False, f"Ошибка: {e}"
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
        """Получить ленту твитов"""
        logger.info(f"fetch_timeline: username={username}, limit={limit}")
        
        if not AGENT_READY:
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            return None, "Не авторизован. Сначала /se_login"
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                return None, "Не удалось загрузить cookies. Авторизуйся заново: /se_login"
            
            url = f"https://x.com/{username}" if username else "https://x.com/home"
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)
            
            current_url = self.driver.current_url
            if "login" in current_url:
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            tweets = []
            attempts = 0
            
            while len(tweets) < limit and attempts < 10:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                for article in articles:
                    try:
                        text_elem = article.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                        text = text_elem.text if text_elem else ""
                        user_elem = article.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
                        user = user_elem.text if user_elem else ""
                        time_elem = article.find_element(By.CSS_SELECTOR, "time")
                        dt = time_elem.get_attribute("datetime") if time_elem else None
                        link_elem = article.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                        link = link_elem.get_attribute("href") if link_elem else ""
                        
                        if text:
                            tweet = {
                                "text": text,
                                "author": user.split("\n")[0] if "\n" in user else user,
                                "handle": user.split("\n")[1] if "\n" in user else "",
                                "time": dt,
                                "url": f"https://x.com{link}" if link and not link.startswith("http") else link,
                            }
                            if tweet not in tweets:
                                tweets.append(tweet)
                    except Exception as e:
                        logger.debug(f"Error parsing tweet: {e}")
                
                if len(tweets) == 0:
                    attempts += 1
                else:
                    attempts = 0
                
                self.driver.execute_script("window.scrollBy(0, 800)")
                time.sleep(1)
            
            self._save_cookies()
            return tweets[:limit], None
            
        except Exception as e:
            logger.error(f"fetch_timeline error: {e}")
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def fetch_trends(self, limit=10):
        """Получить тренды"""
        logger.info(f"fetch_trends: limit={limit}")
        
        if not AGENT_READY:
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            return None, "Не авторизован. Сначала /se_login"
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                return None, "Не удалось загрузить cookies"
            
            self.driver.get("https://x.com/explore/tabs/trending")
            time.sleep(4)
            
            current_url = self.driver.current_url
            if "login" in current_url:
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            trends = []
            attempts = 0
            
            while len(trends) < limit and attempts < 5:
                trend_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="trend"], [href*="/search?q="]')
                for elem in trend_elements:
                    try:
                        text = elem.text or elem.get_attribute("aria-label") or ""
                        href = elem.get_attribute("href") or ""
                        if text and text not in [t["text"] for t in trends]:
                            trends.append({
                                "text": text[:100],
                                "url": href if href.startswith("http") else f"https://x.com{href}",
                            })
                            if len(trends) >= limit:
                                break
                    except Exception as e:
                        logger.debug(f"Error parsing trend: {e}")
                
                if len(trends) == 0:
                    attempts += 1
                
                self.driver.execute_script("window.scrollBy(0, 600)")
                time.sleep(1)
            
            self._save_cookies()
            return trends[:limit], None
            
        except Exception as e:
            logger.error(f"fetch_trends error: {e}")
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def search(self, query, limit=10):
        """Поиск твитов"""
        logger.info(f"search: query={query}, limit={limit}")
        
        if not AGENT_READY:
            return None, "Selenium не готов. Используй /se_install"
        
        auth = get_auth_info()
        if not auth:
            return None, "Не авторизован. Сначала /se_login"
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                return None, "Не удалось загрузить cookies"
            
            encoded = query.replace(" ", "%20")
            url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)
            
            current_url = self.driver.current_url
            if "login" in current_url:
                return None, "Сессия истекла. Авторизуйся заново: /se_login"
            
            tweets = []
            attempts = 0
            
            while len(tweets) < limit and attempts < 8:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                for article in articles:
                    try:
                        text_elem = article.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                        text = text_elem.text if text_elem else ""
                        user_elem = article.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
                        user = user_elem.text if user_elem else ""
                        time_elem = article.find_element(By.CSS_SELECTOR, "time")
                        dt = time_elem.get_attribute("datetime") if time_elem else None
                        link_elem = article.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                        link = link_elem.get_attribute("href") if link_elem else ""
                        
                        if text:
                            tweet = {
                                "text": text,
                                "author": user.split("\n")[0] if "\n" in user else user,
                                "handle": user.split("\n")[1] if "\n" in user else "",
                                "time": dt,
                                "url": f"https://x.com{link}" if link and not link.startswith("http") else link,
                            }
                            if tweet not in tweets:
                                tweets.append(tweet)
                    except Exception as e:
                        logger.debug(f"Error parsing tweet: {e}")
                
                if len(tweets) == 0:
                    attempts += 1
                
                self.driver.execute_script("window.scrollBy(0, 1000)")
                time.sleep(1.5)
            
            self._save_cookies()
            return tweets[:limit], None
            
        except Exception as e:
            logger.error(f"search error: {e}")
            return None, f"Ошибка: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def check_current_auth(self):
        """Проверить активность сессии"""
        logger.info("check_current_auth: Starting")
        
        if not os.path.exists(COOKIES_FILE):
            return False, "Нет cookies файла"
        
        try:
            self._create_driver()
            self.driver.get("https://x.com")
            time.sleep(2)
            
            if not self._load_cookies():
                return False, "Не удалось загрузить cookies"
            
            self.driver.get("https://x.com/home")
            time.sleep(3)
            
            current_url = self.driver.current_url
            if "home" not in current_url:
                self._screenshot("auth_check_not_home")
                return False, f"Не на домашней странице: {current_url}"
            
            try:
                self.driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryColumn"]')
            except:
                return False, "Лента не найдена"
            
            try:
                login_btn = self.driver.find_element(By.CSS_SELECTOR, 'a[href="/i/flow/login"]')
                if login_btn.is_displayed():
                    return False, "Кнопка входа видна — сессия истекла"
            except:
                pass
            
            self._save_cookies()
            return True, "Сессия активна"
            
        except Exception as e:
            logger.error(f"check_current_auth error: {e}")
            return False, f"Ошибка проверки: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None


se_agent = SeleniumXAgent()


# === РЕГИСТРАЦИЯ КОМАНД БОТА ===

def register_selenium_bot(bot):
    print("[SE] === REGISTER SELENIUM BOT ===")
    logger.info("Registering Selenium bot commands")
    
    def get_user_input(chat_id, prompt, timeout=120):
        if chat_id not in login_sessions:
            login_sessions[chat_id] = {}
        login_sessions[chat_id]["awaiting_input"] = True
        login_sessions[chat_id]["input_prompt"] = prompt
        login_sessions[chat_id]["input_received"] = None
        
        bot.send_message(chat_id, prompt, parse_mode="HTML")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if login_sessions[chat_id].get("input_received") is not None:
                result = login_sessions[chat_id]["input_received"]
                login_sessions[chat_id]["input_received"] = None
                login_sessions[chat_id]["awaiting_input"] = False
                return result
            time.sleep(0.5)
        
        login_sessions[chat_id]["awaiting_input"] = False
        return None
    
    @bot.message_handler(commands=["se_status"])
    def se_status_command(message):
        status = get_full_status()
        auth = status.get("auth_info")
        
        def icon(flag):
            return "✅" if flag else "❌"
        
        if auth:
            auth_status = f"👤 <b>Аккаунт:</b> <code>@{auth['username']}</code>\n🕐 <b>Авторизован:</b> {auth['authorized_at']}\n"
        else:
            auth_status = "👤 <b>Аккаунт:</b> <i>не подключён</i>\n"
        
        msg = (
            "🚗 <b>Selenium X Agent — Статус</b>\n\n"
            f"{auth_status}\n"
            f"{icon(status['selenium_pip']['installed'])} <b>Selenium pip:</b> "
            f"{'v' + status['selenium_pip']['version'] if status['selenium_pip']['version'] else 'не установлен'}\n"
            f"{icon(status['chrome_browser']['found'])} <b>Chrome:</b> "
            f"<code>{status['chrome_browser']['path'] or 'не найден'}</code>\n"
            f"{icon(status['chromedriver']['ready'])} <b>ChromeDriver:</b> "
            f"<code>{status['chromedriver']['path'] or 'не готов'}</code>\n\n"
            f"{'🟢' if status['agent_ready'] else '🔴'} <b>Agent готов:</b> "
            f"{'Да' if status['agent_ready'] else 'Нет'}\n"
            f"🍪 <b>Cookies:</b> {'есть' if status['cookies_exist'] else 'нет'}\n"
        )
        
        if not status['agent_ready']:
            msg += "\n⚠️ Нажми /se_install для установки"
        elif not auth:
            msg += "\n⚠️ Авторизуйся: /se_login"
        else:
            msg += "\n✅ Готов! Используй команды ниже ⬇️"
        
        bot.reply_to(message, msg, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logs"])
    def se_logs_command(message):
        if not os.path.exists(LOG_FILE):
            bot.reply_to(message, "❌ Лог-файл не найден")
            return
        
        try:
            with open(LOG_FILE, "r", encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
            
            log_text = "".join(last_lines)
            
            if len(log_text) > 4000:
                with open(LOG_FILE, "rb") as f:
                    bot.send_document(message.chat.id, f, caption="📋 Логи авторизации")
            else:
                bot.reply_to(message, f"📋 <b>Последние логи</b>\n\n<code>{log_text}</code>", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка чтения логов: {e}")
    
    @bot.message_handler(commands=["se_check_auth"])
    def se_check_auth_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install", parse_mode="HTML")
            return
        
        auth = get_auth_info()
        if not auth:
            bot.reply_to(message, "❌ Нет данных об авторизации. Сначала /se_login", parse_mode="HTML")
            return
        
        username = auth.get("username", "?")
        bot.reply_to(message, f"🔍 Проверяю сессию для @{username}...", parse_mode="HTML")
        valid, msg = run_sync_task(se_agent.check_current_auth)
        
        if valid:
            bot.reply_to(message, f"✅ <b>Сессия активна</b>\n👤 @{username}", parse_mode="HTML")
        else:
            bot.reply_to(message, f"❌ <b>Сессия недействительна</b>\n{msg}\n\nАвторизуйся: /se_login", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logout"])
    def se_logout_command(message):
        clear_auth_info()
        bot.reply_to(message, "🚪 <b>Сессия очищена</b>\nТеперь можно авторизоваться заново: /se_login", parse_mode="HTML")
    
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
            bot.reply_to(message, "❌ <b>Установка не завершена</b>\nПопробуй ещё раз: /se_install", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_login"])
    def se_login_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. Сначала /se_install", parse_mode="HTML")
            return
        
        auth = get_auth_info()
        if auth:
            bot.reply_to(message,
                f"⚠️ Уже авторизован как <code>@{auth['username']}</code>\n"
                f"Используй /se_logout чтобы сменить аккаунт",
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
    
    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "username")
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
    
    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "password")
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
        login_sessions[chat_id]["step"] = "processing"
        
        bot.reply_to(message,
            "✅ Пароль получен\n\n"
            "⏳ Начинаю авторизацию...\n"
            "<i>Бот будет отслеживать страницу и запрашивать необходимые данные</i>",
            parse_mode="HTML"
        )
        
        creds = login_sessions[chat_id]
        username = creds["username"]
        password = creds["password"]
        
        def request_email(prompt, timeout=120):
            login_sessions[chat_id]["step"] = "request_email"
            return get_user_input(chat_id, prompt, timeout)
        
        def request_phone(prompt, timeout=120):
            login_sessions[chat_id]["step"] = "request_phone"
            return get_user_input(chat_id, prompt, timeout)
        
        def request_captcha(prompt, timeout=300):
            login_sessions[chat_id]["step"] = "request_captcha"
            return get_user_input(chat_id, prompt, timeout)
        
        se_agent.set_user_input_callback("email", request_email)
        se_agent.set_user_input_callback("phone", request_phone)
        se_agent.set_user_input_callback("captcha", request_captcha)
        
        progress_msg = bot.send_message(chat_id, "🔄 Процесс авторизации запущен...")
        
        def update_progress(step, msg_text):
            try:
                bot.edit_message_text(
                    f"🔄 <b>Шаг: {step}</b>\n\n{msg_text}",
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.debug(f"Progress update error: {e}")
        
        se_agent.set_progress_callback(update_progress)
        
        def do_login():
            return se_agent.login(username, password)
        
        success, error = run_sync_task(do_login)
        
        se_agent.set_progress_callback(None)
        se_agent.set_user_input_callback("email", None)
        se_agent.set_user_input_callback("phone", None)
        se_agent.set_user_input_callback("captcha", None)
        
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        
        if chat_id in login_sessions:
            del login_sessions[chat_id]
        
        auth_after = get_auth_info()
        
        if error:
            bot.reply_to(message, f"❌ {error}")
        elif success and auth_after:
            msg = (
                f"✅ <b>Авторизация УСПЕШНА!</b>\n\n"
                f"👤 Аккаунт: <code>@{auth_after['username']}</code>\n"
                f"🕐 Время: {auth_after['authorized_at']}\n"
            )
            if auth_after.get('following_count'):
                msg += f"📊 Подписок: {auth_after['following_count']}\n"
            if auth_after.get('followers_count'):
                msg += f"📊 Подписчиков: {auth_after['followers_count']}\n"
            
            msg += "\nТеперь можно использовать:\n/se_timeline — лента\n/se_trends — тренды\n/se_search — поиск"
            bot.reply_to(message, msg, parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Авторизация не удалась")
    
    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("awaiting_input", False))
    def se_user_input(message):
        chat_id = message.chat.id
        text = message.text.strip()
        
        if text.startswith("/"):
            if text.lower() == "/se_cancel":
                login_sessions[chat_id]["input_received"] = None
                bot.reply_to(message, "❌ Ввод отменён")
                return
            return
        
        login_sessions[chat_id]["input_received"] = text
        bot.reply_to(message, f"✅ Получено: {text}\nПродолжаю авторизацию...")
    
    @bot.message_handler(commands=["se_cancel"])
    def se_cancel_command(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            login_sessions[chat_id]["input_received"] = None
            login_sessions[chat_id]["awaiting_input"] = False
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Ввод отменён")
        else:
            bot.reply_to(message, "Нет активного ввода")
    
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
            "  /se_login — Войти в X (с автоматическим мониторингом)\n"
            "  /se_cancel — Отменить текущий ввод\n\n"
            "📰 <b>Контент</b>\n"
            "  /se_timeline [user] [N] — Лента\n"
            "  /se_trends [N] — 🔥 Тренды X\n"
            "  /se_search [запрос] [N] — Поиск твитов\n"
            "  /se_screenshot [url] — Скриншот страницы\n\n"
            "⚠️ <b>Особенности:</b>\n"
            "• Автоматический мониторинг страницы\n"
            "• Запрос email/телефона/капчи в чате\n"
            "• Полное логирование в debug.log"
        )
        bot.reply_to(message, msg, parse_mode="HTML")
    
    logger.info("Selenium bot commands registered")
    print("[SE] === REGISTER END ===")


# === ИНИЦИАЛИЗАЦИЯ ===
check_selenium_pip()
check_chrome_binary()
check_driver()

logger.info("Selenium X Agent initialization complete")