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

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 *Бот для X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n"
        "/screen — Скриншот текущей страницы\n\n"
        "🤖 *Умный агент*\n"
        "/agent <команда> — ИИ-агент для X.com\n\n"
        "📝 *Примеры команд:*\n"
        "  /agent найди профиль илона маска\n"
        "  /agent фото бреда питта\n"
        "  /agent твиты илона маска\n"
        "  /agent подписчики илона маска\n"
        "  /agent лайк — лайкнуть твит\n"
        "  /agent главная — на главную\n\n"
        "⚡ *JavaScript*\n"
        "/eval <js> — Выполнить JavaScript"
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
    """Делает скриншот текущей страницы"""
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

# ==================== УМНЫЙ АГЕНТ ====================

async def agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Умный агент для X.com — поиск через X.com"""
    if not context.args:
        await update.message.reply_text(
            "🤖 *Агент X.com*\n\n"
            "Примеры команд:\n"
            "  /agent найди профиль илона маска — найти профиль\n"
            "  /agent фото бреда питта — найти фото\n"
            "  /agent твиты илона маска — найти твиты\n"
            "  /agent подписчики илона маска — подписчики\n"
            "  /agent лайк — лайкнуть твит\n"
            "  /agent главная — на главную",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await update.message.reply_text("🤔 Думаю...")
        
        cmd = command.lower()
        
        # ===== НАЙТИ ПРОФИЛЬ =====
        if any(w in cmd for w in ['найди профиль', 'найти профиль', 'профиль']):
            query = re.sub(r'(найди|найти)?\s*профиль\s*', '', cmd).strip()
            if query:
                await tab.execute_script(f"window.location.href = 'https://x.com/search?q={query}&src=typed_query'")
                await asyncio.sleep(3)
                
                first_profile = await tab.execute_script("""
                    (function() {
                        const links = document.querySelectorAll('a[href*="/"][role="link"]');
                        for (const link of links) {
                            const href = link.getAttribute('href');
                            if (href && href.startsWith('/') && !href.includes('search') && !href.includes('explore')) {
                                const username = href.replace('/', '');
                                if (username && username.length > 1) {
                                    return username;
                                }
                            }
                        }
                        return null;
                    })()
                """)
                
                if first_profile:
                    await tab.execute_script(f"window.location.href = 'https://x.com/{first_profile}'")
                    await asyncio.sleep(2)
                    
                    name = await tab.execute_script(
                        "document.querySelector('div[data-testid=\"UserProfileHeader_Items\"] h2')?.innerText || 'Не найдено'"
                    )
                    followers = await tab.execute_script(
                        "document.querySelector('a[href*=\"/followers\"] span')?.innerText || '0'"
                    )
                    tweets_count = await tab.execute_script(
                        "document.querySelectorAll('article[data-testid=\"tweet\"]').length"
                    )
                    
                    await update.message.reply_text(
                        f"👤 *Найден профиль*\n\n"
                        f"📛 Имя: {name}\n"
                        f"🔗 @{first_profile}\n"
                        f"👥 Подписчиков: {followers}\n"
                        f"📝 Твитов на странице: {tweets_count}\n\n"
                        f"✅ Перешёл в профиль @{first_profile}"
                    )
                else:
                    await update.message.reply_text(f"😕 Не найден профиль по запросу: {query}")
                return
        
        # ===== ФОТО =====
        if 'фото' in cmd or 'photo' in cmd or 'картинки' in cmd:
            query = re.sub(r'(фото|photo|картинки|найди|покажи|найти)', '', cmd).strip()
            
            if query:
                await tab.execute_script(f"window.location.href = 'https://x.com/search?q={query} filter:images&src=typed_query'")
                await asyncio.sleep(3)
                
                images = await tab.execute_script("""
                    (function() {
                        const imgs = document.querySelectorAll('img[src*="media"]');
                        const urls = [];
                        imgs.forEach(img => {
                            const src = img.src;
                            if (src && !urls.includes(src)) urls.push(src);
                        });
                        return urls;
                    })()
                """)
                
                if images and len(images) > 0:
                    reply = f"🔍 Ищу: {query}\n\n📸 Найдено {len(images)} фото:\n"
                    for i, url in enumerate(images[:10], 1):
                        reply += f"  {i}. {url}\n"
                    if len(images) > 10:
                        reply += f"  ... и ещё {len(images) - 10} фото"
                    await update.message.reply_text(reply)
                else:
                    await update.message.reply_text(f"😕 Не найдено фото по запросу: {query}")
                return
        
        # ===== ТВИТЫ =====
        if 'твиты' in cmd or 'tweets' in cmd:
            query = re.sub(r'(твиты|tweets|найди|показать)', '', cmd).strip()
            if query:
                await tab.execute_script(f"window.location.href = 'https://x.com/search?q={query}&src=typed_query'")
                await asyncio.sleep(3)
                
                tweets = await tab.execute_script("""
                    (function() {
                        const tweets = document.querySelectorAll('div[data-testid="tweetText"]');
                        const result = [];
                        tweets.forEach(tweet => {
                            const text = tweet.innerText;
                            if (text && text.length > 0) {
                                result.push(text.substring(0, 150));
                            }
                        });
                        return result;
                    })()
                """)
                
                if tweets and len(tweets) > 0:
                    reply = f"🔍 Твиты по запросу: {query}\n\n📝 Найдено {len(tweets)} твитов:\n"
                    for i, tweet in enumerate(tweets[:5], 1):
                        reply += f"  {i}. {tweet}...\n"
                    if len(tweets) > 5:
                        reply += f"  ... и ещё {len(tweets) - 5} твитов"
                    await update.message.reply_text(reply)
                else:
                    await update.message.reply_text(f"😕 Не найдено твитов по запросу: {query}")
                return
        
        # ===== ПОДПИСЧИКИ =====
        if 'подписчики' in cmd or 'followers' in cmd:
            query = re.sub(r'(подписчики|followers)', '', cmd).strip()
            if query:
                await tab.execute_script(f"window.location.href = 'https://x.com/search?q={query}&src=typed_query'")
                await asyncio.sleep(3)
                
                first_profile = await tab.execute_script("""
                    (function() {
                        const links = document.querySelectorAll('a[href*="/"][role="link"]');
                        for (const link of links) {
                            const href = link.getAttribute('href');
                            if (href && href.startsWith('/') && !href.includes('search')) {
                                return href.replace('/', '');
                            }
                        }
                        return null;
                    })()
                """)
                
                if first_profile:
                    await tab.execute_script(f"window.location.href = 'https://x.com/{first_profile}'")
                    await asyncio.sleep(2)
                    
                    followers = await tab.execute_script(
                        "document.querySelector('a[href*=\"/followers\"] span')?.innerText || '0'"
                    )
                    
                    await update.message.reply_text(
                        f"👥 *Подписчики @{first_profile}*\n\n"
                        f"📊 {followers} подписчиков"
                    )
                else:
                    await update.message.reply_text(f"😕 Не найден профиль по запросу: {query}")
                return
        
        # ===== НАВИГАЦИЯ =====
        if any(w in cmd for w in ['главная', 'home', 'лента']):
            await tab.execute_script("window.location.href = 'https://x.com/home'")
            await update.message.reply_text("🏠 Перешёл на главную")
            return
        
        if any(w in cmd for w in ['explore', 'тренды', 'популярное']):
            await tab.execute_script("window.location.href = 'https://x.com/explore'")
            await update.message.reply_text("🔍 Перешёл на Explore")
            return
        
        if any(w in cmd for w in ['уведомления', 'notifications']):
            await tab.execute_script("window.location.href = 'https://x.com/notifications'")
            await update.message.reply_text("🔔 Перешёл в уведомления")
            return
        
        if any(w in cmd for w in ['сообщения', 'messages']):
            await tab.execute_script("window.location.href = 'https://x.com/messages'")
            await update.message.reply_text("✉️ Перешёл в сообщения")
            return
        
        # ===== ДЕЙСТВИЯ =====
        if 'лайк' in cmd:
            if 'все' in cmd:
                await tab.execute_script("document.querySelectorAll('button[data-testid=\"like\"]').forEach(btn => btn.click())")
                await update.message.reply_text("❤️ Лайкнул все твиты")
            else:
                await tab.execute_script("document.querySelector('button[data-testid=\"like\"]')?.click()")
                await update.message.reply_text("❤️ Лайк поставлен")
            return
        
        if 'ретвит' in cmd or 'репост' in cmd:
            await tab.execute_script("document.querySelector('button[data-testid=\"retweet\"]')?.click()")
            await update.message.reply_text("🔄 Ретвит сделан")
            return
        
        if 'подпишись' in cmd or 'follow' in cmd:
            await tab.execute_script("document.querySelector('div[data-testid=\"follow\"]')?.click()")
            await update.message.reply_text("✅ Подписался")
            return
        
        if 'отпишись' in cmd or 'unfollow' in cmd:
            await tab.execute_script("document.querySelector('div[data-testid=\"unfollow\"]')?.click()")
            await update.message.reply_text("✅ Отписался")
            return
        
        # ===== ПОИСК =====
        if any(w in cmd for w in ['найти', 'search', 'поиск', 'искать']):
            query = re.sub(r'(найти|search|поиск|искать)', '', cmd).strip()
            if query:
                await tab.execute_script(f"window.location.href = 'https://x.com/search?q={query}&src=typed_query'")
                await asyncio.sleep(2)
                
                tweets_count = await tab.execute_script(
                    "document.querySelectorAll('article[data-testid=\"tweet\"]').length"
                )
                
                await update.message.reply_text(
                    f"🔍 Ищу: {query}\n"
                    f"✅ Перешёл на страницу поиска\n"
                    f"📊 Найдено твитов: {tweets_count}"
                )
                return
        
        # ===== ИНФОРМАЦИЯ =====
        if any(w in cmd for w in ['подписчики', 'followers']):
            count = await tab.execute_script("document.querySelector('a[href*=\"/followers\"] span')?.innerText || '0'")
            await update.message.reply_text(f"👥 Подписчиков: {count}")
            return
        
        if any(w in cmd for w in ['твиты', 'tweets']):
            count = await tab.execute_script("document.querySelectorAll('article[data-testid=\"tweet\"]').length")
            await update.message.reply_text(f"📝 Твитов на странице: {count}")
            return
        
        if any(w in cmd for w in ['заголовок', 'title']):
            title = await tab.execute_script("document.title")
            await update.message.reply_text(f"📄 Заголовок: {title}")
            return
        
        if 'url' in cmd:
            url = await tab.execute_script("window.location.href")
            await update.message.reply_text(f"📍 URL: {url}")
            return
        
        # ===== ПРОКРУТКА =====
        if 'вниз' in cmd:
            if 'много' in cmd or 'все' in cmd:
                await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                await update.message.reply_text("⬇️ Прокрутил в самый низ")
            else:
                await tab.execute_script("window.scrollBy(0, 500)")
                await update.message.reply_text("⬇️ Прокрутил вниз на 500px")
            return
        
        if 'вверх' in cmd:
            if 'много' in cmd or 'все' in cmd:
                await tab.execute_script("window.scrollTo(0, 0)")
                await update.message.reply_text("⬆️ Прокрутил в самый верх")
            else:
                await tab.execute_script("window.scrollBy(0, -500)")
                await update.message.reply_text("⬆️ Прокрутил вверх на 500px")
            return
        
        # ===== НЕ ПОНЯЛ =====
        await update.message.reply_text(
            "🤔 Не понял команду\n\n"
            "📝 *Примеры:*\n"
            "  /agent найди профиль илона маска\n"
            "  /agent фото бреда питта\n"
            "  /agent твиты илона маска\n"
            "  /agent подписчики илона маска\n"
            "  /agent лайк — лайкнуть твит\n"
            "  /agent главная — на главную"
        )
        
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
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        result = await tab.execute_script(js_code)
        
        if isinstance(result, dict):
            if 'result' in result and isinstance(result['result'], dict):
                if 'value' in result['result']:
                    result = result['result']['value']
            elif 'value' in result:
                result = result['value']
        
        if isinstance(result, (list, dict)):
            result = json.dumps(result, ensure_ascii=False, indent=2)
        
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
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("agent", agent))
    application.add_handler(CommandHandler("eval", evaluate_js))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()