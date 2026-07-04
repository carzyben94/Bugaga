import os
import logging
import asyncio
import base64
import json
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ==================== МОДЕЛИ ====================

class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

class Author(ExtractionModel):
    name: str = Field(
        selector='div[data-testid="User-Name"] div[dir="ltr"] span:first-child',
        default="[имя не найдено]"
    )
    username: str = Field(
        selector='div[data-testid="User-Name"] div[dir="ltr"] span:last-child',
        default="[никнейм не найден]"
    )
    avatar: str = Field(
        selector='img[alt*="avatar"]',
        attribute='src',
        default="[аватар не найден]"
    )
    verified: bool = Field(
        selector='svg[aria-label="Verified account"]',
        default=False,
        transform=lambda x: True if x else False
    )

class TweetMedia(ExtractionModel):
    type: str = Field(
        selector='[data-testid="tweetPhoto"], [data-testid="tweetVideo"]',
        default="unknown"
    )
    url: str = Field(
        selector='img, video',
        attribute='src',
        default="[ссылка не найдена]"
    )
    alt: str = Field(
        selector='img',
        attribute='alt',
        default="[описание отсутствует]"
    )

class TweetStats(ExtractionModel):
    likes: int = Field(
        selector='div[data-testid="like"] span',
        default=0,
        transform=lambda x: int(x) if x else 0
    )
    retweets: int = Field(
        selector='div[data-testid="retweet"] span',
        default=0,
        transform=lambda x: int(x) if x else 0
    )
    replies: int = Field(
        selector='div[data-testid="reply"] span',
        default=0,
        transform=lambda x: int(x) if x else 0
    )
    views: int = Field(
        selector='div[data-testid="views"] span',
        default=0,
        transform=lambda x: int(x) if x else 0
    )

class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )
    author: Author = Field(
        selector='div[data-testid="User-Name"]'
    )
    media: list[TweetMedia] = Field(
        selector='[data-testid="tweetPhoto"], [data-testid="tweetVideo"]',
        default=[]
    )
    stats: TweetStats = Field(
        selector='div[role="group"]'
    )
    timestamp: str = Field(
        selector='time',
        attribute='datetime',
        default="[время не указано]"
    )
    link: str = Field(
        selector='a[href*="/status/"]',
        attribute='href',
        default="[ссылка не найдена]"
    )
    is_reply: bool = Field(
        selector='[data-testid="reply"]',
        default=False,
        transform=lambda x: True if x else False
    )
    is_retweet: bool = Field(
        selector='[data-testid="retweet"]',
        default=False,
        transform=lambda x: True if x else False
    )
    is_pinned: bool = Field(
        selector='[data-testid="pin"]',
        default=False,
        transform=lambda x: True if x else False
    )

CHROME_PATH = '/usr/bin/chromium'

# Куки для X.com
X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "0lyNYlKnbjXejqIk_blw2x20TfMRtW3SWJ_jmpay.t4-1783123617.0158947-1.0.1.1-1rnugK6C5Aw5r.126FQ3rJYZTCG2WhtPATFYO5Ip0QukW40cCR0qDNfacg6VRv3vRh3w.4Un_NQ6hOnxQfvhm68Grg1hZiLbF6HAyxvxzmS06Q8AzQkKu_i248B5sxj7", "domain": ".x.com", "path": "/"}
]

# Храним браузер и вкладку для каждого пользователя
user_browsers = {}

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu1 = (
        "🤖 *Бот для автоматизации X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n\n"
        "🔍 *Исследование*\n"
        "/explore_page — Полное исследование страницы\n"
        "/explore_selector <селектор> — Детально исследовать элемент\n\n"
        "⚡ *Универсальная команда*\n"
        "/do <запрос> — Всё в одной команде\n\n"
        "📌 *Продвинутые команды:* /start2"
    )
    await update.message.reply_text(menu1, parse_mode='Markdown')

