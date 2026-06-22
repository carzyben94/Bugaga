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
        self.driver_path = None
        self.screenshot_callback = screenshot_callback
        self.step = 0
        
    def take_step_screenshot(self, name="step"):
        try:
            self.step += 1
            filename = f"step_{self.step}_{name}.png"
            self.driver.save_screenshot(filename)
            logger.info(f"📸 Скриншот шага: {filename}")
            
            if self.screenshot_callback:
                self.screenshot_callback(filename, f"Шаг {self.step}: {name}")
            
            return filename
        except Exception as e:
            logger.error(f"❌ Ошибка скриншота шага: {e}")
            return None
    
    def extract_zip_fast(self, zip_path, extract_to):
        try:
            if shutil.which('unzip'):
                logger.info("   ⏳ Распаковка через system unzip...")
                subprocess.check_call(['unzip', '-q', zip_path, '-d', extract_to])
                logger.info("   ✅ Распаковано (unzip)")
                return True
        except:
            pass
        
        logger.info("   ⏳ Распаковка через Python zipfile...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        logger.info("   ✅ Распаковано (Python)")
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
                    logger.info(f"✅ Chrome уже установлен: {chrome_path}")
                    return chrome_path
            
            logger.info("📦 Установка Chrome в /tmp...")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chrome-linux64.zip"
                zip_path = os.path.join(chrome_dir, "chrome.zip")
                
                logger.info("   ⏳ Скачивание Chrome (~80 MB)...")
                urllib.request.urlretrieve(url, zip_path)
                logger.info("   ✅ Скачано")
                
                self.extract_zip_fast(zip_path, chrome_dir)
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
                    logger.info(f"✅ ChromeDriver уже установлен: {driver_path}")
                    return driver_path
            
            logger.info("📦 Установка ChromeDriver в /tmp...")
            
            if sys.platform.startswith('linux'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip"
            elif sys.platform.startswith('win'):
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/win64/chromedriver-win64.zip"
            else:
                url = "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/mac-arm64/chromedriver-mac-arm64.zip"
            
            zip_path = os.path.join(driver_dir, "chromedriver.zip")
            
            logger.info("   ⏳ Скачивание ChromeDriver (~10 MB)...")
            urllib.request.urlretrieve(url, zip_path)
            logger.info("   ✅ Скачано")
            
            self.extract_zip_fast(zip_path, driver_dir)
            os.remove(zip_path)
            
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    driver_path = os.path.join(root, driver_name)
                    os.chmod(driver_path, 0o755)
                    self.driver_path = driver_path
                    logger.info(f"✅ ChromeDriver готов: {driver_path}")
                    return driver_path
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки ChromeDriver: {e}")
            return None
    
    def setup_driver(self):
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            chrome_dir = os.path.join(self.install_dir, "chrome_local")
            for root, dirs, files in os.walk(chrome_dir):
                if "chrome" in files and not files[0].endswith(".zip"):
                    self.chrome_path = os.path.join(root, "chrome")
                    break
        
        if not self.driver_path or not os.path.exists(self.driver_path):
            driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
            driver_dir = os.path.join(self.install_dir, "chromedriver_local")
            for root, dirs, files in os.walk(driver_dir):
                if driver_name in files:
                    self.driver_path = os.path.join(root, driver_name)
                    break
        
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            raise Exception("Chrome не найден. Используйте /install")
        
        if not self.driver_path or not os.path.exists(self.driver_path):
            raise Exception("ChromeDriver не найден. Используйте /install")
        
        options = Options()
        options.binary_location = self.chrome_path
        
        if self.headless:
            options.add_argument('--headless=new')
        
        # === ОПТИМИЗАЦИЯ ===
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
        
        # === ДЕСКТОПНЫЙ USER-AGENT ===
        desktop_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        options.add_argument(f'--user-agent={desktop_user_agent}')
        
        # === ДЕСКТОПНЫЙ РАЗМЕР ЭКРАНА ===
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        
        options.add_argument('--lang=en-US,en;q=0.9')
        
        # === ДЕСКТОПНЫЕ ЗАГОЛОВКИ ===
        options.add_experimental_option('prefs', {
            'intl.accept_languages': 'en-US,en;q=0.9',
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'profile.default_content_settings': {
                'images': 1,  # Включаем картинки для десктопа
                'javascript': 1,
                'popups': 2,
                'notifications': 2,
            },
            'profile.managed_default_content_settings': {
                'images': 1,
                'javascript': 1,
            }
        })
        
        # === ДОПОЛНИТЕЛЬНЫЕ ЗАГОЛОВКИ ===
        options.add_experimental_option('prefs', {
            'profile.default_content_setting_values': {
                'cookies': 1,
                'images': 1,
                'javascript': 1,
                'plugins': 1,
                'popups': 1,
                'geolocation': 2,
                'notifications': 2,
                'auto_select_certificate': 2,
                'fullscreen': 1,
                'mouselock': 1,
                'mixed_script': 1,
                'media_stream': 2,
                'media_stream_mic': 2,
                'media_stream_camera': 2,
                'protocol_handlers': 1,
                'ppapi_broker': 2,
                'renderer': 1,
                'ssl_cert_decisions': 1,
                'web_ui': 1,
            }
        })
        
        service = Service(
            self.driver_path,
            service_args=['--verbose', '--log-path=chromedriver.log'],
            log_output=subprocess.DEVNULL
        )
        
        try:
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            
            # === УСТАНАВЛИВАЕМ ДЕСКТОПНЫЙ РАЗМЕР ===
            self.driver.set_window_size(1920, 1080)
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Chrome: {e}")
            raise
        
        # === СКРЫВАЕМ WEBDRIVER ===
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
            Object.defineProperty(navigator, 'userAgent', {
                get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)
        
        self.wait = WebDriverWait(self.driver, 10)
        logger.info("✅ Браузер готов (десктопная версия)")
        return self.driver
    
    def random_delay(self, min_sec=0.3, max_sec=1.0):
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_click(self, element):
        try:
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            self.random_delay(0.1, 0.2)
            actions.click()
            actions.perform()
            self.random_delay(0.2, 0.5)
            return True
        except Exception as e:
            logger.error(f"Ошибка клика: {e}")
            return False
    
    def human_type(self, element, text):
        try:
            element.click()
            self.random_delay(0.2, 0.3)
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))
            self.random_delay(0.2, 0.4)
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
    
    # ===== ВХОД ЧЕРЕЗ GOOGLE (ДЕСКТОП) =====
    def login_twitter_with_google(self, username, password):
        logger.info("🚀 Открываем Twitter (десктоп)...")
        try:
            self.driver.get("https://x.com/login")
            self.random_delay(2, 3)
            self.take_step_screenshot("login_page")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return False
        
        try:
            # ШАГ 1: Нажимаем "Continue with Google"
            logger.info("🔍 Ищу кнопку 'Continue with Google'...")
            
            google_btn = None
            selectors = [
                "//span[contains(text(), 'Continue with Google')]",
                "//span[contains(text(), 'Continue with Google')]/ancestor::button",
                "//div[contains(text(), 'Continue with Google')]",
                "//button[contains(@class, 'google')]",
                "//*[contains(text(), 'Google')]//ancestor::button",
                "//span[contains(text(), 'Google')]"
            ]
            
            for selector in selectors:
                try:
                    if selector.startswith('//') or selector.startswith('['):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    if element and element.is_displayed():
                        google_btn = element
                        logger.info(f"✅ Найдена кнопка Google по селектору: {selector}")
                        break
                except:
                    continue
            
            if google_btn:
                self.human_click(google_btn)
                logger.info("✅ Нажата кнопка 'Continue with Google'")
                self.take_step_screenshot("click_google")
            else:
                logger.warning("⚠️ Кнопка Google не найдена, ищем все кнопки...")
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for i, btn in enumerate(all_buttons[:10]):
                    try:
                        text = btn.text.strip()
                        if text:
                            logger.info(f"   Кнопка {i+1}: '{text}'")
                    except:
                        pass
                
                for btn in all_buttons:
                    try:
                        if "google" in btn.text.lower() or "google" in btn.get_attribute("class").lower():
                            self.human_click(btn)
                            logger.info("✅ Нажата кнопка с Google")
                            self.take_step_screenshot("click_google_fallback")
                            break
                    except:
                        continue
                
                self.take_step_screenshot("google_not_found")
                return False
            
            self.random_delay(2, 3)
            
            # ШАГ 2: Ввод email в Google
            logger.info("🔍 Ждем поле для ввода email...")
            email_field = self.find_element(By.ID, "identifierId")
            if not email_field:
                email_field = self.find_element(By.NAME, "identifier")
            if not email_field:
                email_field = self.find_element(By.XPATH, "//input[@type='email']")
            
            if email_field:
                self.human_type(email_field, username)
                logger.info(f"✅ Введен email: {username}")
                self.take_step_screenshot("email_entered")
            else:
                logger.error("❌ Поле email не найдено")
                self.take_step_screenshot("email_not_found")
                return False
            
            self.random_delay(1, 2)
            
            # ШАГ 3: Кнопка "Далее" в Google
            logger.info("🔍 Ищем кнопку 'Далее'...")
            next_btn = self.find_element(By.XPATH, "//span[text()='Далее']")
            if not next_btn:
                next_btn = self.find_element(By.XPATH, "//span[text()='Next']")
            if not next_btn:
                next_btn = self.find_element(By.ID, "identifierNext")
            
            if next_btn:
                self.human_click(next_btn)
                logger.info("✅ Нажата кнопка 'Далее'")
                self.take_step_screenshot("click_next")
            else:
                logger.warning("⚠️ Кнопка 'Далее' не найдена")
                self.take_step_screenshot("next_not_found")
            
            self.random_delay(2, 3)
            
            # ШАГ 4: Ввод пароля в Google
            logger.info("🔍 Ждем поле для ввода пароля...")
            password_field = self.find_element(By.NAME, "password")
            if not password_field:
                password_field = self.find_element(By.ID, "password")
            if not password_field:
                password_field = self.find_element(By.XPATH, "//input[@type='password']")
            
            if password_field:
                self.human_type(password_field, password)
                logger.info("✅ Введен пароль")
                self.take_step_screenshot("password_entered")
            else:
                logger.error("❌ Поле пароля не найдено")
                self.take_step_screenshot("password_not_found")
                return False
            
            self.random_delay(1, 2)
            
            # ШАГ 5: Кнопка "Далее" или "Войти"
            logger.info("🔍 Ищем кнопку входа...")
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
                logger.info("✅ Нажата кнопка входа")
                self.take_step_screenshot("click_final_login")
            else:
                logger.warning("⚠️ Кнопка входа не найдена")
                self.take_step_screenshot("login_not_found")
            
            self.random_delay(3, 5)
            self.take_step_screenshot("final_result")
            
            current_url = self.driver.current_url
            logger.info(f"📍 Текущий URL: {current_url}")
            
            if "home" in current_url.lower() or "x.com/home" in current_url.lower():
                logger.info("🎉 Вход выполнен успешно!")
                return True
            elif "oauth2" in current_url.lower() or "accounts.google.com" in current_url.lower():
                logger.warning("⚠️ Требуется подтверждение 2FA или выбор аккаунта")
                self.take_step_screenshot("2fa_needed")
                return False
            else:
                logger.warning(f"⚠️ Неизвестный URL: {current_url}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            self.take_step_screenshot("error_crash")
            return False
    
    # ===== ОБЫЧНЫЙ ВХОД =====
    def login_twitter(self, username, password):
        logger.info("🚀 Открываем Twitter (десктоп)...")
        try:
            self.driver.get("https://x.com/login")
            self.random_delay(2, 3)
            self.take_step_screenshot("login_page")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return False
        
        try:
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Sign in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='loginButton']"):
                logger.info("✅ Кнопка входа нажата")
                self.take_step_screenshot("click_login")
            
            self.random_delay(1, 2)
            
            username_field = self.find_element(By.NAME, "text")
            if username_field:
                self.human_type(username_field, username)
                logger.info(f"✅ Логин: {username}")
                self.take_step_screenshot("username_entered")
            else:
                logger.error("❌ Поле логина не найдено")
                self.take_step_screenshot("error_username_not_found")
                return False
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Далее']") or \
               self.click_safe(By.XPATH, "//span[text()='Next']"):
                logger.info("✅ Кнопка 'Далее' нажата")
                self.take_step_screenshot("click_next")
            
            self.random_delay(2, 3)
            
            password_field = self.find_element(By.NAME, "password")
            if password_field:
                self.human_type(password_field, password)
                logger.info("✅ Пароль введен")
                self.take_step_screenshot("password_entered")
            else:
                logger.error("❌ Поле пароля не найдено")
                self.take_step_screenshot("error_password_not_found")
                return False
            
            self.random_delay(1, 2)
            
            if self.click_safe(By.XPATH, "//span[text()='Войти']") or \
               self.click_safe(By.XPATH, "//span[text()='Log in']") or \
               self.click_safe(By.CSS_SELECTOR, "[data-testid='LoginForm_Login_Button']"):
                logger.info("✅ Кнопка 'Войти' нажата")
                self.take_step_screenshot("click_final_login")
            
            self.random_delay(3, 5)
            self.take_step_screenshot("final_result")
            
            if "home" in self.driver.current_url.lower():
                logger.info("🎉 Вход выполнен успешно!")
                return True
            else:
                logger.warning(f"⚠️ URL: {self.driver.current_url}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            self.take_step_screenshot("error_crash")
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