# selenium_x_agent.py — Рабочий + вход через Google в X (Desktop версия)
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
from datetime import datetime

print("[SE] Начало модуля", flush=True)

APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_FILE = BASE_DIR / "x_cookies.json"
AUTH_FILE = BASE_DIR / "x_auth.json"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
LOG_FILE = BASE_DIR / "agent.log"
RESEARCH_DIR = BASE_DIR / "research"
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# === УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ===
class ChatLogHandler(logging.Handler):
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
    level=logging.DEBUG,
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
_research_sessions = {}  # {chat_id: {"driver": ..., "step": ...}}


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
    
    def _screenshot(self, name, caption=None, research=False):
        try:
            subdir = RESEARCH_DIR if research else SCREENSHOT_DIR
            path = subdir / f"{name}_{int(time.time())}.png"
            self.driver.save_screenshot(str(path))
            logger.info(f"[Screenshot] Saved: {path}")
            if self._bot and self._chat_id and path.exists():
                with open(path, "rb") as f:
                    self._bot.send_photo(self._chat_id, f, caption=caption or f"📸 {name}")
            return str(path)
        except Exception as e:
            logger.warning(f"[Screenshot] Failed: {e}")
            return None
    
    def _get_options(self, headless=True, mobile=True, extra_args=None):
        from selenium.webdriver.chrome.options import Options
        options = Options()
        
        if mobile:
            ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        else:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        
        options.add_argument(f"--user-agent={ua}")
        
        if headless:
            options.add_argument("--headless")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=390,844" if mobile else "--window-size=1280,720")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-US")
        
        # USER DATA DIR
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
        
        if extra_args:
            for arg in extra_args:
                options.add_argument(arg)
        
        if _installer.chrome_path:
            options.binary_location = _installer.chrome_path
            logger.debug(f"[Browser] binary: {_installer.chrome_path}")
        return options
    
    def create(self, headless=True, mobile=True, extra_args=None):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        options = self._get_options(headless=headless, mobile=mobile, extra_args=extra_args)
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        logger.info(f"[Browser] Creating driver... headless={headless}, mobile={mobile}")
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


