# x_play.py — X/Twitter агент через Playwright
import os
import time
import json
import re
from datetime import datetime
import telebot

# Playwright ставится отдельно: pip install playwright && playwright install chromium
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright не установлен. Установи: pip install playwright && playwright install chromium")

# Опционально: BeautifulSoup для парсинга
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


class XAgent:
    """Агент для работы с X/Twitter через Playwright"""
    
    def __init__(self):
        self.cookies_file = "x_cookies.json"
        self.screenshot_dir = "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)
    
    def _ensure_playwright(self):
        if not PLAYWRIGHT_AVAILABLE:
            return False, "Playwright не установлен. На Render: добавь в build command: 'playwright install chromium'"
        return True, None
    
    def _load_cookies(self, context):
        """Загрузить сохранённые cookies"""
        if os.path.exists(self.cookies_file):
            try:
                with open(self.cookies_file, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                return True
            except:
                pass
        return False
    
    def _save_cookies(self, context):
        """Сохранить cookies для повторного входа"""
        try:
            cookies = context.cookies()
            with open(self.cookies_file, "w") as f:
                json.dump(cookies, f)
        except:
            pass
    
    def fetch_timeline(self, username: str = None, limit: int = 10, headless: bool = True):
        """Получить ленту твитов"""
        ok, error = self._ensure_playwright()
        if not ok:
            return None, error
        
        url = f"https://x.com/{username}" if username else "https://x.com/home"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            # Загружаем cookies
            self._load_cookies(context)
            
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Ждём загрузки твитов
                page.wait_for_selector("article", timeout=15000)
                
                # Прокручиваем для подгрузки
                tweets = []
                last_height = 0
                
                while len(tweets) < limit:
                    # Получаем твиты
                    articles = page.query_selector_all("article")[:limit]
                    
                    for article in articles:
                        try:
                            tweet = self._parse_tweet(article)
                            if tweet and tweet not in tweets:
                                tweets.append(tweet)
                        except:
                            pass
                    
                    if len(tweets) >= limit:
                        break
                    
                    # Прокрутка
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1)
                    
                    # Проверяем, есть ли ещё контент
                    new_height = page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                
                # Сохраняем cookies
                self._save_cookies(context)
                
                browser.close()
                return tweets[:limit], None
                
            except PWTimeout:
                browser.close()
                return None, "Таймаут загрузки X. Возможно, требуется авторизация."
            except Exception as e:
                browser.close()
                return None, f"Ошибка: {e}"
    
    def _parse_tweet(self, article):
        """Парсит один твит из article элемента"""
        tweet = {
            "text": "",
            "author": "",
            "handle": "",
            "time": "",
            "replies": "0",
            "retweets": "0",
            "likes": "0",
            "views": "0",
            "url": "",
        }
        
        try:
            # Текст твита
            text_elem = article.query_selector("[data-testid='tweetText']")
            if text_elem:
                tweet["text"] = text_elem.inner_text()
            
            # Автор
            author_elem = article.query_selector("[data-testid='User-Name']")
            if author_elem:
                parts = author_elem.inner_text().split("\n")
                tweet["author"] = parts[0] if parts else ""
                tweet["handle"] = parts[1] if len(parts) > 1 else ""
            
            # Время
            time_elem = article.query_selector("time")
            if time_elem:
                tweet["time"] = time_elem.get_attribute("datetime") or ""
            
            # Статистика
            stats = article.query_selector_all("[data-testid$='count']")
            for stat in stats:
                aria = stat.get_attribute("aria-label") or ""
                if "reply" in aria.lower():
                    tweet["replies"] = self._extract_number(aria)
                elif "repost" in aria.lower() or "retweet" in aria.lower():
                    tweet["retweets"] = self._extract_number(aria)
                elif "like" in aria.lower():
                    tweet["likes"] = self._extract_number(aria)
            
            # Ссылка на твит
            link_elem = article.query_selector("a[href*='/status/']")
            if link_elem:
                href = link_elem.get_attribute("href")
                if href:
                    tweet["url"] = f"https://x.com{href}"
            
            return tweet
            
        except:
            return None
    
    def _extract_number(self, text):
        """Извлекает число из текста"""
        numbers = re.findall(r'[\d,]+', str(text))
        return numbers[0] if numbers else "0"
    
    def search(self, query: str, limit: int = 10, headless: bool = True):
        """Поиск по X"""
        ok, error = self._ensure_playwright()
        if not ok:
            return None, error
        
        encoded_query = query.replace(" ", "%20")
        url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            self._load_cookies(context)
            
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("article", timeout=15000)
                
                tweets = []
                attempts = 0
                
                while len(tweets) < limit and attempts < 5:
                    articles = page.query_selector_all("article")[:limit]
                    
                    for article in articles:
                        tweet = self._parse_tweet(article)
                        if tweet and tweet not in tweets:
                            tweets.append(tweet)
                    
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(1.5)
                    attempts += 1
                
                self._save_cookies(context)
                browser.close()
                return tweets[:limit], None
                
            except Exception as e:
                browser.close()
                return None, f"Ошибка поиска: {e}"
    
    def get_trending(self, headless: bool = True):
        """Получить тренды"""
        ok, error = self._ensure_playwright()
        if not ok:
            return None, error
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            self._load_cookies(context)
            
            page = context.new_page()
            
            try:
                page.goto("https://x.com/explore", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("[data-testid='trend']", timeout=15000)
                
                trends = []
                trend_elems = page.query_selector_all("[data-testid='trend']")[:10]
                
                for elem in trend_elems:
                    try:
                        text = elem.inner_text()
                        # Формат: "Трендинг\nТема\nPosts"
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        if len(lines) >= 2:
                            trends.append({
                                "category": lines[0],
                                "topic": lines[1],
                                "posts": lines[2] if len(lines) > 2 else ""
                            })
                    except:
                        pass
                
                self._save_cookies(context)
                browser.close()
                return trends, None
                
            except Exception as e:
                browser.close()
                return None, f"Ошибка: {e}"
    
    def screenshot_tweet(self, tweet_url: str, headless: bool = True):
        """Скриншот конкретного твита"""
        ok, error = self._ensure_playwright()
        if not ok:
            return None, error
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            self._load_cookies(context)
            
            page = context.new_page()
            
            try:
                page.goto(tweet_url, wait_until="networkidle", timeout=30000)
                page.wait_for_selector("article", timeout=15000)
                
                # Скриншот твита
                article = page.query_selector("article")
                if article:
                    screenshot_path = f"{self.screenshot_dir}/tweet_{int(time.time())}.png"
                    article.screenshot(path=screenshot_path)
                    
                    self._save_cookies(context)
                    browser.close()
                    return screenshot_path, None
                
                browser.close()
                return None, "Твит не найден"
                
            except Exception as e:
                browser.close()
                return None, f"Ошибка: {e}"
    
    def login_flow(self, username: str, password: str, headless: bool = False):
        """Процесс авторизации (для первого входа)"""
        ok, error = self._ensure_playwright()
        if not ok:
            return None, error
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            
            try:
                page.goto("https://x.com/i/flow/login", timeout=30000)
                
                # Ввод username
                page.wait_for_selector("input[name='text']", timeout=10000)
                page.fill("input[name='text']", username)
                page.click("//span[text()='Next']")
                
                # Ввод password
                page.wait_for_selector("input[name='password']", timeout=10000)
                page.fill("input[name='password']", password)
                page.click("//span[text()='Log in']")
                
                # Ждём загрузки
                page.wait_for_selector("[data-testid='primaryColumn']", timeout=15000)
                
                # Сохраняем cookies
                self._save_cookies(context)
                browser.close()
                
                return True, None
                
            except Exception as e:
                browser.close()
                return None, f"Ошибка авторизации: {e}"


# ===== ГЛОБАЛЬНЫЙ ИНСТАНС =====
x_agent = XAgent()


def register_x_play(bot):
    """Регистрирует X Play команды в боте"""

    @bot.message_handler(commands=["x_timeline"])
    def x_timeline_command(message):
        """Лента пользователя: /x_timeline [username] [limit]"""
        args = message.text.split()
        
        username = args[1] if len(args) > 1 else None
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🐦 Загружаю ленту {'@' + username if username else 'главную'}...")
        
        tweets, error = x_agent.fetch_timeline(username, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        if not tweets:
            bot.reply_to(message, "📭 Твиты не найдены")
            return
        
        lines = [f"🐦 <b>Лента {'@' + username if username else 'Home'}</b>\n"]
        
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:200]
            if len(t.get("text", "")) > 200:
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
        """Поиск по X: /x_search [запрос] [limit]"""
        args = message.text.split(maxsplit=2)
        
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи запрос: <code>/x_search python</code>", parse_mode="HTML")
            return
        
        query = args[1]
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5
        
        bot.reply_to(message, f"🔍 Ищу в X: <i>{query}</i>...", parse_mode="HTML")
        
        tweets, error = x_agent.search(query, limit)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        if not tweets:
            bot.reply_to(message, "📭 Ничего не найдено")
            return
        
        lines = [f"🔍 <b>Поиск: {query}</b>\n"]
        
        for i, t in enumerate(tweets, 1):
            text = t.get("text", "")[:180]
            if len(t.get("text", "")) > 180:
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
        
        trends, error = x_agent.get_trending()
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
        """Скриншот твита: /x_screenshot [url]"""
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажи URL твита: <code>/x_screenshot https://x.com/user/status/123</code>", parse_mode="HTML")
            return
        
        url = args[1].strip()
        bot.reply_to(message, "📸 Делаю скриншот...")
        
        path, error = x_agent.screenshot_tweet(url)
        if error:
            bot.reply_to(message, f"❌ {error}")
            return
        
        # Отправляем фото
        with open(path, "rb") as f:
            bot.send_photo(message.chat.id, f, caption=f"📸 Скриншот твита")

    @bot.message_handler(commands=["x_help"])
    def x_help_command(message):
        """Помощь по X Agent"""
        msg = (
            "🐦 <b>X Agent — команды</b>\n\n"
            "📰 <b>Лента</b>\n"
            "  /x_timeline [username] [N] — Лента пользователя\n"
            "  /x_timeline — Главная лента (требует авторизацию)\n\n"
            "🔍 <b>Поиск</b>\n"
            "  /x_search [запрос] [N] — Поиск твитов\n\n"
            "📈 <b>Тренды</b>\n"
            "  /x_trends — Тренды X\n\n"
            "📸 <b>Скриншоты</b>\n"
            "  /x_screenshot [url] — Скриншот твита\n\n"
            "⚠️ <b>На Render:</b>\n"
            "Добавь в build command:\n"
            "<code>playwright install chromium</code>"
        )
        bot.reply_to(message, msg, parse_mode="HTML")
