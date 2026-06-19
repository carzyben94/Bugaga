# selenium_x_agent.py — Рабочий + вход через Google в X
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
    level=logging.INFO,
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
        except:
            return None
    
    def _get_options(self):
        from selenium.webdriver.chrome.options import Options
        options = Options()
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        options.add_argument(f"--user-agent={ua}")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=390,844")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-US")
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if _installer.chrome_path and "chrome-linux64" in _installer.chrome_path:
            options.binary_location = _installer.chrome_path
        return options
    
    def create(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        options = self._get_options()
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
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


# === RESEARCH X.COM ===

def research_x_page(url="https://x.com/login", bot=None, chat_id=None):
    try:
        import selenium
    except ImportError:
        _installer._install_selenium_pip()
        try:
            import selenium
        except ImportError:
            return {"error": "Selenium не установлен"}
    
    if not _installer.ready:
        return {"error": "Chrome/Driver не установлены. Сделай /install"}
    
    session = BrowserSession()
    if bot and chat_id:
        session.set_chat(bot, chat_id)
    
    result = {
        "url": url,
        "buttons": [],
        "links": [],
        "inputs": [],
        "text_elements": [],
        "html": ""
    }
    
    try:
        session.create()
        session.driver.get(url)
        time.sleep(5)
        
        from selenium.webdriver.common.by import By
        
        buttons = session.driver.find_elements(By.XPATH, "//button | //*[@role='button']")
        for i, btn in enumerate(buttons[:50]):
            try:
                text = btn.text[:200] if btn.text else "без текста"
                result["buttons"].append({
                    "id": i+1,
                    "text": text,
                    "class": btn.get_attribute("class") or "",
                    "aria_label": btn.get_attribute("aria-label") or ""
                })
            except:
                pass
        
        links = session.driver.find_elements(By.TAG_NAME, "a")
        for i, link in enumerate(links[:50]):
            try:
                href = link.get_attribute("href") or ""
                text = link.text[:200] if link.text else "без текста"
                result["links"].append({
                    "id": i+1,
                    "text": text,
                    "href": href
                })
            except:
                pass
        
        inputs = session.driver.find_elements(By.XPATH, "//input | //textarea")
        for i, inp in enumerate(inputs[:30]):
            try:
                result["inputs"].append({
                    "id": i+1,
                    "type": inp.get_attribute("type") or "text",
                    "name": inp.get_attribute("name") or "",
                    "placeholder": inp.get_attribute("placeholder") or ""
                })
            except:
                pass
        
        try:
            text_elements = session.driver.find_elements(By.XPATH, "//*[text() and not(self::script) and not(self::style)]")
            for elem in text_elements[:30]:
                try:
                    text = elem.text.strip()
                    if text and len(text) > 3:
                        result["text_elements"].append({
                            "text": text[:300],
                            "tag": elem.tag_name
                        })
                except:
                    pass
        except:
            pass
        
        result["html"] = session.driver.page_source[:10000]
        
        screenshot_path = session._screenshot("research_x")
        if screenshot_path:
            result["screenshot"] = screenshot_path
        
        session.save_cookies()
        return result
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.quit()


# === GOOGLE LOGIN ===

def google_login(email, password, bot=None, chat_id=None):
    try:
        import selenium
    except ImportError:
        _installer._install_selenium_pip()
        try:
            import selenium
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
            except:
                pass
    
    try:
        report("⏳ Запускаю браузер...")
        session.create()
        
        report("📥 Открываю x.com/login...")
        session.driver.get("https://x.com/login")
        time.sleep(5)
        
        session._screenshot("login_page", "📸 Страница входа X")
        
        from selenium.webdriver.common.by import By
        
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        
        try:
            google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Continue with Google')]")
            report("✅ Найдена: 'Continue with Google'")
        except:
            pass
        
        if not google_btn:
            try:
                google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Google')]")
                report("✅ Найден элемент с 'Google'")
            except:
                pass
        
        if not google_btn:
            report("❌ Кнопка Google НЕ найдена!")
            return False, "Кнопка Google не найдена"
        
        report("🖱️ Кликаю по Google...")
        google_btn.click()
        time.sleep(5)
        
        session._screenshot("google_redirect", "📸 После клика")
        
        current_url = session.driver.current_url
        report(f"📍 URL: {current_url[:80]}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ Перешли на Google!")
            
            try:
                email_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
                email_field.send_keys(email)
                report("✅ Email введён")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                next_btn.click()
                time.sleep(3)
            except Exception as e:
                report(f"⚠️ Email: {e}")
            
            try:
                time.sleep(3)
                pass_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                next_btn.click()
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password: {e}")
            
            session._screenshot("google_after_login", "📸 После входа в Google")
        
        report("⏳ Жду редирект на X...")
        for i in range(10):
            time.sleep(2)
            url = session.driver.current_url
            if "x.com" in url and "login" not in url:
                report("✅ Вошли в X!")
                break
        
        session.driver.get("https://x.com/home")
        time.sleep(5)
        session._screenshot("x_home", "📸 X Home")
        
        html = session.driver.page_source.lower()
        if "home" in html or "following" in html:
            report("✅ Авторизация подтверждена!")
            session.save_cookies()
            save_auth_info("google_user", email)
            return True, None
        else:
            report("❌ Не удалось войти в X")
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(traceback.format_exc())
        return False, str(e)
    finally:
        session.quit()


# === AGENT_READY ===

def AGENT_READY():
    return _installer.ready


print(f"[SE] Модуль загружен. ready={_installer.ready}", flush=True)