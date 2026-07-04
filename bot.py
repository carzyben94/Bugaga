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
        "/ai Любая команда (умный eval)"
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

# ==================== AI КОМАНДА (УМНЫЙ EVAL) ====================

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Умный /eval — генерирует код через Agnes AI и выполняет как /eval"""
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
            "🤖 *Умный /eval*\n\n"
            "Просто скажи что хочешь сделать:\n"
            "/ai найди твиты про войну\n"
            "/ai лайкни первый твит\n"
            "/ai сколько подписчиков\n"
            "/ai фото красивых девушек\n"
            "/ai прокрути вниз\n"
            "/ai статистика",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("🧠 *Генерирую код через Agnes AI...*", parse_mode='Markdown')
        
        _, tab = user_browsers[user_id]
        
        # ✅ Проверяем, на X.com ли мы
        try:
            current_url = await tab.current_url
        except:
            current_url = ''
        
        if 'x.com' not in current_url and 'twitter.com' not in current_url:
            await update.message.reply_text("🔄 Перехожу на X.com...", parse_mode='Markdown')
            await tab.go_to('https://x.com')
            await asyncio.sleep(3)
        
        # ✅ Проверяем, есть ли твиты
        tweet_count = 0
        try:
            tweet_count = await tab.execute_script(
                "document.querySelectorAll('article[data-testid=\"tweet\"]').length"
            )
        except:
            tweet_count = 0
        
        # Если твитов нет — используем поиск
        if tweet_count == 0:
            await update.message.reply_text("🔍 Твитов нет, использую поиск...", parse_mode='Markdown')
            
            keywords = command.lower()
            for word in ['найди', 'найти', 'искать', 'поиск', 'покажи']:
                keywords = keywords.replace(word, '')
            keywords = keywords.strip()
            
            if not keywords:
                keywords = command
            
            await tab.go_to(f'https://x.com/search?q={keywords}&src=typed_query')
            await asyncio.sleep(3)
            await update.message.reply_text(f"✅ На странице поиска: {keywords}", parse_mode='Markdown')
            
            # Проверяем твиты после поиска
            try:
                tweet_count = await tab.execute_script(
                    "document.querySelectorAll('article[data-testid=\"tweet\"]').length"
                )
            except:
                tweet_count = 0
        
        # ✅ Если всё равно нет твитов — сообщаем
        if tweet_count == 0:
            await update.message.reply_text(
                "❌ *Не найдено твитов на странице.*\n"
                "Попробуй:\n"
                "1. Выполни /login заново\n"
                "2. Проверь, что ты на X.com\n"
                "3. Попробуй другую команду",
                parse_mode='Markdown'
            )
            return
        
        # ✅ Собираем контекст
        page_info = await tab.execute_script("""
            (function() {
                const ids = {};
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const id = el.dataset.testid;
                    if (id) {
                        ids[id] = (ids[id] || 0) + 1;
                    }
                });
                return {
                    url: window.location.href,
                    title: document.title,
                    testids: ids,
                    tweet_count: document.querySelectorAll('article[data-testid="tweet"]').length
                };
            })()
        """)
        
        # ✅ Генерируем JS код через Agnes AI
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
        - НЕ используй комментарии (// или /* */)
        - Если данных нет — верни пустой массив []
        """
        
        response = await asyncio.wait_for(
            agnes_client.chat.completions.create(
                model="agnes-2.0-flash",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по JavaScript. Отвечай ТОЛЬКО кодом. НИКАКИХ комментариев. Если нет данных — верни []."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            ),
            timeout=20.0
        )
        
        js_code = response.choices[0].message.content
        
        # Очищаем код от markdown
        js_code = re.sub(r'```javascript\n?', '', js_code)
        js_code = re.sub(r'```json\n?', '', js_code)
        js_code = re.sub(r'```\n?', '', js_code)
        
        # ✅ Убираем комментарии и пустые строки
        lines = js_code.split('\n')
        clean_lines = []
        for line in lines:
            # Убираем однострочные комментарии
            if line.strip().startswith('//'):
                continue
            # Убираем многострочные комментарии
            if line.strip().startswith('/*') or line.strip().startswith('*'):
                continue
            # Убираем пустые строки
            if line.strip() == '':
                continue
            clean_lines.append(line)
        js_code = '\n'.join(clean_lines).strip()
        
        # Проверяем, что код не пустой
        if not js_code or len(js_code) < 5:
            await update.message.reply_text(
                "⚠️ *Не удалось сгенерировать код.*\n"
                "Попробуй переформулировать команду.\n\n"
                "💡 *Примеры:*\n"
                "/ai найди твиты про войну\n"
                "/ai сколько твитов\n"
                "/ai лайкни первый твит",
                parse_mode='Markdown'
            )
            return
        
        # ✅ ВЫПОЛНЯЕМ КОД
        await update.message.reply_text(
            f"⚡ *Выполняю код:*\n"
            f"```javascript\n{js_code[:400]}\n```",
            parse_mode='Markdown'
        )
        
        # Выполняем код
        try:
            result = await asyncio.wait_for(
                tab.execute_script(js_code),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("⚠️ Выполнение кода заняло слишком много времени.")
            return
        
        # Форматируем результат
        if isinstance(result, (list, dict)):
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            result_str = str(result)
        
        if len(result_str) > 1000:
            result_str = result_str[:1000] + '...'
        
        if not result_str or result_str == '""' or result_str == "''" or result_str == '[]':
            await update.message.reply_text("⚠️ *Результат пустой.*\nПопробуй другую команду.")
        else:
            await update.message.reply_text(f"📊 *Результат:*\n{result_str[:500]}")
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Agnes AI не ответил вовремя. Попробуй позже.")
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