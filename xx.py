# xx.py — X/Twitter агент через Playwright Async API
import os
import sys
import subprocess
import json
import re
import asyncio
import threading
import time
import telebot

# === НАСТРОЙКА ПУТЕЙ ДЛЯ RENDER ===
PLAYWRIGHT_BROWSERS_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
if PLAYWRIGHT_BROWSERS_PATH:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_PATH
    os.makedirs(PLAYWRIGHT_BROWSERS_PATH, exist_ok=True)

# Env (fallback — можно задать через env, но чат приоритетнее)
X_USERNAME_ENV = os.environ.get("X_USERNAME")
X_PASSWORD_ENV = os.environ.get("X_PASSWORD")
X_EMAIL_ENV = os.environ.get("X_EMAIL")

COOKIES_FILE = "x_cookies.json"
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

PLAYWRIGHT_INSTALLED = False
CHROMIUM_READY = False

# === Хранилище для диалогов авторизации ===
login_sessions = {}

def check_chromium():
    """Проверить, запускается ли Chromium реально"""
    global CHROMIUM_READY
    try:
        from playwright.async_api import async_playwright
        async def _check():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                await browser.close()
                return True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        CHROMIUM_READY = loop.run_until_complete(_check())
        loop.close()
        return CHROMIUM_READY
    except Exception as e:
        print(f"[XX] Chromium check failed: {e}")
        CHROMIUM_READY = False
        return False


def install_playwright():
    """Установить Playwright pip + Chromium (если ещё не готов)"""
    global PLAYWRIGHT_INSTALLED, CHROMIUM_READY

    if check_chromium():
        PLAYWRIGHT_INSTALLED = True
        print("[XX] Playwright + Chromium уже готовы")
        return True

    print("[XX] Установка Playwright...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        import importlib
        try:
            import playwright
            importlib.reload(playwright)
        except ImportError:
            pass
        PLAYWRIGHT_INSTALLED = True
        print("[XX] Playwright pip-package установлен")
    except Exception as e:
        print(f"[XX] Pip install failed: {e}")
        return False

    print("[XX] Скачивание Chromium...")
    try:
        env = os.environ.copy()
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env
        )
        if check_chromium():
            print("[XX] Chromium установлен и проверен!")
            return True
        else:
            print("[XX] Chromium скачался, но не запускается")
            return False
    except Exception as e:
        print(f"[XX] Chromium install failed: {e}")
        return False


try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_INSTALLED = True
except ImportError:
    PLAYWRIGHT_INSTALLED = False


