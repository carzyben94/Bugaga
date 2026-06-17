# xx.py — X/Twitter агент через Playwright с авторизацией
import os
import time
import json
import re
from datetime import datetime
import telebot

# Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright не установлен. pip install playwright && playwright install chromium")

# Env-переменные для авторизации
X_USERNAME = os.environ.get("X_USERNAME")
X_PASSWORD = os.environ.get("X_PASSWORD")
X_EMAIL = os.environ.get("X_EMAIL")

COOKIES_FILE = "x_cookies.json"
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class XPlayAgent:
    """Агент для X/Twitter с авторизацией"""
    
    def __init__(self):
        self.logged_in = False
    
    def _save_cookies(self, context):
        """Сохранить сессию"""
        try:
            cookies = context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            print("[X] Cookies сохранены")
        except Exception as e:
            print(f"[X] Ошибка сохранения cookies: {e}")
    
    def _load_cookies(self, context):
        """Загрузить сессию"""
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                print("[X] Cookies загружены")
                return True
            except Exception as e:
                print(f"[X] Ошибка загрузки cookies: {e}")
        return False
    
    def _login(self, page):
        """Авторизация на X"""
        if not X_USERNAME or not X_PASSWORD:
            return False, "X_USERNAME или X_PASSWORD не настроены"
        
        try:
            print(f"[X] Авторизация как {X_USERNAME}...")
            page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            
            # Ввод username
            page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            page.fill('input[autocomplete="username"]', X_USERNAME)
            
            # Кнопка Next
            page.click('button:has-text("Next")')
            time.sleep(2)
            
            # Проверка на email/телефон
            try:
                email_input = page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000)
                if email_input and X_EMAIL:
                    email_input.fill(X_EMAIL)
                    page.click('button:has-text("Next")')
                    time.sleep(1)
            except:
                pass
            
            # Ввод пароля
            page.wait_for_selector('input[name="password"]', timeout=10000)
            page.fill('input[name="password"]', X_PASSWORD)
            
            # Кнопка Log in
            page.click('button[data-testid="LoginForm_Login_Button"]')
            
            # Ждём загрузки
            page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
            
            print("[X] Авторизация успешна!")
            return True, None
            
        except Exception as e:
            return False, f"Ошибка авторизации: {e}"
    
    def _ensure_browser(self, headless=True):
        """Запустить браузер и авторизоваться"""
        if not PLAYWRIGHT_AVAILABLE:
            return None, None, "Playwright не установлен"
        
        try:
            p = sync_playwright().start()
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            has_cookies = self._load_cookies(context)
            page = context.new_page()
            
            if not has_cookies:
                success, error = self._login(page)
                if not success:
                    browser.close()
                    return None, None, error
                self._save_cookies(context)
            else:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=20000)
                try:
                    page.wait_for_selector('[data-testid="primaryColumn"]', timeout=8000)
                    print("[X] Сессия валидна")
                except:
                    print("[X] Сессия протухла, переавторизация...")
                    success, error = self._login(page)
                    if not success:
                        browser.close()
                        return None, None, error
                    self._save_cookies(context)
            
            return page, browser, None
            
        except Exception as e:
            return None, None, f"Ошибка браузера: {e}"
    
    def _parse_tweet(self, article):
        """Парсит твит из article"""
        tweet = {
            "text": "",
            "author": "",
            "handle": "",
            "time": "",
            "replies": "0",
            "retweets": "0",
            "likes": "0",
            "url": "",
        }
        
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
        """Получить ленту твитов"""
        page, browser, error = self._ensure_browser()
        if error:
            return None, error
        
        try:
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
            
            self._save_cookies(browser.contexts[0])
            browser.close()
            return tweets[:limit], None
            
        except Exception as e:
            browser.close()
            return None, f"Ошибка: {e}"
    
    def search(self, query, limit=10):
        """Поиск по X"""
        page, browser, error = self._ensure_browser()
        if error:
            return None, error
        
        try:
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
            
            self._save_cookies(browser.contexts[0])
            browser.close()
            return tweets[:limit], None
            
        except Exception as e:
            browser.close()
            return None, f"Ошибка поиска: {e}"
    
    def get_trends(self):
        """Получить тренды"""
        page, browser, error = self._ensure_browser()
        if error:
            return None, error
        
        try:
            page.goto("https://x.com/explore", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('[data-testid="trend"]', timeout=15000)
            
            trends = []
            trend_elems = page.query_selector_all('[data-testid="trend"]')[:10]
            
            for elem in trend_elems:
                try:
                    text = elem.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if len(lines) >= 2:
                        trends.append({
                            "category": lines[0],
                            "topic": lines[1],
                            "posts": lines[2] if len(lines) > 2 else ""
                        })
                except:
                    pass
            
            self._save_cookies(browser.contexts[0])
            browser.close()
            return trends, None
            
        except Exception as e:
            browser.close()
            return None, f"Ошибка: {e}"
    
    def screenshot_tweet(self, tweet_url):
        """Скриншот твита"""
        page, browser, error = self._ensure_browser()
        if error:
            return None, error
        
        try:
            page.goto(tweet_url, wait_until="networkidle", timeout=30000)
            page.wait_for_selector("article", timeout=15000)
            
            article = page.query_selector("article")
            if article:
                path = f"{SCREENSHOT_DIR}/tweet_{int(time.time())}.png"
                article.screenshot(path=path)
                
                self._save_cookies(browser.contexts[0])
                browser.close()
                return path, None
            
            browser.close()
            return None, "Твит не найден"
            
        except Exception as e:
            browser.close()
            return None, f"Ошибка: {e}"


# ===== ГЛОБАЛЬНЫЙ ИНСТАНС =====
x_agent = XPlayAgent()


def register_x_play(bot):
    """Регистрирует X Play команды"""
    print("[XX] === REGISTER START ===")

    @bot.message_handler(commands=["x_login"])
    def x_login_command(message):
        """Проверить/выполнить авторизацию"""
        if not PLAYWRIGHT_AVAILABLE:
            bot.reply_to(message, "❌ Playwright не установлен")
            return
        
        if not X_USERNAME or not X_PASSWORD:
            bot.reply_to(message, 
                "❌ Настрой X_USERNAME и X_PASSWORD в переменных окружения\n\n"
                "На Render:\n"
                "X_USERNAME=your_login\n"
                "X_PASSWORD=your_password\n"
                "X_EMAIL=your_email (если 2FA)",
                parse_mode="HTML"
            )
            return
        
        bot.reply_to(message, f"🔐 Авторизация как {X_USERNAME}...")
        
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
        
        page, browser, error = x_agent._ensure_browser(headless=True)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        browser.close()
        bot.reply_to(message, "✅ Авторизация успешна! Cookies сохранены.")

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
        """Лента пользователя"""
        args = message.text.split()
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🐦 Загружаю ленту {'@' + username if username else 'Home'}...")
        
        tweets, error = x_agent.fetch_timeline(username, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        if not tweets:
            bot.reply_to(message, "📭 Твиты не найдены")
            return
        
        lines = [f"🐦 <b>Лента {'@' + username if username else 'Home'}</b>\n"]
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
        
        tweets, error = x_agent.search(query, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        if not tweets:
            bot.reply_to(message, "📭 Ничего не найдено")
            return
        
        lines = [f"🔍 <b>Поиск: {query}</b>\n"]
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:160]
            if len(t.get("text", "")) > 160:
                text += "..."
            
            lines.append(
                f"{i}. <b>{t.get('author', '')}</b> <code>{t.get('handle', '')}</code>\n"
                f"   <i>{text}</i>\n"
                f"   <a href='{t.get('url', '')}'>ссылка</a>\n"
            )
        
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(commands=["x_trends"])
    def x_trends_command(message):
        """Тренды X"""
        bot.reply_to(message, "📈 Загружаю тренды...")
        
        trends, error = x_agent.get_trends()
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        if not trends:
            bot.reply_to(message, "📭 Тренды не найдены")
            return
        
        lines = ["📈 <b>Тренды X</b>\n"]
        for i, t in enumerate(trends, 1):
            lines.append(
                f"{i}. <b>{t.get('topic', '—')}</b>\n"
                f"   <i>{t.get('category', '')}</i> {t.get('posts', '')}\n"
            )
        
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["x_screenshot"])
    def x_screenshot_command(message):
        """Скриншот твита"""
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи URL: <code>/x_screenshot https://x.com/user/status/123</code>", parse_mode="HTML")
            return
        
        url = args[1].strip()
        bot.reply_to(message, "📸 Делаю скриншот...")
        
        path, error = x_agent.screenshot_tweet(url)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        with open(path, "rb") as f:
            bot.send_photo(message.chat.id, f, caption="📸 Скриншот твита")

    @bot.message_handler(commands=["x_help"])
    def x_help_command(message):
        """Помощь"""
        msg = (
            "🐦 <b>X Agent — команды</b>\n\n"
            "🔐 <b>Авторизация</b>\n"
            "  /x_login — Проверить/обновить авторизацию\n\n"
            "📰 <b>Контент</b>\n"
            "  /x_timeline [user] [N] — Лента пользователя\n"
            "  /x_search [запрос] [N] — Поиск твитов\n"
            "  /x_trends — Тренды\n\n"
            "📸 <b>Скриншоты</b>\n"
            "  /x_screenshot [url] — Скриншот твита\n\n"
            f"Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌ не установлен'}\n"
            f"Логин: {'✅' if X_USERNAME else '❌ не настроен'}"
        )
        bot.reply_to(message, msg, parse_mode="HTML")

    print("[XX] === REGISTER END ===")
