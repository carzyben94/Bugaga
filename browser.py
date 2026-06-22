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
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AntiDetectBrowser:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.wait = None
        # Прямые пути к бинарникам в /tmp
        self.chrome_path = "/tmp/chrome_bot/chrome_local/chrome"
        self.driver_path = "/tmp/chrome_bot/chromedriver_local/chromedriver"
        
    def setup_driver(self):
        """Настройка драйвера с готовыми бинарниками"""
        options = Options()
        
        # Используем готовый Chrome
        if os.path.exists(self.chrome_path):
            options.binary_location = self.chrome_path
            logger.info(f"📍 Chrome: {self.chrome_path}")
        else:
            logger.error("❌ Chrome не найден! Запустите /install")
            raise Exception("Chrome не найден. Используйте /install")
        
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
        
        # Используем готовый ChromeDriver
        if os.path.exists(self.driver_path):
            service = Service(self.driver_path)
            logger.info(f"📍 ChromeDriver: {self.driver_path}")
        else:
            logger.error("❌ ChromeDriver не найден! Запустите /install")
            raise Exception("ChromeDriver не найден. Используйте /install")
        
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

# === ФУНКЦИЯ ДЛЯ ПРОВЕРКИ ===
def check_installation():
    """Проверяет наличие бинарников"""
    chrome_path = "/tmp/chrome_bot/chrome_local/chrome"
    driver_path = "/tmp/chrome_bot/chromedriver_local/chromedriver"
    
    result = {
        'chrome': os.path.exists(chrome_path),
        'chromedriver': os.path.exists(driver_path),
        'chrome_path': chrome_path,
        'driver_path': driver_path
    }
    
    return result