class XXAgent:
    def __init__(self):
        self._playwright_checked = False
        self._cookies_valid = False

    async def _ensure_playwright(self):
        global PLAYWRIGHT_INSTALLED, CHROMIUM_READY
        if not self._playwright_checked:
            self._playwright_checked = True
            if not PLAYWRIGHT_INSTALLED:
                try:
                    from playwright.async_api import async_playwright
                    PLAYWRIGHT_INSTALLED = True
                except ImportError:
                    return False
            if not CHROMIUM_READY:
                CHROMIUM_READY = check_chromium()
        return PLAYWRIGHT_INSTALLED and CHROMIUM_READY

    async def _load_cookies(self, context):
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, "r") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                return True
            except:
                pass
        return False

    async def _save_cookies(self, context):
        try:
            cookies = await context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            self._cookies_valid = True
        except:
            pass

    async def _screenshot(self, page, name):
        """Сделать скриншот для отладки"""
        try:
            path = f"{SCREENSHOT_DIR}/{name}_{int(time.time())}.png"
            await page.screenshot(path=path, full_page=True)
            print(f"[XX] Screenshot saved: {path}")
            return path
        except Exception as e:
            print(f"[XX] Screenshot failed: {e}")
            return None

    async def _get_page_info(self, page):
        """Получить информацию о текущей странице для отладки"""
        try:
            url = page.url
            title = await page.title()
            return f"URL: {url}, Title: {title}"
        except:
            return "Could not get page info"

    async def _check_auth(self, page):
        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=8000)
            signin = await page.query_selector('a[href="/i/flow/login"]')
            if signin:
                return False
            return True
        except:
            return False

    async def _smart_fill(self, page, selectors, value, field_name="поле"):
        """Умное заполнение поля без клика"""
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    print(f"[XX] Found {field_name} via locator: {selector}")
                    await locator.clear()
                    await locator.fill(value)
                    await asyncio.sleep(0.5)
                    return True
            except Exception as e:
                print(f"[XX] Locator failed for {selector}: {e}")
                try:
                    elem = await page.wait_for_selector(selector, timeout=5000)
                    if elem:
                        print(f"[XX] Found {field_name} via query_selector: {selector}")
                        await page.evaluate(f'''
                            (function() {{
                                var el = document.querySelector("{selector.replace('"', '\\"')}");
                                if (el) {{
                                    el.value = "{value.replace('"', '\\"')}";
                                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                                return false;
                            }})()
                        ''')
                        await asyncio.sleep(0.5)
                        return True
                except:
                    continue
        return False

    async def _smart_click(self, page, selectors, button_name="кнопка"):
        """Умный клик с force и fallback"""
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    print(f"[XX] Clicking {button_name} via locator: {selector}")
                    await locator.click(force=True, timeout=5000)
                    return True
            except Exception as e:
                print(f"[XX] Locator click failed for {selector}: {e}")
                try:
                    elem = await page.wait_for_selector(selector, timeout=3000)
                    if elem:
                        print(f"[XX] Clicking {button_name} via query_selector: {selector}")
                        try:
                            await elem.click(force=True)
                        except:
                            await page.evaluate("el => el.click()", elem)
                        return True
                except:
                    continue
        return False

    async def _handle_verification_step(self, page, email=None):
        """Обработать дополнительный шаг верификации (email, телефон, капча)"""
        await asyncio.sleep(3)
        await self._screenshot(page, "verification_step")
        
        # Проверяем, есть ли поле для email/телефона
        verify_selectors = [
            'input[name="email"]',
            'input[name="phone"]',
            'input[data-testid="ocfEnterTextTextInput"]',
            'input[type="text"]',
            'input[placeholder*="phone" i]',
            'input[placeholder*="email" i]',
            'input[placeholder*="код" i]',
            'input[placeholder*="code" i]',
        ]
        
        for selector in verify_selectors:
            try:
                verify_input = await page.wait_for_selector(selector, timeout=5000)
                if verify_input:
                    placeholder = await verify_input.get_attribute("placeholder") or ""
                    name_attr = await verify_input.get_attribute("name") or ""
                    label = await page.evaluate('el => el.labels?.[0]?.textContent || el.getAttribute("aria-label") || ""', verify_input)
                    
                    print(f"[XX] Found verification field: {selector}, placeholder: {placeholder}, name: {name_attr}")
                    
                    # Если это поле для кода подтверждения
                    if any(kw in (placeholder + label).lower() for kw in ["code", "код", "verification"]):
                        return False, "Требуется код подтверждения (2FA). Авторизация через чат не поддерживает 2FA. Настрой X_EMAIL в Environment Variables."
                    
                    # Если это поле для email/телефона и у нас есть email
                    if any(kw in (placeholder + name_attr + label).lower() for kw in ["phone", "email", "телефон", "почта"]):
                        if email:
                            filled = await self._smart_fill(page, [selector], email, "verification")
                            if filled:
                                await asyncio.sleep(1)
                                # Нажимаем Next
                                next_selectors = [
                                    'button[type="submit"]',
                                    'button:has-text("Next")',
                                    'button:has-text("Далее")',
                                    'button[role="button"]',
                                ]
                                await self._smart_click(page, next_selectors, "Next after verification")
                                await asyncio.sleep(3)
                                await self._screenshot(page, "verification_after_email")
                                return True, None
                        else:
                            return False, "Требуется дополнительная верификация (email/телефон). Укажи email при авторизации или настрой X_EMAIL в Environment Variables."
            except:
                continue
        
        # Проверяем, есть ли капча
        try:
            captcha_selectors = [
                'iframe[src*="captcha"]',
                'iframe[src*="recaptcha"]',
                '[data-testid="challenge"]',
                '.challenge',
            ]
            for selector in captcha_selectors:
                captcha = await page.query_selector(selector)
                if captcha:
                    return False, "Обнаружена капча. Автоматическая авторизация невозможна. Попробуй войти через браузер и сохранить cookies вручную."
        except:
            pass
        
        return True, None  # Нет дополнительных шагов

    async def _login(self, page, username, password, email=None):
        """Авторизация на X с поддержкой новой формы и дополнительных шагов"""
        try:
            print(f"[XX] Авторизация как {username}...")
            
            # 1. Открываем страницу логина
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            await self._screenshot(page, "login_start")
            print(f"[XX] Page loaded: {await self._get_page_info(page)}")
            
            # 2. Ввод username
            username_selectors = [
                'input[name="username_or_email"]',
                'input#jf-input-username_or_email',
                'input.jf-element.jf-float-input',
                'input[autocomplete="username webauthn"]',
                'input[inputmode="text"]',
                'input[autocomplete="username"]',
                'input[name="text"]',
                'input[type="text"]',
                'input[autocapitalize="none"]',
                'input[data-testid="ocfEnterTextTextInput"]',
            ]
            
            filled = await self._smart_fill(page, username_selectors, username, "username")
            if not filled:
                await self._screenshot(page, "login_no_username")
                return False, "Не найдено поле для ввода логина. X мог изменить страницу."
            
            await asyncio.sleep(1)
            
            # 3. Нажимаем Next
            next_selectors = [
                'button[type="submit"]',
                'button.jf-button',
                'button:has-text("Next")',
                'button:has-text("Далее")',
                'button[role="button"]:nth-child(2)',
                'div[role="button"]:has-text("Next")',
            ]
            
            clicked = await self._smart_click(page, next_selectors, "Next")
            if not clicked:
                try:
                    await page.keyboard.press("Enter")
                    print("[XX] Pressed Enter on keyboard")
                except Exception as e:
                    print(f"[XX] Enter failed: {e}")
            
            await asyncio.sleep(4)
            await self._screenshot(page, "login_after_username")
            print(f"[XX] After username step: {await self._get_page_info(page)}")
            
            # 4. Обрабатываем возможную верификацию (email/телефон)
            success, error = await self._handle_verification_step(page, email)
            if not success:
                return False, error
            
            # 5. Ввод пароля
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
                'input[data-testid="LoginForm_Password_Input"]',
            ]
            
            filled = await self._smart_fill(page, password_selectors, password, "password")
            if not filled:
                # Проверяем, не запросили ли ещё раз username (значит, первый шаг не прошёл)
                username_check = await page.query_selector('input[name="username_or_email"]')
                if username_check:
                    return False, "Не удалось перейти к вводу пароля. Возможно, username неверный или требуется email/телефон."
                
                await self._screenshot(page, "login_no_password")
                return False, "Не найдено поле для ввода пароля. Возможно, требуется email/телефон."
            
            await asyncio.sleep(1)
            
            # 6. Нажимаем Log in
            login_selectors = [
                'button[type="submit"]',
                'button.jf-button',
                'button[data-testid="LoginForm_Login_Button"]',
                'button:has-text("Log in")',
                'button:has-text("Войти")',
                'button:has-text("Sign in")',
                'div[role="button"]:has-text("Log in")',
            ]
            
            clicked = await self._smart_click(page, login_selectors, "Login")
            if not clicked:
                try:
                    await page.keyboard.press("Enter")
                    print("[XX] Pressed Enter for login")
                except Exception as e:
                    print(f"[XX] Enter for login failed: {e}")
            
            # 7. Ждём загрузки и обрабатываем дополнительные шаги
            await asyncio.sleep(5)
            await self._screenshot(page, "login_after_submit")
            print(f"[XX] After login submit: {await self._get_page_info(page)}")
            
            # Проверяем, не появилась ли ещё одна верификация (2FA, капча)
            success, error = await self._handle_verification_step(page, email)
            if not success:
                return False, error
            
            # 8. Проверяем, вошли ли мы
            # Ждём ещё немного и проверяем URL
            await asyncio.sleep(3)
            current_url = page.url
            print(f"[XX] Current URL after login: {current_url}")
            
            if "home" in current_url or "x.com/home" in current_url:
                print("[XX] Auth success detected by URL!")
                return True, None
            
            # Пробуем найти primaryColumn
            try:
                await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=10000)
                print("[XX] primaryColumn found!")
            except:
                # Проверяем ошибки
                error_selectors = [
                    'span:has-text("Wrong password")',
                    'span:has-text("Неверный пароль")',
                    'span:has-text("Incorrect")',
                    '[data-testid="toast"]',
                    'div[role="alert"]',
                    '.jf-error',
                    '[role="alert"]',
                ]
                
                for selector in error_selectors:
                    try:
                        error_elem = await page.query_selector(selector)
                        if error_elem:
                            error_text = await error_elem.inner_text()
                            return False, f"Ошибка входа: {error_text}"
                    except:
                        continue
                
                # Проверяем, не на странице логина ли мы всё ещё
                if "/login" in current_url or "/flow/login" in current_url:
                    await self._screenshot(page, "login_still_on_login_page")
                    return False, "Всё ещё на странице логина. Возможно, неверный пароль или требуется дополнительная верификация."
                
                await self._screenshot(page, "login_unknown_state")
                return False, f"Авторизация не удалась. Текущий URL: {current_url}. Проверь логин/пароль или установи X_EMAIL."
            
            # Финальная проверка
            signin = await page.query_selector('a[href="/i/flow/login"]')
            if signin:
                await self._screenshot(page, "login_still_signin")
                return False, "Авторизация не удалась. Возможно, требуется верификация."
            
            print("[XX] Авторизация успешна!")
            return True, None
            
        except Exception as e:
            try:
                await self._screenshot(page, "login_exception")
            except:
                pass
            return False, f"Ошибка авторизации: {e}"

    async def _ensure_auth(self, context, page, username=None, password=None, email=None):
        """Убедиться, что авторизованы. Можно передать credentials для принудительного входа."""
        is_auth = await self._check_auth(page)
        if not is_auth:
            print("[XX] Не авторизован, выполняю вход...")
            u = username or X_USERNAME_ENV
            p = password or X_PASSWORD_ENV
            e = email or X_EMAIL_ENV
            if not u or not p:
                return False, "Не указаны логин/пароль. Используй /x_login для ввода."
            success, error = await self._login(page, u, p, e)
            if not success:
                return False, error
            await self._save_cookies(context)
        return True, None

    async def _parse_tweet(self, article):
        tweet = {"text": "", "author": "", "handle": "", "time": "", "replies": "0", "retweets": "0", "likes": "0", "url": ""}
        try:
            text_elem = await article.query_selector('[data-testid="tweetText"]')
            if text_elem:
                tweet["text"] = await text_elem.inner_text()
            user_elem = await article.query_selector('[data-testid="User-Name"]')
            if user_elem:
                parts = (await user_elem.inner_text()).split("\n")
                tweet["author"] = parts[0] if parts else ""
                tweet["handle"] = parts[1] if len(parts) > 1 else ""
            time_elem = await article.query_selector("time")
            if time_elem:
                tweet["time"] = await time_elem.get_attribute("datetime") or ""
            buttons = await article.query_selector_all('[role="group"] button')
            for btn in buttons:
                try:
                    label = await btn.get_attribute("aria-label") or ""
                    if "reply" in label.lower():
                        nums = re.findall(r'[\d,]+', label)
                        tweet["replies"] = nums[0] if nums else "0"
                    elif "repost" in label.lower() or "retweet" in label.lower():
                        nums = re.findall(r'[\d,]+', label)
                        tweet["retweets"] = nums[0] if nums else "0"
                    elif "like" in label.lower():
                        nums = re.findall(r'[\d,]+', label)
                        tweet["likes"] = nums[0] if nums else "0"
                except:
                    pass
            link = await article.query_selector('a[href*="/status/"]')
            if link:
                href = await link.get_attribute("href")
                if href:
                    tweet["url"] = f"https://x.com{href}"
            return tweet if tweet["text"] else None
        except:
            return None

    async def fetch_timeline(self, username=None, limit=10, credentials=None):
        if not await self._ensure_playwright():
            return None, "Playwright не установлен"
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                await self._load_cookies(context)
                page = await context.new_page()
                
                if credentials:
                    success, error = await self._ensure_auth(context, page, 
                        credentials.get("username"), 
                        credentials.get("password"), 
                        credentials.get("email"))
                else:
                    success, error = await self._ensure_auth(context, page)
                    
                if not success:
                    await browser.close()
                    return None, error
                url = f"https://x.com/{username}" if username else "https://x.com/home"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector("article", timeout=15000)
                tweets = []
                last_count = 0
                attempts = 0
                while len(tweets) < limit and attempts < 10:
                    articles = await page.query_selector_all("article")
                    for article in articles:
                        tweet = await self._parse_tweet(article)
                        if tweet and tweet not in tweets:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break
                    if len(tweets) == last_count:
                        attempts += 1
                    else:
                        attempts = 0
                        last_count = len(tweets)
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(1)
                await self._save_cookies(context)
                await browser.close()
                return tweets[:limit], None
        except Exception as e:
            return None, f"Ошибка: {e}"

    async def search(self, query, limit=10, credentials=None):
        if not await self._ensure_playwright():
            return None, "Playwright не установлен"
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                await self._load_cookies(context)
                page = await context.new_page()
                
                if credentials:
                    success, error = await self._ensure_auth(context, page,
                        credentials.get("username"),
                        credentials.get("password"),
                        credentials.get("email"))
                else:
                    success, error = await self._ensure_auth(context, page)
                    
                if not success:
                    await browser.close()
                    return None, error
                encoded = query.replace(" ", "%20")
                url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector("article", timeout=15000)
                tweets = []
                attempts = 0
                while len(tweets) < limit and attempts < 8:
                    articles = await page.query_selector_all("article")
                    for article in articles:
                        tweet = await self._parse_tweet(article)
                        if tweet and tweet not in tweets:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break
                    if len(tweets) == 0:
                        attempts += 1
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await asyncio.sleep(1.5)
                await self._save_cookies(context)
                await browser.close()
                return tweets[:limit], None
        except Exception as e:
            return None, f"Ошибка: {e}"


