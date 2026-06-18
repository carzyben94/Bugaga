# selenium_x_agent.py — Selenium X/Twitter агент с прогрессом авторизации
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

# === НАСТРОЙКА ПУТЕЙ ===
SELENIUM_DIR = os.environ.get("SELENIUM_DIR", os.path.join(tempfile.gettempdir(), "selenium_agent"))
os.makedirs(SELENIUM_DIR, exist_ok=True)

CHROME_DIR = os.path.join(SELENIUM_DIR, "chrome")
DRIVER_DIR = os.path.join(SELENIUM_DIR, "driver")
COOKIES_FILE = os.path.join(SELENIUM_DIR, "x_cookies.json")
SCREENSHOT_DIR = os.path.join(SELENIUM_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(CHROME_DIR, exist_ok=True)
os.makedirs(DRIVER_DIR, exist_ok=True)

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except Exception as e:
        return False, "", str(e)


def _download_file(url, dest):
    try:
        print(f"[SE] Скачиваю: {url}")
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"[SE] Ошибка скачивания: {e}")
        return False


def _extract_zip(zip_path, dest_dir):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(dest_dir)
        return True
    except Exception as e:
        print(f"[SE] Ошибка распаковки: {e}")
        return False


def _make_executable(path):
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC)
        return True
    except:
        return False


def check_selenium_pip():
    global SELENIUM_INSTALLED
    try:
        import selenium
        SELENIUM_INSTALLED = True
        return True, selenium.__version__
    except ImportError:
        SELENIUM_INSTALLED = False
        return False, None


def install_selenium_pip():
    global SELENIUM_INSTALLED
    print("[SE] Установка selenium pip...")
    ok, _, err = _run_subprocess([sys.executable, "-m", "pip", "install", "selenium"], timeout=120)
    if not ok:
        print(f"[SE] Ошибка pip install: {err}")
        return False
    import importlib
    if "selenium" in sys.modules:
        importlib.reload(sys.modules["selenium"])
    SELENIUM_INSTALLED = True
    print("[SE] Selenium pip установлен")
    return True


def check_chrome_binary():
    global CHROME_BROWSER_READY
    chrome_path = os.path.join(CHROME_DIR, "chrome-linux64", "chrome")
    if os.path.exists(chrome_path):
        CHROME_BROWSER_READY = True
        return True, chrome_path
    for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
        ok, out, _ = _run_subprocess(["which", name], timeout=5)
        if ok and out.strip():
            CHROME_BROWSER_READY = True
            return True, out.strip()
    CHROME_BROWSER_READY = False
    return False, None


def download_chrome_portable():
    global CHROME_BROWSER_READY
    print("[SE] Скачиваю Chrome portable...")
    zip_path = os.path.join(SELENIUM_DIR, "chrome.zip")
    if not _download_file(CHROME_DOWNLOAD_URL, zip_path):
        return False
    if not _extract_zip(zip_path, CHROME_DIR):
        return False
    chrome_path = os.path.join(CHROME_DIR, "chrome-linux64", "chrome")
    if os.path.exists(chrome_path):
        _make_executable(chrome_path)
        CHROME_BROWSER_READY = True
        print(f"[SE] Chrome готов: {chrome_path}")
        return True
    return False


def check_driver():
    global DRIVER_READY
    driver_path = os.path.join(DRIVER_DIR, "chromedriver-linux64", "chromedriver")
    if os.path.exists(driver_path):
        DRIVER_READY = True
        return True, driver_path
    ok, out, _ = _run_subprocess(["which", "chromedriver"], timeout=5)
    if ok and out.strip():
        DRIVER_READY = True
        return True, out.strip()
    DRIVER_READY = False
    return False, None


def download_driver():
    global DRIVER_READY
    print("[SE] Скачиваю ChromeDriver...")
    zip_path = os.path.join(SELENIUM_DIR, "driver.zip")
    if not _download_file(DRIVER_DOWNLOAD_URL, zip_path):
        return False
    if not _extract_zip(zip_path, DRIVER_DIR):
        return False
    driver_path = os.path.join(DRIVER_DIR, "chromedriver-linux64", "chromedriver")
    if os.path.exists(driver_path):
        _make_executable(driver_path)
        DRIVER_READY = True
        print(f"[SE] ChromeDriver готов: {driver_path}")
        return True
    return False


def get_full_status():
    pip_ok, pip_ver = check_selenium_pip()
    browser_ok, browser_path = check_chrome_binary()
    driver_ok, driver_path = check_driver()
    global AGENT_READY
    AGENT_READY = pip_ok and browser_ok and driver_ok
    return {
        "selenium_pip": {"installed": pip_ok, "version": pip_ver},
        "chrome_browser": {"found": browser_ok, "path": browser_path},
        "chromedriver": {"ready": driver_ok, "path": driver_path},
        "agent_ready": AGENT_READY,
        "cookies_exist": os.path.exists(COOKIES_FILE),
        "selenium_dir": SELENIUM_DIR,
    }


