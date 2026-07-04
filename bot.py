import os
import logging
import asyncio
import base64
import json
import re
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

from openai import AsyncOpenAI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

# Создаём клиент для Agnes AI
agnes_client = None
if AGNES_API_KEY:
    agnes_client = AsyncOpenAI(
        api_key=AGNES_API_KEY,
        base_url="https://apihub.agnes-ai.com/v1"
    )

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

class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )

class TweetPhoto(ExtractionModel):
    photo: str = Field(
        selector='img[src*="media"]',
        attribute='src',
        default=""
    )

# ==================== ФУНКЦИИ ====================

def fix_text(text):
    text = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', text)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([А-ЯЁ])([А-ЯЁ][а-яё])', r'\1 \2', text)
    text = re.sub(r'([«»"\'])([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'([А-Яа-яA-Za-z])([«»"\'])', r'\1 \2', text)
    text = re.sub(r'([—–])([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'([А-Яа-яA-Za-z])([—–])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "/login X.com\n"
        "/close Закрыть браузер\n"
        "/screen Скриншот\n"
        "/search Запрос\n"
        "/getbaby Случайное фото\n"
        "/ai Любая команда"
    )
    await update.message.reply_text(menu)

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

# ==================== ЗАКРЫТЬ БРАУЗЕР ====================

async def close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Браузер уже закрыт или не был открыт")
            return
        
        browser, tab = user_browsers[user_id]
        
        await update.message.reply_text("🔄 Закрываю браузер...")
        
        await browser.close()
        
        del user_browsers[user_id]
        
        await update.message.reply_text("✅ Браузер закрыт! Сессия очищена.")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка при закрытии браузера: {str(e)[:300]}")

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
        
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption="🖼️ Скриншот"
        )
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ПОИСК ====================

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос\nПример: /search python")
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
            
            for i, tweet in enumerate(tweets[:20], 1):
                text = fix_text(tweet.text)
                if len(text) > 600:
                    text = text[:600] + '...'
                reply += f"{i}. {text}\n\n"
            
            if count > 20:
                reply += f"... и ещё {count - 20} твитов"
            
            if len(reply) > 4096:
                parts = []
                current = ""
                for line in reply.split('\n'):
                    if len(current) + len(line) + 1 > 4000:
                        parts.append(current)
                        current = ""
                    current += line + '\n'
                if current:
                    parts.append(current)
                
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😕 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== GETBABY ====================

async def getbaby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    PROFILES = [
        'babesdailyyy',
        'beautyshowcase',
        'EuGirlsDom'
    ]
    
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("📸 Ищу фото...")
        
        _, tab = user_browsers[user_id]
        
        random.shuffle(PROFILES)
        
        all_photos = []
        
        for username in PROFILES:
            try:
                await tab.go_to(f'https://x.com/{username}')
                await asyncio.sleep(3)
                
                photos = await tab.extract_all(
                    TweetPhoto,
                    scope='article[data-testid="tweet"]',
                    timeout=5
                )
                
                for photo_obj in photos[:10]:
                    if photo_obj.photo:
                        all_photos.append(photo_obj.photo)
                
                if not photos:
                    photos_js = await tab.execute_script("""
                        (function() {
                            const images = document.querySelectorAll('img[src*="media"]');
                            const result = [];
                            images.forEach(img => {
                                const src = img.src || img.getAttribute('src');
                                if (src && src.includes('media')) {
                                    result.push(src);
                                }
                            });
                            return result;
                        })()
                    """)
                    for photo in photos_js[:10]:
                        all_photos.append(photo)
                
                if len(all_photos) >= 15:
                    break
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке {username}: {e}")
                continue
        
        if all_photos:
            random.shuffle(all_photos)
            selected = random.choice(all_photos)
            
            await update.message.reply_photo(photo=selected)
            
            await update.message.reply_text(f"📊 Найдено {len(all_photos)} фото")
            
        else:
            await update.message.reply_text("😕 Фото не найдены")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== AI КОМАНДА ====================

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет любую команду через Agnes AI (использует существующий браузер)"""
    if not AGNES_API_KEY:
        await update.message.reply_text(
            "❌ Agnes API ключ не найден.\n"
            "Добавь AGNES_API_KEY в переменные окружения."
        )
        return
    
    if not agnes_client:
        await update.message.reply_text(
            "❌ Ошибка инициализации Agnes AI клиента."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 *AI-агент для X.com*\n\n"
            "Просто скажи что хочешь сделать:\n"
            "/ai найди твиты про войну\n"
            "/ai лайкни первый твит\n"
            "/ai сколько подписчиков\n"
            "/ai фото красивых девушек\n"
            "/ai прокрути вниз\n"
            "/ai статистика\n\n"
            "💰 *Бесплатно, без ограничений!*",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("🧠 *Этап 1/5:* Анализирую команду...", parse_mode='Markdown')
        
        _, tab = user_browsers[user_id]
        
        # ✅ Этап 1.5: Проверяем, на X.com ли мы
        await update.message.reply_text("🌐 *Этап 1.5/5:* Проверяю страницу...", parse_mode='Markdown')
        
        try:
            current_url = await tab.current_url
        except:
            current_url = ''
        
        if 'x.com' not in current_url and 'twitter.com' not in current_url:
            await update.message.reply_text("🔄 Перехожу на X.com...", parse_mode='Markdown')
            await tab.go_to('https://x.com')
            await asyncio.sleep(3)
        
        await update.message.reply_text("✅ На X.com", parse_mode='Markdown')
        
        # ✅ Этап 2: Ждём загрузки
        await update.message.reply_text("📊 *Этап 2/5:* Жду загрузки страницы...", parse_mode='Markdown')
        
        try:
            await tab.wait_for_selector('article[data-testid="tweet"]', timeout=8)
            await update.message.reply_text("✅ Страница загружена", parse_mode='Markdown')
        except:
            await update.message.reply_text("⚠️ Твиты не найдены, обновляю...", parse_mode='Markdown')
            await tab.refresh()
            await asyncio.sleep(3)
        
        # ✅ Этап 2.5: Сбор контекста
        await update.message.reply_text("📊 *Этап 2.5/5:* Собираю контекст страницы...", parse_mode='Markdown')
        
        try:
            page_info = await asyncio.wait_for(
                tab.execute_script("""
                    (function() {
                        const ids = {};
                        const elements = document.querySelectorAll('[data-testid]');
                        for (let i = 0; i < Math.min(elements.length, 30); i++) {
                            const id = elements[i].dataset.testid;
                            if (id) {
                                ids[id] = (ids[id] || 0) + 1;
                            }
                        }
                        return {
                            url: window.location.href,
                            title: document.title,
                            testids: ids,
                            tweet_count: document.querySelectorAll('article[data-testid="tweet"]').length
                        };
                    })()
                """),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("⚠️ *Контекст собран частично*", parse_mode='Markdown')
            try:
                url = await tab.current_url
            except:
                url = 'неизвестно'
            try:
                title = await tab.title
            except:
                title = 'неизвестно'
            page_info = {
                'url': url,
                'title': title,
                'testids': {},
                'tweet_count': 0
            }
        
        testids_count = len(page_info.get('testids', {}))
        
        if testids_count == 0:
            await update.message.reply_text(
                "⚠️ *Не найдено элементов на странице.*\n"
                "Попробуй выполнить /login заново",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text(
            f"✅ *Контекст собран:*\n"
            f"• Твитов: {page_info.get('tweet_count', 0)}\n"
            f"• Элементов: {testids_count}",
            parse_mode='Markdown'
        )
        
        # ✅ Этап 3: Отправка в Agnes AI
        await update.message.reply_text("🧠 *Этап 3/5:* Отправляю запрос в Agnes AI...", parse_mode='Markdown')
        
        prompt = f"""
        Ты — агент по автоматизации X.com (Twitter).
        
        СТРАНИЦА:
        URL: {page_info.get('url', 'неизвестно')}
        Title: {page_info.get('title', 'неизвестно')}
        Твитов на странице: {page_info.get('tweet_count', 0)}
        Доступные data-testid: {json.dumps(page_info.get('testids', {}), ensure_ascii=False)}
        
        ЗАДАЧА: {command}
        
        Сгенерируй ТОЛЬКО JavaScript код для выполнения этой задачи.
        - Если нужно вернуть данные — используй return
        - Если нужно выполнить действие — просто выполни код
        - Используй доступные data-testid из контекста
        - Верни ТОЛЬКО код, без пояснений и markdown.
        """
        
        try:
            response = await asyncio.wait_for(
                agnes_client.chat.completions.create(
                    model="agnes-2.0-flash",
                    messages=[
                        {"role": "system", "content": "Ты — эксперт по JavaScript. Отвечай только кодом, без пояснений."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=1000
                ),
                timeout=20.0
            )
            
            js_code = response.choices[0].message.content
            
            await update.message.reply_text(
                f"✅ *Этап 4/5:* Код сгенерирован!\n"
                f"📏 Длина: {len(js_code)} символов",
                parse_mode='Markdown'
            )
            
            js_code = re.sub(r'```javascript\n?', '', js_code)
            js_code = re.sub(r'```json\n?', '', js_code)
            js_code = re.sub(r'```\n?', '', js_code)
            js_code = js_code.strip()
            
            if not js_code or len(js_code) < 10:
                await update.message.reply_text("❌ Код слишком короткий. Попробуй переформулировать.")
                return
            
            # ✅ Этап 5: Выполнение
            await update.message.reply_text("⚡ *Этап 5/5:* Выполняю код...", parse_mode='Markdown')
            
            try:
                result = await asyncio.wait_for(
                    tab.execute_script(js_code),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                await update.message.reply_text("⚠️ Выполнение кода заняло слишком много времени.")
                return
            
            if isinstance(result, (list, dict)):
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                result_str = str(result)
            
            if len(result_str) > 1000:
                result_str = result_str[:1000] + '...'
            
            if not result_str or result_str == '""' or result_str == "''":
                await update.message.reply_text(
                    f"✅ *ГОТОВО!*\n\n"
                    f"🤖 *Команда:* {command}\n\n"
                    f"📝 *Код:*\n```javascript\n{js_code[:300]}\n```\n"
                    f"⚠️ *Результат пустой.*",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"✅ *ГОТОВО!*\n\n"
                    f"🤖 *Команда:* {command}\n\n"
                    f"📝 *Код:*\n```javascript\n{js_code[:300]}\n```\n"
                    f"📊 *Результат:*\n{result_str[:500]}",
                    parse_mode='Markdown'
                )
            
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Agnes AI не ответил вовремя. Попробуй позже.")
        except Exception as e:
            error_msg = str(e)
            if 'api_key' in error_msg.lower() or 'auth' in error_msg.lower():
                await update.message.reply_text("❌ Ошибка авторизации Agnes AI. Проверь ключ.")
            else:
                await update.message.reply_text(f"❌ Ошибка AI: {error_msg[:200]}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("close", close_browser))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("getbaby", getbaby))
    application.add_handler(CommandHandler("ai", ai_command))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()