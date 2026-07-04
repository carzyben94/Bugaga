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

# Модели для парсинга
class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

class Tweet(ExtractionModel):
    text: str = Field(selector='div[data-testid="tweetText"]', default="[текст не найден]")
    author: str = Field(selector='div[data-testid="User-Name"] span', default="[автор не найден]")
    link: str = Field(selector='a[href*="/status/"]', attribute='href', default="[ссылка не найдена]")
    timestamp: str = Field(selector='time', default="[время не указано]")

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

# Хранилище для пользователей
user_browsers = {}
explored_structures = {}
generated_functions = {}

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu1 = (
        "🤖 Бот для автоматизации X.com\n\n"
        "🔐 Авторизация\n"
        "/login — Войти в X.com\n\n"
        "🔍 Исследование\n"
        "/explore_all — Полное исследование всего X.com\n"
        "/explore <page> — Исследовать конкретную страницу\n"
        "/list — Показать найденные структуры\n\n"
        "⚡ Создание функций\n"
        "/functions — Показать все созданные функции\n"
        "/use <name> — Использовать созданную функцию\n\n"
        "📸 Другое\n"
        "/screen — Скриншот\n"
        "/search <текст> — Поиск\n"
        "/go <url> — Открыть сайт\n\n"
        "📌 Продвинутые команды: /start2"
    )
    await update.message.reply_text(menu1)

async def start2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu2 = (
        "🌑 Shadow DOM\n"
        "/shadow <хост> <селектор> — Найти в Shadow DOM\n"
        "/shadow_all <хост> <селектор> — Найти все в Shadow DOM\n"
        "/shadow_click <хост> <селектор> — Кликнуть в Shadow DOM\n"
        "/shadow_type <хост> <селектор> <текст> — Ввести в Shadow DOM\n\n"
        "🌐 Сеть\n"
        "/network — Показать сетевые запросы\n"
        "/block_images — Блокировать изображения\n"
        "/unblock_images — Разблокировать изображения\n\n"
        "🍪 Куки\n"
        "/cookie {\"name\":\"value\"} — Установить куки\n\n"
        "⚡ Другое\n"
        "/eval <js> — Выполнить JS\n"
        "/parse — Получить цитаты"
    )
    await update.message.reply_text(menu2)

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
        # ✅ Убрал блокировку изображений
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

# ==================== АНАЛИЗ СТРАНИЦЫ ====================

async def analyze_page(tab, page_name):
    """Анализирует страницу и возвращает структуру"""
    
    structure = {
        'url': await tab.current_url,
        'title': await tab.title,
        'elements': {}
    }
    
    # Базовые селекторы для всех страниц
    base_selectors = [
        ('tweets', 'article[data-testid="tweet"]'),
        ('tweet_text', 'div[data-testid="tweetText"]'),
        ('tweet_author', 'div[data-testid="User-Name"] span'),
        ('tweet_time', 'time'),
        ('tweet_likes', 'div[data-testid="like"] span'),
        ('tweet_retweets', 'div[data-testid="retweet"] span'),
        ('tweet_replies', 'div[data-testid="reply"] span'),
        ('tweet_views', 'div[data-testid="views"] span'),
        ('nav_home', 'a[aria-label="Home"]'),
        ('nav_explore', 'a[aria-label="Explore"]'),
        ('nav_notifications', 'a[aria-label="Notifications"]'),
        ('nav_messages', 'a[aria-label="Messages"]'),
        ('nav_profile', 'a[aria-label="Profile"]'),
        ('search_input', 'input[data-testid="SearchBox_Search_Input"]'),
        ('search_button', 'button[data-testid="SearchBox_Search_Button"]'),
        ('compose_button', 'a[data-testid="tweetButton"]'),
        ('like_button', 'button[data-testid="like"]'),
        ('retweet_button', 'button[data-testid="retweet"]'),
        ('reply_button', 'button[data-testid="reply"]'),
        ('share_button', 'button[data-testid="share"]'),
        ('main_container', 'main'),
        ('sidebar', 'aside'),
        ('header', 'header'),
        ('footer', 'footer'),
    ]
    
    # Проверяем все селекторы
    for name, selector in base_selectors:
        try:
            elements = await tab.find_all(selector)
            if elements:
                count = len(elements)
                first_text = ''
                if count > 0:
                    try:
                        if hasattr(elements[0], 'text'):
                            first_text = await elements[0].text()
                            if len(first_text) > 100:
                                first_text = first_text[:100] + '...'
                    except:
                        first_text = '[текст не получен]'
                
                structure['elements'][name] = {
                    'selector': selector,
                    'count': count,
                    'sample': first_text
                }
        except Exception as e:
            pass
    
    return structure