async def start2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu2 = (
        "🌑 *Shadow DOM*\n"
        "/shadow <хост> <селектор> — Найти в Shadow DOM\n"
        "/shadow_all <хост> <селектор> — Найти все в Shadow DOM\n"
        "/shadow_click <хост> <селектор> — Кликнуть в Shadow DOM\n"
        "/shadow_type <хост> <селектор> <текст> — Ввести в Shadow DOM\n\n"
        "🌐 *Сеть*\n"
        "/network — Показать сетевые запросы\n"
        "/block_images — Блокировать изображения\n"
        "/unblock_images — Разблокировать изображения\n\n"
        "🍪 *Куки*\n"
        "/cookie {\"name\":\"value\"} — Установить куки\n\n"
        "⚡ *JavaScript*\n"
        "/eval <js> — Выполнить JavaScript\n\n"
        "📚 *Парсинг*\n"
        "/parse — Получить цитаты"
    )
    await update.message.reply_text(menu2, parse_mode='Markdown')

# ==================== АВТОРИЗАЦИЯ ====================

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        await tab.set_cookies(X_COOKIES)
        await asyncio.sleep(1)
        
        await tab.refresh()
        await asyncio.sleep(5)
        
        user_browsers[user_id] = (browser, tab)
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def extract_url(text):
    pattern = r'https?://(?:x\.com|twitter\.com)/[^\s]+'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def extract_username(text):
    pattern = r'@(\w+)'
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    words = text.split()
    for word in words:
        if word.startswith('@'):
            return word[1:]
    return None

def format_number(num):
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    return str(num)

# ==================== ИССЛЕДОВАНИЕ СТРАНИЦЫ ====================

