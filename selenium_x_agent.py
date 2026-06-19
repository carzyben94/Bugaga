import os
import sys
import time
import json
import logging
import zipfile
import urllib.request
import subprocess
import tempfile
import traceback
import threading
from pathlib import Path
from datetime import datetime  # <-- ДОБАВЬ

# ... (всё остаётся как было до google_login) ...

# === GOOGLE LOGIN С РАСШИРЕННЫМ ЛОГИРОВАНИЕМ ===
def google_login(email, password, bot=None, chat_id=None):
    # Отдельный лог-файл для каждой попытки входа
    login_log_file = BASE_DIR / f"login_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    login_logger = logging.getLogger(f"LoginAttempt_{id(email)}")
    login_logger.setLevel(logging.DEBUG)
    
    # Файловый handler для этой сессии
    fh = logging.FileHandler(str(login_log_file), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    login_logger.addHandler(fh)
    
    login_logger.info(f"START google_login for email={email[:3]}***@{email.split('@')[-1] if '@' in email else '???'}")
    login_logger.info(f"BASE_DIR: {BASE_DIR}")
    login_logger.info(f"Chrome: {_installer.chrome_path}")
    login_logger.info(f"Driver: {_installer.driver_path}")
    
    try:
        import selenium
        login_logger.info(f"Selenium v{selenium.__version__}")
    except ImportError:
        login_logger.warning("Selenium not found, installing...")
        _installer._install_selenium_pip()
        try:
            import selenium
        except ImportError:
            login_logger.error("Selenium install failed")
            return False, "Selenium не удалось установить"
    
    session = BrowserSession()
    if bot and chat_id:
        session.set_chat(bot, chat_id)
    
    def report(text):
        login_logger.info(f"[CHAT] {text}")
        logger.info(f"[Login] {text}")
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                login_logger.debug(f"send_message failed: {e}")
    
    def send_logs_on_error():
        """Отправляет лог-файл в чат при ошибке"""
        try:
            if login_log_file.exists() and bot and chat_id:
                with open(login_log_file, "rb") as f:
                    bot.send_document(
                        chat_id, f,
                        caption="📄 Логи попытки входа",
                        visible_file_name=login_log_file.name
                    )
        except Exception as e:
            logger.error(f"Failed to send log file: {e}")
    
    try:
        report("⏳ Запускаю браузер...")
        session.create()
        login_logger.info(f"Browser created. Session ID: {session.driver.session_id if session.driver else 'None'}")
        
        report("📥 Открываю x.com/login...")
        login_logger.info("Navigating to https://x.com/login")
        session.driver.get("https://x.com/login")
        time.sleep(5)
        
        current_url = session.driver.current_url
        page_title = session.driver.title
        login_logger.info(f"x.com/login loaded. URL: {current_url}")
        login_logger.info(f"Page title: {page_title}")
        login_logger.debug(f"Page source length: {len(session.driver.page_source)}")
        session._screenshot("login_page", "📸 Страница входа X")
        
        from selenium.webdriver.common.by import By
        
        report("🔍 Ищу кнопку Google...")
        google_btn = None
        page_source = session.driver.page_source
        
        # Покажем все кнопки на странице для диагностики
        try:
            all_buttons = session.driver.find_elements(By.TAG_NAME, "button")
            login_logger.info(f"Total buttons on page: {len(all_buttons)}")
            for i, btn in enumerate(all_buttons[:10]):
                btn_text = btn.text.strip()[:50] if btn.text else "[no text]"
                login_logger.info(f"  Button {i}: text='{btn_text}'")
        except Exception as e:
            login_logger.warning(f"Could not list buttons: {e}")
        
        # Ищем кнопку Google
        xpaths_to_try = [
            "//*[contains(text(), 'Continue with Google')]",
            "//*[contains(text(), 'Sign in with Google')]",
            "//*[contains(text(), 'Google')]",
            "//button[.//span[contains(text(), 'Google')]]",
            "//a[contains(@href, 'google')]",
            "//div[@role='button']//*[contains(text(), 'Google')]",
        ]
        
        for xpath in xpaths_to_try:
            try:
                google_btn = session.driver.find_element(By.XPATH, xpath)
                login_logger.info(f"Found Google button with xpath: {xpath}")
                report(f"✅ Найдена кнопка Google (xpath: {xpath[:40]}...)")
                break
            except Exception as e:
                login_logger.debug(f"xpath failed: {xpath} — {e}")
        
        if not google_btn:
            login_logger.error("Google button NOT found on page!")
            login_logger.info(f"Current URL: {session.driver.current_url}")
            login_logger.info(f"Page title: {session.driver.title}")
            login_logger.debug(f"Page source (first 3000 chars):\n{page_source[:3000]}")
            report("❌ Кнопка Google НЕ найдена!")
            send_logs_on_error()
            return False, "Кнопка Google не найдена"
        
        report("🖱️ Кликаю по Google...")
        login_logger.info("Clicking Google button")
        google_btn.click()
        time.sleep(5)
        
        session._screenshot("google_redirect", "📸 После клика")
        
        current_url = session.driver.current_url
        page_title = session.driver.title
        report(f"📍 URL: {current_url[:80]}")
        login_logger.info(f"After click URL: {current_url}")
        login_logger.info(f"After click title: {page_title}")
        
        if "accounts.google.com" in current_url or "google.com" in current_url:
            report("✅ Перешли на Google!")
            login_logger.info("On Google auth page")
            
            # Проверяем, какая страница Google
            login_logger.info(f"Google page source length: {len(session.driver.page_source)}")
            
            # Email
            try:
                login_logger.info("Looking for email field...")
                email_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
                login_logger.info(f"Email field found: {email_field.get_attribute('outerHTML')[:100]}")
                email_field.send_keys(email)
                report("✅ Email введён")
                login_logger.info("Email entered")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                login_logger.info(f"Next button found: {next_btn.get_attribute('outerHTML')[:100]}")
                next_btn.click()
                login_logger.info("Next clicked after email")
                time.sleep(3)
            except Exception as e:
                report(f"⚠️ Email step error: {e}")
                login_logger.error(f"Email step failed: {e}")
                login_logger.error(traceback.format_exc())
                session._screenshot("email_error", "📸 Ошибка email")
            
            # Password
            try:
                time.sleep(3)
                login_logger.info("Looking for password field...")
                pass_field = session.driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                login_logger.info(f"Password field found: {pass_field.get_attribute('outerHTML')[:100]}")
                pass_field.send_keys(password)
                report("✅ Пароль введён")
                login_logger.info("Password entered")
                
                next_btn = session.driver.find_element(By.XPATH, "//*[contains(text(), 'Next') or contains(@value, 'Next')]")
                next_btn.click()
                login_logger.info("Next clicked after password")
                time.sleep(5)
            except Exception as e:
                report(f"⚠️ Password step error: {e}")
                login_logger.error(f"Password step failed: {e}")
                login_logger.error(traceback.format_exc())
                session._screenshot("password_error", "📸 Ошибка пароля")
            
            # Проверяем результат
            time.sleep(3)
            current_url = session.driver.current_url
            login_logger.info(f"After password URL: {current_url}")
            login_logger.info(f"After password title: {session.driver.title}")
            session._screenshot("google_after_login", "📸 После входа в Google")
            
            if "challenge" in current_url:
                login_logger.warning(f"Google CHALLENGE detected! URL: {current_url}")
                report("⚠️ Google требует капчу/доп. проверку!")
                send_logs_on_error()
                return False, "Google требует дополнительную проверку (капча/2FA)"
            
            if "disabled" in current_url:
                login_logger.error(f"Google ACCOUNT DISABLED! URL: {current_url}")
                report("❌ Аккаунт Google заблокирован или отключен")
                send_logs_on_error()
                return False, "Аккаунт Google заблокирован"
        
        else:
            login_logger.warning(f"Did NOT redirect to Google. URL: {current_url}")
            login_logger.debug(f"Page source: {session.driver.page_source[:2000]}")
        
        # Ждём редирект на X
        report("⏳ Жду редирект на X...")
        x_reached = False
        for i in range(10):
            time.sleep(2)
            url = session.driver.current_url
            login_logger.info(f"Wait loop {i+1}/10: {url}")
            if "x.com" in url and "login" not in url:
                report("✅ Вошли в X!")
                login_logger.info("X reached!")
                x_reached = True
                break
        
        if not x_reached:
            login_logger.warning("X not reached after 20 seconds")
            login_logger.info(f"Final URL: {session.driver.current_url}")
            login_logger.info(f"Final title: {session.driver.title}")
        
        session.driver.get("https://x.com/home")
        time.sleep(5)
        current_url = session.driver.current_url
        page_title = session.driver.title
        login_logger.info(f"x.com/home URL: {current_url}")
        login_logger.info(f"x.com/home title: {page_title}")
        session._screenshot("x_home", "📸 X Home")
        
        html = session.driver.page_source.lower()
        login_logger.info(f"x.com/home source length: {len(html)}")
        
        # Проверяем авторизацию
        auth_indicators = ["home", "following", "for you", "compose", "logout", "settings", "notifications"]
        found_indicators = [ind for ind in auth_indicators if ind in html]
        login_logger.info(f"Auth indicators found: {found_indicators}")
        
        # Проверяем также по URL
        if "/home" in current_url or "/i/flow" in current_url:
            login_logger.info("Auth confirmed by URL pattern")
            found_indicators.append("url_pattern")
        
        if found_indicators:
            report(f"✅ Авторизация подтверждена! Индикаторы: {found_indicators}")
            login_logger.info("AUTH SUCCESS")
            session.save_cookies()
            save_auth_info("google_user", email)
            return True, None
        else:
            report("❌ Не удалось войти в X")
            login_logger.error("AUTH FAILED — no indicators found")
            login_logger.debug(f"Page source (first 3000 chars):\n{html[:3000]}")
            send_logs_on_error()
            return False, "Не удалось войти в X"
            
    except Exception as e:
        report(f"❌ Ошибка: {str(e)[:200]}")
        login_logger.error(f"CRITICAL ERROR: {e}")
        login_logger.error(traceback.format_exc())
        send_logs_on_error()
        return False, str(e)
    finally:
        login_logger.info("END — quitting session")
        session.quit()
        # Убираем handler чтобы не дублировалось
        login_logger.removeHandler(fh)
        fh.close()
