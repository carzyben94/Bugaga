# selenium_x_agent.py — Защищённый от ошибок
import os
import sys
import time
import json
import logging
import zipfile
import urllib.request
import subprocess
import tempfile
from pathlib import Path

# === ДИАГНОСТИКА ===
print("[SE] Начало модуля", flush=True)

try:
    APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
    BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = BASE_DIR / "agent.log"
    print(f"[SE] BASE_DIR: {BASE_DIR}", flush=True)
except Exception as e:
    print(f"[SE] ОШИБКА путей: {e}", flush=True)
    # Fallback на /tmp
    BASE_DIR = Path("/tmp/x_browser")
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = BASE_DIR / "agent.log"

# Логгер с защитой
try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger("SeleniumXAgent")
    print("[SE] Логгер OK", flush=True)
except Exception as e:
    print(f"[SE] Логгер ОШИБКА: {e}", flush=True)
    # Фейковый логгер
    class FakeLogger:
        def info(self, msg): print(f"[INFO] {msg}", flush=True)
        def error(self, msg): print(f"[ERROR] {msg}", flush=True)
        def warning(self, msg): print(f"[WARN] {msg}", flush=True)
    logger = FakeLogger()

CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"
CHROME_ZIP = f"{BASE_URL}/chrome-linux64.zip"
DRIVER_ZIP = f"{BASE_URL}/chromedriver-linux64.zip"

print("[SE] Константы OK", flush=True)


class ChromeInstaller:
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
        print(f"[SE] Installer: chrome={self.chrome_path}, driver={self.driver_path}, ready={self.ready}", flush=True)
    
    def _find_existing(self):
        try:
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
        except Exception as e:
            print(f"[SE] _find_existing ОШИБКА: {e}", flush=True)
    
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
        success = True
        if not self.chrome_path:
            success = self._download_chrome() and success
        if not self.driver_path:
            success = self._download_driver() and success
        return success
    
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


# Создание с защитой
print("[SE] Создаю _installer...", flush=True)
try:
    _installer = ChromeInstaller()
    print(f"[SE] _installer OK: ready={_installer.ready}", flush=True)
except Exception as e:
    print(f"[SE] _installer ОШИБКА: {e}", flush=True)
    # Фейковый installer
    class FakeInstaller:
        @property
        def ready(self): return False
        def status(self): return {"chrome": {"found": False, "path": None}, "driver": {"found": False, "path": None}, "ready": False, "base_dir": str(BASE_DIR)}
        def install(self): return False
    _installer = FakeInstaller()
    print("[SE] Использую FakeInstaller", flush=True)


def get_full_status():
    return {
        "selenium_pip": {"installed": False, "version": None},
        "chrome_browser": {"found": _installer.status()["chrome"]["found"], "path": _installer.chrome_path},
        "chromedriver": {"ready": _installer.status()["driver"]["found"], "path": _installer.driver_path},
        "agent_ready": _installer.ready,
        "cookies_exist": False,
        "auth_info": None,
        "selenium_dir": str(BASE_DIR),
    }


def get_auth_info():
    return None


def AGENT_READY():
    return _installer.ready


def icon(flag):
    return "✅" if flag else "❌"


def register_selenium_bot(bot):
    print("[SE] Регистрация команд...", flush=True)
    
    @bot.message_handler(commands=["se_status"])
    def se_status(message):
        st = _installer.status()
        text = (
            "🚗 <b>Selenium X Agent</b>\n\n"
            f"{icon(st['chrome']['found'])} Chrome: <code>{st['chrome']['path'] or 'не найден'}</code>\n"
            f"{icon(st['driver']['found'])} Driver: <code>{st['driver']['path'] or 'не найден'}</code>\n\n"
            f"{'🟢' if st['ready'] else '🔴'} Готов: {'Да' if st['ready'] else 'Нет'}\n"
            f"📁 {st['base_dir']}"
        )
        if not st['ready']:
            text += "\n\n⚠️ /se_install"
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
        bot.reply_to(message, "🔐 Вход через Google — скоро!", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logout"])
    def se_logout(message):
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
    
    print("[SE] Команды зарегистрированы", flush=True)
    logger.info("Selenium команды зарегистрированы")


print(f"[SE] Модуль загружен. ready={_installer.ready}", flush=True)
