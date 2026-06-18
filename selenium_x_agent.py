# selenium_x_agent.py — Полный агент с мониторингом и запросами в чат
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

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(CHROME_DIR, exist_ok=True)
os.makedirs(DRIVER_DIR, exist_ok=True)

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
    t.join(timeout=180)  # 3 минуты на авторизацию
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
        """Установить callback для запроса данных у пользователя"""
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
        """Запросить данные у пользователя через callback"""
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
            page_text = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            # Проверяем URL
            if "home" in current_url or current_url == "https://x.com/" or current_url == "https://x.com":
                return {"status": "success", "message": "Уже на домашней странице"}
            
            # Проверяем наличие ошибок
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
            
            # Проверяем наличие капчи
            captcha_elements = self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="captcha"], iframe[src*="recaptcha"], [data-testid="captcha"]')
            if captcha_elements:
                return {"status": "blocked", "type": "captcha", "message": "🔒 Обнаружена капча! Требуется ручное решение"}
            
            # Проверяем наличие поля email
            email_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[name="email"], input[placeholder*="email"], input[placeholder*="Email"]')
            for inp in email_inputs:
                if inp.is_displayed() and inp.is_enabled():
                    return {"status": "input_needed", "type": "email", "message": "📧 Требуется email для верификации"}
            
            # Проверяем наличие поля телефона
            phone_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="tel"], input[name="phone"], input[placeholder*="phone"], input[placeholder*="Phone"]')
            for inp in phone_inputs:
                if inp.is_displayed() and inp.is_enabled():
                    return {"status": "input_needed", "type": "phone", "message": "📱 Требуется номер телефона для верификации"}
            
            # Проверяем наличие поля пароля
            password_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            if password_inputs:
                return {"status": "input_needed", "type": "password", "message": "🔑 Требуется ввести пароль"}
            
            # Проверяем наличие поля username
            username_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[autocomplete="username"]')
            if username_inputs:
                return {"status": "input_needed", "type": "username", "message": "👤 Требуется ввести username"}
            
            # Проверяем наличие кнопки подтверждения
            confirm_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button:has-text("Confirm"), button:has-text("Подтвердить")')
            if confirm_buttons:
                return {"status": "action_needed", "type": "confirm", "message": "⚠️ Требуется подтверждение (нажмите кнопку)"}
            
            return {"status": "unknown", "type": "unknown", "message": "Неизвестное состояние страницы"}
            
        except Exception as e:
            logger.error(f"Page analysis error: {e}")
            return {"status": "error", "type": "analysis_error", "message": f"Ошибка анализа: {e}"}
    
    def _wait_for_input(self, input_type, timeout=30):
        """Ждет появления поля для ввода"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            analysis = self._analyze_page()
            if analysis.get("type") == input_type or "input_needed" in analysis.get("status", ""):
                return True
            time.sleep(1)
        return False
    
    def login(self, username, password, email=None, phone=None):
        """Универсальная авторизация с мониторингом и запросами в чат"""
        
        logger.info("="*60)
        logger.info(f"START LOGIN for {username}")
        logger.info(f"Email provided: {bool(email)}")
        logger.info(f"Phone provided: {bool(phone)}")
        logger.info("="*60)
        
        target_username = username.strip().lstrip("@")
        
        try:
            self._report("start", f"🚀 Авторизация @{target_username}")
            self._create_driver()
            
            # === ПРОБУЕМ РАЗНЫЕ URL ===
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
                    
                    # Проверяем, есть ли поля
                    inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input')
                    if inputs:
                        logger.info(f"Найдено {len(inputs)} полей ввода")
                        break
                except Exception as e:
                    logger.warning(f"URL {login_url} не работает: {e}")
                    continue
            
            time.sleep(2)
            self._screenshot("login_start")
            
            # === ОСНОВНОЙ ЦИКЛ АВТОРИЗАЦИИ ===
            max_steps = 20
            step = 0
            email_used = email
            phone_used = phone
            
            while step < max_steps:
                step += 1
                logger.info(f"Шаг {step}/{max_steps}")
                
                # Анализируем страницу
                analysis = self._analyze_page()
                logger.info(f"Анализ: {analysis}")
                
                # Показываем в чате
                self._report("analyze", f"🔍 {analysis.get('message', '')}")
                
                # === ОБРАБОТКА РЕЗУЛЬТАТОВ АНАЛИЗА ===
                
                # Успех - на home
                if analysis.get("status") == "success" or "home" in self.driver.current_url:
                    logger.info("✅ Авторизация успешна!")
                    self._save_cookies()
                    save_auth_info(target_username, email_used, {
                        "method": "success",
                        "steps": step
                    })
                    return True, None
                
                # Ошибка
                if analysis.get("status") == "error":
                    error_msg = analysis.get("message", "Неизвестная ошибка")
                    self._screenshot("login_error")
                    return False, f"❌ {error_msg}"
                
                # Капча - запрашиваем у пользователя
                if analysis.get("type") == "captcha":
                    self._report("captcha", "🔒 Обнаружена капча! Требуется ручное решение")
                    
                    # Сохраняем скриншот для пользователя
                    screenshot_path = self._screenshot("captcha_required")
                    
                    # Запрашиваем решение капчи у пользователя
                    captcha_result = self._request_user_input(
                        "captcha",
                        f"🔒 Обнаружена капча!\n\nСкриншот сохранен: {screenshot_path}\n\nПожалуйста, открой страницу и реши капчу вручную.\nПосле решения отправь 'done' или 'готово':",
                        timeout=300
                    )
                    
                    if captcha_result and captcha_result.lower() in ["done", "готово", "ok", "решено"]:
                        self._report("captcha", "✅ Капча решена, продолжаю...")
                        # Обновляем страницу
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    else:
                        return False, "❌ Капча не решена"
                
                # Требуется email
                if analysis.get("type") == "email":
                    if email_used:
                        logger.info(f"Использую email: {email_used}")
                        # Находим и заполняем email
                        email_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[name="email"], input[placeholder*="email"]')
                        for inp in email_inputs:
                            if inp.is_displayed() and inp.is_enabled():
                                inp.clear()
                                inp.send_keys(email_used)
                                time.sleep(1)
                                # Нажимаем Next
                                next_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                                for btn in next_btns:
                                    if btn.is_displayed() and btn.is_enabled():
                                        btn.click()
                                        time.sleep(2)
                                        break
                                break
                    else:
                        # Запрашиваем email у пользователя
                        email_used = self._request_user_input(
                            "email",
                            "📧 Требуется email для верификации!\nВведи email, привязанный к аккаунту:",
                            timeout=120
                        )
                        if email_used:
                            logger.info(f"Получен email: {email_used}")
                            continue
                        else:
                            return False, "❌ Email не указан"
                
                # Требуется телефон
                if analysis.get("type") == "phone":
                    if phone_used:
                        logger.info(f"Использую телефон: {phone_used}")
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
                            "📱 Требуется номер телефона для верификации!\nВведи номер телефона (с кодом страны):",
                            timeout=120
                        )
                        if phone_used:
                            logger.info(f"Получен телефон: {phone_used}")
                            continue
                        else:
                            return False, "❌ Телефон не указан"
                
                # Требуется пароль
                if analysis.get("type") == "password":
                    password_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                    for inp in password_inputs:
                        if inp.is_displayed() and inp.is_enabled():
                            logger.info("Ввожу пароль")
                            inp.clear()
                            inp.send_keys(password)
                            time.sleep(1)
                            # Нажимаем Enter или Login
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
                
                # Требуется username
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
                
                # Требуется подтверждение
                if analysis.get("type") == "confirm":
                    self._report("confirm", "⚠️ Требуется подтверждение")
                    confirm_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button:has-text("Confirm"), button:has-text("Подтвердить")')
                    for btn in confirm_btns:
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            time.sleep(2)
                            break
                
                # Ждем немного перед следующим шагом
                time.sleep(2)
                
                # Делаем скриншот для отладки
                if step % 3 == 0:
                    self._screenshot(f"step_{step}")
            
            # Если вышли из цикла - timeout
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
        # ... (код из предыдущих версий)
        pass
    
    def fetch_trends(self, limit=10):
        # ... (код из предыдущих версий)
        pass
    
    def search(self, query, limit=10):
        # ... (код из предыдущих версий)
        pass
    
    def check_current_auth(self):
        # ... (код из предыдущих версий)
        pass


se_agent = SeleniumXAgent()


# === РЕГИСТРАЦИЯ КОМАНД БОТА ===

def register_selenium_bot(bot):
    print("[SE] === REGISTER SELENIUM BOT ===")
    logger.info("Registering Selenium bot commands")
    
    # === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЕМ ===
    
    def get_user_input(chat_id, prompt, timeout=120):
        """Запрашивает ввод у пользователя и ждет ответа"""
        # Создаем временный ключ в сессии
        if chat_id not in login_sessions:
            login_sessions[chat_id] = {}
        login_sessions[chat_id]["awaiting_input"] = True
        login_sessions[chat_id]["input_prompt"] = prompt
        login_sessions[chat_id]["input_received"] = None
        
        # Отправляем запрос пользователю
        bot.send_message(chat_id, prompt, parse_mode="HTML")
        
        # Ждем ответа
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
    
    # === КОМАНДЫ ===
    
    @bot.message_handler(commands=["se_status"])
    def se_status_command(message):
        status = get_full_status()
        auth = status.get("auth_info")
        
        def icon(flag):
            return "✅" if flag else "❌"
        
        if auth:
            auth_status = (
                f"👤 <b>Аккаунт:</b> <code>@{auth['username']}</code>\n"
                f"🕐 <b>Авторизован:</b> {auth['authorized_at']}\n"
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
        log_file = LOG_FILE
        
        if not os.path.exists(log_file):
            bot.reply_to(message, "❌ Лог-файл не найден")
            return
        
        try:
            with open(log_file, "r", encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
            
            log_text = "".join(last_lines)
            
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
        if not auth:
            bot.reply_to(message, "❌ Нет данных об авторизации. Сначала /se_login", parse_mode="HTML")
            return
        
        username = auth.get("username", "?")
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
        
        # === НАСТРАИВАЕМ CALLBACK ДЛЯ ЗАПРОСА ДАННЫХ ===
        
        def request_email(prompt, timeout=120):
            """Запрашивает email у пользователя"""
            login_sessions[chat_id]["step"] = "request_email"
            return get_user_input(chat_id, prompt, timeout)
        
        def request_phone(prompt, timeout=120):
            """Запрашивает телефон у пользователя"""
            login_sessions[chat_id]["step"] = "request_phone"
            return get_user_input(chat_id, prompt, timeout)
        
        def request_captcha(prompt, timeout=300):
            """Запрашивает решение капчи"""
            login_sessions[chat_id]["step"] = "request_captcha"
            return get_user_input(chat_id, prompt, timeout)
        
        # Устанавливаем callback-и
        se_agent.set_user_input_callback("email", request_email)
        se_agent.set_user_input_callback("phone", request_phone)
        se_agent.set_user_input_callback("captcha", request_captcha)
        
        # Запускаем логин
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
        
        # Очищаем
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
    
    # === ОБРАБОТКА ВВОДА ПОЛЬЗОВАТЕЛЯ ===
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
        
        # Сохраняем ввод
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
    
    # === КОМАНДЫ ДЛЯ КОНТЕНТА ===
    
    @bot.message_handler(commands=["se_timeline"])
    def se_timeline_command(message):
        # ... (код из предыдущих версий)
        bot.reply_to(message, "⏳ В разработке...")
    
    @bot.message_handler(commands=["se_trends"])
    def se_trends_command(message):
        bot.reply_to(message, "⏳ В разработке...")
    
    @bot.message_handler(commands=["se_search"])
    def se_search_command(message):
        bot.reply_to(message, "⏳ В разработке...")
    
    @bot.message_handler(commands=["se_screenshot"])
    def se_screenshot_command(message):
        bot.reply_to(message, "⏳ В разработке...")
    
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
            "  /se_timeline [user] [N] — Лента (в разработке)\n"
            "  /se_trends [N] — 🔥 Тренды (в разработке)\n"
            "  /se_search [запрос] [N] — Поиск (в разработке)\n"
            "  /se_screenshot [url] — Скриншот (в разработке)\n\n"
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