# ==================== ГЕНЕРАЛЬНОЕ ИССЛЕДОВАНИЕ ====================

async def explore_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генеральное исследование всего X.com"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("🔍 Запускаю генеральное исследование X.com...")
        
        _, tab = user_browsers[user_id]
        
        # Список всех страниц для исследования
        pages = {
            'home': 'https://x.com/home',
            'explore': 'https://x.com/explore',
            'notifications': 'https://x.com/notifications',
            'messages': 'https://x.com/messages',
            'profile': 'https://x.com/settings/profile',
            'trending': 'https://x.com/explore/tabs/trending',
            'following': 'https://x.com/i/following',
            'search': 'https://x.com/search?q=test',
        }
        
        all_structures = {}
        
        for page_name, url in pages.items():
            await update.message.reply_text(f"📄 Исследую: {page_name}...")
            
            try:
                await tab.go_to(url)
                await asyncio.sleep(5)
                
                # Ждём загрузки твитов
                try:
                    await tab.wait_for_selector('article[data-testid="tweet"]', timeout=8)
                except:
                    pass
                
                structure = await analyze_page(tab, page_name)
                all_structures[page_name] = structure
                
                elements_count = len(structure.get('elements', {}))
                await update.message.reply_text(f"  ✅ Найдено {elements_count} элементов")
                
            except Exception as e:
                logger.error(f"Ошибка при исследовании {page_name}: {e}")
                all_structures[page_name] = {'error': str(e)}
        
        # Сохраняем всё
        user_key = f"user_{user_id}"
        explored_structures[user_key] = all_structures
        
        # Генерируем функции
        await update.message.reply_text("⚡ Генерирую функции...")
        
        for page_name, structure in all_structures.items():
            if 'error' not in structure:
                func_key = f"{user_key}_{page_name}"
                generated_functions[func_key] = structure
        
        # Отчёт
        report = "✅ *Генеральное исследование завершено!*\n\n"
        report += "📊 *Найдено структур:*\n"
        
        for page_name, structure in all_structures.items():
            if 'error' not in structure:
                elements_count = len(structure.get('elements', {}))
                report += f"  • *{page_name}*: {elements_count} элементов\n"
            else:
                report += f"  • *{page_name}*: ❌ {structure['error']}\n"
        
        report += "\n💡 *Созданные функции:*\n"
        func_keys = [k for k in generated_functions.keys() if k.startswith(user_key)]
        for func_key in func_keys:
            func_name = func_key.replace(f"{user_key}_", "")
            report += f"  • `{func_name}`\n"
        
        report += "\n📋 *Команды:*\n"
        report += "  • `/list` — показать все структуры\n"
        report += "  • `/use <name>` — использовать функцию\n"
        report += "  • `/functions` — показать все функции"
        
        await update.message.reply_text(report, parse_mode='Markdown')
        
        # Сохраняем в JSON
        try:
            with open(f'explore_all_{user_id}.json', 'w', encoding='utf-8') as f:
                json.dump(all_structures, f, ensure_ascii=False, indent=2)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== КОМАНДЫ ДЛЯ РАБОТЫ С ИССЛЕДОВАНИЕМ ====================

