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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_chromedriver_path():
    chrome_driver_dir = "/tmp/chromedriver"
    os.makedirs(chrome_driver_dir, exist_ok=True)
    
    driver_name = "chromedriver.exe" if sys.platform.startswith('win') else "chromedriver"
    driver_path = os.path.join(chrome_driver_dir, driver_name)
    
    if os.path.exists(driver_path):
        logger.info("✅ ChromeDriver уже есть")
        os.chmod(driver_path, 0o755)
        return driver_path
    
    logger.info("📦 Скачивание ChromeDriver...")
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
            self.log_callback(log_entry, level)
        
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
        
        desktop_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        options.add_argument(f'--user-agent={desktop_user_agent}')
        self.log(f"🖥️ User-Agent: {desktop_user_agent[:50]}...", "DEBUG")
        
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--lang=en-US,en;q=0.9')
        
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
            element_text = element.text[:30] if element.text else "без текста"
            self.log(f"🖱️ Клик по элементу: '{element_text}'", "DEBUG")
            
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            time.sleep(0.3)
            actions.click()
            time.sleep(0.2)
            actions.perform()
            
            self.random_delay(0.2, 0.5)
            return True
        except Exception as e:
            self.log(f"❌ Ошибка клика: {e}", "ERROR")
            return False
    
    def type_with_actions(self, element, text):
        try:
            self.log(f"⌨️ Ввод через ActionChains", "DEBUG")
            
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            actions.click()
            actions.perform()
            time.sleep(0.5)
            
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL)
            actions.send_keys('a')
            actions.key_up(Keys.CONTROL)
            actions.send_keys(Keys.DELETE)
            actions.perform()
            time.sleep(0.5)
            
            for char in text:
                actions = ActionChains(self.driver)
                actions.send_keys(char)
                actions.perform()
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
    
    def human_type(self, element, text):
        try:
            self.log(f"⌨️ Ввод текста", "DEBUG")
            time.sleep(1)
            for attempt in range(3):
                try:
                    element.click()
                    break
                except:
                    time.sleep(0.5)
            
            element.clear()
            time.sleep(0.3)
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.03, 0.08))
            
            self.log("✅ Текст введен", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка ввода: {e}", "ERROR")
            return False
    
    def login_google(self, email, password):
        self.email = email
        self.log(f"🚀 Вход в Google: {email}", "INFO")
        
        try:
            self.log("🌐 Открытие Google...", "INFO")
            self.driver.get("https://accounts.google.com/")
            self.random_delay(2, 3)
            self.take_step_screenshot("google_login")
            self.log("✅ Google открыт", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            return False
        
        email_field = self.find_element(By.ID, "identifierId")
        if email_field:
            self.human_type(email_field, email)
            self.take_step_screenshot("google_email")
            self.log("✅ Email введен", "SUCCESS")
        else:
            self.log("❌ Поле email не найдено", "ERROR")
            return False
        
        self.random_delay(1, 2)
        
        next_btn = self.find_element_clickable(By.XPATH, "//span[text()='Далее']")
        if not next_btn:
            next_btn = self.find_element_clickable(By.XPATH, "//span[text()='Next']")
        if not next_btn:
            next_btn = self.find_element_clickable(By.ID, "identifierNext")
        
        if next_btn:
            self.human_click(next_btn)
            self.take_step_screenshot("google_next")
            self.log("✅ 'Далее' нажата", "SUCCESS")
        else:
            self.log("⚠️ Кнопка не найдена", "WARNING")
        
        self.random_delay(2, 4)
        
        self.log("🔍 Поиск поля пароля...", "INFO")
        
        password_field = None
        for selector in [
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[@name='password']"),
            (By.XPATH, "//input[@autocomplete='current-password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                element = self.driver.find_element(*selector)
                if element and element.is_displayed():
                    password_field = element
                    self.log(f"✅ Поле пароля найдено", "SUCCESS")
                    break
            except:
                continue
        
        if password_field:
            self.log("🔑 Ввод пароля...", "INFO")
            
            for attempt in range(5):
                try:
                    if password_field.is_enabled():
                        break
                    time.sleep(1)
                except:
                    time.sleep(1)
            
            success = self.type_with_actions(password_field, password)
            if success:
                self.take_step_screenshot("google_password")
                self.log("✅ Пароль введен", "SUCCESS")
            else:
                try:
                    password_field.click()
                    password_field.clear()
                    password_field.send_keys(password)
                    self.take_step_screenshot("google_password")
                    self.log("✅ Пароль введен (обычный способ)", "SUCCESS")
                except Exception as e:
                    self.log(f"❌ Ошибка: {e}", "ERROR")
                    return False
        else:
            self.log("❌ Поле пароля не найдено", "ERROR")
            return False
        
        self.random_delay(1, 2)
        
        self.log("🔍 Кнопка входа...", "INFO")
        
        login_btn = None
        for selector in [
            (By.XPATH, "//span[text()='Далее']"),
            (By.XPATH, "//span[text()='Next']"),
            (By.XPATH, "//span[text()='Войти']"),
            (By.XPATH, "//span[contains(text(), 'Next')]"),
            (By.ID, "passwordNext"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//div[@role='button']"),
        ]:
            try:
                element = self.driver.find_element(*selector)
                if element and element.is_displayed() and element.is_enabled():
                    login_btn = element
                    self.log(f"✅ Кнопка найдена", "SUCCESS")
                    break
            except:
                continue
        
        if login_btn:
            self.human_click(login_btn)
            self.take_step_screenshot("google_login_final")
            self.log("✅ Кнопка входа нажата", "SUCCESS")
        else:
            self.log("⚠️ Кнопка не найдена, пробую Enter", "WARNING")
            try:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
                self.log("✅ Нажат Enter", "SUCCESS")
            except:
                pass
        
        self.random_delay(3, 5)
        
        current_url = self.driver.current_url
        self.log(f"📍 URL: {current_url[:80]}...", "INFO")
        
        if "challenge" in current_url or "verify" in current_url.lower():
            self.log("🔐 2FA — ожидание подтверждения", "INFO")
            self.take_step_screenshot("google_2fa")
            
            for i in range(12):
                time.sleep(5)
                new_url = self.driver.current_url
                if "challenge" not in new_url and "verify" not in new_url.lower():
                    self.log("✅ 2FA пройдена!", "SUCCESS")
                    break
                self.log(f"⏳ Ожидание... {i+1}/12", "INFO")
        
        self.log("✅ Вход в Google выполнен!", "SUCCESS")
        self.take_step_screenshot("google_done")
        return True
    
    # ============================================================
    # === ИССЛЕДОВАТЕЛЬ — НАХОДИТ КНОПКУ ЛЮБЫМ СПОСОБОМ ===
    # ============================================================
    def find_and_click_continue_as(self):
        """Исследовательская функция — ищет 'Continue as Babe' всеми способами"""
        self.log("=" * 60, "INFO")
        self.log("🔍 ЗАПУСК ИССЛЕДОВАТЕЛЯ", "INFO")
        self.log("=" * 60, "INFO")
        
        # === СОБИРАЕМ ВСЮ ИНФОРМАЦИЮ ===
        self.log("📊 ШАГ 1: Сбор информации о странице...", "INFO")
        
        window_size = self.driver.get_window_size()
        self.log(f"   Размер окна: {window_size['width']}x{window_size['height']}", "INFO")
        
        title = self.driver.title
        self.log(f"   Заголовок: {title}", "INFO")
        
        url = self.driver.current_url
        self.log(f"   URL: {url}", "INFO")
        
        html = self.driver.page_source
        self.log(f"   Длина HTML: {len(html)} символов", "INFO")
        
        # === ПОИСК В HTML ===
        self.log("🔍 ШАГ 2: Поиск в HTML...", "INFO")
        
        keywords = ["Continue as", "Continue with", "Babe", "baruhbenn9@gmail.com"]
        for keyword in keywords:
            if keyword in html:
                self.log(f"   ✅ Найдено в HTML: '{keyword}'", "SUCCESS")
            else:
                self.log(f"   ❌ Не найдено в HTML: '{keyword}'", "WARNING")
        
        # === ПОИСК ВСЕМИ МЕТОДАМИ ===
        self.log("🔍 ШАГ 3: Поиск элемента всеми методами...", "INFO")
        
        all_methods = []
        
        # Метод 1: По тексту "Continue as"
        self.log("   Метод 1: Поиск 'Continue as'...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue as')]")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 2: По тексту "Continue with"
        self.log("   Метод 2: Поиск 'Continue with'...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue with')]")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 3: По тексту "Babe"
        self.log("   Метод 3: Поиск 'Babe'...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, "//*[text()='Babe']")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 4: По email
        self.log(f"   Метод 4: Поиск '{self.email}'...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{self.email}')]")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 5: Все кнопки
        self.log("   Метод 5: Все кнопки...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.TAG_NAME, "button")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 6: Все элементы с role="button"
        self.log("   Метод 6: role='button'...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, "//*[@role='button']")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Метод 7: Все кликабельные div
        self.log("   Метод 7: Кликабельные div...", "DEBUG")
        try:
            elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'css-')]")
            self.log(f"      Найдено: {len(elements)}", "DEBUG")
            all_methods.extend(elements)
        except: pass
        
        # Удаляем дубликаты
        all_methods = list(dict.fromkeys(all_methods))
        self.log(f"📊 Всего уникальных элементов: {len(all_methods)}", "INFO")
        
        # === ПЕРЕБОР ВСЕХ ЭЛЕМЕНТОВ ===
        self.log("🖱️ ШАГ 4: Перебор всех элементов...", "INFO")
        
        for idx, elem in enumerate(all_methods):
            try:
                text = elem.text.strip()
                tag = elem.tag_name
                classes = elem.get_attribute("class")
                role = elem.get_attribute("role")
                
                self.log(f"   Элемент {idx+1}: tag={tag}, text='{text[:30]}', class='{classes[:30]}'", "DEBUG")
                
                # Проверяем, подходит ли элемент
                if any(keyword in text for keyword in ["Continue as", "Continue with", "Babe", self.email]):
                    self.log(f"✅ НАЙДЕН ПОДХОДЯЩИЙ ЭЛЕМЕНТ: '{text}'", "SUCCESS")
                    self.log(f"   Tag: {tag}, Class: {classes}, Role: {role}", "INFO")
                    
                    # === ПРОБУЕМ ВСЕ СПОСОБЫ КЛИКА ===
                    self.log("🔄 Пробую кликнуть...", "INFO")
                    
                    # Способ 1: Обычный клик
                    try:
                        self.human_click(elem)
                        self.log("   ✅ Клик через ActionChains", "SUCCESS")
                        self.take_step_screenshot("xcom_click_found_1")
                        return True
                    except Exception as e:
                        self.log(f"   ❌ Ошибка ActionChains: {e}", "WARNING")
                    
                    # Способ 2: JavaScript клик
                    try:
                        self.driver.execute_script("arguments[0].click();", elem)
                        self.log("   ✅ Клик через JavaScript", "SUCCESS")
                        self.take_step_screenshot("xcom_click_found_2")
                        return True
                    except Exception as e:
                        self.log(f"   ❌ Ошибка JavaScript: {e}", "WARNING")
                    
                    # Способ 3: Клик по родительской кнопке
                    try:
                        parent = elem.find_element(By.XPATH, "./ancestor::button")
                        if parent:
                            self.driver.execute_script("arguments[0].click();", parent)
                            self.log("   ✅ Клик по родительской кнопке", "SUCCESS")
                            self.take_step_screenshot("xcom_click_found_3")
                            return True
                    except Exception as e:
                        self.log(f"   ❌ Ошибка родительской кнопки: {e}", "WARNING")
                    
                    # Способ 4: Клик по родительскому div
                    try:
                        parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'css-')]")
                        if parent:
                            self.driver.execute_script("arguments[0].click();", parent)
                            self.log("   ✅ Клик по родительскому div", "SUCCESS")
                            self.take_step_screenshot("xcom_click_found_4")
                            return True
                    except Exception as e:
                        self.log(f"   ❌ Ошибка родительского div: {e}", "WARNING")
                    
                    # Способ 5: Координаты элемента
                    try:
                        location = elem.location
                        size = elem.size
                        x = location['x'] + size['width'] // 2
                        y = location['y'] + size['height'] // 2
                        
                        self.driver.execute_script(f"""
                            var element = document.elementFromPoint({x}, {y});
                            if (element) {{
                                element.click();
                            }}
                        """)
                        self.log(f"   ✅ Клик по координатам ({x}, {y})", "SUCCESS")
                        self.take_step_screenshot("xcom_click_found_5")
                        return True
                    except Exception as e:
                        self.log(f"   ❌ Ошибка координат: {e}", "WARNING")
                    
                    self.log(f"❌ Не удалось кликнуть по элементу", "ERROR")
            except:
                continue
        
        self.log("❌ НЕ УДАЛОСЬ НАЙТИ 'Continue as Babe'", "ERROR")
        return False
    
    # ============================================================
    # === ПЕРЕХОД НА X.COM ===
    # ============================================================
    def go_to_xcom(self):
        """Переход на X.com"""
        self.log("🌐 ПЕРЕХОД НА X.COM", "INFO")
        
        try:
            self.driver.get("https://x.com")
            time.sleep(5)
            self.take_step_screenshot("xcom_home")
            
            current_url = self.driver.current_url
            self.log(f"📍 URL: {current_url}", "INFO")
            
            if "home" in current_url or "x.com/home" in current_url:
                self.log("🎉 Уже на главной", "SUCCESS")
                return True
            
            # === ЗАПУСК ИССЛЕДОВАТЕЛЯ ===
            result = self.find_and_click_continue_as()
            
            if result:
                time.sleep(2)
                current_url = self.driver.current_url
                if "home" in current_url or "x.com/home" in current_url:
                    self.log("🎉 ВХОД ВЫПОЛНЕН!", "SUCCESS")
                    return True
            
            self.log("❌ Вход не выполнен", "ERROR")
            return False
            
        except Exception as e:
            self.log(f"❌ ОШИБКА: {e}", "ERROR")
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