async def explore_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное исследование страницы с сохранением в файл"""
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await update.message.reply_text("🔍 Исследую страницу...")
        
        # Получаем данные
        url = await tab.current_url
        title = await tab.title
        
        # Все data-testid через execute_script
        all_testids = await tab.execute_script("""
            (function() {
                const ids = new Set();
                document.querySelectorAll('[data-testid]').forEach(el => {
                    ids.add(el.dataset.testid);
                });
                return Array.from(ids);
            })()
        """)
        
        # Основные элементы
        main_selectors = [
            ('Твиты', 'article[data-testid="tweet"]'),
            ('Текст твита', 'div[data-testid="tweetText"]'),
            ('Автор', 'div[data-testid="User-Name"]'),
            ('Лайки', 'button[data-testid="like"]'),
            ('Ретвиты', 'button[data-testid="retweet"]'),
            ('Ответы', 'button[data-testid="reply"]'),
            ('Просмотры', 'div[data-testid="views"]'),
            ('Фото', 'div[data-testid="tweetPhoto"]'),
            ('Видео', 'div[data-testid="tweetVideo"]'),
            ('Кнопка "Написать"', 'a[data-testid="tweetButton"]'),
            ('Поиск', 'input[data-testid="SearchBox_Search_Input"]'),
            ('Кнопка поиска', 'button[data-testid="SearchBox_Search_Button"]'),
            ('Главная', 'a[data-testid="AppTabBar_Home_Link"]'),
            ('Explore', 'a[data-testid="AppTabBar_Explore_Link"]'),
            ('Уведомления', 'a[data-testid="AppTabBar_Notifications_Link"]'),
            ('Сообщения', 'a[data-testid="AppTabBar_Messages_Link"]'),
            ('Профиль', 'a[data-testid="AppTabBar_Profile_Link"]'),
            ('Подписчики', 'a[href*="/followers"]'),
            ('Подписки', 'a[href*="/following"]'),
        ]
        
        elements_info = {}
        for name, selector in main_selectors:
            try:
                count = await tab.execute_script(f"document.querySelectorAll('{selector}').length")
                if count > 0:
                    sample = await tab.execute_script(f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (!el) return '';
                            return el.innerText.substring(0, 100) || '';
                        }})()
                    """)
                    elements_info[name] = {
                        'selector': selector,
                        'count': count,
                        'sample': sample.strip() if sample else ''
                    }
            except:
                pass
        
        # Пример твита
        tweet_sample = await tab.execute_script("""
            (function() {
                const tweet = document.querySelector('article[data-testid="tweet"]');
                if (!tweet) return null;
                const text = tweet.querySelector('div[data-testid="tweetText"]')?.innerText || '';
                const author = tweet.querySelector('div[data-testid="User-Name"] span')?.innerText || '';
                const likes = tweet.querySelector('div[data-testid="like"] span')?.innerText || '0';
                const retweets = tweet.querySelector('div[data-testid="retweet"] span')?.innerText || '0';
                return { text: text.substring(0, 300), author, likes, retweets };
            })()
        """)
        
        # Фото — исправлено: find_all → query_all
        images = await tab.query_all('img[src*="media"]')
        image_urls = []
        for img in images[:10]:
            src = await img.get_attribute('src')
            if src:
                image_urls.append(src)
        
        # Формируем отчёт
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("🔍 ПОЛНОЕ ИССЛЕДОВАНИЕ СТРАНИЦЫ")
        report_lines.append("=" * 60)
        report_lines.append(f"\n📍 URL: {url}")
        report_lines.append(f"📄 Title: {title}")
        report_lines.append(f"🕐 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("📊 НАЙДЕННЫЕ ЭЛЕМЕНТЫ")
        report_lines.append("=" * 60)
        
        for name, data in elements_info.items():
            report_lines.append(f"\n• {name}:")
            report_lines.append(f"  Селектор: {data['selector']}")
            report_lines.append(f"  Количество: {data['count']}")
            if data.get('sample'):
                report_lines.append(f"  Пример: {data['sample'][:100]}...")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("📋 ВСЕ DATA-TESTID")
        report_lines.append("=" * 60)
        
        for i, tid in enumerate(all_testids, 1):
            report_lines.append(f"  {i}. {tid}")
        
        if tweet_sample:
            report_lines.append("\n" + "=" * 60)
            report_lines.append("📝 ПРИМЕР ТВИТА")
            report_lines.append("=" * 60)
            report_lines.append(f"\nТекст: {tweet_sample.get('text', '')}")
            report_lines.append(f"Автор: {tweet_sample.get('author', '')}")
            report_lines.append(f"Лайки: {tweet_sample.get('likes', '0')}")
            report_lines.append(f"Ретвиты: {tweet_sample.get('retweets', '0')}")
        
        if image_urls:
            report_lines.append("\n" + "=" * 60)
            report_lines.append("🖼️ НАЙДЕННЫЕ ФОТО")
            report_lines.append("=" * 60)
            for i, url in enumerate(image_urls, 1):
                report_lines.append(f"  {i}. {url}")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("💡 ИНСТРУКЦИЯ")
        report_lines.append("=" * 60)
        report_lines.append("\n  • Используй /explore_selector <селектор> для детального исследования")
        report_lines.append("  • Используй /do с найденными селекторами")
        report_lines.append("  • Используй /eval для проверки конкретных элементов")
        
        report_text = '\n'.join(report_lines)
        
        # Сохраняем в файл
        filename = f"explore_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        # Короткая версия для чата
        short_reply = f"🔍 *Исследование страницы*\n\n"
        short_reply += f"📍 URL: {url}\n"
        short_reply += f"📄 Title: {title}\n\n"
        
        if elements_info:
            short_reply += "📊 *Найдено элементов:*\n"
            for name, data in list(elements_info.items())[:10]:
                short_reply += f"  • {name}: {data['count']} шт.\n"
            if len(elements_info) > 10:
                short_reply += f"  ... и ещё {len(elements_info) - 10}\n"
        
        if all_testids:
            short_reply += f"\n📋 *Data-testid: {len(all_testids)} шт.*\n"
            for tid in all_testids[:10]:
                short_reply += f"  • `{tid}`\n"
            if len(all_testids) > 10:
                short_reply += f"  ... и ещё {len(all_testids) - 10}\n"
        
        short_reply += f"\n📁 *Файл с полным логом:* `{filename}`"
        
        await update.message.reply_text(short_reply, parse_mode='Markdown')
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📁 Полный лог исследования\n📍 {url}"
            )
        
        # Скриншот
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🖼️ Скриншот страницы"
        )
        
        try:
            os.remove(filename)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ИССЛЕДОВАНИЕ СЕЛЕКТОРА ====================

