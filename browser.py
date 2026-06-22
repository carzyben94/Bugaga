from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import os
import time
import random
import shutil
import logging
import zipfile
import urllib.request
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AntiDetectBrowser:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.wait = None
        self.install_dir = "/tmp/chrome_bot"
        os.makedirs(self.install_dir, exist_ok=True)
        
    def install_chrome_local(self):
        """Установка Chrome в /tmp (без apt-get)"""
        try:
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            os.makedirs(chrome_dir, exist_ok=True)
            
            chrome_path = os.path.join(chrome_dir, "chrome")
            
            if os.path.exists(chrome_path):
                logger.info("✅ Chrome уже установлен в /tmp")
                return chrome_path
            
            logger.info("📦 Установка Chrome в /tmp...")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chrome-linux64.zip"
                zip_path = os.path.join(chrome_dir, "chrome.zip")
                
                logger.info("   ⏳ Скачивание Chrome...")
                urllib.request.urlretrieve(url, zip_path)
                logger.info("   ✅ Скачано")
                
                logger.info("   ⏳ Распаковка...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(chrome_dir)
                logger.info("   ✅ Распаковано")
                
                os.remove(zip_path)
                
                # Ищем исполняемый файл
                for root, dirs, files in os.walk(chrome_dir):
                    if "chrome" in files and not files[0].endswith(".zip"):
                        chrome_path = os.path.join(root, "chrome")
                        os.chmod(chrome_path, 0o755)
                        break
                
                logger.info(f"✅ Chrome установлен в /tmp: {chrome_path}")
                return chrome_path
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки Chrome: {e}")
            return None
    
    def install_chromedriver_local(self):
        """Установка ChromeDriver в /tmp (без apt-get)"""
        try:
            driver_dir = os.path.join(self.install_dir, "chromedriver_local")
            os.makedirs(driver_dir, exist_ok=True)
            
            driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
            driver_path = os.path.join(driver_dir, driver_name)
            
            if os.path.exists(driver_path):
                logger.info("✅ ChromeDriver уже установлен в /tmp")
                return driver_path
            
            logger.info("📦 Установка ChromeDriver в /tmp...")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip"
            elif sys.platform.startswith('win'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/win64/chromedriver-win64.zip"
            else:
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/mac-arm64/chromedriver-mac-arm64.zip"
            
            zip_path = os.path.join(driver_dir, "chromedriver.zip")
            
            logger.info("   ⏳ Скачивание ChromeDriver...")
            urllib.request.urlretrieve(url, zip_path)
            logger.info("   ✅ Скачано")
            
            logger.info("   ⏳ Распаковка...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(driver_dir)
            logger.info("   ✅ Распаковано")
            
            os.remove(zip_path)
            
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    driver_path = os.path.join(root, driver_name)
                    os.chmod(driver_path, 0o755)
                    break
            
            logger.info(f"✅ ChromeDriver установлен в /tmp: {driver_path}")
            return driver_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки ChromeDriver: {e}")
            return None
    
    def setup_driver(self):
        """Настройка драйвера с бинарниками из /tmp"""
        options = Options()
        
        # Устанавливаем Chrome в /tmp
        chrome_path = self.install_chrome_local()
        if chrome_path:
            options.binary_location = chrome_path
            logger.info(f"📍 Chrome: {chrome_path}")
        
        if self.headless:
            options.add_argument('--headless=new')
        
        # === АНТИ-ДЕТЕКТ ===
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # === ДЛЯ RENDER ===
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--remote-debugging-port=9222')
        
        # User-Agent
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        options.add_argument('--lang=en-US,en;q=0.9')
        options.add_experimental_option('prefs', {
            'intl.accept_languages': 'en-US,en;q=0.9',
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
        })
        
        # Устанавливаем ChromeDriver в /tmp
        driver_path = self.install_chromedriver_local()
        
        if driver_path:
            service = Service(driver_path)
            logger.info(f"📍 ChromeDriver: {driver_path}")
        else:
            # fallback
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Скрываем webdriver
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)
        
        self.wait = WebDriverWait(self.driver, 10)
        logger.info("✅ Браузер готов")
        return self.driver
    
    def random_delay(self, min_sec=0.3, max_sec=1.5):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_click(self, element):
        try:
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            self.random_delay(0.1, 0.3)
            actions.click()
            actions.perform()
            self.random_delay(0.3, 0.7)
            return True
        except Exception as e:
            logger.error(f"Ошибка клика: {e}")
            return False
    
    def human_type(self, element, text):
        try:
            element.click()
            self.random_delay(0.2, 0.5)
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.03, 0.12))
            self.random_delay(0.3, 0.6)
            return True
        except Exception as e:
            logger.error(f"Ошибка ввода: {e}")
            return False
    
    def find_element(self, by, selector, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except:
            return None
    
    def click_safe(self, by, selector, timeout=10):
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            return self.human_click(element)
        except:
            return False
    
    def login_twitter(self, username, password):
        logger.info("🚀 Открываем Twitter...")
        self.driver.get("https://x.com/login")
        self.random_delay(2, 4)
        
        try:
            # Кнопка входа
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Sign in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='loginButton']"):
                logger.info("✅ Кнопка входа нажата")
            
            self.random_delay(1, 2)
            
            # Логин
            username_field = self.find_element(By.NAME, "text")
            if username_field:
                self.human_type(username_field, username)
                logger.info(f"✅ Логин: {username}")
            else:
                logger.error("❌ Поле логина не найдено")
                return False
            
            self.random_delay(1, 2)
            
            # Далее
            if self.click_safe(By.XPATH, "//span[text()='Далее']") or \
               self.click_safe(By.XPATH, "//span[text()='Next']"):
                logger.info("✅ Кнопка 'Далее' нажата")
            
            self.random_delay(2, 3)
            
            # Пароль
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                logger.info("✅ Пароль введен")
            else:
                logger.error("❌ Поле пароля не найдено")
                return False
            
            self.random_delay(1, 2)
            
            # Войти
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Log in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='LoginForm_Login_Button']"):
                logger.info("✅ Кнопка 'Войти' нажата")
            
            self.random_delay(3, 5)
            
            if "home" in self.driver.current_url.lower():
                logger.info("🎉 Вход выполнен успешно!")
                return True
            return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def take_screenshot(self, filename="screenshot.png"):
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"✅ Скриншот: {filename}")
            return filename
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота: {e}")
            return None
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Браузер закрыт")
            except:
                pass

# === ОЧИСТКА /tmp ПРИ ЗАПУСКЕ ===
def cleanup_temp():
    temp_dir = "/tmp/chrome_bot"
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logger.info("🧹 Очищена папка /tmp/chrome_bot")
        except:
            pass
    os.makedirs(temp_dir, exist_ok=True)

cleanup_temp()