# selenium_x_agent.py — Чистая установка Chrome + команды для бота
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
from pathlib import Path
from datetime import datetime

# === КОНФИГ ===
APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

CHROME_DIR = BASE_DIR / "chrome"
DRIVER_DIR = BASE_DIR / "driver"
LOG_FILE = BASE_DIR / "agent.log"

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


class ChromeInstaller:
    """Установщик Chrome + ChromeDriver"""
    
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
    """Для совместимости со старым кодом"""
    return {
        "selenium_pip": {"installed": False, "version": None},  # Пока не проверяем pip
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


def icon(flag: bool) -> str:
    return "✅" if flag else "❌"


def register_selenium_bot(bot):
    """Регистрация команд в основном боте"""
    logger.info("Регистрация Selenium команд...")
    
    @bot.message_handler(commands=["se_status"])
    def se_status(message):
        st = _installer.status()
        text = (
            "🚗 <b>Selenium X Agent — Статус</b>\n\n"
            f"{icon(st['chrome']['found'])} <b>Chrome:</b> <code>{st['chrome']['path'] or 'не найден'}</code>\n"
            f"{icon(st['driver']['found'])} <b>Driver:</b> <code>{st['driver']['path'] or 'не найден'}</code>\n\n"
            f"{'🟢' if st['ready'] else '🔴'} <b>Agent готов:</b> {'Да' if st['ready'] else 'Нет'}\n"
            f"📁 <b>Директория:</b> <code>{st['base_dir']}</code>"
        )
        if not st['ready']:
            text += "\n\n⚠️ Нажми /se_install"
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def se_install(message):
        if _installer.ready:
            bot.reply_to(message, "🟢 Уже установлено!\n/se_status", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Скачиваю Chrome + Driver...\n<i>1-2 минуты</i>", parse_mode="HTML")
        
        try:
            success = _installer.install()
        except Exception as e:
            logger.error(f"Install error: {e}")
            bot.edit_message_text(
                f"❌ <b>Ошибка:</b> <code>{str(e)[:200]}</code>",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
            return
        
        if success:
            bot.edit_message_text(
                f"✅ <b>Установка завершена!</b>\n\n"
                f"🌐 Chrome: <code>{_installer.chrome_path}</code>\n"
                f"🔧 Driver: <code>{_installer.driver_path}</code>\n\n"
                f"/se_status — проверить",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
        else:
            bot.edit_message_text(
                "❌ <b>Установка не завершена</b>\n\n"
                f"Проверь логи: <code>{LOG_FILE}</code>\n"
                "/se_install — повторить",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
    
    @bot.message_handler(commands=["se_help"])
    def se_help(message):
        bot.reply_to(message, (
            "🚗 <b>Selenium X Agent</b>\n\n"
            "/se_status — Статус системы\n"
            "/se_install — Установить Chrome + Driver\n"
            "/se_help — Эта помощь\n\n"
            "<i>Браузер ставится автоматически в чате</i>"
        ), parse_mode="HTML")
    
    logger.info("Selenium команды зарегистрированы")


logger.info(f"Selenium module loaded. Chrome ready: {_installer.ready}")
