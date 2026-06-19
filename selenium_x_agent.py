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

# === УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ===
class ChatLogHandler(logging.Handler):
    """Хранит последние N логов в памяти для быстрого доступа через /se_logs"""
    def __init__(self, max_lines=500):
        super().__init__()
        self.max_lines = max_lines
        self._lines = []
        self._lock = threading.Lock()
    
    def emit(self, record):
        with self._lock:
            msg = self.format(record)
            self._lines.append(msg)
            if len(self._lines) > self.max_lines:
                self._lines = self._lines[-self.max_lines:]
    
    def get_logs(self, last_n=50):
        with self._lock:
            return "\n".join(self._lines[-last_n:]) if self._lines else "Логи пусты"
    
    def clear(self):
        with self._lock:
            self._lines = []

_chat_handler = ChatLogHandler(max_lines=500)

logging.basicConfig(
    level=logging.DEBUG,  # DEBUG для максимальной детализации
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
        _chat_handler
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
        logger.info(f"[Installer] ready={self.ready}")
    
    def _find_existing(self):
        CHROME_DIR = BASE_DIR / "chrome"
        DRIVER_DIR = BASE_DIR / "driver"
        
        local_chrome = CHROME_DIR / "chrome-linux64" / "chrome"
        local_driver = DRIVER_DIR / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"[Installer] Local Chrome found: {self.chrome_path}")
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"[Installer] Local driver found: {self.driver_path}")
        
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                try:
                    result = subprocess.run(["which", name], capture_output=True, text=True, timeout=5, check=True)
                    self.chrome_path = result.stdout.strip()
                    logger.info(f"[Installer] System Chrome found via 'which {name}': {self.chrome_path}")
                    break
                except:
                    pass
        
        if not self.driver_path:
            try:
                result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True, timeout=5, check=True)
                self.driver_path = result.stdout.strip()
                logger.info(f"[Installer] System chromedriver found: {self.driver_path}")
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
        logger.info("[Installer] Начинаю установку...")
        self._install_selenium_pip()
        success = True
        if not self.chrome_path:
            success = self._download_chrome() and success
        if not self.driver_path:
            success = self._download_driver() and success
        logger.info(f"[Installer] Install result: success={success}")
        return success
    
    def _install_selenium_pip(self):
        try:
            import selenium
            logger.info(f"[Installer] Selenium уже установлен: v{selenium.__version__}")
            return True
        except ImportError:
            logger.info("[Installer] Устанавливаю selenium...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "selenium"],
                    capture_output=True, text=True, timeout=120
                )
                logger.debug(f"[Installer] pip stdout: {result.stdout[:500]}")
                logger.debug(f"[Installer] pip stderr: {result.stderr[:500]}")
                if result.returncode == 0:
                    logger.info("[Installer] Selenium установлен")
                    import importlib
                    if "selenium" in sys.modules:
                        importlib.reload(sys.modules["selenium"])
                    return True
                else:
                    logger.error(f"[Installer] pip install failed: {result.stderr[:500]}")
                    return False
            except Exception as e:
                logger.error(f"[Installer] Ошибка установки selenium: {e}")
                return False
    
    def _download(self, url, dest):
        logger.info(f"[Installer] Downloading: {url} -> {dest}")
        try:
            urllib.request.urlretrieve(url, dest)
            logger.info(f"[Installer] Download OK: {dest}")
            return True
        except Exception as e:
            logger.error(f"[Installer] Download error: {e}")
            return False
    
    def _extract(self, zip_path, dest_dir):
        logger.info(f"[Installer] Extracting: {zip_path} -> {dest_dir}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(dest_dir)
            zip_path.unlink()
            logger.info(f"[Installer] Extract OK")
            return True
        except Exception as e:
            logger.error(f"[Installer] Extract error: {e}")
            return False
    
    def _make_executable(self, path):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
            logger.debug(f"[Installer] Made executable: {path}")
        except Exception as e:
            logger.warning(f"[Installer] chmod failed: {e}")
    
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
            logger.info(f"[Installer] Chrome ready: {self.chrome_path}")
            return True
        logger.error("[Installer] Chrome binary not found after extract")
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
            logger.info(f"[Installer] Driver ready: {self.driver_path}")
            return True
        logger.error("[Installer] Driver binary not found after extract")
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
    except Exception as e:
        logger.warning(f"[Auth] Failed to read auth file: {e}")
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
        logger.info(f"[Auth] Saved auth for {username}")
        return True
    except Exception as e:
        logger.error(f"[Auth] Failed to save auth: {e}")
        return False


def clear_auth_info():
    try:
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
        if COOKIES_FILE.exists():
            COOKIES_FILE.unlink()
        logger.info("[Auth] Auth and cookies cleared")
        return True
    except Exception as e:
        logger.error(f"[Auth] Failed to clear auth: {e}")
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
        logger.info(f"[Chat] {text}")
        if self._bot and self._chat_id:
            try:
                self._bot.send_message(self._chat_id, text, parse_mode="HTML")
            except Exception as e:
                logger.debug(f"[Chat] send_message failed: {e}")
    
    def _screenshot(self, name, caption=None):
        try:
            path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
            self.driver.save_screenshot(str(path))
            logger.info(f"[Screenshot] Saved: {path}")
            if self._bot and self._chat_id and path.exists():
                with open(path, "rb") as f:
                    self._bot.send_photo(self._chat_id, f, caption=caption or f"📸 {name}")
            return str(path)
        except Exception as e:
            logger.warning(f"[Screenshot] Failed: {e}")
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
        
        # === USER DATA DIR — решает ошибку директории ===
        user_data_dir = BASE_DIR / "chrome_user_data"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")
        logger.debug(f"[Browser] user-data-dir: {user_data_dir}")
        
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        if _installer.chrome_path:
            options.binary_location = _installer.chrome_path
            logger.debug(f"[Browser] binary: {_installer.chrome_path}")
        return options
    
    def create(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        options = self._get_options()
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        logger.info(f"[Browser] Creating driver...")
        logger.info(f"[Browser] Chrome path: {_installer.chrome_path}")
        logger.info(f"[Browser] Driver path: {_installer.driver_path}")
        
        try:
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info(f"[Browser] Driver created OK")
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            logger.info("[Browser] webdriver property hidden")
        except Exception as e:
            logger.error(f"[Browser] FAILED to create driver: {e}")
            raise
        
        return self.driver
    
    def save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            logger.info(f"[Browser] Cookies saved: {len(cookies)} cookies")
            return True
        except Exception as e:
            logger.error(f"[Browser] Failed to save cookies: {e}")
            return False
    
    def quit(self):
        if self.driver:
            try:
                logger.info("[Browser] Quitting driver...")
                self.driver.quit()
            except Exception as e:
                logger.warning(f"[Browser] Quit error: {e}")
            self.driver = None


# === GOOGLE LOGIN С РАСШИРЕННЫМ ЛОГИРОВАНИЕМ ===
def google_login(email, password, bot=None, chat_id=None):
    logger.info(f"[Login] START google_login for email={email[:3]}***")
    
    try:
        import selenium
        logger.info(f"[Login] Selenium v{selenium.__version__}")
    except ImportError:
        logger.warning("[Login] Selenium not found, installing...")
        _installer._install_selenium_pip()
        try:
            import selenium
        except ImportError:
            logger.error("[Login] Selenium install failed")
            return False, "Selenium не удалось установить"
    
    session = BrowserSession()
    if bot and chat_id:
        session.set_chat(bot, chat_id)
    
    def report(text):
        logger.info(f"[Login] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    try:
        report("⏳ Запускаю браузер...")
        session.create()
        
        report("📥 Открываю x.com/login...")
        logger.info("[Login] Navigating to https://x.com/login")
        session.driver.get("https://x.com/login")
        time.sleep(5)
        
        current_url = session.driver.current_url
        logger.info(f"[Login] x.com/login loaded. URL: {current_url}")
        logger.debug(f"[Login] Page title: {session.driver.title}")
        session._screenshot("login_page", "📸 Страница входа X")
        
        from selenium.webdriver.common.by import By
        
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        page_source = session.driver.page_source
        logger.debug(f"[Login] Page source length: {len(page_source)}")
        
        # Ищем кнопку Google
        try:
            google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Continue with Google')]")
            report("✅ Найдена: 'Continue with Google'")
            logger.info("[Login] Found: 'Continue with Google'")
        except Exception as e:
            logger.debug(f"[Login] 'Continue with Google' not found: {e}")
        
        if not google_btn:
            try:
                google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Google')]")
                report("✅ Найден элемент с 'Google'")
                logger.info("[Login] Found: 'Google'")
            except Exception as e:
                logger.debug(f"[Login] 'Google' not found: {e}")
        
        if not google_btn:
            logger.error("[Login] Google button NOT found on page!")
            logger.debug(f"[Login] Page source snippet: {page_source[:2000]}")
            report("❌ Кнопка Google НЕ найдена!")
            return False, "Кнопка Google не найдена"
        
        report("🖱️ Кликаю по Google...")
        logger.info("[Login] Clicking Google button")
        google_btn.click()
        time.sleep(5)
        
        session._screenshot("google_redirect", "📸 После клика")
        
        current_url = session.driver.current_url
        report(f"📍 URL: {current_url[:80]}")
        logger.info(f"[Login] After click URL: {current_url}")
        logger.info(f"[Login] After click title: {session.driver.title}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ Перешли на Google!")
            logger.info("[Login] On Google auth page")
            
            # Email
            try:
                logger.info("[Login] Looking for email field...")
                email_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
                email_field.send_keys(email)
                report("✅ Email введён")
                logger.info("[Login] Email entered")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                next_btn.click()
                logger.info("[Login] Next clicked after email")
                time.sleep(3)
            except Exception as e:
                report(f"⚠️ Email step error: {e}")
                logger.error(f"[Login] Email step failed: {e}")
                session._screenshot("email_error", "📸 Ошибка email")
            
            # Password
            try:
                time.sleep(3)
                logger.info("[Login] Looking for password field...")
                pass_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                logger.info("[Login] Password entered")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                next_btn.click()
                logger.info("[Login] Next clicked after password")
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password step error: {e}")
                logger.error(f"[Login] Password step failed: {e}")
                session._screenshot("password_error", "📸 Ошибка пароля")
            
            # Проверяем, нет ли капчи/доп. проверки
            time.sleep(3)
            current_url = session.driver.current_url
            logger.info(f"[Login] After password URL: {current_url}")
            session._screenshot("google_after_login", "📸 После входа в Google")
            
            if "challenge" in current_url or "interstitial" in current_url:
                logger.warning(f"[Login] Google challenge detected! URL: {current_url}")
                report("⚠️ Google требует дополнительную проверку (капча/2FA)")
        
        # Ждём редирект на X
        report("⏳ Жду редирект на X...")
        x_reached = False
        for i in range(10):
            time.sleep(2)
            url = session.driver.current_url
            logger.info(f"[Login] Wait loop {i+1}/10: {url}")
            if "x.com" in url and "login" not in url:
                report("✅ Вошли в X!")
                logger.info("[Login] X reached!")
                x_reached = True
                break
        
        if not x_reached:
            logger.warning("[Login] X not reached after 20 seconds")
        
        session.driver.get("https://x.com/home")
        time.sleep(5)
        current_url = session.driver.current_url
        logger.info(f"[Login] x.com/home URL: {current_url}")
        logger.info(f"[Login] x.com/home title: {session.driver.title}")
        session._screenshot("x_home", "📸 X Home")
        
        html = session.driver.page_source.lower()
        logger.debug(f"[Login] x.com/home source length: {len(html)}")
        
        # Проверяем авторизацию
        auth_indicators = ["home", "following", "for you", "compose", "logout", "settings"]
        found_indicators = [ind for ind in auth_indicators if ind in html]
        logger.info(f"[Login] Auth indicators found: {found_indicators}")
        
        if found_indicators:
            report(f"✅ Авторизация подтверждена! Индикаторы: {found_indicators}")
            logger.info("[Login] AUTH SUCCESS")
            session.save_cookies()
            save_auth_info("google_user", email)
            return True, None
        else:
            report("❌ Не удалось войти в X")
            logger.error("[Login] AUTH FAILED — no indicators found")
            logger.debug(f"[Login] Page source: {html[:3000]}")
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"[Login] CRITICAL ERROR: {e}")
        logger.error(traceback.format_exc())
        return False, str(e)
    finally:
        logger.info("[Login] END — quitting session")
        session.quit()


# === AGENT_READY ===
def AGENT_READY():
    return _installer.ready


# === РЕГИСТРАЦИЯ КОМАНД ===
def register_selenium_bot(bot):
    logger.info("[Bot] Регистрация команд...")
    
    @bot.message_handler(commands=["se_status"])
    def se_status(message):
        st = get_full_status()
        auth = st.get("auth_info")
        auth_line = f"👤 <code>@{auth['username']}</code>\n" if auth else "👤 <i>не подключён</i>\n"
        
        text = (
            "🚗 <b>Selenium X Agent</b>\n\n"
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
            bot.reply_to(message, f"✅ <b>Вход успешен!</b>\n👤 @{auth['username'] if auth else '?'}\n📧 {email}", parse_mode="HTML")
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
            "/se_logs — Посмотреть логи\n"
            "/se_logs_clear — Очистить логи\n"
            "/se_help — Помощь"
        ), parse_mode="HTML")
    
    @bot.message_handler(commands=["se_cancel"])
    def se_cancel(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
    
    # === НОВЫЕ КОМАНДЫ ЛОГОВ ===
    @bot.message_handler(commands=["se_logs"])
    def se_logs(message):
        """Отправляет последние логи в чат файлом"""
        logger.info(f"[Bot] /se_logs requested by user {message.from_user.id}")
        
        # 1. Отправляем последние строки текстом
        recent = _chat_handler.get_logs(last_n=30)
        preview = f"<b>📝 Последние логи:</b>\n<pre>{recent[:3500]}</pre>"
        bot.reply_to(message, preview, parse_mode="HTML")
        
        # 2. Отправляем полный лог файлом
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "rb") as f:
                    bot.send_document(
                        message.chat.id,
                        f,
                        caption="📄 Полный лог-файл",
                        visible_file_name="agent.log"
                    )
                logger.info("[Bot] Log file sent")
            else:
                bot.reply_to(message, "❌ Лог-файл не найден", parse_mode="HTML")
        except Exception as e:
            logger.error(f"[Bot] Failed to send log file: {e}")
            bot.reply_to(message, f"❌ Ошибка отправки файла: {e}", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logs_clear"])
    def se_logs_clear(message):
        """Очищает логи в памяти"""
        _chat_handler.clear()
        bot.reply_to(message, "🧹 Логи в памяти очищены", parse_mode="HTML")
        logger.info("[Bot] Logs cleared by user")
    
    logger.info("[Bot] Команды зарегистрированы")


logger.info(f"[Module] Загружен. ready={_installer.ready}")
