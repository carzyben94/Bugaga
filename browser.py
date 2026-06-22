from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import os
import time
import random
import shutil
import logging
import zipfile
import urllib.request
import sys
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AntiDetectBrowser:
    def __init__(self, headless=False, screenshot_callback=None):
        self.headless = headless
        self.driver = None
        self.wait = None
        self.install_dir = "/tmp/chrome_bot"
        os.makedirs(self.install_dir, exist_ok=True)
        self.chrome_path = None
        self.screenshot_callback = screenshot_callback
        self.step = 0
        
    def take_step_screenshot(self, name="step"):
        try:
            self.step += 1
            filename = f"step_{self.step}_{name}.png"
            self.driver.save_screenshot(filename)
            if self.screenshot_callback:
                self.screenshot_callback(filename, f"Шаг {self.step}: {name}")
            return filename
        except:
            return None
    
    def install_chrome_local(self):
        try:
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            os.makedirs(chrome_dir, exist_ok=True)
            
            for root, dirs, files in os.walk(chrome_dir):
                if "chrome" in files and not files[0].endswith(".zip"):
                    chrome_path = os.path.join(root, "chrome")
                    os.chmod(chrome_path, 0o755)
                    self.chrome_path = chrome_path
                    logger.info(f"✅ Chrome уже установлен: {chrome_path}")
                    return chrome_path
            
            logger.info("📦 Установка Chrome...")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chrome-linux64.zip"
                zip_path = os.path.join(chrome_dir, "chrome.zip")
                
                urllib.request.urlretrieve(url, zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(chrome_dir)
                
                os.remove(zip_path)
                
                for root, dirs, files in os.walk(chrome_dir):
                    if "chrome" in files and not files[0].endswith(".zip"):
                        chrome_path = os.path.join(root, "chrome")
                        os.chmod(chrome_path, 0o755)
                        self.chrome_path = chrome_path
                        logger.info(f"✅ Chrome готов: {chrome_path}")
                        return chrome_path
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки Chrome: {e}")
            return None
    
    def setup_driver(self):
        logger.info("🔧 Настройка драйвера...")
        
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            for root, dirs, files in os.walk(chrome_dir):
                if "chrome" in files and not files[0].endswith(".zip"):
                    self.chrome_path = os.path.join(root, "chrome")
                    os.chmod(self.chrome_path, 0o755)
                    break
        
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            raise Exception("Chrome не найден. Используйте /install")
        
        options = Options()
        options.binary_location = self.chrome_path
        
        if self.headless:
            options.add_argument('--headless=new')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--window-size=1920,1080')
        
        # === УСТАНОВКА CHROMEDRIVER ===
        logger.info("🚀 Загрузка ChromeDriver...")
        
        driver_path = None
        
        # Способ 1: webdriver_manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            logger.info(f"✅ ChromeDriver через webdriver_manager: {driver_path}")
        except Exception as e:
            logger.warning(f"⚠️ webdriver_manager не сработал: {e}")
        
        # Способ 2: ручная установка в /tmp
        if driver_path is None or not os.path.exists(driver_path):
            logger.info("🔄 Пробую ручную установку ChromeDriver...")
            try:
                driver_dir = os.path.join(self.install_dir, "chromedriver_local")
                os.makedirs(driver_dir, exist_ok=True)
                
                driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
                driver_path = os.path.join(driver_dir, driver_name)
                
                if not os.path.exists(driver_path):
                    # Скачиваем ChromeDriver
                    if sys.platform.startswith('linux'):
                        url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip"
                    elif sys.platform.startswith('win'):
                        url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/win64/chromedriver-win64.zip"
                    else:
                        url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/mac-arm64/chromedriver-mac-arm64.zip"
                    
                    zip_path = os.path.join(driver_dir, "chromedriver.zip")
                    
                    logger.info("⬇️ Скачивание ChromeDriver...")
                    urllib.request.urlretrieve(url, zip_path)
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(driver_dir)
                    
                    os.remove(zip_path)
                    
                    for root, dirs, files in os.walk(driver_dir):
                        if driver_name in files:
                            driver_path = os.path.join(root, driver_name)
                            os.chmod(driver_path, 0o755)
                            break
                
                logger.info(f"✅ ChromeDriver готов: {driver_path}")
                
            except Exception as e2:
                logger.error(f"❌ Ошибка ручной установки: {e2}")
        
        if driver_path is None or not os.path.exists(driver_path):
            raise Exception("Не удалось установить ChromeDriver")
        
        service = Service(driver_path)
        
        logger.info("🚀 Запуск Chrome...")
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(30)
        self.driver.implicitly_wait(10)
        
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.wait = WebDriverWait(self.driver, 10)
        logger.info("✅ Браузер готов")
        return self.driver
    
    def random_delay(self, min_sec=0.3, max_sec=1.0):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_click(self, element):
        try:
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            actions.click()
            actions.perform()
            self.random_delay(0.2, 0.5)
            return True
        except:
            return False
    
    def human_type(self, element, text):
        try:
            element.click()
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.03, 0.08))
            return True
        except:
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
    
    def login_google_first_then_twitter(self, email, password):
        logger.info("🚀 Начало входа через Google")
        
        try:
            self.driver.get("https://accounts.google.com/")
            self.random_delay(2, 3)
            self.take_step_screenshot("google_login")
        except Exception as e:
            logger.error(f"Ошибка Google: {e}")
            return False
        
        email_field = self.find_element(By.ID, "identifierId")
        if email_field:
            self.human_type(email_field, email)
            self.take_step_screenshot("google_email")
        else:
            logger.error("Поле email не найдено")
            return False
        
        self.random_delay(1, 2)
        
        next_btn = self.find_element(By.XPATH, "//span[text()='Далее']")
        if not next_btn:
            next_btn = self.find_element(By.XPATH, "//span[text()='Next']")
        if not next_btn:
            next_btn = self.find_element(By.ID, "identifierNext")
        
        if next_btn:
            self.human_click(next_btn)
            self.take_step_screenshot("google_next")
        
        self.random_delay(2, 3)
        
        password_field = self.find_element(By.NAME, "password")
        if not password_field:
            password_field = self.find_element(By.ID, "password")
        
        if password_field:
            self.human_type(password_field, password)
            self.take_step_screenshot("google_password")
        else:
            logger.error("Поле пароля не найдено")
            return False
        
        self.random_delay(1, 2)
        
        login_btn = self.find_element(By.XPATH, "//span[text()='Далее']")
        if not login_btn:
            login_btn = self.find_element(By.XPATH, "//span[text()='Next']")
        if not login_btn:
            login_btn = self.find_element(By.ID, "passwordNext")
        if not login_btn:
            login_btn = self.find_element(By.XPATH, "//button[@type='submit']")
        
        if login_btn:
            self.human_click(login_btn)
            self.take_step_screenshot("google_login_final")
        
        self.random_delay(3, 5)
        
        current_url = self.driver.current_url
        if "challenge" in current_url or "verify" in current_url:
            logger.info("🔐 Ожидание подтверждения на телефоне...")
            self.take_step_screenshot("google_2fa_wait")
            
            for i in range(12):
                time.sleep(5)
                new_url = self.driver.current_url
                if "challenge" not in new_url and "verify" not in new_url:
                    logger.info("✅ Подтверждение пройдено!")
                    break
        
        self.driver.get("https://x.com")
        self.random_delay(2, 3)
        self.take_step_screenshot("xcom_home")
        
        current_url = self.driver.current_url
        if "home" in current_url or "x.com/home" in current_url:
            logger.info("🎉 Вход выполнен!")
            return True
        else:
            logger.warning(f"⚠️ URL: {current_url}")
            return False
    
    def login_twitter(self, username, password):
        logger.info("🚀 Обычный вход")
        
        self.driver.get("https://x.com/login")
        self.random_delay(2, 3)
        self.take_step_screenshot("twitter_login")
        
        try:
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Sign in']"):
                self.take_step_screenshot("twitter_click_login")
            
            self.random_delay(1, 2)
            
            username_field = self.find_element(By.NAME, "text")
            if username_field:
                self.human_type(username_field, username)
                self.take_step_screenshot("twitter_username")
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Далее']") or \
               self.click_safe(By.XPATH, "//span[text()='Next']"):
                self.take_step_screenshot("twitter_next")
            
            self.random_delay(2, 3)
            
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                self.take_step_screenshot("twitter_password")
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Log in']"):
                self.take_step_screenshot("twitter_final")
            
            self.random_delay(3, 5)
            
            if "home" in self.driver.current_url:
                logger.info("🎉 Вход выполнен!")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return False
    
    def take_screenshot(self, filename="screenshot.png"):
        try:
            self.driver.save_screenshot(filename)
            return filename
        except:
            return None
    
    def get_detailed_logs(self):
        return "Логи доступны в консоли"
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

def check_installation():
    install_dir = "/tmp/chrome_bot"
    chrome_dir = os.path.join(install_dir, "chrome_local")
    
    chrome_found = None
    if os.path.exists(chrome_dir):
        for root, dirs, files in os.walk(chrome_dir):
            if "chrome" in files and not files[0].endswith(".zip"):
                chrome_found = os.path.join(root, "chrome")
                break
    
    return {
        'chrome': chrome_found is not None,
        'chrome_path': chrome_found
    }