# selenium_x_agent.py — Вход через Google в X
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
import queue
from pathlib import Path
from datetime import datetime

# === КОНФИГ ===
APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

CHROME_DIR = BASE_DIR / "chrome"
DRIVER_DIR = BASE_DIR / "driver"
COOKIES_FILE = BASE_DIR / "x_cookies.json"
AUTH_FILE = BASE_DIR / "x_auth.json"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
HTML_DIR = BASE_DIR / "html_pages"
REPORT_DIR = BASE_DIR / "reports"
LOG_FILE = BASE_DIR / "agent.log"

for d in [SCREENSHOT_DIR, HTML_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SeleniumXAgent")

# === ВЕРСИИ ===
CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"
CHROME_ZIP = f"{BASE_URL}/chrome-linux64.zip"
DRIVER_ZIP = f"{BASE_URL}/chromedriver-linux64.zip"

# === МОБИЛЬНЫЕ USER-AGENTS ===
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
]

# === СЕССИИ ВВОДА ===
login_sessions = {}


class ChromeInstaller:
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
    
    def _find_existing(self):
        local_chrome = CHROME_DIR / "chrome-linux64" / "chrome"
        local_driver = DRIVER_DIR / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"Chrome найден: {self.chrome_path}")
        
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"Driver найден: {self.driver_path}")
        
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                if path := self._which(name):
                    self.chrome_path = path
                    break
        
        if not self.driver_path:
            self.driver_path = self._which("chromedriver")
    
    @staticmethod
    def _which(cmd: str) -> str | None:
        try:
            result = subprocess.run(["which", cmd], capture_output=True, text=True, timeout=5, check=True)
            return result.stdout.strip() or None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    
    @property
    def ready(self) -> bool:
        return bool(self.chrome_path and self.driver_path)
    
    def status(self) -> dict:
        return {
            "chrome": {"found": bool(self.chrome_path), "path": self.chrome_path},
            "driver": {"found": bool(self.driver_path), "path": self.driver_path},
            "ready": self.ready,
            "base_dir": str(BASE_DIR)
        }
    
    def install(self) -> bool:
        logger.info("=" * 50)
        logger.info("Начинаю установку Chrome + Driver")
        success = True
        if not self.chrome_path:
            if not self._download_chrome():
                success = False
        if not self.driver_path:
            if not self._download_driver():
                success = False
        logger.info(f"Установка завершена: ready={self.ready}")
        return success
    
    def _download(self, url: str, dest: Path) -> bool:
        try:
            logger.info(f"Скачивание: {url}")
            urllib.request.urlretrieve(url, dest)
            size = dest.stat().st_size
            logger.info(f"Скачано: {size:,} bytes")
            return True
        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return False
    
    def _extract(self, zip_path: Path, dest_dir: Path) -> bool:
        try:
            logger.info(f"Распаковка: {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(dest_dir)
            zip_path.unlink()
            logger.info("Распаковка завершена")
            return True
        except Exception as e:
            logger.error(f"Ошибка распаковки: {e}")
            return False
    
    def _make_executable(self, path: Path):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
            logger.info(f"Права на выполнение: {path}")
        except Exception as e:
            logger.error(f"Ошибка chmod: {e}")
    
    def _download_chrome(self) -> bool:
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
        logger.error("Chrome бинарник не найден после распаковки")
        return False
    
    def _download_driver(self) -> bool:
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
        logger.error("Driver бинарник не найден после распаковки")
        return False


# === ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ===
_installer = ChromeInstaller()


def get_full_status():
    auth = get_auth_info()
    return {
        "selenium_pip": {"installed": False, "version": None},
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
        logger.error(f"Auth read error: {e}")
        return None


def save_auth_info(username, email=None, extra=None):
    try:
        data = {
            "username": str(username),
            "email": email,
            "authorized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            data.update(extra)
        with open(AUTH_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Auth saved: @{username}")
        return True
    except Exception as e:
        logger.error(f"Auth save error: {e}")
        return False


def clear_auth_info():
    try:
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
        if COOKIES_FILE.exists():
            COOKIES_FILE.unlink()
        return True
    except Exception as e:
        logger.error(f"Clear auth error: {e}")
        return False


def icon(flag: bool) -> str:
    return "✅" if flag else "❌"


def run_sync_task(func, *args, **kwargs):
    """Запуск функции в потоке с таймаутом"""
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
    """Сессия Selenium с анти-детектом"""
    
    def __init__(self):
        self.driver = None
        self._chat_id = None
        self._bot = None
        self._progress_msg = None
    
    def set_chat(self, bot, chat_id):
        self._bot = bot
        self._chat_id = chat_id
    
    def _report(self, text):
        logger.info(text)
        if self._bot and self._chat_id:
            try:
                self._bot.send_message(self._chat_id, text, parse_mode="HTML")
            except Exception as e:
                logger.debug(f"Report error: {e}")
    
    def _screenshot(self, name, caption=None):
        try:
            path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
            self.driver.save_screenshot(str(path))
            logger.info(f"Screenshot: {path}")
            if self._bot and self._chat_id and path.exists():
                with open(path, "rb") as f:
                    self._bot.send_photo(self._chat_id, f, caption=caption or f"📸 {name}")
            return str(path)
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None
    
    def _save_html(self, name):
        try:
            path = HTML_DIR / f"{name}_{int(time.time())}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            return str(path)
        except Exception as e:
            logger.error(f"HTML save error: {e}")
            return None
    
    def _get_options(self):
        from selenium.webdriver.chrome.options import Options
        import random
        
        options = Options()
        options.add_argument(f"--user-agent={random.choice(MOBILE_USER_AGENTS)}")
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
        
        logger.info("Creating driver...")
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Скрываем webdriver
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        logger.info(f"Driver created: {self.driver.session_id}")
        return self.driver
    
    def load_cookies(self):
        if not COOKIES_FILE.exists():
            return False
        try:
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            for cookie in cookies:
                cookie.pop("sameSite", None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Cookie error: {e}")
            logger.info(f"Loaded {len(cookies)} cookies")
            return True
        except Exception as e:
            logger.error(f"Load cookies error: {e}")
            return False
    
    def save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            logger.info(f"Saved {len(cookies)} cookies")
            return True
        except Exception as e:
            logger.error(f"Save cookies error: {e}")
            return False
    
    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            logger.info("Driver quit")
    
    def __enter__(self):
        self.create()
        return self
    
    def __exit__(self, *args):
        self.quit()
        return False


# === GOOGLE LOGIN ===
def google_login(email, password, bot=None, chat_id=None):
    """Вход в X через Google"""
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
        
        # === ИЩЕМ КНОПКУ GOOGLE ===
        from selenium.webdriver.common.by import By
        
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        
        # Способ 1: По тексту
        try:
            google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Continue with Google')]")
            report("✅ Найдена: 'Continue with Google'")
        except:
            pass
        
        # Способ 2: По части текста
        if not google_btn:
            try:
                google_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Google')]")
                report("✅ Найден элемент с 'Google'")
            except:
                pass
        
        # Способ 3: По aria-label
        if not google_btn:
            try:
                google_btn = session.driver.find_element(By.CSS_SELECTOR, '[aria-label*="Google" i]')
                report("✅ Найдена по aria-label")
            except:
                pass
        
        if not google_btn:
            report("❌ Кнопка Google НЕ найдена!")
            session._save_html("no_google_btn")
            return False
        
        # === КЛИКАЕМ ===
        report("🖱️ Кликаю по Google...")
        google_btn.click()
        time.sleep(3)
        
        session._screenshot("google_redirect", "📸 После клика Google")
        
        # === ЖДЁМ GOOGLE LOGIN ===
        report("⏳ Жду страницу Google...")
        time.sleep(5)
        
        current_url = session.driver.current_url
        report(f"📍 URL: {current_url[:80]}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ Перешли на Google!")
            
            # Вводим email
            try:
                email_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
                email_field.send_keys(email)
                report(f"✅ Email введён")
                
                # Далее
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(text(), 'Далее')]")
                next_btn.click()
                time.sleep(3)
            except Exception as e:
                report(f"⚠️ Email input: {e}")
            
            # Вводим пароль
            try:
                time.sleep(3)
                pass_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(text(), 'Далее')]")
                next_btn.click()
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password input: {e}")
            
            session._screenshot("google_after_login", "📸 После входа в Google")
        
        # === ЖДЁМ РЕДИРЕКТ НА X ===
        report("⏳ Жду редирект на X...")
        for i in range(10):
            time.sleep(2)
            url = session.driver.current_url
            report(f"⏳ Попытка {i+1}: {url[:60]}")
            
            if "x.com" in url and "login" not in url:
                report("✅ Вошли в X!")
                break
        
        # === ПРОВЕРЯЕМ АВТОРИЗАЦИЮ ===
        session.driver.get("https://x.com/home")
        time.sleep(5)
        session._screenshot("x_home", "📸 X Home")
        
        html = session.driver.page_source.lower()
        if "home" in html or "following" in html or "for you" in html:
            report("✅ Авторизация подтверждена!")
            
            # Получаем username
            username = "unknown"
            try:
                session.driver.get("https://x.com/settings/account")
                time.sleep(3)
                # Или ищем в HTML
                match = session.driver.page_source
                # Простой способ — сохранить куки и отметить успех
            except:
                pass
            
            session.save_cookies()
            save_auth_info(username, email)
            return True
        else:
            report("❌ Не удалось войти в X")
            return False
            
    except Exception as e:
        report(f"❌ <b>Ошибка:</b> {str(e)[:200]}")
        logger.error(traceback.format_exc())
        return False
    finally:
        session.quit()


# === РЕГИСТРАЦИЯ КОМАНД ===
def register_selenium_bot(bot):
    logger.info("Регистрация Selenium команд...")
    
    def get_user_input(chat_id, prompt, timeout=60):
        """Запросить ввод от пользователя"""
        login_sessions[chat_id] = {
            "awaiting": True,
            "prompt": prompt,
            "received": None
        }
        bot.send_message(chat_id, prompt, parse_mode="HTML")
        
        start = time.time()
        while time.time() - start < timeout:
            if login_sessions[chat_id].get("received") is not None:
                result = login_sessions[chat_id]["received"]
                login_sessions[chat_id]["awaiting"] = False
                return result
            time.sleep(0.5)
        
        login_sessions[chat_id]["awaiting"] = False
        return None
    
    @bot.message_handler(commands=["se_status"])
    def se_status(message):
        st = get_full_status()
        auth = st.get("auth_info")
        
        if auth:
            auth_line = f"👤 <code>@{auth['username']}</code> ({auth['authorized_at']})\n"
        else:
            auth_line = "👤 <i>не подключён</i>\n"
        
        text = (
            "🚗 <b>Selenium X Agent</b>\n\n"
            f"{auth_line}"
            f"{icon(st['chrome_browser']['found'])} Chrome: <code>{st['chrome_browser']['path'] or 'не найден'}</code>\n"
            f"{icon(st['chromedriver']['ready'])} Driver: <code>{st['chromedriver']['path'] or 'не найден'}</code>\n"
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
            bot.reply_to(message, "🟢 Уже установлено!", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Скачиваю Chrome + Driver...", parse_mode="HTML")
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
        
        # Запрашиваем email
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
        
        def do_login():
            return google_login(email, password, bot=bot, chat_id=chat_id)
        
        success, error = run_sync_task(do_login)
        
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
            bot.reply_to(message, "❌ Вход не удался. Проверь данные и попробуй снова.", parse_mode="HTML")
    
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
    
    # Обработчик отмены
    @bot.message_handler(commands=["se_cancel"])
    def se_cancel(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Отменено")
    
    logger.info("Selenium команды зарегистрированы")


logger.info(f"Module loaded. Chrome ready: {_installer.ready}")
