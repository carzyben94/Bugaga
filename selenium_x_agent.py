# playwright_x_agent.py - Исправленная версия
"""
Playwright X Agent - Современная альтернатива Selenium
"""

import os
import sys
import json
import logging
import time
import subprocess
import tempfile
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

print("[PW] Запуск Playwright X Agent...", flush=True)

# === КОНФИГУРАЦИЯ ===
APP_DIR = Path("/app") if os.path.exists("/app") else Path(tempfile.gettempdir())
BASE_DIR = Path(os.environ.get("X_BROWSER_DIR", APP_DIR / "x_browser"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = BASE_DIR / "agent.log"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PlaywrightXAgent")

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
_installed = False
_browser_sessions = {}
_playwright_version = None

# === КЛАСС УСТАНОВЩИКА ===
class PlaywrightInstaller:
    """Установка Playwright и браузеров"""
    
    def __init__(self):
        self._check_installed()
        logger.info(f"[Installer] Статус: {'✅ Готов' if self.ready else '❌ Не готов'}")
    
    def _check_installed(self):
        """Проверка наличия Playwright и браузеров"""
        global _installed, _playwright_version
        
        # Проверяем Playwright
        try:
            import playwright
            _installed = True
            # Получаем версию через pip
            try:
                import pkg_resources
                _playwright_version = pkg_resources.get_distribution("playwright").version
            except:
                _playwright_version = "установлен"
            logger.info("[Installer] ✅ Playwright установлен")
        except ImportError:
            _installed = False
            logger.info("[Installer] ❌ Playwright не найден")
            return
        
        # Проверяем браузер
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
                logger.info("[Installer] ✅ Chromium установлен")
        except Exception as e:
            logger.info(f"[Installer] ❌ Chromium не найден: {e}")
            _installed = False
    
    @property
    def ready(self):
        return _installed
    
    def install(self) -> bool:
        """Установка Playwright + браузер"""
        global _installed, _playwright_version
        logger.info("[Installer] 📦 Начинаю установку Playwright...")
        
        try:
            # 1. Устанавливаем Playwright
            logger.info("[Installer] 📦 Устанавливаю playwright...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
                capture_output=True,
                timeout=120
            )
            logger.info("[Installer] ✅ Playwright установлен")
            
            # Получаем версию
            try:
                import pkg_resources
                _playwright_version = pkg_resources.get_distribution("playwright").version
            except:
                _playwright_version = "установлен"
            
            # 2. Устанавливаем браузеры
            logger.info("[Installer] 🌐 Устанавливаю Chromium...")
            subprocess.run(
                ["playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                timeout=300
            )
            logger.info("[Installer] ✅ Chromium установлен")
            
            # 3. Устанавливаем системные зависимости (для Linux)
            logger.info("[Installer] 🐧 Устанавливаю системные зависимости...")
            try:
                subprocess.run(
                    ["playwright", "install-deps"],
                    check=True,
                    capture_output=True,
                    timeout=120
                )
                logger.info("[Installer] ✅ Зависимости установлены")
            except:
                logger.warning("[Installer] ⚠️ Не удалось установить зависимости (возможно уже есть)")
            
            _installed = True
            logger.info("[Installer] ✅ Установка завершена!")
            return True
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"[Installer] ❌ Ошибка команды: {error_msg}")
            return False
        except Exception as e:
            logger.error(f"[Installer] ❌ Критическая ошибка: {e}")
            return False
    
    def status(self) -> Dict:
        return {
            "installed": self.ready,
            "base_dir": str(BASE_DIR),
            "version": _playwright_version
        }

# === ГЛОБАЛЬНЫЙ ИНСТАНС ===
_installer = PlaywrightInstaller()

# === КЛАСС БРАУЗЕРА ===
class BrowserSession:
    """Управление сессией браузера через Playwright"""
    
    def __init__(self, headless: bool = True, mobile: bool = False):
        self.browser = None
        self.context = None
        self.page = None
        self.headless = headless
        self.mobile = mobile
        self._is_active = False
        self._playwright = None
    
    @property
    def is_active(self) -> bool:
        return self._is_active and self.page is not None
    
    def create(self):
        """Создание браузера"""
        if not _installed:
            raise Exception("Playwright не установлен. Используй /se_install")
        
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Exception("Playwright не найден. Используй /se_install")
        
        try:
            self._playwright = sync_playwright().start()
            
            viewport = {"width": 390, "height": 844} if self.mobile else {"width": 1280, "height": 720}
            
            if self.mobile:
                user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            else:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            
            self.browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            user_data_dir = BASE_DIR / "playwright_user_data"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            self.context = self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                user_data_dir=str(user_data_dir),
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            # Маскировка автоматизации
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
            
            self.page = self.context.new_page()
            self._is_active = True
            
            logger.info("[Browser] ✅ Браузер создан (Playwright)")
            return self.page
            
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка создания: {e}")
            self.quit()
            raise
    
    def quit(self):
        """Закрытие браузера"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self._playwright:
                self._playwright.stop()
            self._is_active = False
            logger.info("[Browser] Браузер закрыт")
        except Exception as e:
            logger.warning(f"[Browser] Ошибка при закрытии: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self._playwright = None
    
    def screenshot(self, name: str = "screenshot") -> Optional[str]:
        """Создание скриншота"""
        if not self.is_active:
            logger.warning("[Browser] Браузер не активен")
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            self.page.screenshot(path=str(filepath), full_page=True)
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
            self.page.goto(url, wait_until="domcontentloaded")
            logger.info(f"[Browser] Открыт URL: {url}")
            return True
        except Exception as e:
            logger.error(f"[Browser] ❌ Ошибка открытия URL: {e}")
            return False
    
    def get_title(self) -> str:
        if not self.is_active:
            return ""
        try:
            return self.page.title()
        except:
            return ""

# === ФУНКЦИИ СТАТУСА ===
def get_status() -> Dict:
    """Получение полного статуса"""
    st = _installer.status()
    
    st["playwright"] = {
        "installed": _installed,
        "version": _playwright_version
    }
    
    cookies_file = BASE_DIR / "cookies.json"
    st["cookies"] = cookies_file.exists()
    st["active_sessions"] = len([s for s in _browser_sessions.values() if s.is_active])
    
    # Для совместимости с bot.py
    st["agent_ready"] = _installed
    st["auth_info"] = get_auth_info()
    st["selenium_dir"] = str(BASE_DIR)
    st["chrome_browser"] = {"found": _installed, "path": "Playwright Chromium"}
    st["chromedriver"] = {"ready": _installed, "path": "Playwright"}
    st["selenium_pip"] = {"installed": _installed, "version": _playwright_version}
    st["cookies_exist"] = cookies_file.exists()
    
    return st

def get_full_status() -> Dict:
    return get_status()

def AGENT_READY() -> bool:
    return _installed

# === ФУНКЦИИ ДЛЯ АВТОРИЗАЦИИ ===
def get_auth_info() -> Optional[Dict]:
    auth_file = BASE_DIR / "x_auth.json"
    if not auth_file.exists():
        return None
    try:
        with open(auth_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[Auth] Ошибка чтения: {e}")
        return None

def save_auth_info(username: str, email: str = None, extra: Dict = None) -> bool:
    try:
        data = {
            "username": str(username),
            "email": email,
            "authorized_at": datetime.now().isoformat(),
        }
        if extra:
            data.update(extra)
        
        auth_file = BASE_DIR / "x_auth.json"
        with open(auth_file, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"[Auth] ✅ Сохранена авторизация для {username}")
        return True
    except Exception as e:
        logger.error(f"[Auth] ❌ Ошибка сохранения: {e}")
        return False

def clear_auth_info() -> bool:
    try:
        auth_file = BASE_DIR / "x_auth.json"
        cookies_file = BASE_DIR / "x_cookies.json"
        
        if auth_file.exists():
            auth_file.unlink()
        if cookies_file.exists():
            cookies_file.unlink()
        
        logger.info("[Auth] ✅ Авторизация очищена")
        return True
    except Exception as e:
        logger.error(f"[Auth] ❌ Ошибка очистки: {e}")
        return False

# === ВХОД ЧЕРЕЗ GOOGLE ===
def google_login(email: str, password: str, bot=None, chat_id=None) -> tuple:
    """Вход через Google OAuth с Playwright"""
    login_logger = logging.getLogger(f"Login_{email[:3]}")
    
    session = BrowserSession(headless=True, mobile=False)
    
    def report(text):
        login_logger.info(f"[Chat] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except:
                pass
    
    try:
        report("⏳ Запускаю браузер (Playwright)...")
        page = session.create()
        
        report("📥 Открываю x.com...")
        page.goto("https://x.com", wait_until="domcontentloaded")
        time.sleep(3)
        
        # Ищем кнопку входа
        report("🔍 Ищу кнопку входа...")
        try:
            sign_in = page.locator('a[href="/i/flow/login"]').first
            if sign_in.count() == 0:
                sign_in = page.locator('span:has-text("Sign in")').first
                if sign_in.count() > 0:
                    sign_in = sign_in.locator('xpath=ancestor::a').first
            if sign_in.count() > 0:
                sign_in.click()
            else:
                report("⚠️ Кнопка не найдена, перехожу на /login")
                page.goto("https://x.com/login", wait_until="domcontentloaded")
            time.sleep(3)
        except Exception as e:
            report(f"⚠️ Ошибка поиска кнопки: {e}")
            page.goto("https://x.com/login", wait_until="domcontentloaded")
            time.sleep(3)
        
        # Ищем кнопку Google
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        
        selectors = [
            'button:has-text("Continue with Google")',
            'span:has-text("Continue with Google")',
            'button:has-text("Sign in with Google")',
            'div[data-testid="google_sign_in_container"] button',
            'button[aria-label*="Google"]'
        ]
        
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if element.count() > 0:
                    google_btn = element
                    break
            except:
                pass
        
        if not google_btn:
            # JavaScript поиск
            result = page.evaluate("""
                () => {
                    const spans = document.querySelectorAll('span');
                    for (let s of spans) {
                        if (s.textContent.toLowerCase().includes('continue with google')) {
                            let el = s.closest('button');
                            if (el) return true;
                        }
                    }
                    return false;
                }
            """)
            
            if result:
                google_btn = page.locator('button:has-text("Continue with Google")').first
        
        if not google_btn:
            report("❌ Кнопка Google не найдена")
            session.quit()
            return False, "Кнопка Google не найдена"
        
        # Клик по кнопке Google
        report("🖱️ Кликаю по Google...")
        try:
            google_btn.click()
        except:
            try:
                page.evaluate("""
                    document.querySelector('button:has-text("Continue with Google")')?.click();
                """)
            except:
                report("❌ Не удалось кликнуть")
                session.quit()
                return False, "Не удалось кликнуть по кнопке Google"
        
        time.sleep(5)
        
        # Ожидаем перехода на Google
        try:
            page.wait_for_url(lambda url: "accounts.google.com" in url, timeout=15000)
        except:
            pass
        
        current_url = page.url
        report(f"📍 URL: {current_url[:80]}")
        
        if "accounts.google.com" not in current_url:
            report("⚠️ Не удалось перейти на Google")
            session.quit()
            return False, "Не удалось перейти на Google"
        
        report("✅ Перешли на Google!")
        
        # Ввод email
        try:
            email_field = page.locator('input[type="email"]').first
            email_field.wait_for(timeout=15000)
            email_field.fill(email)
            report("✅ Email введён")
            
            page.locator('span:has-text("Next")').first.click()
            time.sleep(3)
        except Exception as e:
            report(f"❌ Ошибка ввода email: {e}")
            session.quit()
            return False, f"Ошибка ввода email: {e}"
        
        # Ввод пароля
        try:
            pass_field = page.locator('input[type="password"]').first
            pass_field.wait_for(timeout=15000)
            pass_field.fill(password)
            report("✅ Пароль введён")
            
            page.locator('span:has-text("Next")').first.click()
            time.sleep(5)
        except Exception as e:
            report(f"❌ Ошибка ввода пароля: {e}")
            session.quit()
            return False, f"Ошибка ввода пароля: {e}"
        
        # Проверка 2FA
        current_url = page.url
        if "challenge" in current_url:
            report("⚠️ Google требует капчу/2FA")
            session.quit()
            return False, "Google требует дополнительную проверку (капча/2FA)"
        
        # Ждем возврат на X
        report("⏳ Жду редирект на X...")
        try:
            page.wait_for_url(lambda url: "x.com" in url and "login" not in url, timeout=30000)
        except:
            pass
        
        # Проверка авторизации
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        time.sleep(3)
        
        html = page.content().lower()
        auth_indicators = ["home", "following", "for you", "notifications"]
        found = [ind for ind in auth_indicators if ind in html]
        
        if found:
            report(f"✅ Авторизация подтверждена! Индикаторы: {found}")
            cookies = page.context.cookies()
            cookies_file = BASE_DIR / "x_cookies.json"
            with open(cookies_file, "w") as f:
                json.dump(cookies, f)
            save_auth_info("google_user", email)
            session.quit()
            return True, None
        else:
            report("❌ Не удалось подтвердить авторизацию")
            session.quit()
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
        session.quit()
        return False, str(e)

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

# === РЕГИСТРАЦИЯ КОМАНД ===
def register_selenium_bot(bot):
    """Регистрация команд для Telegram бота"""
    logger.info("[Bot] Регистрация команд Playwright...")
    
    @bot.message_handler(commands=["se_status"])
    def cmd_status(message):
        st = get_status()
        
        ready_icon = "🟢" if st['agent_ready'] else "🔴"
        version = st.get('playwright', {}).get('version', 'неизвестно')
        
        text = f"""
🚗 <b>Playwright X Agent</b>
{'─' * 30}

✅ Playwright: {version}
{ready_icon} Готов: {"Да" if st['agent_ready'] else "Нет"}

👤 Авторизация: {'✅' if st['auth_info'] else '❌'}
🍪 Cookies: {'есть' if st['cookies'] else 'нет'}

📁 {st['selenium_dir']}
"""
        bot.reply_to(message, text, parse_mode="HTML")
    
    @bot.message_handler(commands=["se_install"])
    def cmd_install(message):
        if _installed:
            bot.reply_to(message, "✅ Уже установлено!", parse_mode="HTML")
            return
        
        msg = bot.reply_to(message, "⏳ Установка Playwright + Chromium...\nЭто займет 2-3 минуты", parse_mode="HTML")
        
        try:
            success = _installer.install()
            
            if success:
                bot.edit_message_text(
                    f"✅ <b>Установка завершена!</b>\n\n"
                    f"📦 Playwright установлен\n"
                    f"🌐 Chromium установлен\n\n"
                    f"Теперь используй /se_google для входа",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    "❌ <b>Ошибка установки</b>\n"
                    f"Проверь логи: /se_logs",
                    chat_id=msg.chat.id,
                    message_id=msg.message_id,
                    parse_mode="HTML"
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Ошибка: {e}",
                chat_id=msg.chat.id,
                message_id=msg.message_id
            )
    
    @bot.message_handler(commands=["se_google"])
    def cmd_google(message):
        if not _installed:
            bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
            return
        
        chat_id = message.chat.id
        # Используем глобальный словарь из bot.py
        if not hasattr(bot, 'login_sessions'):
            bot.login_sessions = {}
        bot.login_sessions[chat_id] = {"step": "email"}
        bot.reply_to(message, "🔐 Введи <b>email</b> от Google:", parse_mode="HTML")
    
    @bot.message_handler(commands=["se_browser"])
    def cmd_browser(message):
        if not _installed:
            bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
            return
        
        chat_id = message.chat.id
        
        if chat_id in _browser_sessions:
            try:
                _browser_sessions[chat_id].quit()
            except:
                pass
            del _browser_sessions[chat_id]
        
        msg = bot.reply_to(message, "⏳ Запускаю браузер (Playwright)...", parse_mode="HTML")
        
        try:
            session = create_browser(headless=True, mobile=False, chat_id=chat_id)
            session.open_url("https://x.com")
            
            screenshot_path = session.screenshot("browser_start")
            
            response = "✅ Браузер запущен!\n"
            response += f"📄 Title: {session.get_title()}\n"
            
            if screenshot_path:
                with open(screenshot_path, "rb") as f:
                    bot.send_photo(chat_id, f, caption=response)
                bot.delete_message(chat_id, msg.message_id)
            else:
                bot.edit_message_text(response, chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка: {e}", chat_id=chat_id, message_id=msg.message_id)
    
    @bot.message_handler(commands=["se_screenshot"])
    def cmd_screenshot(message):
        chat_id = message.chat.id
        
        if chat_id not in _browser_sessions:
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
        text = """
🚗 <b>Playwright X Agent - Команды</b>
{'━' * 30}

<b>⚙️ Управление</b>
/se_status — Статус агента
/se_install — Установка Playwright + Chromium
/se_logs — Логи

<b>🔐 Авторизация</b>
/se_google — Вход через Google
/se_logout — Выйти

<b>🌐 Браузер</b>
/se_browser — Запустить браузер
/se_screenshot — Скриншот
/se_close — Закрыть браузер

<b>ℹ️ Инфо</b>
/se_help — Эта справка
"""
        bot.reply_to(message, text, parse_mode="HTML")

# === ЭКСПОРТ ===
__all__ = [
    'register_selenium_bot',
    'get_status',
    'get_full_status',
    'get_auth_info',
    'save_auth_info',
    'clear_auth_info',
    'AGENT_READY',
    'create_browser',
    'BrowserSession',
    'google_login',
    '_installer',
    'BASE_DIR'
]

# === ИНИЦИАЛИЗАЦИЯ ===
logger.info("=" * 50)
logger.info("🚗 Playwright X Agent v1.0")
logger.info(f"📁 Директория: {BASE_DIR}")
logger.info(f"🔧 Статус: {'✅ Готов' if _installed else '❌ Не готов'}")
logger.info("=" * 50)

print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🚗 Playwright X Agent v1.0                                ║
╠══════════════════════════════════════════════════════════════╣
║  Статус: {'✅ Готов' if _installed else '❌ Не готов'}                         ║
║  Движок: Playwright (современнее Selenium)                  ║
║  Версия: {_playwright_version or 'неизвестно'}                              ║
║                                                              ║
║  Команды:                                                    ║
║  /se_status — Статус                                        ║
║  /se_install — Установка Playwright + Chromium              ║
║  /se_google — Вход через Google                             ║
║  /se_browser — Запустить браузер                            ║
║  /se_screenshot — Скриншот                                  ║
║  /se_close — Закрыть браузер                                ║
║  /se_logs — Логи                                            ║
║  /se_help — Помощь                                          ║
╚══════════════════════════════════════════════════════════════╝
""")