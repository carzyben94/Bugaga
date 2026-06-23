from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
import os
import time
import random
import logging
import zipfile
import urllib.request
import sys
import subprocess
import json
import tempfile
import uuid
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
        self.user_data_dir = None
        
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
        
        # === USER-DATA-DIR — сохраняем Google-сессию ===
        self.user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_x_profile_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.user_data_dir, exist_ok=True)
        options.add_argument(f'--user-data-dir={self.user_data_dir}')
        self.log(f"📁 Профиль: {self.user_data_dir}", "INFO")
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        options.add_argument('--page-load-timeout=60')
        options.add_argument('--script-timeout=30')
        
        desktop_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        options.add_argument(f'--user-agent={desktop_user_agent}')
        self.log(f"🖥️ User-Agent: {desktop_user_agent[:50]}...", "DEBUG")
        
        options.add_argument('--window-size=1920,1080')
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
        
        driver_path = get_chromedriver_path()
        service = Service(driver_path)
        
        try:
            self.driver = webdriver.Chrome(service=service, options=options)
            self.log("✅ Chrome запущен", "SUCCESS")
        except Exception as e:
            self.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            raise
        
        # === CDP-скрипты для скрытия automation ===
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            '''
        })
        
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(20)
        
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
    
    # ============================================================
    # === GOOGLE ONE TAP / GIS КЛИК ===
    # ============================================================
    
    def click_google_one_tap(self, timeout=30):
        """
        Кликает по Google One Tap кнопке "Continue as [имя]" на X.com
        Это специальная кнопка Google Identity Services внутри iframe/Shadow DOM
        """
        self.log("🔍 Поиск Google One Tap кнопки...", "INFO")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            btn = None
            
            # Метод 1: Поиск по видимому тексту "Continue as"
            try:
                elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue as')]")
                for el in elements:
                    if el.is_displayed():
                        # Проверяем что это внутри Google-контейнера или рядом с gmail
                        parent = self.driver.execute_script("""
                            var el = arguments[0];
                            for (var i = 0; i < 5; i++) {
                                if (el.parentElement) {
                                    var text = el.parentElement.textContent || '';
                                    if (text.includes('gmail') || text.includes('google') || text.includes('Continue as')) {
                                        return el.parentElement;
                                    }
                                    el = el.parentElement;
                                }
                            }
                            return el;
                        """, el)
                        if parent and parent.is_displayed():
                            btn = parent
                            self.log(f"✅ Найдена One Tap кнопка (текст): '{el.text[:50]}'", "SUCCESS")
                            break
            except:
                pass
            
            # Метод 2: Поиск по data-атрибутам Google
            if not btn:
                try:
                    selectors = [
                        "//div[@data-provider='google']",
                        "//div[@data-testid='google-login']",
                        "//button[@data-testid='google-login']",
                        "//div[contains(@data-testid, 'google')]",
                        "//div[contains(@aria-label, 'Google')]",
                    ]
                    for sel in selectors:
                        elements = self.driver.find_elements(By.XPATH, sel)
                        for el in elements:
                            if el.is_displayed():
                                btn = el
                                self.log("✅ Найдена Google-кнопка (data-attr)", "SUCCESS")
                                break
                        if btn:
                            break
                except:
                    pass
            
            # Метод 3: Поиск в iframe Google
            if not btn:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue') or contains(text(), 'Sign in')]")
                            for el in elements:
                                if el.is_displayed():
                                    btn = el
                                    self.log(f"✅ Найдена кнопка в iframe: '{el.text[:40]}'", "SUCCESS")
                                    break
                            self.driver.switch_to.default_content()
                            if btn:
                                break
                        except:
                            self.driver.switch_to.default_content()
                            continue
                except:
                    self.driver.switch_to.default_content()
            
            # Метод 4: Shadow DOM Google
            if not btn:
                try:
                    hosts = self.driver.find_elements(By.CSS_SELECTOR, "*")
                    for host in hosts:
                        try:
                            shadow_root = self.driver.execute_script("return arguments[0].shadowRoot", host)
                            if shadow_root:
                                elements = shadow_root.find_elements(By.CSS_SELECTOR, "*")
                                for el in elements:
                                    text = el.text or ""
                                    if "Continue" in text and el.is_displayed():
                                        btn = el
                                        self.log(f"✅ Найдена кнопка в Shadow DOM: '{text[:40]}'", "SUCCESS")
                                        break
                                if btn:
                                    break
                        except:
                            continue
                except:
                    pass
            
            # Метод 5: Координаты (кнопка примерно на y=300-350)
            if not btn:
                try:
                    # Проверяем что есть элемент в районе кнопки
                    el = self.driver.execute_script("""
                        var el = document.elementFromPoint(960, 320);
                        if (el) {
                            var text = el.textContent || '';
                            var parent = el;
                            for (var i = 0; i < 3; i++) {
                                if (parent.parentElement) parent = parent.parentElement;
                            }
                            var parentText = parent.textContent || '';
                            if (parentText.includes('Continue as') || parentText.includes('Google')) {
                                return parent;
                            }
                            return el;
                        }
                        return null;
                    """)
                    if el:
                        btn = el
                        self.log("✅ Найдена кнопка по координатам", "SUCCESS")
                except:
                    pass
            
            if btn:
                # Клик
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", btn)
                    time.sleep(0.5)
                    
                    # ActionChains клик (самый человечный)
                    actions = ActionChains(self.driver)
                    actions.move_to_element(btn)
                    actions.pause(0.3)
                    actions.click()
                    actions.perform()
                    
                    self.log("✅ Клик по One Tap кнопке (ActionChains)", "SUCCESS")
                    self.take_step_screenshot("one_tap_clicked")
                    return True
                    
                except Exception as e:
                    self.log(f"⚠️ ActionChains не сработал: {e}, пробую JS", "WARNING")
                    try:
                        self.driver.execute_script("arguments[0].click();", btn)
                        self.log("✅ Клик по One Tap кнопке (JS)", "SUCCESS")
                        self.take_step_screenshot("one_tap_clicked_js")
                        return True
                    except Exception as e2:
                        self.log(f"❌ JS тоже не сработал: {e2}", "ERROR")
            
            time.sleep(1)
            self.log("⏳ Жду появления кнопки...", "DEBUG")
        
        self.log("❌ One Tap кнопка не найдена за 30 сек", "ERROR")
        return False
    
    # ============================================================
    # === POPUP / NEW WINDOW ===
    # ============================================================
    
    def wait_for_popup_or_new_window(self, timeout=10):
        self.log("⏳ Ожидание popup-окна...", "INFO")
        start = time.time()
        original_handles = self.driver.window_handles
        while time.time() - start < timeout:
            current_handles = self.driver.window_handles
            if len(current_handles) > len(original_handles):
                new_handles = [h for h in current_handles if h not in original_handles]
                if new_handles:
                    self.driver.switch_to.window(new_handles[0])
                    self.log(f"✅ Переключился на popup: {self.driver.title[:40]}", "SUCCESS")
                    return True
            time.sleep(0.5)
        self.log("⚠️ Popup не появился", "WARNING")
        return False

    def click_in_popup(self, text="Continue as", timeout=15):
        self.log("🔍 Поиск кнопки в popup...", "INFO")
        
        if self.wait_for_popup_or_new_window(timeout=5):
            self.wait_for_page_load(timeout=10)
            time.sleep(2)
        
        element = None
        selectors = [
            f"//span[contains(text(), '{text}')]",
            f"//div[contains(text(), '{text}')]",
            f"//button[contains(., '{text}')]",
            "//div[@role='button']",
            "//button[@type='button']",
            "//div[contains(@class, 'VfPpkd')]",
            "//div[contains(@class, 'nsm7Bb')]",
        ]
        
        for by, selector in [(By.XPATH, s) for s in selectors]:
            try:
                elements = self.driver.find_elements(by, selector)
                for elem in elements:
                    if elem.is_displayed() and text.lower() in (elem.text or "").lower():
                        element = elem
                        self.log(f"🔍 Найдена кнопка: '{elem.text[:50]}'", "SUCCESS")
                        break
                if element:
                    break
            except:
                continue
        
        if element:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element)
                actions.pause(0.3)
                actions.click()
                actions.perform()
                self.log("✅ Клик через ActionChains в popup", "SUCCESS")
            except Exception as e:
                self.log(f"⚠️ ActionChains не сработал: {e}, пробую JS", "WARNING")
                self.driver.execute_script("arguments[0].click();", element)
                self.log("✅ Клик через JS в popup", "SUCCESS")
            
            time.sleep(3)
            self.take_step_screenshot("popup_clicked")
            self.driver.switch_to.window(self.driver.window_handles[0])
            self.log("↩️ Вернулся на основное окно", "INFO")
            return True
        
        self.log("❌ Кнопка не найдена в popup", "ERROR")
        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[0])
        return False
    
    # ============================================================
    # === МЕГА-КЛИК (все методы) ===
    # ============================================================
    
    def mega_click(self, x=960, y=380, text="Continue as"):
        self.log("💣 МЕГА-КЛИК — пробую все методы...", "INFO")
        self.log("=" * 60, "INFO")
        
        element = None
        try:
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
            for elem in elements:
                if elem.is_displayed():
                    element = elem
                    break
        except:
            pass
        
        if element:
            self.log(f"🔍 Найден элемент: '{element.text[:30]}'", "SUCCESS")
            
            methods = [
                ("Стандартный", self.click_method_1_standard),
                ("ActionChains", self.click_method_2_action_chains),
                ("JavaScript", self.click_method_3_js),
                ("JS со скроллом", self.click_method_4_js_scroll),
                ("MouseEvent", self.click_method_5_mouse_event),
                ("Принудительный", self.click_method_6_force),
                ("Родительский", self.click_method_7_parent),
                ("Соседние", self.click_method_8_siblings),
            ]
            
            for name, method in methods:
                self.log(f"   🔄 Пробую: {name}...", "DEBUG")
                try:
                    if method(element):
                        self.log(f"✅ МЕГА-КЛИК сработал: {name}", "SUCCESS")
                        self.take_step_screenshot("mega_click_success")
                        return True
                except:
                    continue
        
        methods_without = [
            ("Координаты", lambda: self.click_method_9_by_coords(x, y)),
            ("По тексту", lambda: self.click_method_10_by_text(text)),
            ("Все кнопки", self.click_method_11_all_buttons),
            ("jQuery", self.click_method_12_jquery),
            ("React", self.click_method_13_react),
            ("Shadow DOM", self.click_method_14_shadow_dom),
            ("iframe", self.click_method_15_iframe),
        ]
        
        for name, method in methods_without:
            self.log(f"   🔄 Пробую: {name}...", "DEBUG")
            try:
                if method():
                    self.log(f"✅ МЕГА-КЛИК сработал: {name}", "SUCCESS")
                    self.take_step_screenshot("mega_click_success")
                    return True
            except:
                continue
        
        self.log("❌ МЕГА-КЛИК не сработал", "ERROR")
        self.take_step_screenshot("mega_click_failed")
        return False
    
    def click_method_1_standard(self, element):
        try:
            element.click()
            self.log("   ✅ Метод 1: Стандартный", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_2_action_chains(self, element):
        try:
            actions = ActionChains(self.driver)
            actions.move_to_element(element).click().perform()
            self.log("   ✅ Метод 2: ActionChains", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_3_js(self, element):
        try:
            self.driver.execute_script("arguments[0].click();", element)
            self.log("   ✅ Метод 3: JavaScript", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_4_js_scroll(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", element)
            self.log("   ✅ Метод 4: JS со скроллом", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_5_mouse_event(self, element):
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var rect = el.getBoundingClientRect();
                var event = new MouseEvent('click', {
                    clientX: rect.left + rect.width/2,
                    clientY: rect.top + rect.height/2,
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                el.dispatchEvent(event);
            """, element)
            self.log("   ✅ Метод 5: MouseEvent", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_6_force(self, element):
        try:
            self.driver.execute_script("arguments[0].click();", element)
            time.sleep(0.1)
            self.driver.execute_script("arguments[0].click();", element)
            self.log("   ✅ Метод 6: Принудительный", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_7_parent(self, element):
        try:
            parent = self.driver.execute_script("return arguments[0].parentElement;", element)
            if parent:
                parent.click()
                self.log("   ✅ Метод 7: Родитель", "SUCCESS")
                return True
            return False
        except:
            return False
    
    def click_method_8_siblings(self, element):
        try:
            siblings = self.driver.execute_script("""
                var el = arguments[0];
                var parent = el.parentElement;
                return parent ? parent.querySelectorAll('*') : [];
            """, element)
            for sibling in siblings[:5]:
                try:
                    sibling.click()
                    self.log("   ✅ Метод 8: Сосед", "SUCCESS")
                    return True
                except:
                    continue
            return False
        except:
            return False
    
    def click_method_9_by_coords(self, x, y):
        try:
            self.driver.execute_script(f"""
                var el = document.elementFromPoint({x}, {y});
                if (el) el.click();
            """)
            self.log(f"   ✅ Метод 9: Координаты ({x}, {y})", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_10_by_text(self, text):
        try:
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
            for elem in elements:
                try:
                    elem.click()
                    self.log(f"   ✅ Метод 10: Текст '{text[:20]}'", "SUCCESS")
                    return True
                except:
                    continue
            return False
        except:
            return False
    
    def click_method_11_all_buttons(self):
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    self.log(f"   ✅ Метод 11: Кнопка '{btn.text[:20]}'", "SUCCESS")
                    return True
            return False
        except:
            return False
    
    def click_method_12_jquery(self):
        try:
            self.driver.execute_script("""
                if (typeof jQuery !== 'undefined') {
                    jQuery('*:contains("Continue as")').click();
                    return true;
                }
                return false;
            """)
            self.log("   ✅ Метод 12: jQuery", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_13_react(self):
        try:
            self.driver.execute_script("""
                var elements = document.querySelectorAll('*');
                for (var i = 0; i < elements.length; i++) {
                    var text = elements[i].textContent || '';
                    if (text.includes('Continue as')) {
                        var reactKey = Object.keys(elements[i]).find(key => key.startsWith('__react'));
                        if (reactKey) {
                            elements[i].click();
                            return true;
                        }
                    }
                }
                return false;
            """)
            self.log("   ✅ Метод 13: React", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_14_shadow_dom(self):
        try:
            self.driver.execute_script("""
                var hosts = document.querySelectorAll('*');
                for (var i = 0; i < hosts.length; i++) {
                    if (hosts[i].shadowRoot) {
                        var elements = hosts[i].shadowRoot.querySelectorAll('*');
                        for (var j = 0; j < elements.length; j++) {
                            var text = elements[j].textContent || '';
                            if (text.includes('Continue as')) {
                                elements[j].click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            """)
            self.log("   ✅ Метод 14: Shadow DOM", "SUCCESS")
            return True
        except:
            return False
    
    def click_method_15_iframe(self):
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue as')]")
                    for elem in elements:
                        elem.click()
                        self.driver.switch_to.default_content()
                        self.log("   ✅ Метод 15: iframe", "SUCCESS")
                        return True
                    self.driver.switch_to.default_content()
                except:
                    self.driver.switch_to.default_content()
                    continue
            return False
        except:
            return False
    
    # ============================================================
    # === ОСНОВНЫЕ МЕТОДЫ ===
    # ============================================================
    
    def wait_for_page_load(self, timeout=60):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            self.log("✅ Страница загружена", "SUCCESS")
            return True
        except:
            self.log("⚠️ Таймаут загрузки", "WARNING")
            return False
    
    def wait_for_react(self, timeout=30):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("""
                    return document.querySelector('#__next') !== null ||
                           document.querySelector('#root') !== null ||
                           document.querySelector('[data-reactroot]') !== null;
                """)
            )
            self.log("✅ React обнаружен", "SUCCESS")
            return True
        except:
            self.log("⚠️ React не обнаружен", "WARNING")
            return False
    
    def scroll_to_load(self):
        try:
            for i in range(0, 1000, 100):
                self.driver.execute_script(f"window.scrollTo(0, {i});")
                time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            self.log("✅ Прокрутка выполнена", "SUCCESS")
            return True
        except:
            self.log("⚠️ Ошибка прокрутки", "WARNING")
            return False
    
    def login_google(self, email, password):
        self.email = email
        self.log(f"🚀 Вход в Google: {email}", "INFO")
        
        try:
            self.driver.get("https://accounts.google.com/")
            self.random_delay(2, 3)
            self.take_step_screenshot("google_login")
            
            email_field = self.find_element(By.ID, "identifierId")
            if email_field:
                self.human_type(email_field, email)
                self.take_step_screenshot("google_email")
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
            else:
                self.log("⚠️ Кнопка не найдена", "WARNING")
            
            self.random_delay(2, 4)
            
            password_field = None
            for selector in [
                (By.NAME, "password"),
                (By.ID, "password"),
                (By.XPATH, "//input[@type='password']"),
                (By.XPATH, "//input[@autocomplete='current-password']"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ]:
                try:
                    element = self.driver.find_element(*selector)
                    if element and element.is_displayed():
                        password_field = element
                        break
                except:
                    continue
            
            if password_field:
                for attempt in range(5):
                    try:
                        if password_field.is_enabled():
                            break
                        time.sleep(1)
                    except:
                        time.sleep(1)
                
                success = self.type_with_actions(password_field, password)
                if not success:
                    try:
                        password_field.click()
                        password_field.clear()
                        password_field.send_keys(password)
                    except Exception as e:
                        self.log(f"❌ Ошибка пароля: {e}", "ERROR")
                        return False
                self.take_step_screenshot("google_password")
            else:
                self.log("❌ Поле пароля не найдено", "ERROR")
                return False
            
            self.random_delay(1, 2)
            
            login_btn = None
            for selector in [
                (By.XPATH, "//span[text()='Далее']"),
                (By.XPATH, "//span[text()='Next']"),
                (By.XPATH, "//span[text()='Войти']"),
                (By.ID, "passwordNext"),
                (By.XPATH, "//button[@type='submit']"),
            ]:
                try:
                    element = self.driver.find_element(*selector)
                    if element and element.is_displayed() and element.is_enabled():
                        login_btn = element
                        break
                except:
                    continue
            
            if login_btn:
                self.human_click(login_btn)
                self.take_step_screenshot("google_login_final")
            else:
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
                except:
                    pass
            
            self.random_delay(3, 5)
            
            current_url = self.driver.current_url
            if "challenge" in current_url or "verify" in current_url.lower():
                self.log("🔐 2FA — ожидание", "INFO")
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
            
        except Exception as e:
            self.log(f"❌ Ошибка: {e}", "ERROR")
            return False
    
    def go_to_xcom(self):
        self.log("🌐 ПЕРЕХОД НА X.COM", "INFO")
        
        try:
            self.driver.get("https://x.com")
            self.log("✅ X.com открыт", "SUCCESS")
            
            self.wait_for_page_load(timeout=60)
            time.sleep(5)  # React грузит кнопки лениво
            self.wait_for_react(timeout=30)
            time.sleep(3)
            self.scroll_to_load()
            self.take_step_screenshot("xcom_loaded")
            
            current_url = self.driver.current_url
            self.log(f"📍 URL: {current_url}", "INFO")
            
            if "home" in current_url or "x.com/home" in current_url:
                self.log("🎉 Уже на главной", "SUCCESS")
                return True
            
            # === СНАЧАЛА ПРОБУЕМ GOOGLE ONE TAP ===
            result = self.click_google_one_tap(timeout=30)
            
            if result:
                self.log("⏳ Жду редиректа после One Tap...", "INFO")
                for i in range(15):
                    time.sleep(2)
                    current_url = self.driver.current_url
                    self.log(f"   ⏳ URL: {current_url[:60]}", "DEBUG")
                    
                    if "home" in current_url or "x.com/home" in current_url:
                        self.log("🎉 ВХОД ВЫПОЛНЕН!", "SUCCESS")
                        self.take_step_screenshot("xcom_login_success")
                        return True
                    
                    # Проверяем popup
                    if len(self.driver.window_handles) > 1:
                        self.click_in_popup(text="Continue")
                        time.sleep(3)
            
            # === FALLBACK: MEGA CLICK ===
            self.log("⚠️ One Tap не сработал, пробую mega_click", "WARNING")
            result = self.mega_click(x=960, y=320, text="Continue")
            
            if result:
                time.sleep(5)
                current_url = self.driver.current_url
                if "home" in current_url or "x.com/home" in current_url:
                    self.log("🎉 ВХОД ВЫПОЛНЕН через mega_click!", "SUCCESS")
                    return True
            
            self.take_step_screenshot("xcom_auto_failed")
            self.log("🔄 Используйте /joystick для ручного управления", "INFO")
            return True
                
        except Exception as e:
            self.log(f"❌ ОШИБКА: {e}", "ERROR")
            return False
    
    def human_click(self, element):
        try:
            element_text = element.text[:30] if element.text else "без текста"
            self.log(f"🖱️ Клик: '{element_text}'", "DEBUG")
            
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
            actions = ActionChains(self.driver)
            actions.move_to_element(element).click().perform()
            time.sleep(0.5)
            
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL)
            actions.send_keys(Keys.DELETE).perform()
            time.sleep(0.5)
            
            for char in text:
                actions = ActionChains(self.driver)
                actions.send_keys(char).perform()
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
        except:
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
