import os
import logging
import asyncio
import base64
import json
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

# Модель для парсинга цитат
class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

# Модель для парсинга твитов
class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )
    author: str = Field(
        selector='div[data-testid="User-Name"] span',
        default="[автор не найден]"
    )
    link: str = Field(
        selector='a[href*="/status/"]',
        attribute='href',
        default="[ссылка не найдена]"
    )
    timestamp: str = Field(
        selector='time',
        default="[время не указано]"
    )

# Путь к браузеру
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное меню (часть 1 - основные команды)"""
    menu1 = (
        "🤖 *Бот для автоматизации — 100% Pydoll*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n\n"
        "🔍 *Навигация*\n"
        "/search <текст> — Поиск на X.com\n"
        "/go <url> — Открыть сайт\n"
        "/scroll <top|bottom|px> — Прокрутка\n\n"
        "📸 *Скриншоты*\n"
        "/screen — Скриншот страницы\n\n"
        "🔎 *Элементы*\n"
        "/find <selector> — Найти элемент\n"
        "/find_all <selector> — Найти все\n"
        "/click <selector> — Кликнуть\n"
        "/type <selector> <text> — Ввести текст\n"
        "/wait <selector> — Ожидать элемент\n"
        "/scroll_to <selector> — Прокрутить к элементу\n\n"
        "📌 *Продвинутые команды:* /start2"
    )
    
    await update.message.reply_text(menu1, parse_mode='Markdown')

async def start2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает только продвинутые команды (часть 2)"""
    menu2 = (
        "🌑 *Shadow DOM*\n"
        "/shadow <selector> — Найти в Shadow DOM\n"
        "/shadow_all <selector> — Найти все в Shadow DOM\n"
        "/shadow_click <selector> — Кликнуть в Shadow DOM\n"
        "/shadow_type <selector> <text> — Ввести в Shadow DOM\n\n"
        "🌐 *Сеть*\n"
        "/network — Показать сетевые запросы\n"
        "/block_images — Блокировать изображения\n"
        "/unblock_images — Разблокировать изображения\n\n"
        "🍪 *Куки*\n"
        "/cookie {\"name\":\"value\"} — Установить куки\n\n"
        "⚡ *Другое*\n"
        "/eval <js> — Выполнить JS\n"
        "/parse — Получить цитаты\n\n"
        "📖 *Селекторы:* .class #id div > p"
    )
    
    await update.message.reply_text(menu2, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматический вход на X.com с куками"""
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")
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
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        try:
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            screenshot_bytes = base64.b64decode(screenshot_base64)
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption="🖼️ Ты авторизован на X.com!"
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Не удалось сделать скриншот, но вход выполнен.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def search_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск на X.com с использованием extract_all"""
    if not context.args:
        await update.message.reply_text("❌ Укажи текст для поиска\nПример: /search python")
        return
    
    search_query = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text(f"🔍 Ищу: {search_query}")
        
        _, tab = user_browsers[user_id]
        
        search_url = f"https://x.com/search?q={search_query}&src=typed_query"
        await tab.go_to(search_url)
        await asyncio.sleep(5)
        
        await update.message.reply_text("📊 Извлекаю твиты через extract_all...")
        
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
            caption=f"🔍 Результаты поиска: {search_query}"
        )
        
        if tweets:
            count = len(tweets)
            reply = f"📊 Найдено {count} твитов\n\n"
            
            for i, tweet in enumerate(tweets[:10], 1):
                text = tweet.text[:150] + "..." if len(tweet.text) > 150 else tweet.text
                reply += f"{i}. {text}\n"
                reply += f"   👤 {tweet.author}\n"
                if tweet.link and tweet.link != "[ссылка не найдена]":
                    reply += f"   🔗 https://x.com{tweet.link}\n"
                reply += "\n"
            
            if count > 10:
                reply += f"... и ещё {count - 10} твитов"
            
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("📊 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает любой сайт"""
    if not context.args:
        await update.message.reply_text("❌ Укажи URL после команды\nПример: /go https://example.com")
        return
    
    url = context.args[0]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text(f"🌐 Открываю: {url}")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.binary_location = CHROME_PATH
        
        if user_id in user_browsers:
            browser, tab = user_browsers[user_id]
            await tab.go_to(url)
            await asyncio.sleep(3)
            await update.message.reply_text(f"✅ Перешёл на {url}")
        else:
            browser = Chrome(options=options)
            tab = await browser.start()
            await tab.go_to(url)
            await asyncio.sleep(3)
            user_browsers[user_id] = (browser, tab)
            await update.message.reply_text(f"✅ Открыл: {url}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот текущей страницы"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        
        await asyncio.sleep(1)
        
        try:
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            
            screenshot_bytes = base64.b64decode(screenshot_base64)
            
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption="🖼️ Скриншот страницы"
            )
            
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def find_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит элемент по селектору"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /find .quote")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        element = await tab.find(selector)
        
        if element:
            text = await element.text()
            await update.message.reply_text(f"✅ Найден элемент:\n\n{text[:500]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def find_all_elements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит все элементы по селектору"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /find_all .quote")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        elements = await tab.find_all(selector)
        
        if elements:
            count = len(elements)
            reply = f"✅ Найдено {count} элементов:\n\n"
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
            await update.message.reply_text(f"❌ Элементы не найдены: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def click_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кликает по элементу с humanize"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /click .button")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        element = await tab.find(selector)
        
        if element:
            await element.click(humanize=True)
            await update.message.reply_text(f"✅ Кликнул по элементу: {selector}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вводит текст в элемент с humanize"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажи селектор и текст\nПример: /type .input hello")
        return
    
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        element = await tab.find(selector)
        
        if element:
            await element.click(humanize=True)
            await asyncio.sleep(0.5)
            await element.type_text(text, humanize=True)
            await update.message.reply_text(f"✅ Ввёл текст в {selector}: {text[:50]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет JavaScript код"""
    if not context.args:
        await update.message.reply_text("❌ Укажи JS код\nПример: /eval document.title")
        return
    
    js_code = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        result = await tab.evaluate(js_code)
        
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def scroll_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прокручивает страницу"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи направление или пиксели\n"
            "Примеры:\n"
            "/scroll top - в начало\n"
            "/scroll bottom - в конец\n"
            "/scroll 500 - на 500px вниз"
        )
        return
    
    scroll_arg = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        if scroll_arg.lower() == 'top':
            await tab.evaluate("window.scrollTo(0, 0)")
            await update.message.reply_text("⬆️ Прокрутил в начало")
        elif scroll_arg.lower() == 'bottom':
            await tab.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await update.message.reply_text("⬇️ Прокрутил в конец")
        else:
            try:
                pixels = int(scroll_arg)
                await tab.evaluate(f"window.scrollBy(0, {pixels})")
                await update.message.reply_text(f"📜 Прокрутил на {pixels}px")
            except ValueError:
                await update.message.reply_text("❌ Неправильный формат. Используй: top, bottom или число")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def scroll_to_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прокручивает к элементу с humanize"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /scroll_to .footer")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        element = await tab.find(selector)
        
        if element:
            await tab.scroll.to_element(element, humanize=True)
            await update.message.reply_text(f"✅ Прокрутил к элементу: {selector}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def wait_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидает появление элемента"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /wait .loading")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await update.message.reply_text(f"⏳ Ожидаю элемент: {selector}")
        
        await tab.wait_for_selector(selector, timeout=30)
        
        await update.message.reply_text(f"✅ Элемент появился: {selector}")
            
    except asyncio.TimeoutError:
        await update.message.reply_text(f"⏰ Таймаут: элемент не появился за 30 сек")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== SHADOW DOM КОМАНДЫ ====================

async def shadow_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит элемент в Shadow DOM"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор для Shadow DOM\nПример: /shadow .internal-btn")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        host_element = await tab.find('#movie_player')
        if not host_element:
            await update.message.reply_text("❌ Хост-элемент не найден. Укажи хост-селектор")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text("❌ Shadow DOM не найден в этом элементе")
            return
        
        element = await shadow_root.query(selector)
        
        if element:
            text = await element.text()
            await update.message.reply_text(f"✅ Найден элемент в Shadow DOM:\n\n{text[:500]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_find_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит все элементы в Shadow DOM"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор для Shadow DOM\nПример: /shadow_all .item")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        host_element = await tab.find('#movie_player')
        if not host_element:
            await update.message.reply_text("❌ Хост-элемент не найден")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text("❌ Shadow DOM не найден")
            return
        
        elements = await shadow_root.query_all(selector)
        
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
            await update.message.reply_text(f"❌ Элементы не найдены в Shadow DOM: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кликает по элементу в Shadow DOM с humanize"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор\nПример: /shadow_click .play-btn")
        return
    
    selector = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        host_element = await tab.find('#movie_player')
        if not host_element:
            await update.message.reply_text("❌ Хост-элемент не найден")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text("❌ Shadow DOM не найден")
            return
        
        element = await shadow_root.query(selector)
        
        if element:
            await element.click(humanize=True)
            await update.message.reply_text(f"✅ Кликнул по элементу в Shadow DOM: {selector}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def shadow_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вводит текст в элемент в Shadow DOM с humanize"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажи селектор и текст\nПример: /shadow_type .input hello")
        return
    
    selector = context.args[0]
    text = ' '.join(context.args[1:])
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        host_element = await tab.find('#movie_player')
        if not host_element:
            await update.message.reply_text("❌ Хост-элемент не найден")
            return
        
        shadow_root = await host_element.get_shadow_root()
        if not shadow_root:
            await update.message.reply_text("❌ Shadow DOM не найден")
            return
        
        element = await shadow_root.query(selector)
        
        if element:
            await element.click(humanize=True)
            await asyncio.sleep(0.5)
            await element.type_text(text, humanize=True)
            await update.message.reply_text(f"✅ Ввёл текст в Shadow DOM: {text[:50]}")
        else:
            await update.message.reply_text(f"❌ Элемент не найден в Shadow DOM: {selector}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== СЕТЕВЫЕ КОМАНДЫ ====================

async def network_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает сетевые запросы"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        await update.message.reply_text("🌐 Получаю сетевые запросы...")
        
        _, tab = user_browsers[user_id]
        
        await tab.enable_network_interception()
        
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
    """Блокирует загрузку изображений"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await tab.enable_network_interception()
        await tab.set_request_interception(
            patterns=[{'urlPattern': '*.jpg', 'interceptionStage': 'Request'}, 
                     {'urlPattern': '*.png', 'interceptionStage': 'Request'},
                     {'urlPattern': '*.gif', 'interceptionStage': 'Request'},
                     {'urlPattern': '*.webp', 'interceptionStage': 'Request'}],
            handle=True
        )
        
        await update.message.reply_text("✅ Изображения заблокированы (страницы будут грузиться быстрее)")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def unblock_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокирует загрузку изображений"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await tab.disable_network_interception()
        
        await update.message.reply_text("✅ Изображения разблокированы")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== КУКИ И ПАРСИНГ ====================

async def cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка кук из JSON"""
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
        
        cookies_list = [
            {"name": name, "value": value}
            for name, value in cookies_data.items()
        ]
        
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

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсит цитаты с quotes.toscrape.com"""
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
            
            quotes = await tab.extract_all(
                Quote,
                scope=".quote",
                timeout=10
            )
            
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("start2", start2))  # ← ВАЖНО! /start2 зарегистрирован
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("search", search_x))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("find", find_element))
    application.add_handler(CommandHandler("find_all", find_all_elements))
    application.add_handler(CommandHandler("click", click_element))
    application.add_handler(CommandHandler("type", type_text))
    application.add_handler(CommandHandler("eval", evaluate_js))
    application.add_handler(CommandHandler("scroll", scroll_page))
    application.add_handler(CommandHandler("scroll_to", scroll_to_element))
    application.add_handler(CommandHandler("wait", wait_element))
    
    # Shadow DOM команды
    application.add_handler(CommandHandler("shadow", shadow_find))
    application.add_handler(CommandHandler("shadow_all", shadow_find_all))
    application.add_handler(CommandHandler("shadow_click", shadow_click))
    application.add_handler(CommandHandler("shadow_type", shadow_type))
    
    # Сетевые команды
    application.add_handler(CommandHandler("network", network_logs))
    application.add_handler(CommandHandler("block_images", block_images))
    application.add_handler(CommandHandler("unblock_images", unblock_images))
    
    # Куки и парсинг
    application.add_handler(CommandHandler("cookie", cookie))
    application.add_handler(CommandHandler("parse", parse))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен с 100% функционалом Pydoll!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()