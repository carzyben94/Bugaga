import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import PageLoadState, Key
from pydoll.decorators import retry
from pydoll.exceptions import ElementNotFound, WaitElementTimeout, NetworkError
from pydoll.extractor import ExtractionModel, Field

# Импортируем модуль с куками
from cookies import get_cookies_for_domain, format_cookies_for_cdp

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ============================================================
# 1. НАСТРОЙКА БРАУЗЕРА
# ============================================================

def get_optimized_options(user_data_dir: Optional[str] = None) -> ChromiumOptions:
    options = ChromiumOptions()
    
    options.binary_location = "/usr/bin/google-chrome"
    options.headless = True
    options.add_argument('--headless=new')
    options.start_timeout = 15
    options.page_load_state = PageLoadState.INTERACTIVE
    
    if user_data_dir:
        options.add_argument(f'--user-data-dir={user_data_dir}')
    
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--use-gl=swiftshader')
    options.add_argument('--lang=en-US')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    options.browser_preferences = {
        'profile': {
            'default_content_setting_values': {
                'notifications': 2,
                'geolocation': 2,
            }
        }
    }
    
    options.webrtc_leak_protection = True
    return options


# ============================================================
# 2. ФУНКЦИЯ ДЛЯ УСТАНОВКИ КУК ЧЕРЕЗ CDP
# ============================================================

async def set_cookies_via_cdp(tab, domain: str = "x.com") -> bool:
    """
    Устанавливает куки через CDP команду Network.setCookies
    """
    try:
        cookies = get_cookies_for_domain(domain)
        if not cookies:
            logger.warning(f"❌ Нет кук для домена {domain}")
            return False
        
        # Форматируем куки для CDP
        cookies_list = format_cookies_for_cdp(cookies)
        
        # Отправляем CDP команду
        await tab.send("Network.setCookies", {
            "cookies": cookies_list  # все 11 кук одной командой
        })
        
        logger.info(f"✅ Установлено {len(cookies_list)} кук для {domain} через CDP")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка установки кук: {e}")
        return False


# ============================================================
# 3. ФУНКЦИЯ ДЛЯ ПРОВЕРКИ АВТОРИЗАЦИИ
# ============================================================

async def ensure_x_session(tab) -> bool:
    """
    Гарантирует авторизованную сессию X.com через куки
    """
    # Переходим на X.com
    await tab.go_to('https://x.com/home')
    await asyncio.sleep(3)
    
    # Устанавливаем куки через CDP
    if await set_cookies_via_cdp(tab, "x.com"):
        # Перезагружаем страницу после установки кук
        await tab.refresh()
        await asyncio.sleep(3)
        
        # Проверяем, авторизованы ли
        current_url = await tab.current_url
        if 'home' in current_url or 'x.com/home' in current_url:
            logger.info("✅ Авторизован через куки")
            return True
        else:
            logger.warning("⚠️ Куки установлены, но авторизация не подтверждена")
            return False
    else:
        logger.error("❌ Не удалось установить куки")
        return False


# ============================================================
# 4. МОДЕЛИ ДЛЯ ПАРСИНГА X.COM
# ============================================================

class TweetModel(ExtractionModel):
    """Модель для парсинга твита"""
    text: str = Field(selector='div[data-testid="tweetText"]', description='Текст твита')
    author_name: str = Field(selector='div[data-testid="User-Name"] a span', description='Имя автора')
    author_username: str = Field(selector='div[data-testid="User-Name"] a span[dir="ltr"]', description='Username')
    timestamp: str = Field(selector='time', attribute='datetime', description='Время')
    likes: str = Field(selector='button[data-testid="like"] span', description='Лайки')
    retweets: str = Field(selector='button[data-testid="retweet"] span', description='Ретвиты')
    replies: str = Field(selector='button[data-testid="reply"] span', description='Ответы')
    views: str = Field(selector='span[data-testid="views"] span', description='Просмотры')


class ProfileModel(ExtractionModel):
    """Модель для парсинга профиля"""
    name: str = Field(selector='div[data-testid="UserName"] span', description='Имя')
    username: str = Field(selector='div[data-testid="UserName"] span[dir="ltr"]', description='Username')
    bio: str = Field(selector='div[data-testid="UserDescription"]', description='Биография')
    location: str = Field(selector='span[data-testid="UserLocation"]', description='Локация')
    joined: str = Field(selector='span[data-testid="UserJoinDate"]', description='Дата регистрации')
    followers: str = Field(selector='a[href$="/followers"] span', description='Подписчики')
    following: str = Field(selector='a[href$="/following"] span', description='Подписки')


# ============================================================
# 5. ФУНКЦИИ ДЛЯ РАБОТЫ С X.COM
# ============================================================