# === ИССЛЕДОВАНИЕ X.COM ===
def research_x_com(bot, chat_id, steps=None):
    """
    Исследует x.com пошагово, собирая данные о структуре страниц.
    steps: список шагов для выполнения. Если None — выполняет все.
    """
    if steps is None:
        steps = ["basic", "desktop", "no_headless", "cookies", "login_page_analysis"]
    
    session = BrowserSession()
    session.set_chat(bot, chat_id)
    
    def report(text):
        logger.info(f"[Research] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    def save_research_data(name, data):
        """Сохраняет данные исследования в файл"""
        filepath = RESEARCH_DIR / f"research_{name}_{int(time.time())}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"[Research] Saved data: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[Research] Failed to save data: {e}")
            return None
    
    results = {}
    
    try:
        # === ШАГ 1: Базовый headless mobile ===
        if "basic" in steps:
            report("🔬 <b>Шаг 1/5:</b> Базовый headless mobile")
            try:
                session.create(headless=True, mobile=True)
                session.driver.get("https://x.com")
                time.sleep(5)
                
                data = {
                    "step": "basic_headless_mobile",
                    "url": session.driver.current_url,
                    "title": session.driver.title,
                    "source_length": len(session.driver.page_source),
                    "source_preview": session.driver.page_source[:2000],
                }
                filepath = save_research_data("basic", data)
                session._screenshot("step1_basic", "📸 Шаг 1: Базовый headless mobile", research=True)
                
                report(f"📊 <b>Результат шага 1:</b>\n"
                       f"URL: <code>{data['url']}</code>\n"
                       f"Title: <code>{data['title'] or '[пусто]'}</code>\n"
                       f"Source length: {data['source_length']}")
                
                if data['source_length'] < 100:
                    report("⚠️ Страница пустая — X блокирует headless!")
                results["basic"] = data
                
            except Exception as e:
                report(f"❌ Шаг 1 ошибка: {e}")
                results["basic"] = {"error": str(e)}
            finally:
                session.quit()
        
        # === ШАГ 2: Desktop headless ===
        if "desktop" in steps:
            report("🔬 <b>Шаг 2/5:</b> Desktop headless")
            try:
                session.create(headless=True, mobile=False)
                session.driver.get("https://x.com")
                time.sleep(5)
                
                data = {
                    "step": "desktop_headless",
                    "url": session.driver.current_url,
                    "title": session.driver.title,
                    "source_length": len(session.driver.page_source),
                    "source_preview": session.driver.page_source[:2000],
                }
                save_research_data("desktop", data)
                session._screenshot("step2_desktop", "📸 Шаг 2: Desktop headless", research=True)
                
                report(f"📊 URL: <code>{data['url']}</code>\n"
                       f"Title: <code>{data['title'] or '[пусто]'}</code>\n"
                       f"Source length: {data['source_length']}")
                results["desktop"] = data
                
            except Exception as e:
                report(f"❌ Шаг 2 ошибка: {e}")
                results["desktop"] = {"error": str(e)}
            finally:
                session.quit()
        
        # === ШАГ 3: С доп. аргументами анти-детекта ===
        if "no_headless" in steps:
            report("🔬 <b>Шаг 3/5:</b> Headless с расширенными аргументами")
            try:
                extra = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-site-isolation-trials",
                ]
                session.create(headless=True, mobile=True, extra_args=extra)
                session.driver.get("https://x.com")
                time.sleep(5)
                
                data = {
                    "step": "extra_args",
                    "url": session.driver.current_url,
                    "title": session.driver.title,
                    "source_length": len(session.driver.page_source),
                    "source_preview": session.driver.page_source[:2000],
                }
                save_research_data("extra_args", data)
                session._screenshot("step3_extra", "📸 Шаг 3: Extra args", research=True)
                
                report(f"📊 URL: <code>{data['url']}</code>\n"
                       f"Title: <code>{data['title'] or '[пусто]'}</code>\n"
                       f"Source length: {data['source_length']}")
                results["extra_args"] = data
                
            except Exception as e:
                report(f"❌ Шаг 3 ошибка: {e}")
                results["extra_args"] = {"error": str(e)}
            finally:
                session.quit()
        
        # === ШАГ 4: С cookies ===
        if "cookies" in steps:
            report("🔬 <b>Шаг 4/5:</b> С поддельными cookies")
            try:
                session.create(headless=True, mobile=True)
                
                # Устанавливаем базовые cookies
                session.driver.get("https://x.com")
                session.driver.add_cookie({
                    "name": "guest_id",
                    "value": "v1%3A" + str(int(time.time())),
                    "domain": ".x.com"
                })
                session.driver.add_cookie({
                    "name": "guest_id_marketing",
                    "value": "v1%3A" + str(int(time.time())),
                    "domain": ".x.com"
                })
                session.driver.add_cookie({
                    "name": "guest_id_ads",
                    "value": "v1%3A" + str(int(time.time())),
                    "domain": ".x.com"
                })
                
                time.sleep(3)
                session.driver.get("https://x.com/login")
                time.sleep(5)
                
                data = {
                    "step": "with_cookies",
                    "url": session.driver.current_url,
                    "title": session.driver.title,
                    "source_length": len(session.driver.page_source),
                    "cookies": session.driver.get_cookies(),
                    "source_preview": session.driver.page_source[:2000],
                }
                save_research_data("cookies", data)
                session._screenshot("step4_cookies", "📸 Шаг 4: С cookies", research=True)
                
                report(f"📊 URL: <code>{data['url']}</code>\n"
                       f"Title: <code>{data['title'] or '[пусто]'}</code>\n"
                       f"Source length: {data['source_length']}\n"
                       f"Cookies: {len(data['cookies'])}")
                results["cookies"] = data
                
            except Exception as e:
                report(f"❌ Шаг 4 ошибка: {e}")
                results["cookies"] = {"error": str(e)}
            finally:
                session.quit()
        
        # === ШАГ 5: Детальный анализ login страницы ===
        if "login_page_analysis" in steps:
            report("🔬 <b>Шаг 5/5:</b> Детальный анализ login страницы")
            try:
                session.create(headless=True, mobile=True)
                session.driver.get("https://x.com/i/flow/login")
                time.sleep(8)
                
                from selenium.webdriver.common.by import By
                
                # Собираем ВСЕ элементы
                all_buttons = []
                try:
                    buttons = session.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        try:
                            all_buttons.append({
                                "text": btn.text.strip()[:100],
                                "class": btn.get_attribute("class"),
                                "id": btn.get_attribute("id"),
                                "aria_label": btn.get_attribute("aria-label"),
                                "outer_html": btn.get_attribute("outerHTML")[:300],
                            })
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"Buttons collection error: {e}")
                
                all_links = []
                try:
                    links = session.driver.find_elements(By.TAG_NAME, "a")
                    for link in links[:20]:
                        try:
                            all_links.append({
                                "text": link.text.strip()[:100],
                                "href": link.get_attribute("href"),
                                "outer_html": link.get_attribute("outerHTML")[:300],
                            })
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"Links collection error: {e}")
                
                all_inputs = []
                try:
                    inputs = session.driver.find_elements(By.TAG_NAME, "input")
                    for inp in inputs:
                        try:
                            all_inputs.append({
                                "type": inp.get_attribute("type"),
                                "name": inp.get_attribute("name"),
                                "placeholder": inp.get_attribute("placeholder"),
                                "id": inp.get_attribute("id"),
                            })
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"Inputs collection error: {e}")
                
                data = {
                    "step": "login_analysis",
                    "url": session.driver.current_url,
                    "title": session.driver.title,
                    "source_length": len(session.driver.page_source),
                    "buttons_count": len(all_buttons),
                    "buttons": all_buttons,
                    "links_count": len(all_links),
                    "links": all_links,
                    "inputs_count": len(all_inputs),
                    "inputs": all_inputs,
                    "source_preview": session.driver.page_source[:3000],
                }
                save_research_data("login_analysis", data)
                session._screenshot("step5_login", "📸 Шаг 5: Анализ login", research=True)
                
                report(f"📊 <b>Анализ login страницы:</b>\n"
                       f"URL: <code>{data['url']}</code>\n"
                       f"Title: <code>{data['title'] or '[пусто]'}</code>\n"
                       f"Source length: {data['source_length']}\n"
                       f"Buttons: {data['buttons_count']}\n"
                       f"Links: {data['links_count']}\n"
                       f"Inputs: {data['inputs_count']}")
                
                # Показываем найденные кнопки
                if all_buttons:
                    btn_texts = [b['text'] for b in all_buttons if b['text']]
                    report(f"🎯 <b>Кнопки:</b>\n" + "\n".join([f"  • <code>{t[:60]}</code>" for t in btn_texts[:10]]))
                
                results["login_analysis"] = data
                
            except Exception as e:
                report(f"❌ Шаг 5 ошибка: {e}")
                results["login_analysis"] = {"error": str(e)}
            finally:
                session.quit()
        
        # Итог
        report("✅ <b>Исследование завершено!</b>\n"
               f"Результаты сохранены в: <code>{RESEARCH_DIR}</code>\n"
               f"Всего шагов: {len([r for r in results.values() if 'error' not in r])}/{len(steps)}")
        
        return results
        
    except Exception as e:
        report(f"❌ Критическая ошибка исследования: {e}")
        logger.error(traceback.format_exc())
        session.quit()
        return {"error": str(e)}