def full_install():
    global SELENIUM_INSTALLED, CHROME_BROWSER_READY, DRIVER_READY, AGENT_READY
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
    return AGENT_READY


# === Selenium Agent с прогрессом ===

class SeleniumXAgent:
    def __init__(self):
        self.driver = None
        self._cookies_valid = False
        self._progress_callback = None
    
    def set_progress_callback(self, callback):
        """Установить callback для прогресса: callback(step, message)"""
        self._progress_callback = callback
    
    def _report(self, step, message):
        """Отправить прогресс"""
        print(f"[SE] [{step}] {message}")
        if self._progress_callback:
            try:
                self._progress_callback(step, message)
            except Exception as e:
                print(f"[SE] Callback error: {e}")
    
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
        return options
    
    def _create_driver(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        options = self._get_chrome_options()
        driver_ok, driver_path = check_driver()
        if driver_ok and driver_path:
            service = Service(driver_path)
        else:
            service = Service()
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        return self.driver
    
    def _screenshot(self, name):
        try:
            path = os.path.join(SCREENSHOT_DIR, f"{name}_{int(time.time())}.png")
            self.driver.save_screenshot(path)
            print(f"[SE] Screenshot: {path}")
            return path
        except Exception as e:
            print(f"[SE] Screenshot error: {e}")
            return None
    
    def _load_cookies(self):
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            for cookie in cookies:
                cookie.pop("sameSite", None)
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            return True
        except Exception as e:
            print(f"[SE] Cookie load error: {e}")
            return False
    
    def _save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            self._cookies_valid = True
            return True
        except Exception as e:
            print(f"[SE] Cookie save error: {e}")
            return False
    
    def login(self, username, password, email=None):
        """Авторизация с детальным прогрессом"""
        try:
            self._report("start", f"🚀 Начинаю авторизацию как @{username}")
            
            self._report("browser", "🌐 Запускаю Chrome...")
            self._create_driver()
            self._report("browser", "✅ Chrome запущен")
            
            self._report("page", "📄 Открываю страницу входа...")
            self.driver.get("https://x.com/i/flow/login")
            time.sleep(4)
            self._screenshot("login_start")
            self._report("page", f"📄 Страница загружена: {self.driver.title}")
            
            self._report("username", "⌨️ Ввожу username...")
            username_selectors = [
                'input[autocomplete="username"]',
                'input[name="text"]',
                'input[type="text"]',
                'input[autocapitalize="none"]',
                'input[inputmode="text"]',
            ]
            if not self._smart_fill(username_selectors, username, "username"):
                self._screenshot("login_no_username")
                return False, "❌ Поле username не найдено. X мог изменить форму."
            self._report("username", f"✅ Username введён: @{username}")
            
            time.sleep(1)
            
            self._report("next", "➡️ Нажимаю Next...")
            next_selectors = [
                'button[type="submit"]',
                'button:has-text("Next")',
                'button:has-text("Далее")',
                'div[role="button"]:has-text("Next")',
            ]
            self._smart_click(next_selectors, "Next")
            time.sleep(3)
            self._screenshot("login_after_username")
            self._report("next", "✅ Перешли к следующему шагу")
            
            # Проверка доп. верификации
            self._report("verify", "🔍 Проверяю дополнительную верификацию...")
            from selenium.webdriver.common.by import By
            verify_selectors = [
                'input[name="email"]',
                'input[name="phone"]',
                'input[data-testid="ocfEnterTextTextInput"]',
            ]
            for selector in verify_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem.is_displayed():
                        self._report("verify", f"⚠️ Найдено поле верификации: {selector}")
                        if email:
                            self._report("verify", f"⌨️ Ввожу email: {email}")
                            elem.clear()
                            elem.send_keys(email)
                            time.sleep(1)
                            self._smart_click(['button[type="submit"]'], "Next after verify")
                            time.sleep(3)
                            self._report("verify", "✅ Email принят")
                        else:
                            return False, "❌ Требуется email/телефон для верификации. Укажи email."
                except:
                    pass
            self._report("verify", "✅ Дополнительной верификации нет")
            
            self._report("password", "⌨️ Ввожу пароль...")
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
            ]
            if not self._smart_fill(password_selectors, password, "password"):
                try:
                    self.driver.find_element(By.CSS_SELECTOR, 'input[autocomplete="username"]')
                    return False, "❌ Не удалось перейти к паролю. Возможно, неверный username или требуется email."
                except:
                    pass
                return False, "❌ Поле пароля не найдено"
            self._report("password", "✅ Пароль введён")
            
            time.sleep(1)
            
            self._report("submit", "🔓 Нажимаю Log in...")
            login_selectors = [
                'button[data-testid="LoginForm_Login_Button"]',
                'button:has-text("Log in")',
                'button:has-text("Войти")',
                'button[type="submit"]',
            ]
            self._smart_click(login_selectors, "Log in")
            self._report("submit", "⏳ Жду ответа сервера...")
            
            time.sleep(5)
            self._screenshot("login_after_submit")
            
            # Проверка результата
            current_url = self.driver.current_url
            self._report("check", f"🔍 Проверяю результат... URL: {current_url}")
            
            if "home" in current_url:
                self._save_cookies()
                self._report("success", "🏠 Обнаружена домашняя страница!")
                return True, None
            
            # Проверяем ошибки
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
                    err_text = err.text
                    self._report("error", f"❌ Найдена ошибка: {err_text}")
                    return False, f"❌ Ошибка входа: {err_text}"
                except:
                    pass
            
            # Проверяем, не на странице логина ли
            if "/login" in current_url or "/flow/login" in current_url:
                self._screenshot("login_still_on_page")
                self._report("error", "❌ Всё ещё на странице логина")
                return False, "❌ Всё ещё на странице логина. Возможно:\n• Неверный пароль\n• Требуется верификация\n• Аккаунт заблокирован"
            
            # Проверяем капчу
            try:
                captcha = self.driver.find_element(By.CSS_SELECTOR, 'iframe[src*="captcha"], iframe[src*="recaptcha"]')
                if captcha:
                    self._report("error", "❌ Обнаружена капча")
                    return False, "❌ Обнаружена капча. Автоматический вход невозможен."
            except:
                pass
            
            self._save_cookies()
            self._report("success", "✅ Авторизация прошла (по косвенным признакам)")
            return True, None
            
        except Exception as e:
            self._report("error", f"💥 Критическая ошибка: {str(e)}")
            self._screenshot("login_exception")
            return False, f"💥 Ошибка авторизации: {e}"
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def _smart_fill(self, selectors, value, field_name="поле"):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        for selector in selectors:
            try:
                elem = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                elem.clear()
                elem.send_keys(value)
                print(f"[SE] Заполнено {field_name}: {selector}")
                time.sleep(0.5)
                return True
            except Exception as e:
                print(f"[SE] Не удалось {selector}: {e}")
                continue
        return False
    
    def _smart_click(self, selectors, button_name="кнопка"):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        for selector in selectors:
            try:
                elem = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                elem.click()
                print(f"[SE] Клик {button_name}: {selector}")
                time.sleep(0.5)
                return True
            except Exception as e:
                print(f"[SE] Клик не удался {selector}: {e}")
                continue
        return False
    
    def fetch_timeline(self, username=None, limit=10):
        if not AGENT_READY:
            return None, "Selenium не готов. Используй /se_install"
        try:
            self._create_driver()
            self._load_cookies()
            url = f"https://x.com/{username}" if username else "https://x.com/home"
            self.driver.get(url)
            time.sleep(4)
            from selenium.webdriver.common.by import By
            tweets = []
            last_count = 0
            attempts = 0
            while len(tweets) < limit and attempts < 10:
                articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
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
                    except:
                        pass
                if len(tweets) == last_count:
                    attempts += 1
                else:
                    attempts = 0
                    last_count = len(tweets)
                self.driver.execute_script("window.scrollBy(0, 800)")
                time.sleep(1)
            self._save_cookies()
            return tweets[:limit], None
        except Exception as e:
            return None, f"Ошибка: {e}"
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