async def post_tweet(text: str) -> bool:
    """
    Публикация твита
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        
        if not await ensure_x_session(tab):
            return False
        
        # Нажимаем кнопку "Написать твит"
        tweet_btn = await tab.find(css_selector='button[data-testid="tweetButtonInline"]', timeout=10)
        await tweet_btn.click(humanize=True)
        await asyncio.sleep(1)
        
        # Находим поле ввода
        textarea = await tab.find(css_selector='div[data-testid="tweetTextarea_0"]', timeout=10)
        await textarea.click(humanize=True)
        await textarea.type_text(text, humanize=True)
        await asyncio.sleep(1)
        
        # Отправляем
        submit_btn = await tab.find(css_selector='button[data-testid="tweetButton"]', timeout=10)
        await submit_btn.click(humanize=True)
        await asyncio.sleep(3)
        
        logger.info(f"✅ Твит опубликован: {text[:50]}...")
        return True


async def reply_to_tweet(tweet_url: str, text: str) -> bool:
    """
    Ответ на твит
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(tweet_url)
        
        if not await ensure_x_session(tab):
            return False
        
        # Нажимаем кнопку "Ответить"
        reply_btn = await tab.find(css_selector='button[data-testid="reply"]', timeout=10)
        await reply_btn.click(humanize=True)
        await asyncio.sleep(1)
        
        # Находим поле ввода ответа
        textarea = await tab.find(css_selector='div[data-testid="tweetTextarea_0"]', timeout=10)
        await textarea.type_text(text, humanize=True)
        await asyncio.sleep(1)
        
        # Отправляем
        submit_btn = await tab.find(css_selector='button[data-testid="tweetButton"]', timeout=10)
        await submit_btn.click(humanize=True)
        await asyncio.sleep(3)
        
        logger.info(f"✅ Ответ опубликован: {text[:50]}...")
        return True


async def like_tweet(tweet_url: str) -> bool:
    """
    Поставить лайк
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(tweet_url)
        
        if not await ensure_x_session(tab):
            return False
        
        like_btn = await tab.find(css_selector='button[data-testid="like"]', timeout=10)
        await like_btn.click(humanize=True)
        await asyncio.sleep(1)
        
        logger.info(f"✅ Лайк поставлен: {tweet_url}")
        return True


async def retweet_tweet(tweet_url: str) -> bool:
    """
    Сделать ретвит
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(tweet_url)
        
        if not await ensure_x_session(tab):
            return False
        
        # Нажимаем кнопку ретвита
        retweet_btn = await tab.find(css_selector='button[data-testid="retweet"]', timeout=10)
        await retweet_btn.click(humanize=True)
        await asyncio.sleep(1)
        
        # Подтверждаем ретвит
        confirm_btn = await tab.find(css_selector='button[data-testid="retweetConfirm"]', timeout=10)
        await confirm_btn.click(humanize=True)
        await asyncio.sleep(2)
        
        logger.info(f"✅ Ретвит сделан: {tweet_url}")
        return True


async def get_profile(username: str) -> dict:
    """
    Получить информацию о профиле
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(f'https://x.com/{username}')
        
        if not await ensure_x_session(tab):
            return {}
        
        await asyncio.sleep(3)
        
        # Парсим профиль
        profiles = await tab.extract_all(ProfileModel, scope='div[data-testid="primaryColumn"]', timeout=10)
        
        if profiles:
            return profiles[0].model_dump()
        return {}


async def get_timeline(username: str, limit: int = 10) -> list[dict]:
    """
    Получить последние твиты пользователя
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(f'https://x.com/{username}')
        
        if not await ensure_x_session(tab):
            return []
        
        await asyncio.sleep(3)
        
        # Скроллим для подгрузки
        for _ in range(3):
            await tab.execute_script("window.scrollBy(0, 800);")
            await asyncio.sleep(2)
        
        tweets = await tab.extract_all(
            TweetModel,
            scope='article[data-testid="tweet"]',
            timeout=10
        )
        
        return [t.model_dump() for t in tweets[:limit]]


async def search_tweets(query: str, limit: int = 10) -> list[dict]:
    """
    Поиск твитов по запросу
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(f'https://x.com/search?q={query}')
        
        if not await ensure_x_session(tab):
            return []
        
        await asyncio.sleep(3)
        
        # Скроллим для подгрузки
        for _ in range(3):
            await tab.execute_script("window.scrollBy(0, 800);")
            await asyncio.sleep(2)
        
        tweets = await tab.extract_all(
            TweetModel,
            scope='article[data-testid="tweet"]',
            timeout=10
        )
        
        return [t.model_dump() for t in tweets[:limit]]


async def follow_user(username: str) -> bool:
    """
    Подписаться на пользователя
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(f'https://x.com/{username}')
        
        if not await ensure_x_session(tab):
            return False
        
        # Находим кнопку "Подписаться"
        follow_btn = await tab.find(css_selector='button[data-testid="follow"]', timeout=10)
        await follow_btn.click(humanize=True)
        await asyncio.sleep(2)
        
        logger.info(f"✅ Подписан на @{username}")
        return True


async def unfollow_user(username: str) -> bool:
    """
    Отписаться от пользователя
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(f'https://x.com/{username}')
        
        if not await ensure_x_session(tab):
            return False
        
        # Находим кнопку "Отписаться"
        unfollow_btn = await tab.find(css_selector='button[data-testid="unfollow"]', timeout=10)
        await unfollow_btn.click(humanize=True)
        await asyncio.sleep(1)
        
        # Подтверждаем
        confirm_btn = await tab.find(css_selector='button[data-testid="unfollowConfirm"]', timeout=5)
        await confirm_btn.click(humanize=True)
        await asyncio.sleep(2)
        
        logger.info(f"✅ Отписан от @{username}")
        return True