async def explore_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальное исследование конкретного элемента"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи селектор\n"
            "Пример: /explore_selector article[data-testid=\"tweet\"]"
        )
        return
    
    selector = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        # Проверяем существование через execute_script
        exists = await tab.execute_script(f"!!document.querySelector('{selector}')")
        if not exists:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            return
        
        # Получаем HTML
        html = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return 'Элемент не найден';
                return el.outerHTML.substring(0, 1500);
            }})()
        """)
        
        # Получаем все data-testid внутри
        testids = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                const ids = [];
                el.querySelectorAll('[data-testid]').forEach(el => {{
                    const id = el.dataset.testid;
                    if (!ids.includes(id)) ids.push(id);
                }});
                return ids;
            }})()
        """)
        
        # Получаем текст
        text = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return el.innerText.substring(0, 500);
            }})()
        """)
        
        # Получаем классы
        classes = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return el.className || '';
            }})()
        """)
        
        reply = f"🔍 *Исследование селектора:* `{selector}`\n\n"
        
        if classes:
            reply += f"📦 *Классы:* `{classes}`\n\n"
        
        if testids and len(testids) > 0:
            reply += "📋 *Найденные data-testid:*\n"
            for tid in testids[:20]:
                reply += f"  • `{tid}`\n"
            if len(testids) > 20:
                reply += f"  ... и ещё {len(testids) - 20}\n"
        
        if text:
            reply += f"\n📝 *Текст:*\n{text[:300]}..."
        
        await update.message.reply_text(reply, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== УНИВЕРСАЛЬНАЯ КОМАНДА /do ====================

async def do_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальная команда для любых действий"""
    if not context.args:
        await update.message.reply_text(
            "📋 *Что я умею:*\n\n"
            "👤 *Профили*\n"
            "  /do @username — профиль + фото\n"
            "  /do профиль @username — профиль + твиты\n\n"
            "🔍 *Поиск*\n"
            "  /do найти текст — поиск\n"
            "  /do текст — поиск по умолчанию\n\n"
            "❤️ *Действия с твитами*\n"
            "  /do лайк url — поставить лайк\n"
            "  /do ретвит url — ретвитнуть\n\n"
            "👥 *Подписки*\n"
            "  /do подпишись @username — подписаться\n"
            "  /do отпишись @username — отписаться\n\n"
            "🏠 *Навигация*\n"
            "  /do главная — на главную\n"
            "  /do тренды — на Explore\n"
            "  /do уведомления — в уведомления\n"
            "  /do сообщения — в сообщения\n"
            "  /do назад — назад\n"
            "  /do вперёд — вперёд\n\n"
            "📸 *Другое*\n"
            "  /do скриншот — скриншот",
            parse_mode='Markdown'
        )
        return
    
    full_text = ' '.join(context.args)
    action = context.args[0].lower()
    args = context.args[1:] if len(context.args) > 1 else []
    
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        # ПРОФИЛЬ С ТВИТАМИ
        if action in ['профиль', 'profile'] or 'профиль' in full_text:
            username = None
            for word in context.args:
                if word.startswith('@'):
                    username = word[1:]
                    break
                elif word not in ['профиль', 'profile']:
                    username = word
                    break
            
            if not username:
                await update.message.reply_text("❌ Укажи имя пользователя\nПример: /do профиль elonmusk")
                return
            
            await update.message.reply_text(f"👤 Загружаю профиль: @{username}")
            
            await tab.go_to(f'https://x.com/{username}')
            await asyncio.sleep(3)
            
            try:
                profile_name = await tab.execute_script(
                    "document.querySelector('div[data-testid=\"UserProfileHeader_Items\"] h2')?.innerText || 'Не найдено'"
                )
            except:
                profile_name = "Не найдено"
            
            tweets = await tab.extract_all(
                Tweet,
                scope='article[data-testid="tweet"]',
                timeout=10
            )
            
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            screenshot_bytes = base64.b64decode(screenshot_base64)
            
            reply = f"👤 *Профиль: @{username}*\n"
            reply += f"📛 Имя: {profile_name}\n\n"
            
            if tweets:
                reply += f"📊 *Первые {min(3, len(tweets))} твитов:*\n\n"
                for i, tweet in enumerate(tweets[:3], 1):
                    reply += f"*{i}. {tweet.text[:200]}*"
                    if len(tweet.text) > 200:
                        reply += "..."
                    reply += "\n"
                    reply += f"   👤 {tweet.author.name} (@{tweet.author.username})"
                    if tweet.author.verified:
                        reply += " ✅"
                    reply += "\n"
                    if tweet.timestamp and tweet.timestamp != "[время не указано]":
                        reply += f"   📅 {tweet.timestamp[:10]} {tweet.timestamp[11:16] if len(tweet.timestamp) > 10 else ''}\n"
                    if tweet.media:
                        reply += f"   🖼️ {len(tweet.media)} фото/видео\n"
                    if tweet.stats:
                        likes = format_number(tweet.stats.likes)
                        retweets = format_number(tweet.stats.retweets)
                        replies = format_number(tweet.stats.replies)
                        views = format_number(tweet.stats.views) if tweet.stats.views else 0
                        reply += f"   ❤️ {likes}  🔄 {retweets}  💬 {replies}"
                        if views:
                            reply += f"  👁️ {views}"
                        reply += "\n"
                    if tweet.is_reply:
                        reply += "   💬 Это ответ\n"
                    if tweet.is_retweet:
                        reply += "   🔄 Это ретвит\n"
                    if tweet.is_pinned:
                        reply += "   📌 Закреплённый твит\n"
                    if tweet.link and tweet.link != "[ссылка не найдена]":
                        reply += f"   🔗 https://x.com{tweet.link}\n"
                    reply += "\n"
            else:
                reply += "😕 Твиты не найдены\n"
            
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption=f"👤 Профиль: @{username}"
            )
            
            await update.message.reply_text(reply, parse_mode='Markdown')
            return
        
        # ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (@username)
        if action.startswith('@'):
            username = action[1:]
            await update.message.reply_text(f"👤 Перехожу в профиль: @{username}")
            
            await tab.go_to(f'https://x.com/{username}')
            await asyncio.sleep(3)
            
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            screenshot_bytes = base64.b64decode(screenshot_base64)
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption=f"👤 Профиль: @{username}"
            )
            
            await update.message.reply_text("📸 Ищу фото...")
            # Исправлено: find_all → query_all
            images = await tab.query_all('img[src*="media"]')
            
            if images:
                img_urls = []
                for img in images[:10]:
                    src = await img.get_attribute('src')
                    if src and src not in img_urls:
                        img_urls.append(src)
                
                await update.message.reply_text(f"📸 Найдено {len(img_urls)} фото")
                for url in img_urls[:5]:
                    await update.message.reply_text(f"🖼️ {url}")
                if len(img_urls) > 5:
                    await update.message.reply_text(f"... и ещё {len(img_urls) - 5} фото")
            else:
                await update.message.reply_text("😕 Фото не найдены")
            return
        
        # ЛАЙК
        if action in ['лайк', 'like']:
            url = extract_url(full_text)
            if not url:
                await update.message.reply_text("❌ Укажи ссылку на твит\nПример: /do лайк https://x.com/...")
                return
            
            await update.message.reply_text("❤️ Лайкаю твит...")
            await tab.go_to(url)
            await asyncio.sleep(2)
            
            like_btn = await tab.find('button[data-testid="like"]')
            if like_btn:
                await like_btn.click(humanize=True)
                await update.message.reply_text("✅ Лайк поставлен!")
            else:
                await update.message.reply_text("❌ Кнопка лайка не найдена")
            return
        
        # РЕТВИТ
        if action in ['ретвит', 'репост', 'retweet']:
            url = extract_url(full_text)
            if not url:
                await update.message.reply_text("❌ Укажи ссылку на твит\nПример: /do ретвит https://x.com/...")
                return
            
            await update.message.reply_text("🔄 Ретвичу...")
            await tab.go_to(url)
            await asyncio.sleep(2)
            
            retweet_btn = await tab.find('button[data-testid="retweet"]')
            if retweet_btn:
                await retweet_btn.click(humanize=True)
                await asyncio.sleep(1)
                confirm_btn = await tab.find('div[data-testid="retweetConfirm"]')
                if confirm_btn:
                    await confirm_btn.click()
                await update.message.reply_text("✅ Ретвит сделан!")
            else:
                await update.message.reply_text("❌ Кнопка ретвита не найдена")
            return
        
        # ПОДПИСАТЬСЯ
        if action in ['подпишись', 'follow']:
            username = extract_username(full_text)
            if not username:
                await update.message.reply_text("❌ Укажи имя пользователя\nПример: /do подпишись elonmusk")
                return
            
            await update.message.reply_text(f"👤 Подписываюсь на @{username}...")
            await tab.go_to(f'https://x.com/{username}')
            await asyncio.sleep(2)
            
            follow_btn = await tab.find('div[data-testid="follow"]')
            if follow_btn:
                await follow_btn.click(humanize=True)
                await update.message.reply_text(f"✅ Подписался на @{username}")
            else:
                await update.message.reply_text(f"❌ Кнопка подписки не найдена")
            return
        
        # ОТПИСАТЬСЯ
        if action in ['отпишись', 'unfollow']:
            username = extract_username(full_text)
            if not username:
                await update.message.reply_text("❌ Укажи имя пользователя\nПример: /do отпишись elonmusk")
                return
            
            await update.message.reply_text(f"👤 Отписываюсь от @{username}...")
            await tab.go_to(f'https://x.com/{username}')
            await asyncio.sleep(2)
            
            unfollow_btn = await tab.find('div[data-testid="unfollow"]')
            if unfollow_btn:
                await unfollow_btn.click(humanize=True)
                await asyncio.sleep(1)
                confirm_btn = await tab.find('div[data-testid="unfollowConfirm"]')
                if confirm_btn:
                    await confirm_btn.click()
                await update.message.reply_text(f"✅ Отписался от @{username}")
            else:
                await update.message.reply_text(f"❌ Кнопка отписки не найдена")
            return
        
        # НАВИГАЦИЯ
        if action in ['главная', 'home']:
            await tab.go_to('https://x.com/home')
            await update.message.reply_text("🏠 Перешёл на главную")
            return
        
        if action in ['тренды', 'explore']:
            await tab.go_to('https://x.com/explore')
            await update.message.reply_text("🔍 Перешёл на Explore")
            return
        
        if action in ['уведомления', 'notifications']:
            await tab.go_to('https://x.com/notifications')
            await update.message.reply_text("🔔 Перешёл в уведомления")
            return
        
        if action in ['сообщения', 'messages']:
            await tab.go_to('https://x.com/messages')
            await update.message.reply_text("✉️ Перешёл в сообщения")
            return
        
        # ПОИСК
        if action in ['найти', 'искать', 'поиск', 'search']:
            if not args:
                await update.message.reply_text("❌ Укажи что искать\nПример: /do найти новости")
                return
            query = ' '.join(args)
            await update.message.reply_text(f"🔍 Ищу: {query}")
            
            await tab.go_to(f'https://x.com/search?q={query}&src=typed_query')
            await asyncio.sleep(3)
            
            tweets = await tab.extract_all(Tweet, scope='article[data-testid="tweet"]', timeout=10)
            
            if tweets:
                count = len(tweets)
                reply = f"📊 Найдено {count} твитов\n\n"
                for i, tweet in enumerate(tweets[:10], 1):
                    text = tweet.text[:150] + '...' if len(tweet.text) > 150 else tweet.text
                    reply += f"{i}. {text}\n"
                    reply += f"   👤 {tweet.author.username}\n"
                    if tweet.stats:
                        likes = format_number(tweet.stats.likes)
                        retweets = format_number(tweet.stats.retweets)
                        replies = format_number(tweet.stats.replies)
                        reply += f"   ❤️ {likes}  🔄 {retweets}  💬 {replies}\n"
                    reply += "\n"
                if count > 10:
                    reply += f"... и ещё {count - 10} твитов"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("😕 Твиты не найдены")
            return
        
        # СКРИНШОТ
        if action in ['скриншот', 'скрин', 'screen', 'screenshot']:
            await update.message.reply_text("📸 Делаю скриншот...")
            await asyncio.sleep(1)
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            screenshot_bytes = base64.b64decode(screenshot_base64)
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption="🖼️ Скриншот страницы"
            )
            return
        
        # НАЗАД / ВПЕРЁД
        if action in ['назад', 'back']:
            await tab.go_back()
            await asyncio.sleep(2)
            await update.message.reply_text("⬅️ Назад")
            return
        
        if action in ['вперёд', 'forward']:
            await tab.go_forward()
            await asyncio.sleep(2)
            await update.message.reply_text("➡️ Вперёд")
            return
        
        # ОТКРЫТЬ URL
        if action in ['открой', 'open', 'перейди', 'go']:
            if not args:
                await update.message.reply_text("❌ Укажи URL\nПример: /do открой x.com")
                return
            url = args[0]
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await tab.go_to(url)
            await asyncio.sleep(2)
            await update.message.reply_text(f"🌐 Открыл: {url}")
            return
        
        # ПОИСК ПО УМОЛЧАНИЮ
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Ищу: {query}")
        
        await tab.go_to(f'https://x.com/search?q={query}&src=typed_query')
        await asyncio.sleep(3)
        
        tweets = await tab.extract_all(Tweet, scope='article[data-testid="tweet"]', timeout=10)
        
        if tweets:
            count = len(tweets)
            reply = f"📊 Найдено {count} твитов\n\n"
            for i, tweet in enumerate(tweets[:10], 1):
                text = tweet.text[:150] + '...' if len(tweet.text) > 150 else tweet.text
                reply += f"{i}. {text}\n"
                reply += f"   👤 {tweet.author.username}\n"
                if tweet.stats:
                    likes = format_number(tweet.stats.likes)
                    retweets = format_number(tweet.stats.retweets)
                    replies = format_number(tweet.stats.replies)
                    reply += f"   ❤️ {likes}  🔄 {retweets}  💬 {replies}\n"
                reply += "\n"
            if count > 10:
                reply += f"... и ещё {count - 10} твитов"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😕 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== SHADOW DOM ====================

async def shadow_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Укажи хост-селектор и селектор для Shadow DOM\n"
            "Пример: /shadow #movie_player .play-btn"
        )
        return
    
    host_selector = context.args[0]
    shadow_selector = context.args[1]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        host_element = await tab.find(host_selector)
        if not host_element:
            await update.message.reply_text(f"❌ Хост-элемент не найден: {host_selector}")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text(f"❌ Shadow DOM не найден в {host_selector}")
            return
        
        element = await shadow_root.query(shadow_selector)
        if element:
            text = await element.text()
            await update.message.reply_text(f"✅ Найден элемент в Shadow DOM:\n\n{text[:500]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {shadow_selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_find_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Укажи хост-селектор и селектор для Shadow DOM\n"
            "Пример: /shadow_all #movie_player .item"
        )
        return
    
    host_selector = context.args[0]
    shadow_selector = context.args[1]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        host_element = await tab.find(host_selector)
        if not host_element:
            await update.message.reply_text(f"❌ Хост-элемент не найден: {host_selector}")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text(f"❌ Shadow DOM не найден в {host_selector}")
            return
        
        elements = await shadow_root.query_all(shadow_selector)
        if elements:
            count = len(elements)
            reply = f"✅ Найдено {count} элементов в Shadow DOM:\n\n"
            for i, element in enumerate(elements[:5], 1):
                try:
                    text = await element.text()
                    reply += f"{i}. {text[:100]}\n"
                except:
                    reply += f"{i}. [не удалось получить текст]\n"
            if count > 5:
                reply += f"\n... и ещё {count - 5} элементов"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(f"❌ Элементы не найдены в Shadow DOM: {shadow_selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Укажи хост-селектор и селектор для Shadow DOM\n"
            "Пример: /shadow_click #movie_player .play-btn"
        )
        return
    
    host_selector = context.args[0]
    shadow_selector = context.args[1]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        host_element = await tab.find(host_selector)
        if not host_element:
            await update.message.reply_text(f"❌ Хост-элемент не найден: {host_selector}")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text(f"❌ Shadow DOM не найден в {host_selector}")
            return
        
        element = await shadow_root.query(shadow_selector)
        if element:
            await element.click(humanize=True)
            await update.message.reply_text(f"✅ Кликнул по элементу в Shadow DOM: {shadow_selector}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {shadow_selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Укажи хост-селектор, селектор и текст\n"
            "Пример: /shadow_type #movie_player .input hello"
        )
        return
    
    host_selector = context.args[0]
    shadow_selector = context.args[1]
    text = ' '.join(context.args[2:])
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        host_element = await tab.find(host_selector)
        if not host_element:
            await update.message.reply_text(f"❌ Хост-элемент не найден: {host_selector}")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text(f"❌ Shadow DOM не найден в {host_selector}")
            return
        
        element = await shadow_root.query(shadow_selector)
        if element:
            await element.click(humanize=True)
            await asyncio.sleep(0.5)
            await element.type_text(text, humanize=True)
            await update.message.reply_text(f"✅ Ввёл текст в Shadow DOM: {text[:50]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {shadow_selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== СЕТЬ ====================

async def network_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        await update.message.reply_text("🌐 Получаю сетевые запросы...")
        _, tab = user_browsers[user_id]
        
        # По документации: enable_network_events
        await tab.enable_network_events()
        logs = await tab.get_network_logs()
        
        if logs:
            reply = "🌐 Последние сетевые запросы:\n\n"
            for i, log in enumerate(logs[:10], 1):
                url = log.get('url', 'неизвестно')[:80]
                status = log.get('status', '???')
                method = log.get('method', '???')
                reply += f"{i}. {method} {status} — {url}\n"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("📊 Сетевых запросов не найдено")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def block_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await tab.enable_network_events()
        await tab.set_request_interception(
            patterns=[{'urlPattern': '*.jpg', 'interceptionStage': 'Request'}, 
                     {'urlPattern': '*.png', 'interceptionStage': 'Request'},
                     {'urlPattern': '*.gif', 'interceptionStage': 'Request'},
                     {'urlPattern': '*.webp', 'interceptionStage': 'Request'}],
            handle=True
        )
        await update.message.reply_text("✅ Изображения заблокированы")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def unblock_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await tab.disable_network_events()
        await update.message.reply_text("✅ Изображения разблокированы")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== КУКИ ====================

async def cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Передай JSON с куками\n"
            "Пример: /cookie {\"auth_token\":\"123\",\"ct0\":\"456\"}"
        )
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        json_str = ' '.join(context.args)
        cookies_data = json.loads(json_str)
        cookies_list = [{"name": name, "value": value} for name, value in cookies_data.items()]
        await tab.set_cookies(cookies_list)
        await update.message.reply_text(f"✅ Установлено {len(cookies_list)} кук!")
        
    except json.JSONDecodeError:
        await update.message.reply_text(
            "❌ Неправильный JSON формат\n"
            "Пример: /cookie {\"auth_token\":\"123\",\"ct0\":\"456\"}"
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ПАРСИНГ ====================

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Начинаю парсинг...")
    
    try:
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        async with Chrome(options=options) as browser:
            tab = await browser.start()
            await tab.go_to('https://quotes.toscrape.com')
            await asyncio.sleep(3)
            
            quotes = await tab.extract_all(Quote, scope=".quote", timeout=10)
            
            if quotes:
                reply = "📚 Цитаты:\n\n"
                for i, q in enumerate(quotes[:5], 1):
                    reply += f"{i}. \"{q.text}\"\n   — {q.author}\n   🏷️ {q.tags}\n\n"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("😕 Ничего не найдено")
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== EVAL ====================

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи JS код\n"
            "Пример: /eval document.title"
        )
        return
    
    js_code = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        result = await tab.execute_script(js_code)
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ОБРАБОТЧИК ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Меню
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("start2", start2))
    
    # Авторизация
    application.add_handler(CommandHandler("login", login))
    
    # Исследование
    application.add_handler(CommandHandler("explore_page", explore_page))
    application.add_handler(CommandHandler("explore_selector", explore_selector))
    
    # Универсальная команда
    application.add_handler(CommandHandler("do", do_action))
    
    # Shadow DOM
    application.add_handler(CommandHandler("shadow", shadow_find))
    application.add_handler(CommandHandler("shadow_all", shadow_find_all))
    application.add_handler(CommandHandler("shadow_click", shadow_click))
    application.add_handler(CommandHandler("shadow_type", shadow_type))
    
    # Сеть
    application.add_handler(CommandHandler("network", network_logs))
    application.add_handler(CommandHandler("block_images", block_images))
    application.add_handler(CommandHandler("unblock_images", unblock_images))
    
    # Куки и парсинг
    application.add_handler(CommandHandler("cookie", cookie))
    application.add_handler(CommandHandler("eval", evaluate_js))
    application.add_handler(CommandHandler("parse", parse))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()