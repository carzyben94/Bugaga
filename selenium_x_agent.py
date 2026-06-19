# selenium_x_agent.py
"""
Selenium X Agent - Полная версия
Поддержка: установка Chrome, статус, браузер, скриншоты
"""

import os
import sys
import json
import logging
import time
import subprocess
import tempfile
import zipfile
import urllib.request
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

print("[SE] Запуск Selenium X Agent...", flush=True)

# === КОНФИГУРАЦИЯ ===
APP_DIR = Path("/app") if os.path.exists("/app") else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = BASE_DIR / "agent.log"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SeleniumXAgent")

# === ВЕРСИИ CHROME ===
CHROME_VERSION = "126.0.6478.126"
BASE_URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux64"

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
_installer = None
_browser_sessions = {}

# === КЛАСС УСТАНОВЩИКА ===
class ChromeInstaller:
    """Установка и управление Chrome + Chromedriver"""
    
    def __init__(self):
        self.chrome_path = None
        self.driver_path = None
        self._find_existing()
        logger.info(f"[Installer] Статус: {'✅ Готов' if self.ready else '❌ Не готов'}")
    
    def _find_existing(self):
        """Поиск уже установленного Chrome"""
        # Локальные пути
        local_chrome = BASE_DIR / "chrome" / "chrome-linux64" / "chrome"
        local_driver = BASE_DIR / "driver" / "chromedriver-linux64" / "chromedriver"
        
        if local_chrome.exists():
            self.chrome_path = str(local_chrome)
            logger.info(f"[Installer] ✅ Локальный Chrome: {self.chrome_path}")
        
        if local_driver.exists():
            self.driver_path = str(local_driver)
            logger.info(f"[Installer] ✅ Локальный Driver: {self.driver_path}")
        
        # Системные пути
        if not self.chrome_path:
            for name in ["google-chrome", "chromium", "chromium-browser", "chrome"]:
                try:
                    result = subprocess.run(["which", name], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        self.chrome_path = result.stdout.strip()
                        logger.info(f"[Installer] ✅ Системный Chrome: {self.chrome_path}")
                        break
                except:
                    pass
        
        if not self.driver_path:
            try:
                result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.driver_path = result.stdout.strip()
                    logger.info(f"[Installer] ✅ Системный Driver: {self.driver_path}")
            except:
                pass
    
    @property
    def ready(self):
        return bool(self.chrome_path and self.driver_path)
    
    def status(self) -> Dict:
        return {
            "chrome": {
                "found": bool(self.chrome_path),
                "path": self.chrome_path or "не найден"
            },
            "driver": {
                "found": bool(self.driver_path),
                "path": self.driver_path or "не найден"
            },
            "ready": self.ready,
            "base_dir": str(BASE_DIR)
        }
    
    def install(self) -> bool:
        """Установка Chrome + Driver"""
        logger.info("[Installer] 📦 Начинаю установку...")
        
        # Проверяем Selenium
        try:
            import selenium
            logger.info(f"[Installer] ✅ Selenium уже установлен")
        except ImportError:
            logger.info("[Installer] 📦 Устанавливаю selenium...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "selenium"],
                    check=True,
                    capture_output=True,
                    timeout=120
                )
                logger.info("[Installer] ✅ Selenium установлен")
            except Exception as e:
                logger.error(f"[Installer] ❌ Ошибка установки Selenium: {e}")
                return False
        
        # Устанавливаем Chrome
        if not self.chrome_path:
            if not self._download_chrome():
                return False
        
        # Устанавливаем Driver
        if not self.driver_path:
            if not self._download_driver():
                return False
        
        logger.info("[Installer] ✅ Установка завершена!")
        return self.ready
    
    def _download_chrome(self) -> bool:
        """Скачивание Chrome"""
        logger.info("[Installer] 📥 Скачиваю Chrome...")
        chrome_dir = BASE_DIR / "chrome"
        chrome_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "chrome.zip"
        url = f"{BASE_URL}/chrome-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("[Installer] 📦 Распаковываю Chrome...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(chrome_dir)
            
            zip_path.unlink()
            
            chrome_bin = chrome_dir / "chrome-linux64" / "chrome"
            if chrome_bin.exists():
                os.chmod(chrome_bin, 0o755)
                self.chrome_path = str(chrome_bin)
                logger.info(f"[Installer] ✅ Chrome установлен: {self.chrome_path}")
                return True
            else:
                logger.error("[Installer] ❌ Chrome не найден после распаковки")
                return False
                
        except Exception as e:
            logger.error(f"[Installer] ❌ Ошибка загрузки Chrome: {e}")
            return False
    
    def _download_driver(self) -> bool:
        """Скачивание Chromedriver"""
        logger.info("[Installer] 📥 Скачиваю Chromedriver...")
        driver_dir = BASE_DIR / "driver"
        driver_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = BASE_DIR / "driver.zip"
        url = f"{BASE_URL}/chromedriver-linux64.zip"
        
        try:
            urllib.request.urlretrieve(url, zip_path)
            logger.info("[Installer] 📦 Распаковываю Driver...")
            
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(driver_dir)
            
            zip_path.unlink()
            
            driver_bin = driver_dir / "chromedriver-linux64" / "chromedriver"
            if driver_bin.exists():
                os.chmod(driver_bin, 0o755)
                self.driver_path = str(driver_bin)
                logger.info(f"[Installer] ✅ Driver установлен: {self.driver_path}")
                return True
            else:
                logger.error("[Installer] ❌ Driver не найден после распаковки")
                return False
                
        except Exception as e:
            logger.error(f"[Installer] ❌ Ошибка загрузки Driver: {e}")
            return False

# === КЛАСС БРАУЗЕРА ===
class BrowserSession:
    """Управление сессией браузера"""
    
    def __init__(self, headless: bool = True, mobile: bool = False):
        self.driver = None
        self.headless = headless
        self.mobile = mobile
        self._is_active = False
    
    @property
    def is_active(self) -> bool:
        return self._is_active and self.driver is not None
    
    def create(self):
        """Создание браузера"""
        if not _installer.ready:
            raise Exception("Chrome не установлен. Используй /se_install")
        
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        options = Options()
        
        # User-Agent
        if self.mobile:
            ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            window_size = "--window-size=390,844"
        else:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            window_size = "--window-size=1280,720"
        
        options.add_argument(f"--user-agent={ua}")
        options.add_argument(window_size)
        
        # Headless
        if self.headless:
            options.add_argument("--headless")
        
        # Анти-детект
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Путь к Chrome
        if _installer.chrome_path:
            options.binary_location = _installer.chrome_path
        
        # User data dir
        user_data_dir = BASE_DIR / "chrome_user_data"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")
        
        # Создаем драйвер
        service = Service(_installer.driver_path) if _installer.driver_path else Service()
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Маскировка webdriver
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
        self._is_active = True
        logger.info("[Browser] ✅ Браузер создан")
        return self.driver
    
    def quit(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("[Browser] Браузер закрыт")
            except Exception as e:
                logger.warning(f"[Browser] Ошибка при закрытии: {e}")
            finally:
                self.driver = None
                self._is_active = False
    
    def screenshot(self, name: str = "screenshot") -> Optional[str]:
        """Создание скриншота"""
        if not self.is_active:
            logger.warning("[Browser] Браузер не активен")
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            self.driver.save_screenshot(str(filepath))
            logger.info(f"[Browser] 📸 Скриншот: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка скриншота: {e}")
            return None
    
    def open_url(self, url: str) -> bool:
        """Открытие URL"""
        if not self.is_active:
            logger.warning("[Browser] Браузер не активен")
            return False
        
        try:
            self.driver.get(url)
            time.sleep(2)
            logger.info(f"[Browser] Открыт URL: {url}")
            return True
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка открытия URL: {e}")
            return False
    
    def get_page_source(self) -> str:
        """Получение HTML страницы"""
        if not self.is_active:
            return ""
        try:
            return self.driver.page_source
        except:
            return ""
    
    def get_title(self) -> str:
        """Получение заголовка страницы"""
        if not self.is_active:
            return ""
        try:
            return self.driver.title
        except:
            return ""

# === ГЛОБАЛЬНЫЙ ИНСТАНС ===
_installer = ChromeInstaller()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def get_status() -> Dict:
    """Получение полного статуса"""
    st = _installer.status()
    
    # Проверка Selenium
    try:
        import selenium
        selenium_installed = True
        selenium_version = selenium.__version__
    except ImportError:
        selenium_installed = False
        selenium_version = None
    
    st["selenium"] = {
        "installed": selenium_installed,
        "version": selenium_version
    }
    
    # Проверка cookies
    cookies_file = BASE_DIR / "cookies.json"
    st["cookies"] = cookies_file.exists()
    
    # Активные сессии
    st["active_sessions"] = len([s for s in _browser_sessions.values() if s.is_active])
    
    return st

def create_browser(headless: bool = True, mobile: bool = False, chat_id: int = None) -> BrowserSession:
    """Создание новой сессии браузера"""
    session = BrowserSession(headless=headless, mobile=mobile)
    try:
        session.create()
        if chat_id:
            _browser_sessions[chat_id] = session
        return session
    except Exception as e:
        logger.error(f"[Browser] ❌ Ошибка создания: {e}")
        raise

# === РЕГИСТРАЦИЯ КОМАНД ДЛЯ БОТА ===
def register_selenium_bot(bot):
    """Регистрация команд для Telegram бота"""
    logger.info("[Bot] Регистрация команд Selenium...")
    
    @bot.message_handler(commands=["se_status"])
    def cmd_status(message):
        """Статус агента"""
        st = get_status()
        
        chrome_icon = "✅" if st['chrome']['found'] else "❌"
        driver_icon = "✅" if st['driver']['found'] else "❌"
        ready_icon = "🟢" if st['ready'] else "🔴"
        selenium_icon = "✅" if st['selenium']['installed'] else "❌"
        
        text = f"""🚗 <b>Selenium X Agent</b>

{chrome_icon} Chrome: <code>{st['chrome']['path']}</code>
{driver_icon} Driver: <code>{st['driver']['path']}</code>
{selenium_icon} Selenium: {'v' + st['selenium']['version'] if st['selenium']['installed'] else 'не установлен'}
{ready_icon} Готов: {"Да" if st['ready'] else "Нет"}

🍪 Cookies: {"есть" if st['cookies'] else "нет"}
🌐 Активных сессий: {st['active_sessions']}

📁 {st['base_dir']}

/se_install — Установить Chrome + Driver
/se_browser — Запустить браузер
/se_screenshot — Сделать скриншот
/se_help — Помощь"""
        
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def cmd_install(message):
        """Установка Chrome + Driver"""
        if _installer.ready:
            bot.reply_to(message, "✅ Уже установлено!", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Установка Chrome + Driver...\nЭто займет 1-2 минуты", parse_mode="HTML")
        
        try:
            success = _installer.install()
            
            if success:
                bot.edit_message_text(
                    f"✅ <b>Установка завершена!</b>\n\n"
                    f"🌐 Chrome: <code>{_installer.chrome_path}</code>\n"
                    f"🔧 Driver: <code>{_installer.driver_path}</code>\n\n"
                    f"Теперь можно использовать /se_browser",
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
    
    @bot.message_handler(commands=["se_browser"])
    def cmd_browser(message):
        """Запуск браузера"""
        chat_id = message.chat.id
        
        if not _installer.ready:
            bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
            return
        
        # Закрываем старую сессию если есть
        if chat_id in _browser_sessions:
            try:
                _browser_sessions[chat_id].quit()
            except:
                pass
            del _browser_sessions[chat_id]
        
        msg = bot.reply_to(message, "⏳ Запускаю браузер...", parse_mode="HTML")
        
        try:
            session = create_browser(headless=True, mobile=False, chat_id=chat_id)
            session.open_url("https://x.com")
            
            # Скриншот
            screenshot_path = session.screenshot("browser_start")
            
            response = "✅ Браузер запущен!\n"
            response += f"📄 Title: {session.get_title()}\n"
            response += f"🔗 URL: {session.driver.current_url[:60]}..."
            
            if screenshot_path:
                with open(screenshot_path, "rb") as f:
                    bot.send_photo(chat_id, f, caption=response)
                bot.delete_message(chat_id, msg.message_id)
            else:
                bot.edit_message_text(response, chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
                
        except Exception as e:
            bot.edit_message_text(
                f"❌ Ошибка запуска браузера: {e}",
                chat_id=chat_id,
                message_id=msg.message_id
            )
    
    @bot.message_handler(commands=["se_screenshot"])
    def cmd_screenshot(message):
        """Сделать скриншот"""
        chat_id = message.chat.id
        
        if chat_id not in _browser_sessions or not _browser_sessions[chat_id].is_active:
            bot.reply_to(message, "❌ Браузер не запущен. Используй /se_browser", parse_mode="HTML")
            return
        
        try:
            session = _browser_sessions[chat_id]
            screenshot_path = session.screenshot("manual")
            
            if screenshot_path:
                with open(screenshot_path, "rb") as f:
                    bot.send_photo(
                        chat_id, f,
                        caption=f"📸 Скриншот\n🌐 {session.get_title()}"
                    )
            else:
                bot.reply_to(message, "❌ Не удалось сделать скриншот", parse_mode="HTML")
                
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_close"])
    def cmd_close(message):
        """Закрыть браузер"""
        chat_id = message.chat.id
        
        if chat_id in _browser_sessions:
            try:
                _browser_sessions[chat_id].quit()
                del _browser_sessions[chat_id]
                bot.reply_to(message, "✅ Браузер закрыт", parse_mode="HTML")
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")
        else:
            bot.reply_to(message, "ℹ️ Браузер не запущен", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_logs"])
    def cmd_logs(message):
        """Показать логи"""
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "rb") as f:
                    bot.send_document(
                        message.chat.id,
                        f,
                        caption="📄 Логи агента",
                        visible_file_name="agent.log"
                    )
            else:
                bot.reply_to(message, "❌ Лог-файл не найден", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_help"])
    def cmd_help(message):
        """Помощь"""
        text = """🚗 <b>Selenium X Agent - Команды</b>

<b>⚙️ Управление</b>
/se_status — Статус агента
/se_install — Установка Chrome + Driver
/se_logs — Показать логи

<b>🌐 Браузер</b>
/se_browser — Запустить браузер
/se_screenshot — Сделать скриншот
/se_close — Закрыть браузер

<b>ℹ️ Инфо</b>
/se_help — Эта справка

<b>Статус:</b>
🟢 Готов к работе
🔴 Требуется установка"""
        
        bot.reply_to(message, text, parse_mode="HTML")

# === ИНИЦИАЛИЗАЦИЯ ===
logger.info("=" * 50)
logger.info("🚗 Selenium X Agent v2.0")
logger.info(f"📁 Директория: {BASE_DIR}")
logger.info(f"🔧 Статус: {'✅ Готов' if _installer.ready else '❌ Не готов'}")
logger.info("=" * 50)

print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🚗 Selenium X Agent v2.0                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Статус: {'✅ Готов' if _installer.ready else '❌ Не готов'}                         ║
║  Директория: {BASE_DIR} ║
║                                                              ║
║  Команды:                                                    ║
║  /se_status — Статус                                        ║
║  /se_install — Установка                                    ║
║  /se_browser — Запустить браузер                            ║
║  /se_screenshot — Скриншот                                  ║
║  /se_close — Закрыть браузер                                ║
║  /se_logs — Логи                                            ║
║  /se_help — Помощь                                          ║
╚══════════════════════════════════════════════════════════════╝
""")

# Экспорт
__all__ = [
    'register_selenium_bot',
    'get_status',
    'create_browser',
    'BrowserSession',
    '_installer',
    'BASE_DIR'
]