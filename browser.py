"""
Модуль браузера с анти-детектом для автоматизации
Поддерживает: Twitter/X, Instagram, Facebook и другие
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import os
import time
import json
import random
import subprocess
import shutil
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === КОНСТАНТЫ ===
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

class AntiDetectBrowser:
    """Браузер с анти-детектом для обхода блокировок"""
    
    def __init__(self, headless=False, user_data_dir=None, proxy=None):
        """
        Инициализация браузера
        
        Args:
            headless: Запуск в фоновом режиме
            user_data_dir: Папка для сохранения сессии
            proxy: Прокси сервер (например: "http://proxy:8080")
        """
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self.driver = None
        self.wait = None
        self.is_ready = False
        
    def setup_driver(self):
        """Настройка драйвера с анти-детект параметрами"""
        options = Options()
        
        # === БАЗОВЫЕ НАСТРОЙКИ ===
        if self.headless:
            options.add_argument('--headless=new')
        
        # === ПРОКСИ ===
        if self.proxy:
            options.add_argument(f'--proxy-server={self.proxy}')
        
        # === ПОЛЬЗОВАТЕЛЬСКАЯ ПАПКА ДЛЯ СЕССИИ ===
        if self.user_data_dir:
            options.add_argument(f'--user-data-dir={self.user_data_dir}')
        
        # === АНТИ-ДЕТЕКТ ПАРАМЕТРЫ ===
        # Отключаем автоматизацию
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Скрываем WebDriver
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        
        # Отключаем уведомления
        options.add_argument('--disable-notifications')
        
        # Оптимизация производительности
        options.add_argument('--disable-accelerated-2d-canvas')
        options.add_argument('--disable-accelerated-javascript-decoding')
        options.add_argument('--disable-accelerated-mjpeg-decode')
        options.add_argument('--disable-accelerated-video-decode')
        
        # Случайный User-Agent
        user_agent = random.choice(USER_AGENTS)
        options.add_argument(f'--user-agent={user_agent}')
        
        # Язык и время
        options.add_argument('--lang=en-US,en;q=0.9')
        options.add_experimental_option('prefs', {
            'intl.accept_languages': 'en-US,en;q=0.9',
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'profile.default_content_setting_values.notifications': 2,
        })
        
        # === УСТАНОВКА ДРАЙВЕРА ===
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.error(f"❌ Ошибка установки драйвера: {e}")
            # Пробуем использовать системный Chrome
            try:
                options.binary_location = shutil.which('google-chrome') or shutil.which('google-chrome-stable')
                self.driver = webdriver.Chrome(options=options)
            except Exception as e2:
                logger.error(f"❌ Ошибка запуска Chrome: {e2}")
                raise
        
        # === ПОДМЕНА NAVIGATOR.WEBDRIVER ===
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ru-RU', 'ru']
            });
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            Object.defineProperty(navigator, 'userAgent', {
                get: () => arguments[0]
            });
        """, random.choice(USER_AGENTS))
        
        # === ДОПОЛНИТЕЛЬНЫЕ СКРИПТЫ ===
        self.driver.execute_script("""
            // Подмена chrome
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Подмена WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
        """)
        
        self.wait = WebDriverWait(self.driver, 10)
        self.is_ready = True
        logger.info("✅ Браузер готов")
        return self.driver
    
    def random_delay(self, min_sec=0.3, max_sec=1.5):
        """Случайная задержка для имитации человека"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_click(self, element):
        """Человеческий клик с движением мыши"""
        try:
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            self.random_delay(0.1, 0.3)
            actions.click()
            actions.perform()
            self.random_delay(0.3, 0.7)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            return False
    
    def human_type(self, element, text, delay=True):
        """Человеческий ввод текста"""
        try:
            element.click()
            self.random_delay(0.2, 0.5)
            element.clear()
            
            if delay:
                # Вводим посимвольно с задержкой
                for char in text:
                    element.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.12))
            else:
                element.send_keys(text)
            
            self.random_delay(0.3, 0.6)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка ввода: {e}")
            return False
    
    def scroll_to_element(self, element):
        """Прокрутка до элемента"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            self.random_delay(0.5, 1.0)
            return True
        except:
            return False
    
    def find_element(self, by, selector, timeout=10):
        """Поиск элемента с ожиданием"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def find_clickable(self, by, selector, timeout=10):
        """Поиск кликабельного элемента"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def click_safe(self, by, selector, timeout=10):
        """Безопасный клик"""
        try:
            element = self.find_clickable(by, selector, timeout)
            if element:
                self.scroll_to_element(element)
                return self.human_click(element)
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка клика: {e}")
            return False
    
    def wait_for_url(self, url_contains, timeout=15):
        """Ожидание изменения URL"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.url_contains(url_contains)
            )
            return True
        except TimeoutException:
            return False
    
    def get_current_url(self):
        """Получить текущий URL"""
        return self.driver.current_url
    
    # === СПЕЦИАЛЬНЫЕ МЕТОДЫ ДЛЯ РАЗНЫХ САЙТОВ ===
    
    def login_twitter(self, username, password):
        """Вход в Twitter/X"""
        logger.info("🚀 Открываем Twitter...")
        self.driver.get("https://x.com/login")
        self.random_delay(2, 4)
        
        try:
            # Кнопка "Войти"
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Sign in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='loginButton']"):
                logger.info("✅ Нажата кнопка входа")
            
            self.random_delay(1, 2)
            
            # Поле логина
            username_field = self.find_element(By.NAME, "text")
            if username_field:
                self.human_type(username_field, username)
                logger.info(f"✅ Введен логин: {username}")
            else:
                logger.error("❌ Поле логина не найдено")
                return False
            
            self.random_delay(1, 2)
            
            # Кнопка "Далее"
            if self.click_safe(By.XPATH, "//span[text()='Далее']") or \
               self.click_safe(By.XPATH, "//span[text()='Next']"):
                logger.info("✅ Нажата кнопка 'Далее'")
            
            self.random_delay(2, 3)
            
            # Поле пароля
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                logger.info("✅ Введен пароль")
            else:
                logger.error("❌ Поле пароля не найдено")
                return False
            
            self.random_delay(1, 2)
            
            # Кнопка "Войти"
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Log in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='LoginForm_Login_Button']"):
                logger.info("✅ Нажата кнопка 'Войти'")
            
            self.random_delay(3, 5)
            
            # Проверка
            if "home" in self.driver.current_url.lower():
                logger.info("🎉 Вход выполнен успешно!")
                return True
            else:
                logger.warning(f"⚠️ Неизвестный URL: {self.driver.current_url}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def login_instagram(self, username, password):
        """Вход в Instagram"""
        logger.info("🚀 Открываем Instagram...")
        self.driver.get("https://www.instagram.com/accounts/login/")
        self.random_delay(2, 4)
        
        try:
            # Поле логина
            username_field = self.find_element(By.NAME, "username")
            if username_field:
                self.human_type(username_field, username)
                logger.info(f"✅ Введен логин: {username}")
            
            # Поле пароля
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                logger.info("✅ Введен пароль")
            
            self.random_delay(1, 2)
            
            # Кнопка входа
            if self.click_safe(By.XPATH, "//button[@type='submit']"):
                logger.info("✅ Нажата кнопка входа")
            
            self.random_delay(3, 5)
            
            # Проверка
            if "instagram.com" in self.driver.current_url and "login" not in self.driver.current_url:
                logger.info("🎉 Вход выполнен успешно!")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    # === РАБОТА С КУКАМИ ===
    
    def get_cookies(self):
        """Получить все cookies"""
        return self.driver.get_cookies()
    
    def save_cookies(self, filename="cookies.json"):
        """Сохранить cookies в файл"""
        cookies = self.get_cookies()
        with open(filename, 'w') as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"✅ Cookies сохранены в {filename}")
        return cookies
    
    def load_cookies(self, filename="cookies.json"):
        """Загрузить cookies из файла"""
        try:
            with open(filename, 'r') as f:
                cookies = json.load(f)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            
            logger.info(f"✅ Cookies загружены из {filename}")
            return True
        except:
            logger.error(f"❌ Ошибка загрузки cookies")
            return False
    
    # === СКРИНШОТЫ ===
    
    def take_screenshot(self, filename="screenshot.png"):
        """Сделать скриншот"""
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"✅ Скриншот сохранен: {filename}")
            return filename
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    def take_full_page_screenshot(self, filename="fullpage.png"):
        """Скриншот всей страницы"""
        try:
            # Получаем размер страницы
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            self.driver.set_window_size(1920, total_height)
            self.driver.save_screenshot(filename)
            logger.info(f"✅ Полный скриншот сохранен: {filename}")
            return filename
        except Exception as e:
            logger.error(f"❌ Ошибка полного скриншота: {e}")
            return None
    
    # === УПРАВЛЕНИЕ ===
    
    def refresh(self):
        """Обновить страницу"""
        self.driver.refresh()
        self.random_delay(1, 2)
    
    def go_back(self):
        """Назад"""
        self.driver.back()
        self.random_delay(1, 2)
    
    def close_tab(self):
        """Закрыть текущую вкладку"""
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
    
    def new_tab(self, url=None):
        """Открыть новую вкладку"""
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        if url:
            self.driver.get(url)
        self.random_delay(1, 2)
    
    # === ЗАКРЫТИЕ ===
    
    def close(self):
        """Закрыть браузер"""
        if self.driver:
            try:
                self.driver.quit()
                self.is_ready = False
                logger.info("✅ Браузер закрыт")
            except:
                pass

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def check_chrome_installed():
    """Проверка установки Chrome"""
    paths = [
        shutil.which('google-chrome'),
        shutil.which('google-chrome-stable'),
        shutil.which('chrome'),
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'
    ]
    
    for path in paths:
        if path and os.path.exists(path):
            try:
                version = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT)
                return path, version.decode().strip()
            except:
                pass
    
    return None, None

def install_chrome():
    """Установка Chrome (только Linux)"""
    try:
        if sys.platform.startswith('linux'):
            subprocess.check_call(['apt-get', 'update'])
            subprocess.check_call(['apt-get', 'install', '-y', 'google-chrome-stable'])
            return True
        elif sys.platform.startswith('win'):
            subprocess.check_call([
                'powershell', '-Command',
                'Invoke-WebRequest -Uri "https://dl.google.com/chrome/install/latest/chrome_installer.exe" -OutFile "chrome_installer.exe"'
            ])
            subprocess.check_call(['chrome_installer.exe', '/silent', '/install'])
            return True
        elif sys.platform.startswith('darwin'):
            subprocess.check_call(['brew', 'install', '--cask', 'google-chrome'])
            return True
        return False
    except:
        return False

# === ТЕСТИРОВАНИЕ ===

if __name__ == "__main__":
    print("🧪 Тестирование браузера...")
    
    browser = AntiDetectBrowser(headless=True)
    browser.setup_driver()
    
    try:
        browser.driver.get("https://www.google.com")
        print(f"✅ Google открыт: {browser.get_current_url()}")
        
        # Проверка на WebDriver
        result = browser.driver.execute_script("return navigator.webdriver")
        print(f"🔍 navigator.webdriver: {result}")
        
        screenshot = browser.take_screenshot("test.png")
        print(f"📸 Скриншот: {screenshot}")
        
    finally:
        browser.close()
        print("✅ Тест завершен")