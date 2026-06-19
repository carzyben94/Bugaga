# selenium_x_agent.py — Фикс: обход блокировок X + вход через Google
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
import uuid
import shutil
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

CHROME_VERSION = "133.0.6943.53"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"
CHROME_ZIP = f"{BASE_URL}/chrome-linux64.zip"
DRIVER_ZIP = f"{BASE_URL}/chromedriver-linux64.zip"

login_sessions = {}
# === ЗАЩИТА ОТ ДУБЛЕЙ ===
_processing_messages = set()


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
                    [sys.executable, "-m", "pip", "install", "selenium==4.27.1"],
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
        self._user_data_dir = None

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

    def _kill_old_chrome(self):
        """Убиваем старые процессы Chrome/chromedriver перед запуском"""
        try:
            subprocess.run(["pkill", "-9", "-f", "chrome"], capture_output=True, timeout=5)
            subprocess.run(["pkill", "-9", "-f", "chromedriver"], capture_output=True, timeout=5)
            time.sleep(1)
            logger.info("Killed old Chrome processes")
        except Exception as e:
            logger.warning(f"Kill old Chrome failed: {e}")

    def _get_options(self):
        from selenium.webdriver.chrome.options import Options
        options = Options()

        # === ФИКС: УНИКАЛЬНЫЙ ПРОФИЛЬ внутри BASE_DIR ===
        profile_dir = BASE_DIR / f"profile_{uuid.uuid4().hex[:12]}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._user_data_dir = str(profile_dir)
        options.add_argument(f"--user-data-dir={self._user_data_dir}")
        logger.info(f"User data dir: {self._user_data_dir}")

        # === УЛУЧШЕННЫЙ USER-AGENT ===
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.53 Safari/537.36"
        options.add_argument(f"--user-agent={ua}")

        # === HEADLESS ===
        options.add_argument("--headless=new")

        # === ОСНОВНЫЕ АРГУМЕНТЫ ===
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-US,en")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-breakpad")
        options.add_argument("--disable-component-extensions-with-background-pages")
        options.add_argument("--disable-features=TranslateUI,InterestFeedContentSuggestions,CalculateNativeWinOcclusion,OptimizationHints,AudioServiceOutOfProcess,IsolateOrigins,site-per-process")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
        options.add_argument("--force-color-profile=srgb")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--no-first-run")
        options.add_argument("--password-store=basic")
        options.add_argument("--use-mock-keychain")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--mute-audio")

        # === Анти-детект ===
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        # === Предпочтения ===
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_settings.popups": 0,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "intl.accept_languages": "en-US,en",
        }
        options.add_experimental_option("prefs", prefs)

        if _installer.chrome_path and "chrome-linux64" in _installer.chrome_path:
            options.binary_location = _installer.chrome_path

        return options

    def create(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service

        # === ФИКС: убиваем старые процессы перед запуском ===
        self._kill_old_chrome()

        options = self._get_options()
        service = Service(_installer.driver_path) if _installer.driver_path else Service()

        self.driver = webdriver.Chrome(service=service, options=options)

        # === CDP: скрываем webdriver ===
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
            """
        })

        # === CDP: эмуляция реального viewport ===
        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False
        })

        # === CDP: отключаем WebDriver в navigator ===
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
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
        # === ФИКС: ОЧИСТКА ПРОФИЛЯ ===
        if self._user_data_dir and os.path.exists(self._user_data_dir):
            try:
                shutil.rmtree(self._user_data_dir, ignore_errors=True)
                logger.info(f"Cleaned profile: {self._user_data_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean profile: {e}")


def _send_log_file(bot, chat_id, prefix=""):
    """Отправить файл логов в чат"""
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "rb") as f:
                caption = f"{prefix}\n📄 Логи: {LOG_FILE.name}" if prefix else f"📄 Логи: {LOG_FILE.name}"
                bot.send_document(chat_id, f, caption=caption)
    except Exception as e:
        logger.error(f"Failed to send log: {e}")


# === GOOGLE LOGIN ===
def google_login(email, password, bot=None, chat_id=None):
    try:
        import selenium
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        _installer._install_selenium_pip()
        try:
            import selenium
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
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

        # === ШАГ 0: Проверяем, что браузер работает ===
        report("🌐 Тестирую соединение...")
        session.driver.get("https://www.google.com")
        time.sleep(3)
        test_title = session.driver.title
        test_url = session.driver.current_url
        logger.info(f"Google test - URL: {test_url}, Title: {test_title}")
        report(f"📍 Google test: {test_title[:50]}")
        session._screenshot("step0_google_test", "📸 Тест Google")

        if "Google" not in test_title:
            report_error("Браузер не загружает страницы корректно!")
            return False, "Браузер не работает"

        # === ШАГ 1: Заходим на x.com/login напрямую ===
        report("📥 Открываю x.com/login...")
        logger.info("Navigating to https://x.com/i/flow/login")
        session.driver.get("https://x.com/i/flow/login")
        time.sleep(8)

        current_url = session.driver.current_url
        title = session.driver.title
        logger.info(f"After x.com/login load - URL: {current_url}, Title: {title}")
        report(f"📍 URL: {current_url[:80]}")
        report(f"📰 Title: {title[:80]}")

        session._screenshot("step1_login_page", "📸 Шаг 1: Страница входа")
        session._save_html("step1_login_page")

        # === Проверяем, загрузилась ли страница ===
        if current_url == "data:," or not title or len(session.driver.page_source) < 500:
            logger.error("Page did not load properly, trying alternative approach")
            report("⚠️ Страница не загрузилась, пробую альтернативный подход...")

            session.driver.get("https://x.com")
            time.sleep(8)
            current_url = session.driver.current_url
            logger.info(f"After x.com (alt) - URL: {current_url}")
            session._screenshot("step1_alt", "📸 Альтернативный вход")
            session._save_html("step1_alt")

        # === ШАГ 2: Ищем кнопку Google ===
        report("🔍 Ищу кнопку Google...")
        time.sleep(3)

        google_btn = None

        # === МЕТОД 1: XPath по тексту ===
        xpaths = [
            "//span[contains(text(), 'Continue with Google')]",
            "//span[contains(text(), 'Sign in with Google')]",
            "//span[contains(text(), 'Google')]",
            "//div[contains(text(), 'Continue with Google')]",
            "//div[contains(text(), 'Sign in with Google')]",
            "//button[.//*[contains(text(), 'Google')]]",
            "//div[@role='button' and .//*[contains(text(), 'Google')]]",
            "//a[.//*[contains(text(), 'Google')]]",
            "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]",
            "//div[contains(@class, 'google')]",
            "//div[contains(@class, 'Google')]",
        ]

        for xp in xpaths:
            try:
                elements = session.driver.find_elements(By.XPATH, xp)
                logger.debug(f"Google XPath '{xp[:50]}' found: {len(elements)}")
                if elements:
                    google_btn = elements[0]
                    logger.info(f"Found Google via: {xp[:50]}")
                    report(f"✅ Найдено: {xp[:50]}")
                    break
            except Exception as e:
                logger.debug(f"Google XPath failed: {e}")

        # === МЕТОД 2: Поиск по SVG/иконке Google ===
        if not google_btn:
            logger.info("Trying to find Google by SVG icon...")
            try:
                svg_xpaths = [
                    "//svg[contains(@viewBox, '24 24')]//path[contains(@fill, '#EA4335')]",
                    "//svg[contains(@viewBox, '24 24')]//path[contains(@fill, '#4285F4')]",
                    "//*[name()='svg']//*[contains(@fill, '#EA4335')]",
                ]
                for svg_xp in svg_xpaths:
                    svg_elements = session.driver.find_elements(By.XPATH, svg_xp)
                    if svg_elements:
                        parent = svg_elements[0].find_element(By.XPATH, "./ancestor::button | ./ancestor::div[@role='button'] | ./ancestor::a")
                        if parent:
                            google_btn = parent
                            logger.info("Found Google button via SVG icon")
                            report("✅ Найдено через иконку Google")
                            break
            except Exception as e:
                logger.debug(f"SVG search failed: {e}")

        # === МЕТОД 3: Перебор всех кликабельных элементов ===
        if not google_btn:
            logger.info("XPath search failed, trying all clickable elements")
            report("🔍 Перебираю все кнопки...")
            all_buttons = session.driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //a")
            logger.info(f"Total clickable elements found: {len(all_buttons)}")
            report(f"   Всего: {len(all_buttons)}")

            for idx, btn in enumerate(all_buttons[:30]):
                try:
                    text = btn.text or btn.get_attribute("aria-label") or btn.get_attribute("title") or ""
                    href = btn.get_attribute("href") or ""
                    btn_class = btn.get_attribute("class") or ""
                    logger.debug(f"Button [{idx}]: text='{text[:50]}' href='{href[:50]}' class='{btn_class[:50]}'")

                    if text or href:
                        report(f"   [{idx}] {text[:50]} | href={href[:50]}")
                        if "google" in (text + href + btn_class).lower():
                            google_btn = btn
                            logger.info(f"Found Google button at index {idx}")
                            report(f"   ✅ Это Google!")
                            break
                except Exception as e:
                    logger.debug(f"Button [{idx}] error: {e}")

        if not google_btn:
            logger.error("Google button not found")
            report_error("❌ Кнопка Google не найдена!")
            session._screenshot("no_google_found", "📸 Нет кнопки Google")
            return False, "Кнопка Google не найдена"

        # === КЛИКАЕМ ПО GOOGLE ===
        report("🖱️ Кликаю Google...")
        logger.info("Clicking Google button")
        try:
            session.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", google_btn)
            time.sleep(1)
            google_btn.click()
            logger.info("Google button clicked successfully")
        except Exception as e:
            logger.warning(f"Normal click failed: {e}, trying JS click")
            session.driver.execute_script("arguments[0].click();", google_btn)

        time.sleep(6)
        session._screenshot("after_google_click", "📸 После клика Google")
        logger.info(f"After Google click - URL: {session.driver.current_url}")

        # === Google Auth Flow ===
        current_url = session.driver.current_url
        logger.info(f"Current URL before Google auth: {current_url}")
        report(f"📍 URL: {current_url[:80]}")

        if "accounts.google.com" in current_url or "google.com" in current_url:
            logger.info("On Google auth page")
            report("✅ На странице Google!")

            # === Email ===
            try:
                logger.info("Looking for email field")
                email_field = WebDriverWait(session.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
                )
                email_field.clear()
                email_field.send_keys(email)
                logger.info("Email entered")
                report("✅ Email введён")
                time.sleep(1)
                email_field.send_keys(Keys.RETURN)
                time.sleep(5)
                logger.info(f"After email - URL: {session.driver.current_url}")
            except Exception as e:
                logger.error(f"Email input failed: {e}")
                report(f"⚠️ Email: {e}")

            # === Password ===
            try:
                logger.info("Looking for password field")
                pass_field = WebDriverWait(session.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
                )
                pass_field.clear()
                pass_field.send_keys(password)
                logger.info("Password entered")
                report("✅ Пароль введён")
                time.sleep(1)
                pass_field.send_keys(Keys.RETURN)
                time.sleep(8)
                logger.info(f"After password - URL: {session.driver.current_url}")
            except Exception as e:
                logger.error(f"Password input failed: {e}")
                report(f"⚠️ Password: {e}")

            session._screenshot("google_done", "📸 После Google login")

        # === Ждём редиректа на X ===
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

        # === Проверяем авторизацию ===
        session._screenshot("final_check", "📸 Финальная проверка")
        html = session.driver.page_source.lower()

        auth_confirmed = any(k in html for k in ["home", "following", "for you", "для вас", "главная", "compose", "logout", "settings"])
        logger.info(f"Auth confirmed: {auth_confirmed}")

        if auth_confirmed:
            report("✅ Авторизация подтверждена!")
            session.save_cookies()

            username = None
            try:
                url_match = re.search(r'x\.com/([^/]+)', final_url or "")
                if url_match:
                    username = url_match.group(1)
            except:
                pass

            save_auth_info(username or "unknown", email)
            logger.info(f"Saved auth: username={username}")

            report(f"👤 @{username or 'unknown'} | 📧 {email}")
            return True, None
        else:
            logger.error("Auth not confirmed")
            report_error("❌ Авторизация не подтверждена")
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
        auth_line = f"👤 <code>@{auth['username']}</code>\n" if auth else "👤 <i>не подключён</i>\n"

        text = (
            "🚗 <b>Selenium X Agent</b> (v2)\n\n"
            f"{auth_line}"
            f"{icon(st['chrome_browser']['found'])} Chrome: <code>{st['chrome_browser']['path'] or 'не найден'}</code>\n"
            f"{icon(st['chromedriver']['ready'])} Driver: <code>{st['chromedriver']['path'] or 'не найден'}</code>\n"
            f"{icon(st['selenium_pip']['installed'])} Selenium pip: {'установлен' if st['selenium_pip']['installed'] else 'не установлен'}\n"
            f"{'🟢' if st['agent_ready'] else '🔴'} Готов: {'Да' if st['agent_ready'] else 'Нет'}\n"
            f"🍪 Cookies: {'есть' if st['cookies_exist'] else 'нет'}\n"
            f"📁 {st['selenium_dir']}"
        )
        if not st['agent_ready']:
            text += "\n\n⚠️ /se_install"
        elif not auth:
            text += "\n\n⚠️ /se_google — войти"
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

        msg = bot.reply_to(message, "⏳ Скачиваю Chrome 133 + Driver + Selenium...", parse_mode="HTML")
        success = _installer.install()

        if success:
            bot.edit_message_text(
                f"✅ Установлено!\n🌐 <code>{_installer.chrome_path}</code>\n🔧 <code>{_installer.driver_path}</code>",
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
        bot.reply_to(message, "🔐 <b>Вход через Google</b>\n\nВведи <b>email</b> от Google:", parse_mode="HTML")
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
        bot.reply_to(message, f"✅ Email: <code>{email}</code>\n\nТеперь введи <b>пароль</b>:", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "google_password")
    def se_google_password(message):
        chat_id = message.chat.id

        # === ЗАЩИТА ОТ ДУБЛЕЙ ===
        msg_id = message.message_id
        if msg_id in _processing_messages:
            logger.warning(f"Duplicate message {msg_id} ignored")
            return
        _processing_messages.add(msg_id)

        password = message.text
        if password.startswith("/"):
            del login_sessions[chat_id]
            _processing_messages.discard(msg_id)
            bot.reply_to(message, "❌ Отменено")
            return

        email = login_sessions[chat_id]["email"]
        del login_sessions[chat_id]

        msg = bot.reply_to(message, "⏳ Вхожу через Google...\n<i>60-120 сек</i>", parse_mode="HTML")

        success, error = run_sync_task(google_login, email, password, bot, chat_id)

        try:
            bot.delete_message(chat_id, msg.message_id)
        except:
            pass

        _processing_messages.discard(msg_id)

        if error:
            bot.reply_to(message, f"❌ {error}", parse_mode="HTML")
            try:
                _send_log_file(bot, chat_id, prefix="❌ Ошибка входа")
            except:
                pass
        elif success:
            auth = get_auth_info()
            username = auth.get("username", "?") if auth else "?"
            bot.reply_to(message, f"✅ <b>Вход успешен!</b>\n👤 @{username}\n📧 {email}", parse_mode="HTML")
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
            "🚗 <b>Selenium X Agent v2</b>\n\n"
            "/se_status — Статус\n"
            "/se_install — Установить Chrome 133\n"
            "/se_google — Войти через Google\n"
            "/se_log — Получить логи\n"
            "/se_logout — Выйти\n"
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
