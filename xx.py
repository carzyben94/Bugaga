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
# {chat_id: {"step": "username|password|email|done", "username": "...", "password": "...", "email": "..."}}
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

    async def _login(self, page, username, password, email=None):
        """
        Авторизация на X с переданными credentials.
        username, password, email — из чата или env.
        """
        try:
            print(f"[XX] Авторизация как {username}...")
            
            # 1. Открываем страницу логина
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await self._screenshot(page, "login_start")
            
            # 2. Ввод username — пробуем несколько селекторов
            username_selectors = [
                'input[autocomplete="username"]',
                'input[name="text"]',
                'input[type="text"]',
                'input[autocapitalize="none"]',
                'input[data-testid="ocfEnterTextTextInput"]',
                'input[placeholder*="phone" i]',
                'input[placeholder*="email" i]',
                'input[placeholder*="username" i]',
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = await page.wait_for_selector(selector, timeout=5000)
                    if username_input:
                        print(f"[XX] Found username input: {selector}")
                        break
                except:
                    continue
            
            if not username_input:
                await self._screenshot(page, "login_no_username")
                return False, "Не найдено поле для ввода логина. X мог изменить страницу."
            
            await username_input.click()
            await username_input.fill(username)
            await asyncio.sleep(1)
            
            # 3. Нажимаем Next
            next_selectors = [
                'button:has-text("Next")',
                'button:has-text("Далее")',
                'button[role="button"]:nth-child(2)',
                'button[type="button"]:nth-child(2)',
                'div[role="button"]:has-text("Next")',
                'div[role="button"]:has-text("Далее")',
            ]
            
            next_clicked = False
            for selector in next_selectors:
                try:
                    next_btn = await page.query_selector(selector)
                    if next_btn:
                        await next_btn.click()
                        next_clicked = True
                        print(f"[XX] Clicked Next: {selector}")
                        break
                except:
                    continue
            
            if not next_clicked:
                await username_input.press("Enter")
                print("[XX] Pressed Enter instead of Next")
            
            await asyncio.sleep(3)
            await self._screenshot(page, "login_after_username")
            
            # 4. Проверка на email/телефон (дополнительная проверка)
            try:
                email_selectors = [
                    'input[data-testid="ocfEnterTextTextInput"]',
                    'input[name="text"]',
                    'input[type="text"]',
                    'input[autocomplete="on"]',
                ]
                
                for selector in email_selectors:
                    try:
                        email_input = await page.wait_for_selector(selector, timeout=5000)
                        if email_input and email:
                            placeholder = await email_input.get_attribute("placeholder") or ""
                            label = await page.evaluate('el => el.labels?.[0]?.textContent || el.getAttribute("aria-label") || ""', email_input)
                            
                            if any(kw in (placeholder + label).lower() for kw in ["phone", "email", "телефон", "почта"]):
                                await email_input.fill(email)
                                await asyncio.sleep(1)
                                
                                for next_sel in next_selectors:
                                    try:
                                        next_btn = await page.query_selector(next_sel)
                                        if next_btn:
                                            await next_btn.click()
                                            break
                                    except:
                                        continue
                                
                                await asyncio.sleep(3)
                                await self._screenshot(page, "login_after_email")
                                break
                    except:
                        continue
                        
            except Exception as e:
                print(f"[XX] Email step skipped or failed: {e}")
            
            # 5. Ввод пароля
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
                'input[data-testid="LoginForm_Password_Input"]',
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = await page.wait_for_selector(selector, timeout=8000)
                    if password_input:
                        print(f"[XX] Found password input: {selector}")
                        break
                except:
                    continue
            
            if not password_input:
                await self._screenshot(page, "login_no_password")
                return False, "Не найдено поле для ввода пароля. Возможно, требуется email/телефон."
            
            await password_input.click()
            await password_input.fill(password)
            await asyncio.sleep(1)
            
            # 6. Нажимаем Log in
            login_selectors = [
                'button[data-testid="LoginForm_Login_Button"]',
                'button:has-text("Log in")',
                'button:has-text("Войти")',
                'button:has-text("Sign in")',
                'div[role="button"]:has-text("Log in")',
                'div[role="button"]:has-text("Войти")',
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    login_btn = await page.query_selector(selector)
                    if login_btn:
                        await login_btn.click()
                        login_clicked = True
                        print(f"[XX] Clicked Login: {selector}")
                        break
                except:
                    continue
            
            if not login_clicked:
                await password_input.press("Enter")
                print("[XX] Pressed Enter instead of Login")
            
            # 7. Ждём загрузки
            await asyncio.sleep(4)
            await self._screenshot(page, "login_after_submit")
            
            try:
                await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
            except:
                error_selectors = [
                    'span:has-text("Wrong password")',
                    'span:has-text("Неверный пароль")',
                    'span:has-text("Incorrect")',
                    '[data-testid="toast"]',
                    'div[role="alert"]',
                ]
                
                for selector in error_selectors:
                    try:
                        error_elem = await page.query_selector(selector)
                        if error_elem:
                            error_text = await error_elem.inner_text()
                            return False, f"Ошибка входа: {error_text}"
                    except:
                        continue
                
                await self._screenshot(page, "login_failed")
                return False, "Авторизация не удалась. Проверь логин/пароль или установи X_EMAIL."
            
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
            # Используем переданные или из env
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
                
                # Если переданы credentials — используем их, иначе из env/cookies
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

    @bot.message_handler(commands=["x_install"])
    def x_install_command(message):
        """Установить/проверить Playwright и Chromium"""
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
        """Запустить диалог авторизации в X"""
        chat_id = message.chat.id
        
        # Если уже есть сессия — сбрасываем
        if chat_id in login_sessions:
            del login_sessions[chat_id]
        
        # Проверяем, есть ли env credentials
        has_env = bool(X_USERNAME_ENV and X_PASSWORD_ENV)
        
        msg = (
            "🔐 <b>Авторизация в X</b>\n\n"
            "Введи свой <b>username</b> (без @):\n\n"
        )
        if has_env:
            msg += f"💡 Или используй env: <code>{X_USERNAME_ENV}</code>\nОтправь <code>/x_login_env</code> для быстрого входа"
        
        bot.reply_to(message, msg, parse_mode="HTML")
        login_sessions[chat_id] = {"step": "username"}

    @bot.message_handler(commands=["x_login_env"])
    def x_login_env_command(message):
        """Быстрая авторизация через Environment Variables"""
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

    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id]["step"] == "username")
    def x_login_username_step(message):
        """Шаг 1: Получили username"""
        chat_id = message.chat.id
        username = message.text.strip()
        
        # Убираем @ если есть
        if username.startswith("@"):
            username = username[1:]
        
        login_sessions[chat_id]["username"] = username
        login_sessions[chat_id]["step"] = "password"
        
        bot.reply_to(message, 
            f"✅ Username: <code>{username}</code>\n\n"
            f"Теперь введи <b>пароль</b>:\n"
            f"<i>(сообщение с паролем будет удалено после авторизации для безопасности)</i>",
            parse_mode="HTML"
        )

    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id]["step"] == "password")
    def x_login_password_step(message):
        """Шаг 2: Получили password"""
        chat_id = message.chat.id
        password = message.text
        
        login_sessions[chat_id]["password"] = password
        login_sessions[chat_id]["step"] = "email"
        
        bot.reply_to(message,
            "✅ Пароль получен\n\n"
            "Если у тебя настроена дополнительная проверка (email/телефон), введи email сейчас.\n"
            "Или отправь <code>skip</code> чтобы пропустить:",
            parse_mode="HTML"
        )

    @bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id]["step"] == "email")
    def x_login_email_step(message):
        """Шаг 3: Получили email (или skip)"""
        chat_id = message.chat.id
        email = message.text.strip()
        
        if email.lower() == "skip":
            email = None
        
        login_sessions[chat_id]["email"] = email
        login_sessions[chat_id]["step"] = "done"
        
        # Получаем все данные
        creds = login_sessions[chat_id]
        username = creds["username"]
        password = creds["password"]
        email = creds.get("email")
        
        # Удаляем сообщение с паролем для безопасности
        try:
            bot.delete_message(chat_id, message.message_id - 1)  # Сообщение с паролем
            bot.delete_message(chat_id, message.message_id)       # Сообщение с email/skip
        except Exception as e:
            print(f"[XX] Could not delete password message: {e}")
        
        bot.reply_to(message, f"🔐 Авторизация как <code>{username}</code>...", parse_mode="HTML")
        
        # Удаляем старые cookies
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
        
        success, error = run_async_task(do_login_chat())
        
        # Очищаем сессию
        del login_sessions[chat_id]
        
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        if success:
            bot.reply_to(message, "✅ Авторизация успешна! Cookies сохранены.\nТеперь можно использовать /x_timeline и /x_search")
        else:
            bot.reply_to(message, "❌ Авторизация не удалась")

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
        """Лента пользователя"""
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
        """Поиск по X"""
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
            if len(t.get("text", "") > 160:
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

    @bot.message_handler(commands=["x_status"])
    def x_status_command(message):
        """Проверить статус Playwright и Chromium"""
        # Проверяем, есть ли активная сессия
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

    @bot.message_handler(commands=["x_cancel"])
    def x_cancel_command(message):
        """Отменить диалог авторизации"""
        chat_id = message.chat.id
        if chat_id in login_sessions:
            del login_sessions[chat_id]
            bot.reply_to(message, "❌ Ввод отменён. Данные очищены.")
        else:
            bot.reply_to(message, "Нет активного ввода.")

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

    print("[XX] === REGISTER END ===")
