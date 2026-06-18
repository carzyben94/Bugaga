# x_browser_bot.py — Чистая установка Chrome через Telegram
import os
import sys
import json
import time
import tempfile
import logging
import zipfile
import urllib.request
import subprocess
from pathlib import Path
from datetime import datetime

# === КОНФИГ ===
APP_DIR = Path("/app") if os.path.exists("/app") and os.access("/app", os.W_OK) else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

CHROME_DIR = BASE_DIR / "chrome"
DRIVER_DIR = BASE_DIR / "driver"
LOG_FILE = BASE_DIR / "bot.log"

# Логгер
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("XBrowser")

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
        """Ищем уже установленное"""
        # Локальное
        local_chrome = CHROME_DIR / "chrome-linux64" / "chrome"
        local_driver = DRIVER_DIR / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"Chrome найден: {self.chrome_path}")
        
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"Driver найден: {self.driver_path}")
        
        # Системное
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                if path := self._which(name):
                    self.chrome_path = path
                    break
        
        if not self.driver_path:
            self.driver_path = self._which("chromedriver")
    
    @staticmethod
    def _which(cmd: str) -> str | None:
        """which аналог"""
        try:
            result = subprocess.run(
                ["which", cmd], 
                capture_output=True, 
                text=True, 
                timeout=5,
                check=True
            )
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
        """Полная установка"""
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
        """Скачать файл"""
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
        """Распаковать zip"""
        try:
            logger.info(f"Распаковка: {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(dest_dir)
            zip_path.unlink()  # Удаляем архив
            logger.info("Распаковка завершена")
            return True
        except Exception as e:
            logger.error(f"Ошибка распаковки: {e}")
            return False
    
    def _make_executable(self, path: Path):
        """+x"""
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
            logger.info(f"Права на выполнение: {path}")
        except Exception as e:
            logger.error(f"Ошибка chmod: {e}")
    
    def _download_chrome(self) -> bool:
        """Скачать и распаковать Chrome"""
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
        """Скачать и распаковать Driver"""
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


# === TELEGRAM БОТ ===
try:
    import telebot
except ImportError:
    logger.error("Установи: pip install pyTelegramBotAPI")
    raise

# Токен из env
TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
bot = telebot.TeleBot(TOKEN)

# Глобальный установщик
installer = ChromeInstaller()


def icon(flag: bool) -> str:
    return "✅" if flag else "❌"


@bot.message_handler(commands=["start", "help"])
def cmd_help(message):
    bot.reply_to(message, (
        "🤖 <b>X Browser Bot</b>\n\n"
        "<b>Установка:</b>\n"
        "  /status — Проверить Chrome\n"
        "  /install — Установить Chrome + Driver\n\n"
        "<b>Браузер:</b>\n"
        "  /explore [url] — Открыть страницу\n"
    ), parse_mode="HTML")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    st = installer.status()
    
    text = (
        "📊 <b>Статус системы</b>\n\n"
        f"{icon(st['chrome']['found'])} <b>Chrome:</b> <code>{st['chrome']['path'] or 'не найден'}</code>\n"
        f"{icon(st['driver']['found'])} <b>Driver:</b> <code>{st['driver']['path'] or 'не найден'}</code>\n\n"
        f"{'🟢' if st['ready'] else '🔴'} <b>Готов:</b> {'Да' if st['ready'] else 'Нет'}\n"
        f"📁 <b>Директория:</b> <code>{st['base_dir']}</code>"
    )
    
    if not st['ready']:
        text += "\n\n⚠️ Нажми /install"
    
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(commands=["install"])
def cmd_install(message):
    if installer.ready:
        bot.reply_to(message, "🟢 Уже установлено!\n/status", parse_mode="HTML")
        return
    
    msg = bot.reply_to(message, "⏳ Скачиваю Chrome + Driver...\n<i>1-2 минуты</i>", parse_mode="HTML")
    
    success = installer.install()
    
    if success:
        bot.edit_message_text(
            f"✅ <b>Установка завершена!</b>\n\n"
            f"🌐 Chrome: <code>{installer.chrome_path}</code>\n"
            f"🔧 Driver: <code>{installer.driver_path}</code>\n\n"
            f"/explore https://x.com/login",
            chat_id=msg.chat.id,
            message_id=msg.message_id,
            parse_mode="HTML"
        )
    else:
        bot.edit_message_text(
            "❌ <b>Ошибка установки</b>\n\n"
            "Проверь логи:\n"
            f"<code>{LOG_FILE}</code>",
            chat_id=msg.chat.id,
            message_id=msg.message_id,
            parse_mode="HTML"
        )


@bot.message_handler(commands=["explore"])
def cmd_explore(message):
    if not installer.ready:
        bot.reply_to(message, "❌ Сначала /install", parse_mode="HTML")
        return
    
    args = message.text.split()
    url = args[1] if len(args) > 1 else "https://x.com/login"
    
    bot.reply_to(message, f"🔍 Открываю: {url}\n<i>10 сек...</i>", parse_mode="HTML")
    
    # Здесь будет Selenium — пока заглушка
    # TODO: подключить webdriver с опциями из installer
    bot.reply_to(message, f"✅ Браузер готов!\nChrome: {installer.chrome_path}")


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("X Browser Bot запущен")
    logger.info(f"BASE_DIR: {BASE_DIR}")
    logger.info(f"Chrome ready: {installer.ready}")
    logger.info("=" * 50)
    
    bot.polling(none_stop=True)
