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
import logging
import zipfile
import urllib.request
import sys
import subprocess
from datetime import datetime

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
LOG_FILE = "bot.log"

if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_chromedriver_path():
    logger.info("📦 Загрузка ChromeDriver...")
    chrome_driver_dir = "/tmp/chromedriver"
    os.makedirs(chrome_driver_dir, exist_ok=True)
    
    driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
    driver_path = os.path.join(chrome_driver_dir, driver_name)
    
    if os.path.exists(driver_path):
        logger.info("✅ ChromeDriver уже есть")
        os.chmod(driver_path, 0o755)
        return driver_path
    
    url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/149.0.7827.155/linux64/chromedriver-linux64.zip"
    zip_path = os.path.join(chrome_driver_dir, "chromedriver.zip")
    
    urllib.request.urlretrieve(url, zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(chrome_driver_dir)
    
    os.remove(zip_path)
    
    for root, dirs, files in os.walk(chrome_driver_dir):
        if driver_name in files:
            driver_path = os.path.join(root, driver_name)
            os.chmod(driver_path, 0o755)
            logger.info("✅ ChromeDriver готов")
            return driver_path
    
    raise Exception("ChromeDriver не найден")

class AntiDetectBrowser:
    def __init__(self, headless=False, screenshot_callback=None, log_callback=None):
        self.headless = headless
        self.driver = None
        self.wait = None
        self.screenshot_callback = screenshot_callback
        self.log_callback = log_callback
        self.step = 0
        self.email = None
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        if self.log_callback:
            self.log_callback(log_entry)
        
        return log_entry
        
    def take_step_screenshot(self, name="step"):
        try:
            self.step += 1
            filename = f"step_{self.step}_{name}.png"
            self.driver.save_screenshot(filename)
            self.log(f"📸 Скриншот: {name}", "STEP")
            if self.screenshot_callback:
                self.screenshot_callback(filename, f"Шаг {self.step}: {name}")
            return filename
        except Exception as e:
            self.log(f"❌ Ошибка скриншота: {e}", "ERROR")
            return None
    
    def setup_driver(self):
        self.log("🔧 Настройка драйвера...", "INFO")
        
        options = Options()
        options.binary_location = "/usr/bin/google-chrome"
        
        if self.headless:
            options.add_argument('--headless=new')
            self.log("🔇 Headless режим", "INFO")
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36')
        options.add_argument('--window-size=1920,1080')
        
        driver_path = get_chromedriver_path()
        service = Service(driver_path)
        
        try:
            self.driver = webdriver.Chrome(service=service, options=options)
            self.log("✅ Chrome запущен", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            raise
        
        self.driver.set_page_load_timeout(30)
        self.driver.implicitly_wait(10)
        
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.wait = WebDriverWait(self.driver, 10)
        self.log("✅ Браузер готов", "SUCCESS")
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
        except Exception as e:
            self.log(f"❌ Ошибка клика: {e}", "ERROR")
            return False
    
    # ===== НОВЫЙ МЕТОД ВВОДА ЧЕРЕЗ ACTIONCHAINS =====
    def type_with_actions(self, element, text):
        """Ввод текста через ActionChains (надежно)"""
        try:
            self.log(f"⌨️ Ввод через ActionChains", "DEBUG")
            
            # Кликаем по элементу
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            actions.click()
            actions.perform()
            time.sleep(0.5)
            
            # Очищаем (Ctrl+A + Delete)
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL)
            actions.send_keys('a')
            actions.key_up(Keys.CONTROL)
            actions.send_keys(Keys.DELETE)
            actions.perform()
            time.sleep(0.5)
            
            # Вводим текст посимвольно
            for char in text:
                actions = ActionChains(self.driver)
                actions.send_keys(char)
                actions.perform()
                time.sleep(random.uniform(0.05, 0.15))
            
            self.log("✅ Текст введен через ActionChains", "SUCCESS")
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка ввода через ActionChains: {e}", "ERROR")
            return False
    
    # ===== НОВЫЙ МЕТОД ПОИСКА ПОЛЯ ПАРОЛЯ =====
    def safe_find_password_field(self, timeout=30):
        """Найти поле пароля с большим терпением"""
        selectors = [
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[@name='password']"),
            (By.XPATH, "//div[@class='pwd']//input"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.XPATH, "//div[@data-brand='accounts.google.com']//input[@type='password']"),
            (By.CSS_SELECTOR, "div[class*='password'] input"),
            (By.XPATH, "//input[@autocomplete='current-password']"),
        ]
        
        for attempt in range(5):
            self.log(f"🔍 Попытка {attempt+1} поиска поля пароля...", "DEBUG")
            
            for by, selector in selectors:
                try:
                    self.log(f"   Пробую: {by}={selector}", "DEBUG")
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if element and element.is_displayed():
                        # Ждем кликабельности
                        try:
                            WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((by, selector))
                            )
                            self.log(f"✅ Поле пароля найдено: {selector}", "SUCCESS")
                            return element
                        except:
                            self.log(f"   Элемент есть, но не кликабелен", "DEBUG")
                            continue
                except Exception as e:
                    continue
            
            self.random_delay(2, 3)
            
            if attempt == 2:
                self.take_step_screenshot("password_field_search")
        
        self.log("❌ Поле пароля не найдено", "ERROR")
        return None
    
    # ===== СТАРЫЙ МЕТОД human_type (оставляем для совместимости) =====
    def human_type(self, element, text):
        try:
            self.log(f"⌨️ Ввод текста: {text[:3]}***{text[-3:] if len(text) > 6 else ''}", "DEBUG")
            
            # Ждем 2 секунды перед вводом
            time.sleep(2)
            
            # Пробуем кликнуть несколько раз
            for attempt in range(5):
                try:
                    element.click()
                    time.sleep(0.5)
                    if element.is_enabled():
                        break
                except:
                    time.sleep(0.5)
            
            element.clear()
            time.sleep(0.5)
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            self.log("✅ Текст введен", "SUCCESS")
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка ввода: {e}", "ERROR")
            return False
    
    def find_element(self, by, selector, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except Exception as e:
            self.log(f"❌ Элемент не найден: {selector}", "WARNING")
            return None
    
    def find_element_clickable(self, by, selector, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
        except:
            return None
    
    def login_google(self, email, password):
        self.email = email
        self.log(f"🚀 Вход в Google: {email[:3]}***{email[-3:] if len(email) > 6 else ''}", "INFO")
        
        try:
            self.log("🌐 Открытие Google...", "INFO")
            self.driver.get("https://accounts.google.com/")
            self.random_delay(2, 3)
            self.take_step_screenshot("google_login")
            self.log("✅ Google открыт", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка Google: {e}", "ERROR")
            return False
        
        # === ВВОД EMAIL ===
        self.log("🔍 Поиск поля email...", "INFO")
        email_field = self.find_element(By.ID, "identifierId")
        if email_field:
            self.human_type(email_field, email)
            self.take_step_screenshot("google_email")
            self.log(f"✅ Email введен", "SUCCESS")
        else:
            self.log("❌ Поле email не найдено", "ERROR")
            return False
        
        self.random_delay(1, 2)
        
        # === КНОПКА "ДАЛЕЕ" ===
        self.log("🔍 Поиск кнопки 'Далее'...", "INFO")
        next_btn = self.find_element_clickable(By.XPATH, "//span[text()='Далее']")
        if not next_btn:
            next_btn = self.find_element_clickable(By.XPATH, "//span[text()='Next']")
        if not next_btn:
            next_btn = self.find_element_clickable(By.ID, "identifierNext")
        
        if next_btn:
            self.human_click(next_btn)
            self.take_step_screenshot("google_next")
            self.log("✅ Кнопка 'Далее' нажата", "SUCCESS")
        else:
            self.log("⚠️ Кнопка 'Далее' не найдена", "WARNING")
        
        self.random_delay(2, 4)
        
        # === ПРОВЕРЯЕМ СТРАНИЦУ ===
        current_url = self.driver.current_url
        
        # Если страница подтверждения
        if "challenge" in current_url or "verify" in current_url.lower():
            self.log("🔐 Страница подтверждения Google", "INFO")
            self.take_step_screenshot("google_verify_page")
            
            self.log("📱 Подтвердите вход на телефоне", "INFO")
            self.log("⏳ Ожидание... 60 секунд", "INFO")
            
            for i in range(12):
                time.sleep(5)
                new_url = self.driver.current_url
                if "challenge" not in new_url and "verify" not in new_url.lower():
                    self.log("✅ Подтверждение пройдено!", "SUCCESS")
                    break
                self.log(f"⏳ Ожидание... {i+1}/12", "INFO")
            
            self.log("✅ Продолжаем...", "INFO")
            return True
        
        # === ВВОД ПАРОЛЯ (НОВЫЙ МЕТОД) ===
        self.log("🔍 Поиск поля пароля...", "INFO")
        
        # Ждем появления поля пароля
        self.log("⏳ Ожидание появления поля пароля...", "INFO")
        self.random_delay(2, 4)
        
        # Ищем поле пароля через safe_find_password_field
        password_field = self.safe_find_password_field()
        
        if password_field:
            self.log("✅ Поле пароля найдено, пробую ввести...", "SUCCESS")
            
            # Пробуем ввести через ActionChains
            success = self.type_with_actions(password_field, password)
            
            if success:
                self.take_step_screenshot("google_password_entered")
                self.log("✅ Пароль введен через ActionChains", "SUCCESS")
            else:
                # Fallback: обычный ввод
                try:
                    self.log("🔄 Пробую обычный ввод...", "DEBUG")
                    password_field.click()
                    self.random_delay(0.5, 1)
                    password_field.clear()
                    password_field.send_keys(password)
                    self.log("✅ Пароль введен (обычный способ)", "SUCCESS")
                    self.take_step_screenshot("google_password_entered")
                except Exception as e:
                    self.log(f"❌ Ошибка ввода пароля: {e}", "ERROR")
                    self.take_step_screenshot("google_password_error")
                    return False
        else:
            self.log("❌ Поле пароля не найдено", "ERROR")
            self.take_step_screenshot("google_password_not_found")
            return False
        
        self.random_delay(1, 2)
        
        # === ФИНАЛЬНАЯ КНОПКА ===
        self.log("🔍 Поиск кнопки входа...", "INFO")
        login_btn = self.find_element_clickable(By.XPATH, "//span[text()='Далее']")
        if not login_btn:
            login_btn = self.find_element_clickable(By.XPATH, "//span[text()='Next']")
        if not login_btn:
            login_btn = self.find_element_clickable(By.ID, "passwordNext")
        if not login_btn:
            login_btn = self.find_element_clickable(By.XPATH, "//button[@type='submit']")
        
        if login_btn:
            self.human_click(login_btn)
            self.take_step_screenshot("google_login_final")
            self.log("✅ Кнопка входа нажата", "SUCCESS")
        else:
            self.log("⚠️ Кнопка входа не найдена", "WARNING")
        
        self.random_delay(3, 5)
        
        # === ПРОВЕРКА 2FA ===
        current_url = self.driver.current_url
        self.log(f"📍 Финальный URL: {current_url[:80]}...", "INFO")
        
        if "challenge" in current_url or "verify" in current_url.lower():
            self.log("🔐 Требуется подтверждение на телефоне", "INFO")
            self.take_step_screenshot("google_2fa_wait")
            
            for i in range(12):
                time.sleep(5)
                new_url = self.driver.current_url
                if "challenge" not in new_url and "verify" not in new_url.lower():
                    self.log("✅ Подтверждение пройдено!", "SUCCESS")
                    break
                self.log(f"⏳ Ожидание подтверждения... {i+1}/12", "INFO")
        
        self.log("✅ Вход в Google выполнен!", "SUCCESS")
        self.take_step_screenshot("google_done")
        return True
    
    def go_to_xcom(self):
        """Переход на X.com"""
        self.log("🌐 Переход на X.com...", "INFO")
        
        try:
            self.driver.get("https://x.com")
            self.random_delay(3, 5)
            self.take_step_screenshot("xcom_home")
            
            current_url = self.driver.current_url
            self.log(f"📍 URL: {current_url}", "INFO")
            
            if "home" in current_url or "x.com/home" in current_url:
                self.log("🎉 Уже на главной X.com", "SUCCESS")
                return True
            
            if "login" in current_url or "i/flow" in current_url:
                self.log("🔍 На странице входа, ищу кнопки...", "INFO")
                
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                self.log(f"📊 Найдено кнопок: {len(buttons)}", "INFO")
                
                for btn in buttons:
                    try:
                        text = btn.text.strip()
                        if text and ("Continue" in text or "Войти" in text or "Google" in text):
                            self.log(f"✅ Нажимаю кнопку: '{text[:30]}'", "SUCCESS")
                            self.human_click(btn)
                            self.random_delay(2, 3)
                            self.take_step_screenshot("xcom_click_button")
                            break
                    except:
                        continue
                
                if self.email:
                    try:
                        email_elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{self.email}')]")
                        for elem in email_elements:
                            if elem.is_displayed():
                                self.log(f"✅ Найден email: {self.email}", "SUCCESS")
                                self.human_click(elem)
                                self.random_delay(2, 3)
                                self.take_step_screenshot("xcom_click_email")
                                break
                    except:
                        pass
                
                try:
                    continue_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue')]")
                    for elem in continue_elements:
                        if elem.is_displayed() and elem.is_enabled():
                            self.log(f"✅ Нажимаю 'Continue': {elem.text[:30]}", "SUCCESS")
                            self.human_click(elem)
                            self.random_delay(2, 3)
                            self.take_step_screenshot("xcom_click_continue")
                            break
                except:
                    pass
            
            self.random_delay(2, 3)
            current_url = self.driver.current_url
            self.log(f"📍 Финальный URL: {current_url}", "INFO")
            
            if "home" in current_url or "x.com/home" in current_url:
                self.log("🎉 Вход выполнен успешно!", "SUCCESS")
                return True
            else:
                self.log(f"⚠️ Неизвестный URL: {current_url}", "WARNING")
                return False
            
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            return False
    
    def login_twitter(self, username, password):
        self.log("🚀 Обычный вход", "INFO")
        
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
                self.log("🎉 Вход выполнен!", "SUCCESS")
                return True
            return False
            
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            return False
    
    def click_safe(self, by, selector, timeout=10):
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            return self.human_click(element)
        except:
            return False
    
    def take_screenshot(self, filename="screenshot.png"):
        try:
            self.driver.save_screenshot(filename)
            return filename
        except:
            return None
    
    def get_logs(self):
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return "Логов пока нет"
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                self.log("✅ Браузер закрыт", "SUCCESS")
            except:
                pass

def check_installation():
    return {
        'chrome': os.path.exists("/usr/bin/google-chrome"),
        'chrome_path': "/usr/bin/google-chrome"
    }