async def explore_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исследует конкретную страницу"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи страницу для исследования\n"
            "Примеры: /explore home, /explore profile, /explore @username"
        )
        return
    
    page = context.args[0]
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text(f"🔍 Исследую: {page}")
        
        _, tab = user_browsers[user_id]
        
        # Определяем URL
        urls = {
            'home': 'https://x.com/home',
            'explore': 'https://x.com/explore',
            'notifications': 'https://x.com/notifications',
            'messages': 'https://x.com/messages',
            'profile': 'https://x.com/settings/profile',
            'trending': 'https://x.com/explore/tabs/trending',
            'following': 'https://x.com/i/following',
        }
        
        if page in urls:
            await tab.go_to(urls[page])
        elif page.startswith('@'):
            await tab.go_to(f'https://x.com/{page}')
        else:
            await tab.go_to(f'https://x.com/search?q={page}&src=typed_query')
        
        await asyncio.sleep(5)
        
        structure = await analyze_page(tab, page)
        
        user_key = f"user_{user_id}"
        if user_key not in explored_structures:
            explored_structures[user_key] = {}
        explored_structures[user_key][page] = structure
        
        func_key = f"{user_key}_{page}"
        generated_functions[func_key] = structure
        
        # Отчёт
        reply = f"✅ *Исследование завершено: {page}*\n\n"
        reply += f"📍 URL: {structure['url']}\n"
        reply += f"📄 Title: {structure['title']}\n\n"
        
        found = {k: v for k, v in structure['elements'].items() if v.get('count', 0) > 0}
        if found:
            reply += "📋 *Найденные элементы:*\n"
            for name, data in list(found.items())[:10]:
                reply += f"  • `{name}`: {data['count']} элементов\n"
                if data.get('sample'):
                    reply += f"    Пример: {data['sample']}\n"
        
        reply += f"\n✅ Создана функция: `{page}`"
        reply += "\n📋 Используй: `/use " + page + "`"
        
        await update.message.reply_text(reply, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def list_structures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все сохранённые структуры"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    if user_key not in explored_structures or not explored_structures[user_key]:
        await update.message.reply_text("📭 Нет сохранённых структур. Используй /explore_all или /explore")
        return
    
    reply = "📂 *Сохранённые структуры:*\n\n"
    for page, structure in explored_structures[user_key].items():
        elements = len(structure.get('elements', {}))
        url = structure.get('url', 'неизвестно')
        reply += f"• *{page}*\n"
        reply += f"  URL: {url}\n"
        reply += f"  Элементов: {elements}\n\n"
    
    reply += "💡 Используй /use <name> для применения"
    
    await update.message.reply_text(reply, parse_mode='Markdown')

async def list_functions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все созданные функции"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    funcs = [k.replace(f"{user_key}_", "") for k in generated_functions.keys() if k.startswith(user_key)]
    
    if not funcs:
        await update.message.reply_text("📭 Нет созданных функций. Используй /explore_all")
        return
    
    reply = "⚡ *Созданные функции:*\n\n"
    for func in funcs:
        reply += f"  • `{func}`\n"
    
    reply += "\n💡 Используй: `/use <name>`"
    
    await update.message.reply_text(reply, parse_mode='Markdown')

async def use_function(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Использует созданную функцию для парсинга"""
    if not context.args:
        await update.message.reply_text("❌ Укажи имя функции\nПример: /use home")
        return
    
    func_name = context.args[0]
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    func_key = f"{user_key}_{func_name}"
    
    if func_key not in generated_functions:
        await update.message.reply_text(f"❌ Функция '{func_name}' не найдена. Используй /list")
        return
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text(f"🔍 Использую функцию: {func_name}")
        
        _, tab = user_browsers[user_id]
        structure = generated_functions[func_key]
        
        # Переходим на страницу из структуры
        await tab.go_to(structure['url'])
        await asyncio.sleep(3)
        
        # Извлекаем твиты
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
            caption=f"🖼️ {func_name.capitalize()}"
        )
        
        # Результаты
        if tweets:
            reply = f"📊 *Найдено {len(tweets)} твитов на {func_name}*\n\n"
            for i, tweet in enumerate(tweets[:5], 1):
                text = tweet.text[:150] + '...' if len(tweet.text) > 150 else tweet.text
                reply += f"{i}. {text}\n\n"
            
            await update.message.reply_text(reply, parse_mode='Markdown')
        else:
            await update.message.reply_text("📊 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ДРУГИЕ КОМАНДЫ ====================

async def search_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        await update.message.reply_text("📊 Извлекаю твиты...")
        
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
                reply += f"{i}. {text}\n\n"
            if count > 10:
                reply += f"... и ещё {count - 10} твитов"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text("📊 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        # ✅ Убрал блокировку изображений
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
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
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
            caption="🖼️ Скриншот страницы"
        )
            
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
        await tab.disable_network_interception()
        await update.message.reply_text("✅ Изображения разблокированы")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== КУКИ И ПАРСИНГ ====================

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

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def find_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def wait_element(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("start2", start2))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("search", search_x))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("find", find_element))
    application.add_handler(CommandHandler("find_all", find_all_elements))
    application.add_handler(CommandHandler("click", click_element))
    application.add_handler(CommandHandler("type", type_text))
    application.add_handler(CommandHandler("wait", wait_element))
    application.add_handler(CommandHandler("scroll", scroll_page))
    application.add_handler(CommandHandler("scroll_to", scroll_to_element))
    application.add_handler(CommandHandler("eval", evaluate_js))
    
    # Исследование
    application.add_handler(CommandHandler("explore_all", explore_all))
    application.add_handler(CommandHandler("explore", explore_page))
    application.add_handler(CommandHandler("list", list_structures))
    application.add_handler(CommandHandler("functions", list_functions))
    application.add_handler(CommandHandler("use", use_function))
    
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