xx_agent = XXAgent()


def run_async_task(coro):
    result = [None, None]
    def target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            result[1] = str(e)
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=120)
    if t.is_alive():
        return None, "Таймаут (120 сек)"
    if result[1]:
        return None, result[1]
    return result[0]


def register_x_play(bot):
    print("[XX] === REGISTER START ===")

    def is_in_login_dialog(chat_id, step):
        return chat_id in login_sessions and login_sessions[chat_id].get("step") == step

    def do_login_with_creds(chat_id, username, password, email=None):
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            print("[XX] Старые cookies удалены")
        
        async def do_login_chat():
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                success, error = await xx_agent._login(page, username, password, email)
                if success:
                    await xx_agent._save_cookies(context)
                await browser.close()
                return success, error
        
        return run_async_task(do_login_chat())

    @bot.message_handler(commands=["x_install"])
    def x_install_command(message):
        global PLAYWRIGHT_INSTALLED, CHROMIUM_READY
        status_before = (
            f"📦 <b>Статус до установки:</b>\n"
            f"Playwright pip: {'✅' if PLAYWRIGHT_INSTALLED else '❌'}\n"
            f"Chromium бинарник: {'✅' if CHROMIUM_READY else '❌'}\n"
            f"Browsers path: <code>{PLAYWRIGHT_BROWSERS_PATH or 'default (эфемерный)'}</code>\n\n"
            f"⏳ Начинаю установку..."
        )
        bot.reply_to(message, status_before, parse_mode="HTML")
        success = install_playwright()
        status_after = (
            f"{'✅' if success else '❌'} <b>Результат установки</b>\n\n"
            f"Playwright pip: {'✅' if PLAYWRIGHT_INSTALLED else '❌'}\n"
            f"Chromium бинарник: {'✅' if CHROMIUM_READY else '❌'}\n"
            f"Browsers path: <code>{PLAYWRIGHT_BROWSERS_PATH or 'default'}</code>\n\n"
        )
        if success:
            status_after += (
                "🎉 Готово! Теперь можно использовать:\n"
                "/x_login — авторизация\n"
                "/x_timeline — лента\n"
                "/x_search — поиск"
            )
        else:
            status_after += (
                "❌ Ошибка установки.\n\n"
                "💡 <b>Совет для Render:</b>\n"
                "Добавь Environment Variable:\n"
                "<code>PLAYWRIGHT_BROWSERS_PATH=/data/playwright-browsers</code>\n"
                "и подключи Render Disk к <code>/data</code>"
            )
        bot.reply_to(message, status_after, parse_mode="HTML")

    @bot.message_handler(commands=["x_login"])
    def x_login_command(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
        
        has_env = bool(X_USERNAME_ENV and X_PASSWORD_ENV)
        
        msg = (
            "🔐 <b>Авторизация в X</b>\n\n"
            "Введи свой <b>username</b> (без @):\n\n"
        )
        if has_env:
            msg += f"💡 Или используй env: <code>{X_USERNAME_ENV}</code>\nОтправь <code>/x_login_env</code> для быстрого входа"
        
        bot.reply_to(message, msg, parse_mode="HTML")
        login_sessions[chat_id] = {"step": "username"}
        print(f"[XX] Login dialog started for chat {chat_id}, step: username")

    @bot.message_handler(commands=["x_login_env"])
    def x_login_env_command(message):
        if not X_USERNAME_ENV or not X_PASSWORD_ENV:
            bot.reply_to(message, "❌ X_USERNAME и X_PASSWORD не настроены в Environment Variables")
            return
        
        bot.reply_to(message, f"🔐 Авторизация через env как <code>{X_USERNAME_ENV}</code>...", parse_mode="HTML")
        
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            print("[XX] Старые cookies удалены")
        
        async def do_login_env():
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                success, error = await xx_agent._login(page, X_USERNAME_ENV, X_PASSWORD_ENV, X_EMAIL_ENV)
                if success:
                    await xx_agent._save_cookies(context)
                await browser.close()
                return success, error
        
        success, error = run_async_task(do_login_env())
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if success:
            bot.reply_to(message, "✅ Авторизация через env успешна! Cookies сохранены.")
        else:
            bot.reply_to(message, "❌ Авторизация не удалась")

    @bot.message_handler(commands=["x_cancel"])
    def x_cancel_command(message):
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Ввод отменён. Данные очищены.")
        else:
            bot.reply_to(message, "Нет активного ввода.")

    @bot.message_handler(commands=["x_status"])
    def x_status_command(message):
        chat_id = message.chat.id
        has_session = chat_id in login_sessions
        
        status = (
            "📊 <b>Статус X Agent</b>\n\n"
            f"Playwright pip: {'✅' if PLAYWRIGHT_INSTALLED else '❌'}\n"
            f"Chromium бинарник: {'✅' if CHROMIUM_READY else '❌'}\n"
            f"Browsers path: <code>{PLAYWRIGHT_BROWSERS_PATH or 'default (эфемерный)'}</code>\n"
            f"Env логин: {'✅' if X_USERNAME_ENV else '❌'}\n"
            f"Env пароль: {'✅' if X_PASSWORD_ENV else '❌'}\n"
            f"Env email: {'✅' if X_EMAIL_ENV else '❌ (не обязательно)'}\n"
            f"Активная сессия ввода: {'✅' if has_session else '❌'}\n\n"
        )
        if not CHROMIUM_READY:
            status += "⚠️ Chromium не установлен. Используй /x_install\n"
        elif not X_USERNAME_ENV:
            status += "ℹ️ Env логин не настроен. Используй /x_login для ввода в чате\n"
        else:
            status += "✅ Готов к работе! Используй /x_login или /x_login_env\n"
        bot.reply_to(message, status, parse_mode="HTML")

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
        if not CHROMIUM_READY:
            bot.reply_to(message, "⏳ Chromium не найден, запускаю установку...")
            if not install_playwright():
                bot.reply_to(message, "❌ Установка не удалась. Используй /x_install")
                return
        args = message.text.split()
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        bot.reply_to(message, f"🐦 Загружаю {'@' + username if username else 'Home'}...")
        tweets, error = run_async_task(xx_agent.fetch_timeline(username, limit))
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not tweets:
            bot.reply_to(message, "📭 Твиты не найдены")
            return
        lines = [f"🐦 <b>{'@' + username if username else 'Home'}</b>\n"]
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:180]
            if len(t.get("text", "")) > 180:
                text += "..."
            lines.append(
                f"{i}. <b>{t.get('author', '')}</b> <code>{t.get('handle', '')}</code>\n"
                f"   <i>{text}</i>\n"
                f"   ❤️ {t.get('likes', '0')}  🔄 {t.get('retweets', '0')}  💬 {t.get('replies', '0')}\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n<i>...обрезано</i>"
        bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(commands=["x_search"])
    def x_search_command(message):
        if not CHROMIUM_READY:
            bot.reply_to(message, "⏳ Chromium не найден, запускаю установку...")
            if not install_playwright():
                bot.reply_to(message, "❌ Установка не удалась. Используй /x_install")
                return
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи запрос: <code>/x_search python</code>", parse_mode="HTML")
            return
        query = args[1]
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        bot.reply_to(message, f"🔍 Ищу: <i>{query}</i>...", parse_mode="HTML")
        tweets, error = run_async_task(xx_agent.search(query, limit))
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if not tweets:
            bot.reply_to(message, "📭 Ничего не найдено")
            return
        lines = [f"🔍 <b>{query}</b>\n"]
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:160]
            if len(t.get("text", "")) > 160:
                text += "..."
            lines.append(
                f"{i}. <b>{t.get('author', '')}</b>\n"
                f"   <i>{text}</i>\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(commands=["x_trends"])
    def x_trends_command(message):
        bot.reply_to(message, "📈 Используй /x_search для поиска по темам")

    @bot.message_handler(commands=["x_screenshot"])
    def x_screenshot_command(message):
        bot.reply_to(message, "📸 Скриншоты в разработке")

    @bot.message_handler(commands=["x_help"])
    def x_help_command(message):
        msg = (
            "🐦 <b>X Agent — команды</b>\n\n"
            "🔧 <b>Настройка</b>\n"
            "  /x_status — Проверить статус системы\n"
            "  /x_install — Установить Playwright + Chromium\n\n"
            "🔐 <b>Авторизация</b>\n"
            "  /x_login — Войти в X (ввод в чате: username → пароль → email)\n"
            "  /x_login_env — Быстрый вход через Environment Variables\n"
            "  /x_cancel — Отменить ввод\n\n"
            "📰 <b>Контент</b>\n"
            "  /x_timeline [user] [N] — Лента пользователя\n"
            "  /x_search [запрос] [N] — Поиск твитов\n\n"
            "⚠️ <b>Внимание:</b> Сообщения с паролем удаляются после авторизации, "
            "но остаются в истории Telegram-серверов. Для максимальной безопасности "
            "используй Environment Variables."
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    # === ОБРАБОТЧИКИ ДИАЛОГА ===

    @bot.message_handler(func=lambda m: is_in_login_dialog(m.chat.id, "username"))
    def x_login_username_step(message):
        chat_id = message.chat.id
        username = message.text.strip()
        
        if username.startswith("@"):
            username = username[1:]
        
        if username.startswith("/"):
            bot.reply_to(message, "❌ Это похоже на команду. Введи username или /x_cancel для отмены.")
            return
        
        login_sessions[chat_id]["username"] = username
        login_sessions[chat_id]["step"] = "password"
        
        print(f"[XX] Chat {chat_id}: username received, moving to password")
        
        bot.reply_to(message, 
            f"✅ Username: <code>{username}</code>\n\n"
            f"Теперь введи <b>пароль</b>:\n"
            f"<i>(сообщение с паролем будет удалено после авторизации)</i>",
            parse_mode="HTML"
        )

    @bot.message_handler(func=lambda m: is_in_login_dialog(m.chat.id, "password"))
    def x_login_password_step(message):
        chat_id = message.chat.id
        password = message.text
        
        if password.startswith("/"):
            bot.reply_to(message, "❌ Это похоже на команду. Введи пароль или /x_cancel для отмены.")
            return
        
        login_sessions[chat_id]["password"] = password
        login_sessions[chat_id]["step"] = "email"
        
        print(f"[XX] Chat {chat_id}: password received, moving to email")
        
        bot.reply_to(message,
            "✅ Пароль получен\n\n"
            "Если у тебя настроена дополнительная проверка (email/телефон), введи email сейчас.\n"
            "Или отправь <code>skip</code> чтобы пропустить:",
            parse_mode="HTML"
        )

    @bot.message_handler(func=lambda m: is_in_login_dialog(m.chat.id, "email"))
    def x_login_email_step(message):
        chat_id = message.chat.id
        email_input_text = message.text.strip()
        
        if email_input_text.startswith("/") and email_input_text.lower() != "/skip":
            bot.reply_to(message, "❌ Это похоже на команду. Введи email, <code>skip</code> или /x_cancel для отмены.")
            return
        
        email = None if email_input_text.lower() == "skip" else email_input_text
        
        login_sessions[chat_id]["email"] = email
        login_sessions[chat_id]["step"] = "done"
        
        creds = login_sessions[chat_id]
        username = creds["username"]
        password = creds["password"]
        email = creds.get("email")
        
        print(f"[XX] Chat {chat_id}: email received, starting login with username={username}")
        
        # Отправляем уведомление о начале авторизации
        status_msg = bot.send_message(
            chat_id, 
            f"🔐 <b>Авторизация началась!</b>\n"
            f"Username: <code>{username}</code>\n"
            f"⏳ Открываю браузер и захожу на X...\n"
            f"<i>Это может занять 15-30 секунд</i>",
            parse_mode="HTML"
        )
        
        # Пытаемся удалить сообщения с паролем (не критично)
        try:
            bot.delete_message(chat_id, message.message_id - 1)
            bot.delete_message(chat_id, message.message_id)
        except Exception as e:
            print(f"[XX] Could not delete password message: {e}")
        
        # Выполняем авторизацию
        success, error = do_login_with_creds(chat_id, username, password, email)
        
        # Очищаем сессию
        del login_sessions[chat_id]
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if success:
            bot.reply_to(message, "✅ Авторизация успешна! Cookies сохранены.\nТеперь можно использовать /x_timeline и /x_search")
        else:
            bot.reply_to(message, "❌ Авторизация не удалась")

    print("[XX] === REGISTER END ===")
