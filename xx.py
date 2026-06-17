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
            PLAYWRIGHT_INSTALLED = False  # Переустановим
        finally:
            try:
                loop.close()
            except:
                pass
    
    print("[XX] Installing Playwright...")
    try:
        # Устанавливаем playwright
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright"],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        # Скачиваем Chromium
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        # Перезагружаем импорт
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
    
    async def _ensure_playwright(self):
        if not self._playwright_checked:
            self._playwright_checked = True
            if not PLAYWRIGHT_INSTALLED:
                # Попробуем ещё раз (может уже установился в другом потоке)
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
        except:
            pass
    
    async def _login(self, page):
        if not X_USERNAME or not X_PASSWORD:
            return False, "X_USERNAME или X_PASSWORD не настроены"
        
        try:
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            
            await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            await page.fill('input[autocomplete="username"]', X_USERNAME)
            await page.click('button:has-text("Next")')
            await asyncio.sleep(2)
            
            try:
                email_input = await page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000)
                if email_input and X_EMAIL:
                    await email_input.fill(X_EMAIL)
                    await page.click('button:has-text("Next")')
                    await asyncio.sleep(1)
            except:
                pass
            
            await page.wait_for_selector('input[name="password"]', timeout=10000)
            await page.fill('input[name="password"]', X_PASSWORD)
            await page.click('button[data-testid="LoginForm_Login_Button"]')
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
            
            return True, None
            
        except Exception as e:
            return False, f"Ошибка авторизации: {e}"
    
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
                
                # Проверка сессии
                await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=8000)
                except:
                    await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
                    success, error = await self._login(page)
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
    result = [None, None]  # [success, error]
    
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
        # Проверяем, установлен ли уже
        if PLAYWRIGHT_INSTALLED:
            # Проверим Chromium
            def check():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def test():
                    async with async_playwright() as p:
                        await p.chromium.launch(headless=True, args=["--no-sandbox"])
                
                try:
                    loop.run_until_complete(test())
                    loop.close()
                    return True, None
                except Exception as e:
                    loop.close()
                    return False, str(e)
            
            ok, err = check()
            if ok:
                bot.reply_to(message, "✅ Playwright уже установлен и работает!")
                return
        
        bot.reply_to(message, "🔐 Установка Playwright... Это может занять минуту.")
        
        success = install_playwright()
        if success:
            bot.reply_to(message, "✅ Playwright установлен!")
        else:
            bot.reply_to(message, "❌ Не удалось установить")

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
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
                f"   ❤️ {t.get('likes', '0')}  🔄 {t.get('retweets', '0')}\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n<i>...обрезано</i>"
        
        bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(commands=["x_search"])
    def x_search_command(message):
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(message, "❌ /x_search [запрос]", parse_mode="HTML")
            return
        
        query = args[1]
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🔍 {query}...")
        
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
        bot.reply_to(message, "📈 Используй /x_search")

    @bot.message_handler(commands=["x_screenshot"])
    def x_screenshot_command(message):
        bot.reply_to(message, "📸 Используй /x_login для проверки")

    @bot.message_handler(commands=["x_help"])
    def x_help_command(message):
        msg = (
            "🐦 <b>X Agent</b>\n\n"
            "🔐 /x_login — Проверить/установить Playwright\n"
            "📰 /x_timeline [user] [N] — Лента\n"
            "🔍 /x_search [запрос] [N] — Поиск\n"
            "⚠️ Первая установка ~1 минута"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    print("[XX] === REGISTER END ===")
