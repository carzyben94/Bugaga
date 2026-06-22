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
import subprocess
import json
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AntiDetectBrowser:
    def __init__(self, headless=False, screenshot_callback=None, log_callback=None):
        self.headless = headless
        self.driver = None
        self.wait = None
        self.install_dir = "/tmp/chrome_bot"
        os.makedirs(self.install_dir, exist_ok=True)
        self.chrome_path = None
        self.driver_path = None
        self.screenshot_callback = screenshot_callback
        self.log_callback = log_callback
        self.step = 0
        self.detailed_logs = []
        
    def log(self, message, level="INFO", data=None):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = {
            "time": timestamp,
            "level": level,
            "message": message,
            "data": data
        }
        self.detailed_logs.append(log_entry)
        
        log_text = f"[{timestamp}] [{level}] {message}"
        if data:
            log_text += f"\n   📎 {json.dumps(data, ensure_ascii=False, indent=2)}"
        
        logger.info(log_text)
        
        if self.log_callback:
            self.log_callback(log_text, level)
        
        return log_entry
    
    def take_step_screenshot(self, name="step"):
        try:
            self.step += 1
            filename = f"step_{self.step}_{name}.png"
            self.driver.save_screenshot(filename)
            self.log(f"📸 Скриншот: {name}", "STEP", {"filename": filename, "step": self.step})
            
            if self.screenshot_callback:
                self.screenshot_callback(filename, f"Шаг {self.step}: {name}")
            
            return filename
        except Exception as e:
            self.log(f"❌ Ошибка скриншота: {e}", "ERROR")
            return None
    
    def extract_zip_fast(self, zip_path, extract_to):
        try:
            if shutil.which('unzip'):
                self.log("⏳ Распаковка через system unzip...", "DEBUG")
                subprocess.check_call(['unzip', '-q', zip_path, '-d', extract_to])
                self.log("✅ Распаковано (unzip)", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"⚠️ Ошибка unzip: {e}, пробую Python", "WARNING")
        
        self.log("⏳ Распаковка через Python zipfile...", "DEBUG")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        self.log("✅ Распаковано (Python)", "SUCCESS")
        return True
    
    def install_chrome_local(self):
        try:
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            os.makedirs(chrome_dir, exist_ok=True)
            
            for root, dirs, files in os.walk(chrome_dir):
                if "chrome" in files and not files[0].endswith(".zip"):
                    chrome_path = os.path.join(root, "chrome")
                    os.chmod(chrome_path, 0o755)
                    self.chrome_path = chrome_path
                    self.log(f"✅ Chrome уже установлен: {chrome_path}", "SUCCESS")
                    return chrome_path
            
            self.log("📦 Установка Chrome в /tmp...", "INFO")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chrome-linux64.zip"
                zip_path = os.path.join(chrome_dir, "chrome.zip")
                
                self.log(f"⬇️ Скачивание Chrome: {url}", "INFO")
                urllib.request.urlretrieve(url, zip_path)
                self.log(f"✅ Скачано: {os.path.getsize(zip_path)} bytes", "SUCCESS")
                
                self.extract_zip_fast(zip_path, chrome_dir)
                os.remove(zip_path)
                
                for root, dirs, files in os.walk(chrome_dir):
                    if "chrome" in files and not files[0].endswith(".zip"):
                        chrome_path = os.path.join(root, "chrome")
                        os.chmod(chrome_path, 0o755)
                        self.chrome_path = chrome_path
                        self.log(f"✅ Chrome готов: {chrome_path}", "SUCCESS")
                        return chrome_path
            
            return None
            
        except Exception as e:
            self.log(f"❌ Ошибка установки Chrome: {e}", "ERROR")
            return None
    
    def install_chromedriver_local(self):
        try:
            driver_dir = os.path.join(self.install_dir, "chromedriver_local")
            os.makedirs(driver_dir, exist_ok=True)
            
            driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
            
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    driver_path = os.path.join(root, driver_name)
                    os.chmod(driver_path, 0o755)
                    self.driver_path = driver_path
                    self.log(f"✅ ChromeDriver уже установлен: {driver_path}", "SUCCESS")
                    return driver_path
            
            self.log("📦 Установка ChromeDriver в /tmp...", "INFO")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip"
            elif sys.platform.startswith('win'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/win64/chromedriver-win64.zip"
            else:
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/mac-arm64/chromedriver-mac-arm64.zip"
            
            zip_path = os.path.join(driver_dir, "chromedriver.zip")
            
            self.log(f"⬇️ Скачивание ChromeDriver: {url}", "INFO")
            urllib.request.urlretrieve(url, zip_path)
            self.log(f"✅ Скачано: {os.path.getsize(zip_path)} bytes", "SUCCESS")
            
            self.extract_zip_fast(zip_path, driver_dir)
            os.remove(zip_path)
            
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    driver_path = os.path.join(root, driver_name)
                    os.chmod(driver_path, 0o755)
                    self.driver_path = driver_path
                    self.log(f"✅ ChromeDriver готов: {driver_path}", "SUCCESS")
                    return driver_path
            
            return None
            
        except Exception as e:
            self.log(f"❌ Ошибка установки ChromeDriver: {e}", "ERROR")
            return None
    
    def setup_driver(self):
        self.log("🔧 Настройка драйвера...", "INFO")
        
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            for root, dirs, files in os.walk(chrome_dir):
                if "chrome" in files and not files[0].endswith(".zip"):
                    self.chrome_path = os.path.join(root, "chrome")
                    self.log(f"✅ Найден Chrome: {self.chrome_path}", "SUCCESS")
                    break
        
        if not self.driver_path or not os.path.exists(self.driver_path):
            driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
            driver_dir = os.path.join(self.install_dir, "chromedriver_local")
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    self.driver_path = os.path.join(root, driver_name)
                    self.log(f"✅ Найден ChromeDriver: {self.driver_path}", "SUCCESS")
                    break
        
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            raise Exception("Chrome не найден. Используйте /install")
        
        if not self.driver_path or not os.path.exists(self.driver_path):
            raise Exception("ChromeDriver не найден. Используйте /install")
        
        options = Options()
        options.binary_location = self.chrome_path
        
        if self.headless:
            options.add_argument('--headless=new')
            self.log("🔇 Headless режим включен", "INFO")
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=256')
        options.add_argument('--js-flags=--max-old-space-size=256')
        options.add_argument('--disable-dev-tools')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-session-crashed-bubble')
        
        # Десктопный User-Agent
        desktop_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        options.add_argument(f'--user-agent={desktop_user_agent}')
        self.log(f"🖥️ User-Agent: {desktop_user_agent[:50]}...", "DEBUG")
        
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        options.add_argument('--lang=en-US,en;q=0.9')
        
        options.add_experimental_option('prefs', {
            'intl.accept_languages': 'en-US,en;q=0.9',
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'profile.default_content_settings': {
                'images': 1,
                'javascript': 1,
                'popups': 2,
                'notifications': 2,
            },
        })
        
        service = Service(
            self.driver_path,
            service_args=['--verbose', '--log-path=chromedriver.log'],
            log_output=subprocess.DEVNULL
        )
        
        try:
            self.log("🚀 Запуск Chrome...", "INFO")
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            self.driver.set_window_size(1920, 1080)
            self.log("✅ Chrome запущен", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            raise
        
        # Скрываем webdriver
        self.log("🔧 Скрытие признаков автоматизации...", "DEBUG")
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
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)
        self.log("✅ WebDriver скрыт", "SUCCESS")
        
        self.wait = WebDriverWait(self.driver, 10)
        self.log("✅ Браузер готов (десктопная версия)", "SUCCESS")
        return self.driver
    
    def random_delay(self, min_sec=0.3, max_sec=1.0):
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return delay
    
    def human_click(self, element):
        try:
            element_text = element.text[:30] if element.text else "без текста"
            self.log(f"🖱️ Клик по элементу: '{element_text}'", "DEBUG")
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            self.random_delay(0.1, 0.2)
            actions.click()
            actions.perform()
            self.random_delay(0.2, 0.5)
            self.log("✅ Клик выполнен", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка клика: {e}", "ERROR")
            return False
    
    def human_type(self, element, text):
        try:
            self.log(f"⌨️ Ввод текста: {text[:3]}***{text[-3:] if len(text) > 6 else ''}", "DEBUG")
            element.click()
            self.random_delay(0.2, 0.3)
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))
            self.random_delay(0.2, 0.4)
            self.log("✅ Текст введен", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка ввода: {e}", "ERROR")
            return False
    
    def find_element(self, by, selector, timeout=10):
        try:
            self.log(f"🔍 Поиск элемента: {by}={selector}", "DEBUG")
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            self.log(f"✅ Элемент найден: {selector}", "SUCCESS")
            return element
        except Exception as e:
            self.log(f"❌ Элемент не найден: {selector} ({e})", "WARNING")
            return None
    
    def click_safe(self, by, selector, timeout=10):
        try:
            self.log(f"🔍 Поиск кликабельного элемента: {by}={selector}", "DEBUG")
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            self.log(f"✅ Элемент кликабелен: {selector}", "SUCCESS")
            return self.human_click(element)
        except Exception as e:
            self.log(f"❌ Элемент не кликабелен: {selector} ({e})", "WARNING")
            return False
    
    def get_page_info(self):
        try:
            info = {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "page_source_length": len(self.driver.page_source)
            }
            self.log(f"📄 Информация о странице: {info['url']}", "INFO", info)
            return info
        except Exception as e:
            self.log(f"❌ Ошибка получения информации: {e}", "ERROR")
            return None
    
    # ===== НОВЫЙ МЕТОД: СНАЧАЛА GOOGLE, ПОТОМ X.COM =====
    def login_google_first_then_twitter(self, email, password):
        """
        Вход: сначала авторизация в Google, потом переход на X.com
        """
        self.log("🚀 ===== НАЧАЛО ВХОДА (Google → X.com) =====", "INFO")
        self.log(f"📧 Email: {email[:3]}***{email[-3:] if len(email) > 6 else ''}", "INFO")
        self.log(f"🔑 Пароль: {'*' * len(password)}", "INFO")
        
        # ===== ШАГ 1: Авторизация в Google =====
        self.log("🌐 ШАГ 1: Открытие Google", "STEP")
        try:
            self.driver.get("https://accounts.google.com/")
            self.random_delay(2, 3)
            self.log("✅ Google открыт", "SUCCESS")
            self.take_step_screenshot("google_login_page")
        except Exception as e:
            self.log(f"❌ Ошибка загрузки Google: {e}", "ERROR")
            return False
        
        # ШАГ 2: Ввод email
        self.log("🔍 ШАГ 2: Ввод email", "STEP")
        email_field = self.find_element(By.ID, "identifierId")
        if not email_field:
            email_field = self.find_element(By.NAME, "identifier")
        if not email_field:
            email_field = self.find_element(By.XPATH, "//input[@type='email']")
        
        if email_field:
            self.human_type(email_field, email)
            self.take_step_screenshot("google_email_entered")
        else:
            self.log("❌ Поле email не найдено", "ERROR")
            self.take_step_screenshot("google_email_not_found")
            return False
        
        self.random_delay(1, 2)
        
        # ШАГ 3: Кнопка "Далее" в Google
        self.log("🔍 ШАГ 3: Кнопка 'Далее' в Google", "STEP")
        next_btn = self.find_element(By.XPATH, "//span[text()='Далее']")
        if not next_btn:
            next_btn = self.find_element(By.XPATH, "//span[text()='Next']")
        if not next_btn:
            next_btn = self.find_element(By.ID, "identifierNext")
        
        if next_btn:
            self.human_click(next_btn)
            self.take_step_screenshot("google_click_next")
        else:
            self.log("⚠️ Кнопка 'Далее' не найдена", "WARNING")
            self.take_step_screenshot("google_next_not_found")
        
        self.random_delay(2, 3)
        
        # ШАГ 4: Ввод пароля
        self.log("🔍 ШАГ 4: Ввод пароля в Google", "STEP")
        password_field = self.find_element(By.NAME, "password")
        if not password_field:
            password_field = self.find_element(By.ID, "password")
        if not password_field:
            password_field = self.find_element(By.XPATH, "//input[@type='password']")
        
        if password_field:
            self.human_type(password_field, password)
            self.take_step_screenshot("google_password_entered")
        else:
            self.log("❌ Поле пароля не найдено", "ERROR")
            self.take_step_screenshot("google_password_not_found")
            return False
        
        self.random_delay(1, 2)
        
        # ШАГ 5: Финальная кнопка входа в Google
        self.log("🔍 ШАГ 5: Финальный вход в Google", "STEP")
        login_btn = self.find_element(By.XPATH, "//span[text()='Далее']")
        if not login_btn:
            login_btn = self.find_element(By.XPATH, "//span[text()='Next']")
        if not login_btn:
            login_btn = self.find_element(By.ID, "passwordNext")
        if not login_btn:
            login_btn = self.find_element(By.XPATH, "//span[text()='Войти']")
        if not login_btn:
            login_btn = self.find_element(By.XPATH, "//button[@type='submit']")
        
        if login_btn:
            self.human_click(login_btn)
            self.take_step_screenshot("google_final_login")
        else:
            self.log("⚠️ Кнопка входа не найдена", "WARNING")
            self.take_step_screenshot("google_login_not_found")
        
        self.random_delay(3, 5)
        self.take_step_screenshot("google_logged_in")
        
        # Проверка: успешно ли вошли в Google
        current_url = self.driver.current_url
        self.log(f"📍 URL после Google: {current_url}", "INFO")
        
        if "accounts.google.com" in current_url and "signin" in current_url:
            self.log("⚠️ Возможно требуется 2FA или подтверждение", "WARNING")
            self.take_step_screenshot("google_2fa_needed")
            # Проверяем наличие кода подтверждения
            try:
                code_field = self.driver.find_elements(By.XPATH, "//input[@type='text']")
                if code_field:
                    self.log("🔢 Найдено поле для кода 2FA", "INFO")
                    return False
            except:
                pass
        
        # ===== ШАГ 6: Переход на X.com =====
        self.log("🌐 ШАГ 6: Переход на X.com", "STEP")
        try:
            self.driver.get("https://x.com/login")
            self.random_delay(2, 3)
            self.log("✅ X.com открыт", "SUCCESS")
            self.take_step_screenshot("xcom_login_page")
        except Exception as e:
            self.log(f"❌ Ошибка загрузки X.com: {e}", "ERROR")
            return False
        
        # ШАГ 7: Нажимаем "Continue with Google" (теперь это быстро)
        self.log("🔍 ШАГ 7: Нажатие 'Continue with Google'", "STEP")
        
        google_btn = None
        selectors = [
            "//span[contains(text(), 'Continue with Google')]",
            "//span[contains(text(), 'Continue with Google')]/ancestor::button",
            "//div[contains(text(), 'Continue with Google')]",
            "//button[contains(@class, 'google')]",
            "//*[contains(text(), 'Google')]//ancestor::button"
        ]
        
        for selector in selectors:
            try:
                if selector.startswith('//'):
                    element = self.driver.find_element(By.XPATH, selector)
                else:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                
                if element and element.is_displayed():
                    google_btn = element
                    self.log(f"✅ Найдена кнопка Google", "SUCCESS")
                    break
            except:
                continue
        
        if google_btn:
            self.human_click(google_btn)
            self.take_step_screenshot("xcom_click_google")
        else:
            self.log("⚠️ Кнопка Google не найдена", "WARNING")
            self.take_step_screenshot("xcom_google_not_found")
            return False
        
        self.random_delay(3, 5)
        self.take_step_screenshot("xcom_final_result")
        
        # ШАГ 8: Проверка результата
        self.log("🔍 ШАГ 8: Проверка результата", "STEP")
        current_url = self.driver.current_url
        self.log(f"📍 Финальный URL: {current_url}", "INFO")
        
        if "home" in current_url.lower() or "x.com/home" in current_url.lower():
            self.log("🎉 Вход выполнен успешно!", "SUCCESS")
            return True
        else:
            self.log(f"⚠️ Неизвестный URL: {current_url}", "WARNING")
            return False
    
    # ===== СТАРЫЙ МЕТОД (оставляем для совместимости) =====
    def login_twitter_with_google(self, email, password):
        """Старый метод - вход через всплывающее окно"""
        return self.login_google_first_then_twitter(email, password)
    
    def login_twitter(self, username, password):
        """Обычный вход"""
        self.log("🚀 ===== ОБЫЧНЫЙ ВХОД =====", "INFO")
        
        try:
            self.driver.get("https://x.com/login")
            self.log("✅ X.com открыт", "SUCCESS")
            self.random_delay(2, 3)
            self.take_step_screenshot("login_page")
        except Exception as e:
            self.log(f"❌ Ошибка загрузки: {e}", "ERROR")
            return False
        
        try:
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Sign in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='loginButton']"):
                self.log("✅ Кнопка входа нажата", "SUCCESS")
                self.take_step_screenshot("click_login")
            
            self.random_delay(1, 2)
            
            username_field = self.find_element(By.NAME, "text")
            if username_field:
                self.human_type(username_field, username)
                self.log(f"✅ Логин введен", "SUCCESS")
                self.take_step_screenshot("username_entered")
            else:
                self.log("❌ Поле логина не найдено", "ERROR")
                return False
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Далее']") or \
               self.click_safe(By.XPATH, "//span[text()='Next']"):
                self.log("✅ Кнопка 'Далее' нажата", "SUCCESS")
                self.take_step_screenshot("click_next")
            
            self.random_delay(2, 3)
            
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                self.log("✅ Пароль введен", "SUCCESS")
                self.take_step_screenshot("password_entered")
            else:
                self.log("❌ Поле пароля не найдено", "ERROR")
                return False
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Log in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='LoginForm_Login_Button']"):
                self.log("✅ Кнопка 'Войти' нажата", "SUCCESS")
                self.take_step_screenshot("click_final_login")
            
            self.random_delay(3, 5)
            self.take_step_screenshot("final_result")
            
            if "home" in self.driver.current_url.lower():
                self.log("🎉 Вход выполнен успешно!", "SUCCESS")
                return True
            else:
                self.log(f"⚠️ URL: {self.driver.current_url}", "WARNING")
                return False
                
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            self.take_step_screenshot("error_crash")
            return False
    
    def take_screenshot(self, filename="screenshot.png"):
        try:
            self.driver.save_screenshot(filename)
            self.log(f"✅ Скриншот: {filename}", "SUCCESS")
            return filename
        except Exception as e:
            self.log(f"❌ Ошибка скриншота: {e}", "ERROR")
            return None
    
    def get_detailed_logs(self):
        result = []
        for log in self.detailed_logs:
            text = f"[{log['time']}] [{log['level']}] {log['message']}"
            result.append(text)
        return "\n".join(result)
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                self.log("✅ Браузер закрыт", "SUCCESS")
            except:
                pass

# === ФУНКЦИИ ДЛЯ ПРОВЕРКИ ===
def check_installation():
    install_dir = "/tmp/chrome_bot"
    chrome_dir = os.path.join(install_dir, "chrome_local")
    driver_dir = os.path.join(install_dir, "chromedriver_local")
    
    chrome_found = None
    driver_found = None
    
    if os.path.exists(chrome_dir):
        for root, dirs, files in os.walk(chrome_dir):
            if "chrome" in files and not files[0].endswith(".zip"):
                chrome_found = os.path.join(root, "chrome")
                break
    
    if os.path.exists(driver_dir):
        driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
        for root, dirs, files in os.walk(driver_dir):
            if driver_name in files:
                driver_found = os.path.join(root, driver_name)
                break
    
    return {
        'chrome': chrome_found is not None,
        'chromedriver': driver_found is not None,
        'chrome_path': chrome_found,
        'driver_path': driver_found
    }

def cleanup_temp():
    temp_dir = "/tmp/chrome_bot"
    if os.path.exists(temp_dir):
        try:
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f.endswith('.zip'):
                        os.remove(os.path.join(root, f))
            logger.info("🧹 Очищены временные zip файлы")
        except:
            pass

cleanup_temp()