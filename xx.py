# xx.py — X/Twitter агент через Playwright Async API
import os
import sys
import subprocess
import json
import re
import asyncio
import threading
import telebot

# Проверяем установку Playwright
PLAYWRIGHT_INSTALLED = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_INSTALLED = True
    print("[XX] Playwright already installed")
except ImportError:
    print("[XX] Playwright not installed")

# Env
X_USERNAME = os.environ.get("X_USERNAME")
X_PASSWORD = os.environ.get("X_PASSWORD")
X_EMAIL = os.environ.get("X_EMAIL")

COOKIES_FILE = "x_cookies.json"
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def install_playwright():
    """Установить Playwright и Chromium (один раз)"""
    global PLAYWRIGHT_INSTALLED
    
    if PLAYWRIGHT_INSTALLED:
        # Проверим, что Chromium тоже есть
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def check():
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    await p.chromium.launch(headless=True, args=["--no-sandbox"])
            
            loop.run_until_complete(check())
            loop.close()
            print("[XX] Playwright + Chromium OK")
            return True
        except Exception as e:
            print(f"[XX] Chromium missing: {e}")
            PLAYWRIGHT_INSTALLED = False
        finally:
            try:
                loop.close()
            except:
                pass
    
    print("[XX] Installing Playwright...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright"],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        import importlib
        import playwright
        importlib.reload(playwright)
        
        PLAYWRIGHT_INSTALLED = True
        print("[XX] Playwright installed successfully")
        return True
        
    except Exception as e:
        print(f"[XX] Install failed: {e}")
        return False


class XXAgent:
    def __init__(self):
        self._playwright_checked = False
        self._cookies_valid = False
    
    async def _ensure_playwright(self):
        if not self._playwright_checked:
            self._playwright_checked = True
            if not PLAYWRIGHT_INSTALLED:
                try:
                    from playwright.async_api import async_playwright
                except ImportError:
                    return False
        return PLAYWRIGHT_INSTALLED
    
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
    
    async def _check_auth(self, page):
        """Проверить, авторизованы ли мы"""
        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=8000)
            
            # Проверяем, есть ли кнопка "Sign in" (значит не авторизованы)
            signin = await page.query_selector('a[href="/i/flow/login"]')
            if signin:
                return False
            
            return True
        except:
            return False
    
    async def _login(self, page):
        """Полная авторизация на X"""
        if not X_USERNAME or not X_PASSWORD:
            return False, "X_USERNAME или X_PASSWORD не настроены"
        
        try:
            print(f"[XX] Авторизация как {X_USERNAME}...")
            
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            
            # Ввод username
            await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            await page.fill('input[autocomplete="username"]', X_USERNAME)
            
            # Next
            await page.click('button:has-text("Next")')
            await asyncio.sleep(2)
            
            # Проверка на email/телефон
            try:
                email_input = await page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000)
                if email_input and X_EMAIL:
                    await email_input.fill(X_EMAIL)
                    await page.click('button:has-text("Next")')
                    await asyncio.sleep(1)
            except:
                pass
            
            # Ввод пароля
            await page.wait_for_selector('input[name="password"]', timeout=10000)
            await page.fill('input[name="password"]', X_PASSWORD)
            
            # Log in
            await page.click('button[data-testid="LoginForm_Login_Button"]')
            
            # Ждём загрузки
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
            
            # Проверим, что вошли
            signin = await page.query_selector('a[href="/i/flow/login"]')
            if signin:
                return False, "Авторизация не удалась. Проверь логин/пароль."
            
            print("[XX] Авторизация успешна!")
            return True, None
            
        except Exception as e:
            return False, f"Ошибка авторизации: {e}"
    
    async def _ensure_auth(self, context, page):
        """Убедиться, что авторизованы"""
        is_auth = await self._check_auth(page)
        
        if not is_auth:
            print("[XX] Не авторизован, выполняю вход...")
            success, error = await self._login(page)
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
    
    async def fetch_timeline(self, username=None, limit=10):
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
                
                # Проверка/авторизация
                success, error = await self._ensure_auth(context, page)
                if not success:
                    await browser.close()
                    return None, error
                
                # Загрузка ленты
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
    
    async def search(self, query, limit=10):
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
                
                # Проверка/авторизация
                success, error = await self._ensure_auth(context, page)
                if not success:
                    await browser.close()
                    return None, error
                
                # Поиск
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
    """Запустить async корутину в отдельном потоке с новым event loop"""
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
    t.join(timeout=60)
    
    if t.is_alive():
        return None, "Таймаут (60 сек)"
    
    if result[1]:
        return None, result[1]
    
    return result[0]


def register_x_play(bot):
    print("[XX] === REGISTER START ===")

    @bot.message_handler(commands=["x_login"])
    def x_login_command(message):
        """Проверить/выполнить авторизацию на X"""
        if not PLAYWRIGHT_INSTALLED:
            bot.reply_to(message, "🔐 Установка Playwright...")
            success = install_playwright()
            if not success:
                bot.reply_to(message, "❌ Не удалось установить Playwright")
                return
        
        if not X_USERNAME or not X_PASSWORD:
            bot.reply_to(message,
                "❌ Настрой X_USERNAME и X_PASSWORD в переменных окружения\n\n"
                "На Render:\n"
                "<code>X_USERNAME=your_login</code>\n"
                "<code>X_PASSWORD=your_password</code>\n"
                "<code>X_EMAIL=your_email</code> (если 2FA)",
                parse_mode="HTML"
            )
            return
        
        bot.reply_to(message, f"🔐 Авторизация как <code>{X_USERNAME}</code>...", parse_mode="HTML")
        
        # Принудительная переавторизация — удаляем старые cookies
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            print("[XX] Старые cookies удалены")
        
        # Запускаем авторизацию
        async def do_login():
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await context.new_page()
                
                success, error = await xx_agent._login(page)
                if success:
                    await xx_agent._save_cookies(context)
                
                await browser.close()
                return success, error
        
        success, error = run_async_task(do_login())
        
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
            "🔐 <b>Авторизация</b>\n"
            "  /x_login — Войти в X (сохранить сессию)\n\n"
            "📰 <b>Контент</b>\n"
            "  /x_timeline [user] [N] — Лента пользователя\n"
            "  /x_search [запрос] [N] — Поиск твитов\n\n"
            f"Playwright: {'✅' if PLAYWRIGHT_INSTALLED else '❌'}\n"
            f"Логин: {'✅' if X_USERNAME else '❌ не настроен'}"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    print("[XX] === REGISTER END ===")