# === GOOGLE LOGIN (DESKTOP VERSION) ===
def google_login(email, password, bot=None, chat_id=None):
    login_log_file = BASE_DIR / f"login_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    login_logger = logging.getLogger(f"LoginAttempt_{id(email)}")
    login_logger.setLevel(logging.DEBUG)
    
    fh = logging.FileHandler(str(login_log_file), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    login_logger.addHandler(fh)
    
    login_logger.info(f"START google_login for email={email[:3]}***@{email.split('@')[-1] if '@' in email else '???'}")
    login_logger.info(f"BASE_DIR: {BASE_DIR}")
    login_logger.info(f"Chrome: {_installer.chrome_path}")
    login_logger.info(f"Driver: {_installer.driver_path}")
    
    try:
        import selenium
        login_logger.info(f"Selenium v{selenium.__version__}")
    except ImportError:
        login_logger.warning("Selenium not found, installing...")
        _installer._install_selenium_pip()
        try:
            import selenium
        except ImportError:
            login_logger.error("Selenium install failed")
            return False, "Selenium не удалось установить"
    
    session = BrowserSession()
    if bot and chat_id:
        session.set_chat(bot, chat_id)
    
    def report(text):
        login_logger.info(f"[CHAT] {text}")
        logger.info(f"[Login] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    def send_logs_on_error():
        try:
            if login_log_file.exists() and bot and chat_id:
                with open(login_log_file, "rb") as f:
                    bot.send_document(
                        chat_id, f,
                        caption="📄 Логи попытки входа",
                        visible_file_name=login_log_file.name
                    )
        except Exception as e:
            logger.error(f"Failed to send log file: {e}")
    
    try:
        report("⏳ Запускаю браузер (desktop)...")
        # === ИЗМЕНЕНИЕ: desktop режим ===
        session.create(headless=True, mobile=False)
        login_logger.info(f"Browser created (desktop). Session ID: {session.driver.session_id if session.driver else 'None'}")
        
        report("📥 Открываю x.com...")
        login_logger.info("Navigating to https://x.com")
        session.driver.get("https://x.com")
        time.sleep(3)
        
        report("🖱️ Ищу кнопку 'Sign in'...")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Ждём и кликаем "Sign in" на главной
        try:
            sign_in_btn = WebDriverWait(session.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@href='/i/flow/login'] | //span[contains(text(), 'Sign in')]/ancestor::a"))
            )
            sign_in_btn.click()
            login_logger.info("Clicked 'Sign in' on homepage")
            time.sleep(3)
        except Exception as e:
            login_logger.warning(f"Sign in button not found or click failed: {e}")
            # Пробуем сразу открыть login
            session.driver.get("https://x.com/login")
            time.sleep(3)
        
        current_url = session.driver.current_url
        page_title = session.driver.title
        login_logger.info(f"Login page loaded. URL: {current_url}")
        login_logger.info(f"Page title: {page_title}")
        login_logger.debug(f"Page source length: {len(session.driver.page_source)}")
        session._screenshot("login_page", "📸 Страница входа X (desktop)")
        
        report("🔍 Ищу кнопку Google...")
        
        # === ИЗМЕНЕНИЕ: WebDriverWait для кнопки Google ===
        google_btn = None
        wait = WebDriverWait(session.driver, 15)
        
        # Пробуем разные селекторы для desktop кнопки Google
        selectors = [
            # По тексту "Continue with Google"
            (By.XPATH, "//span[contains(text(), 'Continue with Google')]"),
            # По роли button с текстом Google
            (By.XPATH, "//button//*[contains(text(), 'Continue with Google')]"),
            # По data-testid (если есть)
            (By.XPATH, "//div[@data-testid='google_sign_in_container']//button"),
            # По aria-label
            (By.XPATH, "//button[contains(@aria-label, 'Google')]"),
            # Общий поиск по Google
            (By.XPATH, "//*[contains(text(), 'Continue with Google') or contains(text(), 'Sign in with Google')]"),
        ]
        
        for by, selector in selectors:
            try:
                google_btn = wait.until(EC.element_to_be_clickable((by, selector)))
                login_logger.info(f"Found Google button with: {by}={selector[:50]}...")
                report(f"✅ Найдена кнопка Google")
                break
            except Exception as e:
                login_logger.debug(f"Selector failed: {selector[:50]}... — {e}")
        
        if not google_btn:
            # Последняя попытка — найти любую кнопку с логотипом Google
            try:
                google_btn = session.driver.find_element(By.XPATH, "//img[contains(@src, 'google') or contains(@alt, 'Google')]/ancestor::button")
                login_logger.info("Found Google button via logo image")
            except:
                pass
        
        if not google_btn:
            login_logger.error("Google button NOT found on page!")
            login_logger.info(f"Current URL: {session.driver.current_url}")
            login_logger.info(f"Page title: {session.driver.title}")
            login_logger.debug(f"Page source (first 3000 chars):\n{session.driver.page_source[:3000]}")
            report("❌ Кнопка Google НЕ найдена!")
            send_logs_on_error()
            return False, "Кнопка Google не найдена"
        
        report("🖱️ Кликаю по Google...")
        login_logger.info("Clicking Google button")
        google_btn.click()
        time.sleep(5)
        
        session._screenshot("google_redirect", "📸 После клика Google")
        
        current_url = session.driver.current_url
        page_title = session.driver.title
        report(f"📍 URL: {current_url[:80]}")
        login_logger.info(f"After click URL: {current_url}")
        login_logger.info(f"After click title: {page_title}")
        
        # === Работа с Google OAuth ===
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ Перешли на Google!")
            login_logger.info("On Google auth page")
            
            # Email
            try:
                login_logger.info("Looking for email field...")
                email_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="email"]')))
                login_logger.info(f"Email field found")
                email_field.send_keys(email)
                report("✅ Email введён")
                login_logger.info("Email entered")
                
                # Кнопка Next после email
                next_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next') or @id='identifierNext']")))
                next_btn.click()
                login_logger.info("Next clicked after email")
                time.sleep(3)
            except Exception as e:
                report(f"⚠️ Email step error: {e}")
                login_logger.error(f"Email step failed: {e}")
                login_logger.error(traceback.format_exc())
                session._screenshot("email_error", "📸 Ошибка email")
                send_logs_on_error()
                return False, f"Ошибка ввода email: {e}"
            
            # Password
            try:
                login_logger.info("Looking for password field...")
                pass_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="password"]')))
                login_logger.info(f"Password field found")
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                login_logger.info("Password entered")
                
                next_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next') or @id='passwordNext']")))
                next_btn.click()
                login_logger.info("Next clicked after password")
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password step error: {e}")
                login_logger.error(f"Password step failed: {e}")
                login_logger.error(traceback.format_exc())
                session._screenshot("password_error", "📸 Ошибка пароля")
                send_logs_on_error()
                return False, f"Ошибка ввода пароля: {e}"
            
            # Проверка 2FA / капчи
            time.sleep(3)
            current_url = session.driver.current_url
            login_logger.info(f"After password URL: {current_url}")
            
            if "challenge" in current_url:
                login_logger.warning(f"Google CHALLENGE detected! URL: {current_url}")
                report("⚠️ Google требует капчу/доп. проверку!")
                send_logs_on_error()
                return False, "Google требует дополнительную проверку (капча/2FA)"
            
            if "disabled" in current_url:
                login_logger.error(f"Google ACCOUNT DISABLED! URL: {current_url}")
                report("❌ Аккаунт Google заблокирован или отключен")
                send_logs_on_error()
                return False, "Аккаунт Google заблокирован"
        else:
            login_logger.warning(f"Did NOT redirect to Google. URL: {current_url}")
            login_logger.debug(f"Page source: {session.driver.page_source[:2000]}")
        
        # Ждём редирект обратно на X
        report("⏳ Жду редирект на X...")
        x_reached = False
        for i in range(15):  # Увеличил до 30 сек
            time.sleep(2)
            url = session.driver.current_url
            login_logger.info(f"Wait loop {i+1}/15: {url}")
            if "x.com" in url and "login" not in url and "google" not in url:
                report("✅ Вошли в X!")
                login_logger.info("X reached!")
                x_reached = True
                break
        
        if not x_reached:
            login_logger.warning("X not reached after 30 seconds")
            login_logger.info(f"Final URL: {session.driver.current_url}")
            login_logger.info(f"Final title: {session.driver.title}")
        
        # Проверка авторизации
        session.driver.get("https://x.com/home")
        time.sleep(5)
        current_url = session.driver.current_url
        page_title = session.driver.title
        login_logger.info(f"x.com/home URL: {current_url}")
        login_logger.info(f"x.com/home title: {page_title}")
        session._screenshot("x_home", "📸 X Home")
        
        html = session.driver.page_source.lower()
        login_logger.info(f"x.com/home source length: {len(html)}")
        
        auth_indicators = ["home", "following", "for you", "compose", "logout", "settings", "notifications"]
        found_indicators = [ind for ind in auth_indicators if ind in html]
        login_logger.info(f"Auth indicators found: {found_indicators}")
        
        if "/home" in current_url or "/i/flow" in current_url:
            login_logger.info("Auth confirmed by URL pattern")
            found_indicators.append("url_pattern")
        
        if found_indicators:
            report(f"✅ Авторизация подтверждена! Индикаторы: {found_indicators}")
            login_logger.info("AUTH SUCCESS")
            session.save_cookies()
            save_auth_info("google_user", email)
            return True, None
        else:
            report("❌ Не удалось войти в X")
            login_logger.error("AUTH FAILED — no indicators found")
            login_logger.debug(f"Page source (first 3000 chars):\n{html[:3000]}")
            send_logs_on_error()
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Ошибка: {str(e)[:200]}")
        login_logger.error(f"CRITICAL ERROR: {e}")
        login_logger.error(traceback.format_exc())
        send_logs_on_error()
        return False, str(e)
    finally:
        login_logger.info("END — quitting session")
        session.quit()
        login_logger.removeHandler(fh)
        fh.close()


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
            "/se_research — Исследовать x.com\n"
            "/se_research_stop — Остановить исследование\n"
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
    
    @bot.message_handler(commands=["se_logs"])
    def se_logs(message):
        logger.info(f"[Bot] /se_logs requested by user {message.from_user.id}")
        
        recent = _chat_handler.get_logs(last_n=30)
        preview = f"<b>📝 Последние логи:</b>\n<pre>{recent[:3500]}</pre>"
        bot.reply_to(message, preview, parse_mode="HTML")
        
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
        _chat_handler.clear()
        bot.reply_to(message, "🧹 Логи в памяти очищены", parse_mode="HTML")
        logger.info("[Bot] Logs cleared by user")
    
    # === НОВЫЕ КОМАНДЫ ИССЛЕДОВАНИЯ ===
    @bot.message_handler(commands=["se_research"])
    def se_research(message):
        chat_id = message.chat.id
        
        if chat_id in _research_sessions:
            bot.reply_to(message, "⚠️ Исследование уже запущено. Используй /se_research_stop чтобы остановить.", parse_mode="HTML")
            return
        
        if not _installer.ready:
            bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
            return
        
        bot.reply_to(message, "🔬 <b>Запускаю исследование x.com...</b>\n<i>Это займёт ~60 сек</i>", parse_mode="HTML")
        
        def do_research():
            _research_sessions[chat_id] = {"active": True}
            try:
                research_x_com(bot, chat_id)
            finally:
                if chat_id in _research_sessions:
                    del _research_sessions[chat_id]
        
        t = threading.Thread(target=do_research)
        t.start()
    
    @bot.message_handler(commands=["se_research_stop"])
    def se_research_stop(message):
        chat_id = message.chat.id
        if chat_id in _research_sessions:
            del _research_sessions[chat_id]
            bot.reply_to(message, "🛑 Исследование остановлено", parse_mode="HTML")
        else:
            bot.reply_to(message, "ℹ️ Исследование не запущено", parse_mode="HTML")
    
    logger.info("[Bot] Команды зарегистрированы")


logger.info(f"[Module] Загружен. ready={_installer.ready}")
