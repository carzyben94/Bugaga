# selenium_x_agent_minimal.py
"""
Минималистичный Selenium X Agent
Только базовые функции: установка и статус
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
import zipfile
import urllib.request
from pathlib import Path
from datetime import datetime

print("[SE] Запуск Minimal Edition", flush=True)

# === КОНФИГУРАЦИЯ ===
APP_DIR = Path("/app") if os.path.exists("/app") else Path(tempfile.gettempdir())
BASE_DIR = APP_DIR / "x_browser"
BASE_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = BASE_DIR / "agent.log"

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("XAgent")

# === ВЕРСИИ ===
CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"

# === КЛАСС УСТАНОВЩИКА ===
class ChromeInstaller:
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
    
    def _find_existing(self):
        """Поиск уже установленного Chrome"""
        # Локальные пути
        local_chrome = BASE_DIR / "chrome" / "chrome-linux64" / "chrome"
        local_driver = BASE_DIR / "driver" / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"✅ Chrome найден: {self.chrome_path}")
        
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"✅ Driver найден: {self.driver_path}")
        
        # Системные пути
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chrome"]:
                try:
                    result = subprocess.run(["which", name], capture_output=True, text=True)
                    if result.returncode == 0:
                        self.chrome_path = result.stdout.strip()
                        logger.info(f"✅ Chrome системный: {self.chrome_path}")
                        break
                except:
                    pass
        
        if not self.driver_path:
            try:
                result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True)
                if result.returncode == 0:
                    self.driver_path = result.stdout.strip()
                    logger.info(f"✅ Driver системный: {self.driver_path}")
            except:
                pass
    
    @property
    def ready(self):
        return bool(self.chrome_path and self.driver_path)
    
    def status(self):
        return {
            "chrome": {
                "found": bool(self.chrome_path),
                "path": self.chrome_path or "не найден"
            },
            "driver": {
                "found": bool(self.driver_path),
                "path": self.driver_path or "не найден"
            },
            "ready": self.ready
        }
    
    def install(self):
        """Установка Chrome + Driver"""
        logger.info("📦 Начинаю установку...")
        
        # Проверяем Selenium
        try:
            import selenium
            logger.info(f"✅ Selenium уже установлен")
        except ImportError:
            logger.info("📦 Устанавливаю selenium...")
            subprocess.run([sys.executable, "-m", "pip", "install", "selenium"], check=True)
        
        # Устанавливаем Chrome
        if not self.chrome_path:
            if not self._download_chrome():
                return False
        
        # Устанавливаем Driver
        if not self.driver_path:
            if not self._download_driver():
                return False
        
        logger.info("✅ Установка завершена!")
        return self.ready
    
    def _download_chrome(self):
        """Скачивание Chrome"""
        logger.info("📥 Скачиваю Chrome...")
        chrome_dir = BASE_DIR / "chrome"
        chrome_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "chrome.zip"
        url = f"{BASE_URL}/chrome-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("📦 Распаковываю Chrome...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(chrome_dir)
            
            zip_path.unlink()
            
            chrome_bin = chrome_dir / "chrome-linux64" / "chrome"
            if chrome_bin.exists():
                os.chmod(chrome_bin, 0o755)
                self.chrome_path = str(chrome_bin)
                logger.info(f"✅ Chrome установлен: {self.chrome_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def _download_driver(self):
        """Скачивание Chromedriver"""
        logger.info("📥 Скачиваю Chromedriver...")
        driver_dir = BASE_DIR / "driver"
        driver_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "driver.zip"
        url = f"{BASE_URL}/chromedriver-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("📦 Распаковываю Driver...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(driver_dir)
            
            zip_path.unlink()
            
            driver_bin = driver_dir / "chromedriver-linux64" / "chromedriver"
            if driver_bin.exists():
                os.chmod(driver_bin, 0o755)
                self.driver_path = str(driver_bin)
                logger.info(f"✅ Driver установлен: {self.driver_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

# === ГЛОБАЛЬНЫЙ ИНСТАНС ===
installer = ChromeInstaller()

# === ТЕЛЕГРАМ КОМАНДЫ ===
def register_commands(bot):
    """Регистрация команд для Telegram бота"""
    
    @bot.message_handler(commands=["se_status"])
    def status(message):
        """Показать статус"""
        st = installer.status()
        
        # Определяем иконки
        chrome_icon = "✅" if st['chrome']['found'] else "❌"
        driver_icon = "✅" if st['driver']['found'] else "❌"
        ready_icon = "🟢" if st['ready'] else "🔴"
        
        text = f"""🚗 <b>Selenium X Agent</b>

{chrome_icon} Chrome: <code>{st['chrome']['path']}</code>
{driver_icon} Driver: <code>{st['driver']['path']}</code>
{ready_icon} Готов: {"Да" if st['ready'] else "Нет"}

📁 {BASE_DIR}

/se_install — Установить Chrome + Driver
/se_status — Показать статус
"""
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def install(message):
        """Установка Chrome + Driver"""
        if installer.ready:
            bot.reply_to(message, "✅ Уже установлено!", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Установка Chrome + Driver...\nЭто займет 1-2 минуты", parse_mode="HTML")
        
        try:
            success = installer.install()
            
            if success:
                bot.edit_message_text(
                    f"✅ <b>Установка завершена!</b>\n\n"
                    f"🌐 Chrome: <code>{installer.chrome_path}</code>\n"
                    f"🔧 Driver: <code>{installer.driver_path}</code>\n\n"
                    f"Теперь можно использовать /se_status",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    "❌ <b>Ошибка установки</b>\n"
                    f"Проверь логи: <code>{LOG_FILE}</code>",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Критическая ошибка: {e}",
                chat_id=msg.chat.id,
                message_id=msg.message_id
            )
    
    @bot.message_handler(commands=["se_help"])
    def help(message):
        """Помощь"""
        text = """🚗 <b>Selenium X Agent - Помощь</b>

/se_status — Статус агента
/se_install — Установить Chrome + Driver
/se_help — Эта справка

<b>Статус:</b>
🟢 Готов к работе
🔴 Требуется установка
"""
        bot.reply_to(message, text, parse_mode="HTML")
    
    logger.info("✅ Команды зарегистрированы")

# === ИНИЦИАЛИЗАЦИЯ ===
logger.info(f"🚗 Selenium X Agent Minimal v1.0")
logger.info(f"📁 Директория: {BASE_DIR}")
logger.info(f"🔧 Статус: {'✅ Готов' if installer.ready else '❌ Не готов'}")

# Экспортируем для бота
__all__ = ['register_commands', 'installer', 'BASE_DIR']

print(f"""
╔═══════════════════════════════════════╗
║  🚗 Selenium X Agent Minimal v1.0    ║
╠═══════════════════════════════════════╣
║  Статус: {'✅ Готов' if installer.ready else '❌ Не готов'}             ║
║  Директория: {BASE_DIR} ║
║                                       ║
║  Команды:                             ║
║  /se_status — Статус                 ║
║  /se_install — Установка             ║
║  /se_help — Помощь                   ║
╚═══════════════════════════════════════╝
""")