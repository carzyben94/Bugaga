import os
import logging
import asyncio
import base64
import json
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

CHROME_PATH = '/usr/bin/chromium'

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

user_browsers = {}

# ==================== МОДЕЛИ ====================

class TweetMedia(ExtractionModel):
    """Модель медиа-вложения (фото и видео)"""
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

class Tweet(ExtractionModel):
    """Полная модель твита с фото"""
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )
    author_name: str = Field(
        selector='div[data-testid="User-Name"] span[dir="ltr"]:first-child',
        default="[имя не найдено]"
    )
    author_username: str = Field(
        selector='div[data-testid="User-Name"] span[dir="ltr"]:last-child',
        default="[никнейм не найден]"
    )
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
    link: str = Field(
        selector='a[href*="/status/"]',
        attribute='href',
        default="[ссылка не найдена]"
    )
    timestamp: str = Field(
        selector='time',
        attribute='datetime',
        default="[время не указано]"
    )
    media: list[TweetMedia] = Field(
        selector='[data-testid="tweetPhoto"], [data-testid="tweetVideo"]',
        default=[]
    )

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 *Бот для X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n"
        "/screen — Скриншот текущей страницы\n\n"
        "🔍 *Поиск*\n"
        "/search <текст> — Поиск твитов с фото"
    )
    await update.message.reply_text(menu, parse_mode='Markdown')

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

# ==================== СКРИНШОТ ====================

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        
        await asyncio.sleep(1)
        
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        url = await tab.current_url
        
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🖼️ Скриншот страницы\n📍 {url}"
        )
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ПОИСК ====================

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск твитов на X.com через extract с фото"""
    if not context.args:
        await update.message.reply_text("❌ Укажи текст для поиска\nПример: /search python")
        return
    
    query = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text(f"🔍 Ищу: {query}")
        
        _, tab = user_browsers[user_id]
        
        await tab.go_to(f'https://x.com/search?q={query}&src=typed_query')
        await asyncio.sleep(3)
        
        tweets = await tab.extract_all(
            Tweet,
            scope='article[data-testid="tweet"]',
            timeout=10
        )
        
        # Скриншот
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🔍 Результаты поиска: {query}"
        )
        
        if tweets:
            count = len(tweets)
            reply = f"📊 Найдено {count} твитов\n\n"
            
            for i, tweet in enumerate(tweets[:10], 1):
                # Текст
                text = tweet.text[:150] + '...' if len(tweet.text) > 150 else tweet.text
                reply += f"{i}. {text}\n"
                
                # Автор
                reply += f"   👤 @{tweet.author_username} ({tweet.author_name})\n"
                
                # Статистика
                if tweet.likes or tweet.retweets or tweet.replies:
                    likes = f"{tweet.likes:,}" if tweet.likes else "0"
                    retweets = f"{tweet.retweets:,}" if tweet.retweets else "0"
                    replies = f"{tweet.replies:,}" if tweet.replies else "0"
                    reply += f"   ❤️ {likes}  🔄 {retweets}  💬 {replies}\n"
                
                # Фото
                if tweet.media:
                    reply += f"   🖼️ {len(tweet.media)} фото/видео\n"
                    for media in tweet.media[:3]:
                        if media.url and media.url != "[ссылка не найдена]":
                            reply += f"      📎 {media.url}\n"
                    if len(tweet.media) > 3:
                        reply += f"      ... и ещё {len(tweet.media) - 3}\n"
                
                # Ссылка
                if tweet.link and tweet.link != "[ссылка не найдена]":
                    reply += f"   🔗 https://x.com{tweet.link}\n"
                
                reply += "\n"
            
            if count > 10:
                reply += f"... и ещё {count - 10} твитов"
            
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😕 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ОБРАБОТЧИК ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("search", search))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()