# === РЕГИСТРАЦИЯ КОМАНД ===

def register_selenium_bot(bot):
    print("[SE] === REGISTER SELENIUM BOT ===")
    
    @bot.message_handler(commands=["se_status"])
    def se_status_command(message):
        status = get_full_status()
        def icon(flag):
            return "✅" if flag else "❌"
        msg = (
            "🔧 <b>Selenium X Agent — Статус</b>\n\n"
            f"{icon(status['selenium_pip']['installed'])} <b>Selenium pip:</b> "
            f"{'v' + status['selenium_pip']['version'] if status['selenium_pip']['version'] else 'не установлен'}\n"
            f"{icon(status['chrome_browser']['found'])} <b>Chrome браузер:</b> "
            f"<code>{status['chrome_browser']['path'] or 'не найден'}</code>\n"
            f"{icon(status['chromedriver']['ready'])} <b>ChromeDriver:</b> "
            f"<code>{status['chromedriver']['path'] or 'не готов'}</code>\n\n"
            f"{'🟢' if status['agent_ready'] else '🔴'} <b>Agent готов:</b> "
            f"{'Да' if status['agent_ready'] else 'Нет'}\n"
            f"🍪 <b>Cookies:</b> {'есть' if status['cookies_exist'] else 'нет'}\n"
            f"📁 <b>Рабочая директория:</b> <code>{status['selenium_dir']}</code>\n\n"
        )
        if not status['agent_ready']:
            msg += "⚠️ Нажми /se_install для установки\n"
        else:
            msg += "✅ Готов! /se_login для авторизации"
        bot.reply_to(message, msg, parse_mode="HTML")
    
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
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
        bot.reply_to(message,
            "🔐 <b>Авторизация в X (Selenium)</b>\n\n"
            "Введи <b>username</b> (без @):",
            parse_mode="HTML"
        )
        login_sessions[chat_id] = {"step": "username", "method": "selenium"}
        print(f"[SE] Login dialog started for chat {chat_id}")
    
    @bot.message_handler(commands=["se_timeline"])
    def se_timeline_command(message):
        if not AGENT_READY:
            bot.reply_to(message, "❌ Selenium не готов. /se_install")
            return
        args = message.text.split()
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        bot.reply_to(message, f"🐦 Загружаю {'@' + username if username else 'Home'}...")
        tweets, error = run_sync_task(se_agent.fetch_timeline, username, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not tweets:
            bot.reply_to(message, "📭 Твиты не найдены")
            return
        lines = [f"🐦 <b>{'@' + username if username else 'Home'}</b>\n"]
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
    
    @bot.message_handler(commands=["se_help"])
    def se_help_command(message):
        msg = (
            "🚗 <b>Selenium X Agent — команды</b>\n\n"
            "🔧 <b>Настройка</b>\n"
            "  /se_status — Полный статус системы\n"
            "  /se_install — Установить Selenium + Chrome + Driver\n\n"
            "🔐 <b>Авторизация</b>\n"
            "  /se_login — Войти в X (ввод в чате)\n\n"
            "📰 <b>Контент</b>\n"
            "  /se_timeline [user] [N] — Лента\n\n"
            "⚠️ <b>Особенности:</b>\n"
            "• Chrome скачивается автоматически (~150MB)\n"
            "• Работает без apt-get на Render\n"
            "• Cookies сохраняются между сессиями"
        )
        bot.reply_to(message, msg, parse_mode="HTML")
    
    # === Диалог авторизации с прогрессом ===
    
    def is_se_login_dialog(chat_id, step):
        return (chat_id in login_sessions
                and login_sessions[chat_id].get("method") == "selenium"
                and login_sessions[chat_id].get("step") == step)
    
    @bot.message_handler(func=lambda m: is_se_login_dialog(m.chat.id, "username"))
    def se_login_username(message):
        chat_id = message.chat.id
        username = message.text.strip().lstrip("@")
        if username.startswith("/"):
            bot.reply_to(message, "❌ Это команда. Введи username или /se_cancel")
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
        password = message.text
        if password.startswith("/"):
            bot.reply_to(message, "❌ Это команда. Введи пароль или /se_cancel")
            return
        login_sessions[chat_id]["password"] = password
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
        email_text = message.text.strip()
        email = None if email_text.lower() == "skip" else email_text
        creds = login_sessions[chat_id]
        username = creds["username"]
        password = creds["password"]
        
        # Удаляем сообщения с паролем
        try:
            bot.delete_message(chat_id, message.message_id - 1)
            bot.delete_message(chat_id, message.message_id)
        except:
            pass
        
        # Отправляем начальное сообщение
        progress_msg = bot.send_message(chat_id,
            f"🔐 <b>Авторизация @{username}</b>\n\n"
            f"⏳ Подготовка...",
            parse_mode="HTML"
        )
        
        # Очередь для прогресса
        progress_q = queue.Queue()
        
        def update_progress(step, msg_text):
            progress_q.put((step, msg_text))
        
        def progress_worker():
            """Поток для обновления сообщений в Telegram"""
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
                            print(f"[SE] Edit error: {e}")
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"[SE] Progress worker error: {e}")
        
        # Запускаем поток прогресса
        progress_thread = threading.Thread(target=progress_worker)
        progress_thread.start()
        
        # Устанавливаем callback и запускаем авторизацию
        se_agent.set_progress_callback(update_progress)
        
        def do_login():
            result = se_agent.login(username, password, email)
            progress_q.put(("done", ""))
            return result
        
        success, error = run_sync_task(do_login)
        
        # Ждём завершения потока прогресса
        progress_thread.join(timeout=5)
        
        # Очищаем callback
        se_agent.set_progress_callback(None)
        
        # Удаляем сессию
        del login_sessions[chat_id]
        
        # Финальное сообщение
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        
        if error:
            bot.reply_to(message, f"❌ {error}")
        elif success:
            bot.reply_to(message, "✅ Авторизация успешна! Cookies сохранены.\nТеперь /se_timeline")
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
    
    print("[SE] === REGISTER END ===")


# === Инициализация ===
check_selenium_pip()
check_chrome_binary()
check_driver()
