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
        """Установить selenium как в старом коде"""
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
    
    def _save_html(self, name):
        try:
            html = self.driver.page_source
            html_path = BASE_DIR / f"{name}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            return str(html_path)
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
            except:
                pass
    
    try:
        report("⏳ Запускаю браузер...")
        session.create()
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # === ШАГ 0: Заходим на x.com ===
        report("📥 Открываю x.com...")
        session.driver.get("https://x.com")
        time.sleep(6)
        session._screenshot("step0_x_com", "📸 Шаг 0: x.com")
        session._save_html("step0_x_com")
        
        current_url = session.driver.current_url
        title = session.driver.title
        report(f"📍 URL: {current_url}")
        report(f"📰 Title: {title}")
        
        # === ШАГ 0.5: Если попали на onboarding — работаем с ним ===
        if "onboarding" in current_url or "mode=login" in current_url:
            report("🔀 Обнаружен onboarding flow!")
            
            try:
                body_text = session.driver.find_element(By.TAG_NAME, "body").text
                report(f"📄 Текст onboarding:\n{body_text[:1000]}")
            except:
                pass
            
            onboarding_xpaths = [
                "//span[contains(text(), 'Continue with Google')]",
                "//span[contains(text(), 'Sign in with Google')]",
                "//span[contains(text(), 'Google')]",
                "//div[contains(text(), 'Continue with Google')]",
                "//div[contains(text(), 'Sign in with Google')]",
                "//div[contains(text(), 'Google')]",
                "//button[.//*[contains(text(), 'Google')]]",
                "//div[@role='button' and .//*[contains(text(), 'Google')]]",
                "//a[contains(@href, 'google')]",
                "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]",
                "//div[@data-testid and contains(., 'Google')]",
                "//div[contains(@class, 'google')]",
            ]
            
            google_btn = None
            for xp in onboarding_xpaths:
                try:
                    elements = session.driver.find_elements(By.XPATH, xp)
                    if elements:
                        google_btn = elements[0]
                        report(f"✅ Найдено на onboarding: {xp[:50]}")
                        break
                except:
                    continue
            
            if not google_btn:
                report("🔍 Перебираю все кнопки...")
                all_buttons = session.driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //a")
                report(f"   Всего: {len(all_buttons)}")
                for idx, btn in enumerate(all_buttons[:25]):
                    try:
                        text = btn.text or btn.get_attribute("aria-label") or btn.get_attribute("title") or ""
                        href = btn.get_attribute("href") or ""
                        if text or href:
                            report(f"   [{idx}] {text[:50]} | href={href[:50]}")
                            if "google" in (text + href).lower():
                                google_btn = btn
                                report(f"   ✅ Это Google!")
                                break
                    except:
                        pass
            
            if google_btn:
                report("🖱️ Кликаю по Google...")
                try:
                    session.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", google_btn)
                    time.sleep(1)
                    google_btn.click()
                except:
                    href = google_btn.get_attribute("href")
                    if href:
                        report(f"🔗 Переход по href: {href[:100]}")
                        session.driver.get(href)
                    else:
                        session.driver.execute_script("arguments[0].click();", google_btn)
                
                time.sleep(5)
                session._screenshot("after_google_click", "📸 После клика Google")
            else:
                report("❌ Google не найден на onboarding!")
                session._screenshot("no_google_onboarding", "📸 Нет Google")
                return False, "Google не найден на onboarding-странице"
        
        else:
            # === СТАРЫЙ ФЛОУ ===
            report("✅ Остались на x.com, ищу Sign in...")
            sign_in_selectors = [
                "//span[contains(text(), 'Sign in')]",
                "//span[contains(text(), 'Log in')]",
                "//a[contains(@href, '/login')]",
                "//a[contains(@href, '/i/flow/login')]",
                "//div[@role='button' and .//*[contains(text(), 'Sign in')]]",
                "//div[@role='button' and .//*[contains(text(), 'Log in')]]",
                "//button[.//*[contains(text(), 'Sign in')]]",
                "//button[.//*[contains(text(), 'Log in')]]",
            ]
            sign_in_btn = None
            for sel in sign_in_selectors:
                elements = session.driver.find_elements(By.XPATH, sel)
                if elements:
                    sign_in_btn = elements[0]
                    report(f"✅ Найден 'Sign in' по: {sel[:50]}")
                    break
            
            if sign_in_btn:
                report("🖱️ Кликаю 'Sign in'...")
                session.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sign_in_btn)
                time.sleep(1)
                try:
                    sign_in_btn.click()
                except:
                    session.driver.execute_script("arguments[0].click();", sign_in_btn)
                time.sleep(4)
                session._screenshot("after_signin", "📸 После Sign in")
                session._save_html("after_signin")
            else:
                report("⚠️ Sign in не найден, пробую /login напрямую...")
                session.driver.get("https://x.com/i/flow/login")
                time.sleep(4)
                session._screenshot("direct_login", "📸 Прямой login")
                session._save_html("direct_login")
            
            report("🔍 Ищу Google...")
            time.sleep(3)
            
            google_btn = None
            xpaths = [
                "//span[contains(text(), 'Continue with Google')]",
                "//span[contains(text(), 'Sign in with Google')]",
                "//span[contains(text(), 'Google')]",
                "//div[contains(text(), 'Continue with Google')]",
                "//div[contains(text(), 'Sign in with Google')]",
                "//div[contains(text(), 'Google')]",
                "//button[.//*[contains(text(), 'Google')]]",
                "//a[.//*[contains(text(), 'Google')]]",
                "//div[@role='button' and .//*[contains(text(), 'Google')]]",
                "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'google')]",
            ]
            
            for xp in xpaths:
                try:
                    elements = session.driver.find_elements(By.XPATH, xp)
                    if elements:
                        google_btn = elements[0]
                        report(f"✅ Найдено: {xp[:50]}")
                        break
                except:
                    continue
            
            if not google_btn:
                report("❌ Google не найден!")
                return False, "Кнопка Google не найдена"
            
            report("🖱️ Кликаю Google...")
            try:
                session.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", google_btn)
                time.sleep(1)
                google_btn.click()
            except:
                href = google_btn.get_attribute("href")
                if href:
                    session.driver.get(href)
                else:
                    session.driver.execute_script("arguments[0].click();", google_btn)
            
            time.sleep(5)
            session._screenshot("after_google", "📸 После Google")
        
        # === Google Auth Flow ===
        current_url = session.driver.current_url
        report(f"📍 URL: {current_url[:80]}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ На странице Google!")
            
            try:
                email_field = WebDriverWait(session.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
                )
                email_field.clear()
                email_field.send_keys(email)
                report("✅ Email введён")
                time.sleep(1)
                email_field.send_keys(Keys.RETURN)
                time.sleep(4)
            except Exception as e:
                report(f"⚠️ Email: {e}")
            
            try:
                pass_field = WebDriverWait(session.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
                )
                pass_field.clear()
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                time.sleep(1)
                pass_field.send_keys(Keys.RETURN)
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password: {e}")
            
            session._screenshot("google_done", "📸 После Google login")
        
        # === Ждём редиректа ===
        report("⏳ Жду редирект на X...")
        for i in range(15):
            time.sleep(2)
            url = session.driver.current_url
            report(f"  [{i+1}/15] {url[:70]}")
            
            if "x.com/home" in url:
                report("✅ Домашняя страница!")
                break
            if "x.com" in url and "login" not in url and "flow" not in url and "onboarding" not in url:
                report("✅ Вошли в X!")
                break
        
        # === ЗАБИРАЕМ ИНФОРМАЦИЮ О ПОЛЬЗОВАТЕЛЕ ===
        username = None
        followers = None
        following = None
        
        try:
            session.driver.get("https://x.com/home")
            time.sleep(5)
            session._screenshot("home_for_info", "📸 Home для получения информации")
            
            # Способ 1: из URL профиля в сайдбаре
            profile_links = session.driver.find_elements(By.XPATH, "//a[contains(@href, '/')]//span[contains(text(), '@')]")
            if profile_links:
                username = profile_links[0].text.replace("@", "").strip()
                report(f"✅ Имя из сайдбара: @{username}")
            
            # Способ 2: data-testid
            if not username:
                try:
                    user_element = session.driver.find_element(By.XPATH, "//div[@data-testid='UserName']//span[starts-with(text(), '@')]")
                    username = user_element.text.replace("@", "").strip()
                    report(f"✅ Имя из UserName: @{username}")
                except:
                    pass
            
            # Способ 3: из заголовка страницы
            if not username:
                title = session.driver.title
                if "@" in title:
                    username = title.split("@")[1].split()[0].strip()
                    report(f"✅ Имя из title: @{username}")
            
            # Способ 4: из cookies или localStorage
            if not username:
                try:
                    username = session.driver.execute_script("return window.__INITIAL_STATE__?.session?.user_id")
                    report(f"✅ user_id из INITIAL_STATE: {username}")
                except:
                    pass
            
            # Способ 5: любой span с @ на странице
            if not username:
                spans = session.driver.find_elements(By.XPATH, "//span[starts-with(text(), '@')]")
                for sp in spans:
                    text = sp.text.strip()
                    if text.startswith("@") and len(text) > 1 and " " not in text:
                        username = text.replace("@", "")
                        report(f"✅ Имя из span: @{username}")
                        break
            
            # === ПОДПИСЧИКИ И ПОДПИСКИ ===
            if username:
                report(f"🔍 Ищу подписчиков и подписки...")
                
                # Переходим на профиль
                session.driver.get(f"https://x.com/{username}")
                time.sleep(4)
                session._screenshot("profile_page", f"📸 Профиль @{username}")
                session._save_html("profile_page")
                
                # Способ 1: через aria-label или текст ссылки
                try:
                    stats = session.driver.find_elements(By.XPATH, 
                        "//a[contains(@href, '/following')] | //a[contains(@href, '/followers')] | " +
                        "//span[contains(text(), 'following')] | //span[contains(text(), 'followers')] | " +
                        "//span[contains(text(), 'Following')] | //span[contains(text(), 'Followers')]"
                    )
                    
                    for stat in stats:
                        text = stat.text.strip()
                        report(f"📊 Найдено: {text}")
                        
                        if "following" in text.lower() and not following:
                            num = text.split()[0].replace(",", "").replace("K", "000").replace("M", "000000").replace(".", "")
                            try:
                                following = int(num)
                                report(f"✅ Подписки: {following}")
                            except:
                                following = text
                                report(f"✅ Подписки (текст): {following}")
                        
                        if "follower" in text.lower() and not followers:
                            num = text.split()[0].replace(",", "").replace("K", "000").replace("M", "000000").replace(".", "")
                            try:
                                followers = int(num)
                                report(f"✅ Подписчики: {followers}")
                            except:
                                followers = text
                                report(f"✅ Подписчики (текст): {followers}")
                
                except Exception as e:
                    report(f"⚠️ Ошибка получения статистики: {e}")
                
                # Способ 2: через data-testid
                if not followers or not following:
                    try:
                        all_spans = session.driver.find_elements(By.XPATH, "//span")
                        for i, span in enumerate(all_spans):
                            text = span.text.strip().lower()
                            if text == "following" and i > 0:
                                prev_text = all_spans[i-1].text.strip()
                                report(f"📊 Following число: {prev_text}")
                                try:
                                    following = int(prev_text.replace(",", ""))
                                except:
                                    following = prev_text
                            if text == "followers" and i > 0:
                                prev_text = all_spans[i-1].text.strip()
                                report(f"📊 Followers число: {prev_text}")
                                try:
                                    followers = int(prev_text.replace(",", ""))
                                except:
                                    followers = prev_text
                    except Exception as e:
                        report(f"⚠️ Способ 2: {e}")
                
                # Способ 3: через JavaScript
                if not followers or not following:
                    try:
                        stats_js = session.driver.execute_script("""
                            const state = window.__INITIAL_STATE__ || {};
                            const user = state.entities?.users || {};
                            const keys = Object.keys(user);
                            if (keys.length > 0) {
                                const u = user[keys[0]].legacy || {};
                                return {
                                    followers: u.followers_count,
                                    following: u.friends_count
                                };
                            }
                            return null;
                        """)
                        if stats_js:
                            followers = stats_js.get("followers")
                            following = stats_js.get("following")
                            report(f"✅ Из JS: followers={followers}, following={following}")
                    except Exception as e:
                        report(f"⚠️ JS способ: {e}")
        
        except Exception as e:
            report(f"⚠️ Не удалось получить информацию: {e}")
        
        # Финальная проверка
        session._screenshot("final_home", "📸 Финальная проверка")
        
        html = session.driver.page_source.lower()
        if any(k in html for k in ["home", "following", "for you", "для вас", "главная"]):
            report("✅ Авторизация подтверждена!")
            session.save_cookies()
            
            # Сохраняем с подписчиками и подписками
            extra = {}
            if followers is not None:
                extra["followers"] = followers
            if following is not None:
                extra["following"] = following
            
            save_auth_info(username or "unknown", email, extra if extra else None)
            report(f"👤 @{username or 'unknown'} | 📧 {email}")
            if followers:
                report(f"👥 Подписчики: {followers}")
            if following:
                report(f"📌 Подписки: {following}")
            
            return True, None
        else:
            report("❌ Не подтверждено")
            return False, "Не удалось войти"
            
    except Exception as e:
        report(f"❌ Ошибка: {str(e)[:300]}")
        logger.error(traceback.format_exc())
        return False, str(e)
    finally:
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
        
        # Добавляем подписчиков и подписки в статус
        followers_line = ""
        following_line = ""
        if auth:
            if auth.get("followers"):
                followers_line = f"👥 Подписчики: <code>{auth['followers']}</code>\n"
            if auth.get("following"):
                following_line = f"📌 Подписки: <code>{auth['following']}</code>\n"
        
        text = (
            "🚗 <b>Selenium X Agent</b>\n\n"
            f"{auth_line}"
            f"{followers_line}"
            f"{following_line}"
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
        
        msg = bot.reply_to(message, "⏳ Скачиваю Chrome + Driver + Selenium...", parse_mode="HTML")
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
        password = message.text
        if password.startswith("/"):
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
            return
        
        email = login_sessions[chat_id]["email"]
        del login_sessions[chat_id]
        
        msg = bot.reply_to(message, "⏳ Вхожу через Google...\n<i>30-60 сек</i>", parse_mode="HTML")
        
        success, error = run_sync_task(google_login, email, password, bot, chat_id)
        
        try:
            bot.delete_message(chat_id, msg.message_id)
        except:
            pass
        
        if error:
            bot.reply_to(message, f"❌ {error}", parse_mode="HTML")
        elif success:
            auth = get_auth_info()
            username = auth.get("username", "?") if auth else "?"
            followers = auth.get("followers", "")
            following = auth.get("following", "")
            
            extra_lines = ""
            if followers:
                extra_lines += f"\n👥 Подписчики: <code>{followers}</code>"
            if following:
                extra_lines += f"\n📌 Подписки: <code>{following}</code>"
            
            bot.reply_to(message, f"✅ <b>Вход успешен!</b>\n👤 @{username}\n📧 {email}{extra_lines}", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Вход не удался", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logout"])
    def se_logout(message):
        clear_auth_info()
        bot.reply_to(message, "🚪 Сессия очищена", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_help"])
    def se_help(message):
        bot.reply_to(message, (
            "🚗 <b>Selenium X Agent</b>\n\n"
            "/se_status — Статус\n"
            "/se_install — Установить Chrome\n"
            "/se_google — Войти через Google\n"
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
