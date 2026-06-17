# xx.py — X/Twitter агент с автоустановкой Playwright
import os
import sys
import subprocess
import json
import re
import time
import telebot

# Попытка импорта Playwright
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Env
X_USERNAME = os.environ.get("X_USERNAME")
X_PASSWORD = os.environ.get("X_PASSWORD")
X_EMAIL = os.environ.get("X_EMAIL")

COOKIES_FILE = "x_cookies.json"
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def install_playwright():
    """Установить Playwright и Chromium при необходимости"""
    global PLAYWRIGHT_AVAILABLE
    
    if PLAYWRIGHT_AVAILABLE:
        # Проверим, есть ли браузер
        try:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            try:
                p.chromium.launch(headless=True)
                p.stop()
                print("[XX] Playwright + Chromium OK")
                return True
            except Exception as e:
                p.stop()
                print(f"[XX] Chromium missing: {e}")
        except:
            pass
    
    print("[XX] Installing Playwright...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[XX] Playwright installed, downloading Chromium...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[XX] Chromium downloaded")
        
        # Перезагружаем импорт
        import importlib
        import playwright
        importlib.reload(playwright)
        from playwright.sync_api import sync_playwright
        PLAYWRIGHT_AVAILABLE = True
        return True
        
    except Exception as e:
        print(f"[XX] Install failed: {e}")
        return False


class XXAgent:
    def __init__(self):
        self._playwright_ready = None  # None = не проверяли, True/False = результат
    
    def _ensure_playwright(self):
        if self._playwright_ready is None:
            self._playwright_ready = install_playwright()
        return self._playwright_ready
    
    def _load_cookies(self, context):
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                return True
            except:
                pass
        return False
    
    def _save_cookies(self, context):
        try:
            cookies = context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
        except:
            pass
    
    def _login(self, page):
        if not X_USERNAME or not X_PASSWORD:
            return False, "X_USERNAME или X_PASSWORD не настроены"
        
        try:
            page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            
            page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            page.fill('input[autocomplete="username"]', X_USERNAME)
            page.click('button:has-text("Next")')
            time.sleep(2)
            
            try:
                email_input = page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000)
                if email_input and X_EMAIL:
                    email_input.fill(X_EMAIL)
                    page.click('button:has-text("Next")')
                    time.sleep(1)
            except:
                pass
            
            page.wait_for_selector('input[name="password"]', timeout=10000)
            page.fill('input[name="password"]', X_PASSWORD)
            page.click('button[data-testid="LoginForm_Login_Button"]')
            page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
            
            return True, None
            
        except Exception as e:
            return False, f"Ошибка авторизации: {e}"
    
    def _parse_tweet(self, article):
        tweet = {"text": "", "author": "", "handle": "", "time": "", "replies": "0", "retweets": "0", "likes": "0", "url": ""}
        
        try:
            text_elem = article.query_selector('[data-testid="tweetText"]')
            if text_elem:
                tweet["text"] = text_elem.inner_text()
            
            user_elem = article.query_selector('[data-testid="User-Name"]')
            if user_elem:
                parts = user_elem.inner_text().split("\n")
                tweet["author"] = parts[0] if parts else ""
                tweet["handle"] = parts[1] if len(parts) > 1 else ""
            
            time_elem = article.query_selector("time")
            if time_elem:
                tweet["time"] = time_elem.get_attribute("datetime") or ""
            
            for btn in article.query_selector_all('[role="group"] button'):
                try:
                    label = btn.get_attribute("aria-label") or ""
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
            
            link = article.query_selector('a[href*="/status/"]')
            if link:
                href = link.get_attribute("href")
                if href:
                    tweet["url"] = f"https://x.com{href}"
            
            return tweet if tweet["text"] else None
            
        except:
            return None
    
    def fetch_timeline(self, username=None, limit=10):
        if not self._ensure_playwright():
            return None, "Playwright не установлен"
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                
                self._load_cookies(context)
                page = context.new_page()
                
                # Проверка сессии
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=20000)
                try:
                    page.wait_for_selector('[data-testid="primaryColumn"]', timeout=8000)
                except:
                    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
                    success, error = self._login(page)
                    if not success:
                        browser.close()
                        return None, error
                
                # Загрузка ленты
                url = f"https://x.com/{username}" if username else "https://x.com/home"
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("article", timeout=15000)
                
                tweets = []
                last_count = 0
                attempts = 0
                
                while len(tweets) < limit and attempts < 10:
                    articles = page.query_selector_all("article")
                    
                    for article in articles:
                        tweet = self._parse_tweet(article)
                        if tweet and tweet not in tweets:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break
                    
                    if len(tweets) == last_count:
                        attempts += 1
                    else:
                        attempts = 0
                        last_count = len(tweets)
                    
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1)
                
                self._save_cookies(context)
                browser.close()
                return tweets[:limit], None
                
        except Exception as e:
            return None, f"Ошибка: {e}"
    
    def search(self, query, limit=10):
        if not self._ensure_playwright():
            return None, "Playwright не установлен"
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                
                self._load_cookies(context)
                page = context.new_page()
                
                encoded = query.replace(" ", "%20")
                url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
                
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("article", timeout=15000)
                
                tweets = []
                attempts = 0
                
                while len(tweets) < limit and attempts < 8:
                    articles = page.query_selector_all("article")
                    
                    for article in articles:
                        tweet = self._parse_tweet(article)
                        if tweet and tweet not in tweets:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break
                    
                    if len(tweets) == 0:
                        attempts += 1
                    
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(1.5)
                
                self._save_cookies(context)
                browser.close()
                return tweets[:limit], None
                
        except Exception as e:
            return None, f"Ошибка: {e}"


xx_agent = XXAgent()


def register_x_play(bot):
    print("[XX] === REGISTER START ===")

    @bot.message_handler(commands=["x_login"])
    def x_login_command(message):
        bot.reply_to(message, "🔐 Установка Playwright... Это может занять минуту.")
        
        success = install_playwright()
        if success:
            bot.reply_to(message, "✅ Playwright установлен!")
        else:
            bot.reply_to(message, "❌ Не удалось установить Playwright")

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
        args = message.text.split()
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🐦 Загружаю {'@' + username if username else 'Home'}...")
        
        tweets, error = xx_agent.fetch_timeline(username, limit)
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
        
        tweets, error = xx_agent.search(query, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
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
        bot.reply_to(message, "📸 Скриншоты требуют установки через /x_login")

    @bot.message_handler(commands=["x_help"])
    def x_help_command(message):
        msg = (
            "🐦 <b>X Agent</b>\n\n"
            "🔐 /x_login — Установить Playwright\n"
            "📰 /x_timeline [user] [N] — Лента\n"
            "🔍 /x_search [запрос] [N] — Поиск\n"
            "⚠️ Первая установка ~1 минута"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    print("[XX] === REGISTER END ===")
