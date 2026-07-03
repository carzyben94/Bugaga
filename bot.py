import os
import logging
import asyncio
import base64
import random
import json
from datetime import datetime
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Pydantic для структуры
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== PYDAВТИК МОДЕЛИ ==========
class AuthStatusModel(BaseModel):
    is_logged_in: bool = False
    username: str | None = None
    has_auth_token: bool = False
    has_ct0: bool = False
    last_check: datetime | None = None
    cookies_valid: bool = False

# ========== МОДЕЛИ ДЛЯ EXTRACT ==========
class TweetExtract(BaseModel):
    """Модель для извлечения твита"""
    text: str = ""
    author: str = ""
    time: str = ""
    likes: str = ""
    retweets: str = ""
    url: str = ""

class ProfileExtract(BaseModel):
    """Модель для извлечения профиля"""
    name: str = ""
    username: str = ""
    bio: str = ""
    followers: str = ""
    following: str = ""
    joined: str = ""

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
engine_mode = "pydoll"
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== ПОЛНЫЕ КУКИ X.COM ==========
COOKIES = [
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
    {"name": "__cf_bm", "value": "nTs3wcXdCJEOwWzrJyjIg_huVdfck44vXhCJEXi.WuM-1783057691.7981694-1.0.1.1-pPPuXat31U4x5zNib67xLk9EFfH73h1ZdJPU8GvpXVu3pQ6TVu_rRHHpSZZMRRlzToQCMmjHQmaxoa_A4lwaYonLGPxEPsBIDig2wlei1L210t._g0yt.3n7XxfTQzrP", "domain": ".x.com", "path": "/"}
]

logger.info(f"🍪 Загружено {len(COOKIES)} кук")

browser = None
tab = None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def random_delay(min_sec=0.5, max_sec=2.0):
    return random.uniform(min_sec, max_sec)

async def human_goto(page, url):
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)

async def execute_js(script):
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'execute_script'):
            return await page.execute_script(script)
        elif hasattr(page, 'evaluate'):
            return await page.evaluate(script)
    except Exception as e:
        logger.error(f"Ошибка JS: {e}")
        return None

# ========== БРАУЗЕР ==========
async def get_browser():
    global browser, tab
    
    if tab:
        try:
            await tab.execute_script('return 1')
            return tab
        except:
            await close_browser()
    
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        
        logger.info("🚀 Запускаю Pydoll браузер...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        
        chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
        for path in chromium_paths:
            if os.path.exists(path):
                options.binary_location = path
                logger.info(f"📍 Использую: {path}")
                break
        
        browser = Chrome(options=options)
        tab = await browser.start()
        logger.info("✅ Браузер запущен")
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await tab.set_cookie(**cookie)
                cookies_set += 1
            except Exception as e:
                logger.warning(f"⚠️ Ошибка {cookie['name']}: {e}")
                try:
                    js_cookie = f"document.cookie='{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '.x.com')}; path={cookie.get('path', '/')}'"
                    await tab.execute_script(js_cookie)
                    cookies_set += 1
                except:
                    pass
        
        logger.info(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        return tab
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None

async def close_browser():
    global browser, tab
    if browser:
        try:
            await browser.close()
            logger.info("✅ Браузер закрыт")
        except:
            pass
        browser = None
        tab = None

async def take_screenshot():
    page = await get_browser()
    if not page:
        return None
    try:
        screenshot = await page.take_screenshot(as_base64=True)
        if screenshot:
            return base64.b64decode(screenshot)
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
    return None

# ============================================================
# 1. SHADOW DOM - РАБОТА С ВЕБ-КОМПОНЕНТАМИ
# ============================================================
async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исследование Shadow DOM на странице"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Исследую Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        # Находим все элементы с shadowRoot
        result = await page.execute_script('''
            () => {
                const elements = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        const shadowChildren = [];
                        el.shadowRoot.childNodes.forEach(child => {
                            if (child.nodeType === 1) {
                                shadowChildren.push({
                                    tag: child.tagName,
                                    id: child.id || '',
                                    class: child.className || ''
                                });
                            }
                        });
                        elements.push({
                            tag: el.tagName,
                            id: el.id || '',
                            class: el.className || '',
                            shadowChildren: shadowChildren
                        });
                    }
                });
                return elements;
            }
        ''')
        
        report = "🛡️ **SHADOW DOM**\n\n"
        
        if result and len(result) > 0:
            report += f"✅ Найдено {len(result)} элементов с Shadow DOM:\n\n"
            for el in result[:3]:
                report += f"📦 {el.get('tag', '')}"
                if el.get('id'):
                    report += f" id='{el.get('id')}'"
                report += f"\n   Дочерних: {len(el.get('shadowChildren', []))}\n\n"
            
            report += "💡 **Как использовать:**\n"
            report += "```python\n"
            report += "# Найти хост\n"
            report += "host = await tab.find('#shadow-host')\n"
            report += "# Получить shadowRoot\n"
            report += "shadow = await host.get_shadow_root()\n"
            report += "# Найти внутри shadow\n"
            report += "element = await shadow.query('.inner-class')\n"
            report += "```"
        else:
            report += "❌ Shadow DOM элементы НЕ найдены\n\n"
            report += "💡 **Что такое Shadow DOM?**\n"
            report += "Это изолированная часть DOM, скрытая от основного документа.\n\n"
            report += "**Где искать:**\n"
            report += "1. Веб-компоненты\n"
            report += "2. Сложные UI элементы\n"
            report += "3. Сторонние виджеты\n\n"
            report += "**Как найти:**\n"
            report += "1. Открой DevTools (F12)\n"
            report += "2. Включи 'Show user agent shadow DOM'\n"
            report += "3. Ищи элементы с #shadow-root"
        
        await msg.edit_text(report, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 2. API - ПЕРЕХВАТ И ВЫПОЛНЕНИЕ ЗАПРОСОВ
# ============================================================
async def api_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение API запросов с сессией браузера"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🌐 Выполняю API запрос...")
    else:
        msg = await update.message.reply_text("🌐 Выполняю API запрос...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        # Проверка авторизации
        if not login_status['is_logged_in']:
            await msg.edit_text("❌ Сначала авторизуйся! Используй /login")
            return
        
        # Тестовый API запрос к X.com
        api_url = "https://x.com/i/api/1.1/onboarding/task.json"
        
        # Используем Pydoll request (UI + API гибрид)
        try:
            # Метод через fetch в браузере
            result = await page.execute_script(f'''
                (async () => {{
                    try {{
                        const response = await fetch('{api_url}', {{
                            method: 'GET',
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Content-Type': 'application/json'
                            }}
                        }});
                        
                        const data = await response.json();
                        return {{
                            status: response.status,
                            ok: response.ok,
                            data: data,
                            url: response.url
                        }};
                    }} catch (e) {{
                        return {{
                            error: e.message,
                            status: 0
                        }};
                    }}
                }})()
            ''')
        except:
            # Альтернативный метод
            result = await page.execute_script(f'''
                function() {{
                    return fetch('{api_url}', {{
                        credentials: 'include'
                    }})
                    .then(r => r.json())
                    .then(data => ({{status: 200, ok: true, data: data}}))
                    .catch(e => ({{error: e.message, status: 0}}));
                }}
            ''')
        
        # Проверка кук
        cookies_check = await page.execute_script('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                return {
                    has_auth_token: !!cookies.auth_token,
                    has_ct0: !!cookies.ct0,
                    cookies_count: Object.keys(cookies).length
                };
            }
        ''')
        
        report = "🌐 **API - ГИБРИДНАЯ АВТОМАТИЗАЦИЯ**\n\n"
        
        report += "🍪 **Куки в сессии:**\n"
        report += f"  auth_token: {'✅' if cookies_check.get('has_auth_token') else '❌'}\n"
        report += f"  ct0: {'✅' if cookies_check.get('has_ct0') else '❌'}\n"
        report += f"  Всего: {cookies_check.get('cookies_count', 0)}\n\n"
        
        if result and not result.get('error'):
            report += f"📊 **API Запрос:**\n"
            report += f"  URL: {api_url[:50]}...\n"
            report += f"  Статус: {result.get('status', 0)}\n"
            report += f"  Успешно: {'✅' if result.get('ok') else '❌'}\n\n"
            
            if result.get('data'):
                data_str = json.dumps(result['data'], indent=2, ensure_ascii=False)[:300]
                report += f"📝 **Данные:**\n```json\n{data_str}...\n```\n"
        else:
            report += "❌ **API не отвечает**\n"
            report += f"  Ошибка: {result.get('error', 'Неизвестно')}\n\n"
            report += "💡 **Возможные причины:**\n"
            report += "1. Неправильные куки\n"
            report += "2. Требуется обновление токена\n"
            report += "3. Блокировка со стороны X.com"
        
        report += "\n💡 **Как работает гибридная автоматизация:**\n"
        report += "1. UI авторизация через браузер\n"
        report += "2. API запросы с той же сессией\n"
        report += "3. Куки и заголовки наследуются автоматически"
        
        await msg.edit_text(report, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 3. EXTRACT - СТРУКТУРИРОВАННОЕ ИЗВЛЕЧЕНИЕ
# ============================================================
async def extract_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Извлечение структурированных данных со страницы"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📊 Извлекаю структурированные данные...")
    else:
        msg = await update.message.reply_text("📊 Извлекаю структурированные данные...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        # Проверка авторизации
        if not login_status['is_logged_in']:
            await msg.edit_text("❌ Сначала авторизуйся! Используй /login")
            return
        
        # Извлекаем твиты
        tweets_data = await page.execute_script('''
            () => {
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const textEl = el.querySelector('[data-testid="tweetText"]');
                    const userEl = el.querySelector('[data-testid="User-Name"]');
                    const timeEl = el.querySelector('time');
                    
                    // Ищем лайки и ретвиты
                    const likeEl = el.querySelector('[data-testid="like"]');
                    const retweetEl = el.querySelector('[data-testid="retweet"]');
                    
                    tweets.push({
                        text: textEl ? textEl.textContent : '',
                        author: userEl ? userEl.textContent : '',
                        time: timeEl ? timeEl.getAttribute('datetime') : '',
                        likes: likeEl ? likeEl.textContent : '0',
                        retweets: retweetEl ? retweetEl.textContent : '0'
                    });
                });
                return tweets.slice(0, 10);
            }
        ''')
        
        if not tweets_data or len(tweets_data) == 0:
            await msg.edit_text("❌ Нет твитов для извлечения!\n\nПерейди на страницу с твитами или проверь авторизацию.")
            return
        
        # Конвертируем в Pydantic модели
        extracted_tweets = []
        for tweet in tweets_data:
            try:
                extracted_tweets.append(TweetExtract(**tweet))
            except Exception as e:
                logger.warning(f"Ошибка валидации твита: {e}")
        
        # Формируем отчет
        report = f"📊 **EXTRACT - СТРУКТУРИРОВАННЫЕ ДАННЫЕ**\n\n"
        report += f"✅ Извлечено {len(extracted_tweets)} твитов\n\n"
        
        for i, tweet in enumerate(extracted_tweets[:5], 1):
            report += f"**{i}.** {tweet.author}\n"
            report += f"   {tweet.text[:100]}...\n"
            if tweet.time:
                report += f"   🕐 {tweet.time[:10]}\n"
            if tweet.likes and tweet.likes != '0':
                report += f"   ❤️ {tweet.likes} | 🔄 {tweet.retweets or '0'}\n"
            report += "\n"
        
        if len(extracted_tweets) > 5:
            report += f"... и еще {len(extracted_tweets) - 5} твитов\n\n"
        
        # Сохраняем в JSON
        filename = f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([t.dict() for t in extracted_tweets], f, indent=2, ensure_ascii=False)
        
        report += f"📁 Данные сохранены в `{filename}`"
        
        await msg.edit_text(report, parse_mode='Markdown')
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"📄 {len(extracted_tweets)} твитов"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# КОМАНДА /login (РАБОЧАЯ ВЕРСИЯ)
# ============================================================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com с эмуляцией"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(random_delay(2.0, 4.0))
        
        auth_status = await execute_js('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const hasSignupLink = !!document.querySelector('a[href="/signup"]');
                const hasLoginButton = !!document.querySelector('[data-testid="loginButton"]');
                
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                if (!username) {
                    const accountBtn = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                    if (accountBtn) {
                        const text = accountBtn.textContent || '';
                        const match = text.match(/@([a-zA-Z0-9_]+)/);
                        if (match) username = match[1];
                    }
                }
                
                const hasNoLoginButtons = !hasLoginLink && !hasSignupLink && !hasLoginButton;
                const hasUserElements = hasProfileLink || hasSideNav || hasTweetBtn;
                const isLoggedIn = hasAuthToken || (hasNoLoginButtons && hasUserElements);
                
                return {
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    hasNoLoginButtons: hasNoLoginButtons,
                    hasUserElements: hasUserElements,
                    username: username || 'неизвестно',
                    isLoggedIn: isLoggedIn
                };
            }
        ''')
        
        if auth_status is None:
            await msg.edit_text("❌ Не удалось проверить авторизацию")
            return
        
        global login_status
        login_status['is_logged_in'] = auth_status.get('isLoggedIn', False)
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False)
        
        status_msg = f"✅ X.com ({engine_mode})\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status.get('hasCt0') else '❌'}\n\n"
        
        if auth_status.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username') and auth_status.get('username') != 'неизвестно':
                status_msg += f"👤 @{auth_status['username']}\n"
            status_msg += "\n💡 Теперь доступны расширенные функции:"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
            status_msg += "\nОбновите куки в коде"
        
        await msg.edit_text(status_msg)
        
        screenshot = await take_screenshot()
        if screenshot:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
                )
            else:
                await update.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
                )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 LOGIN", callback_data="login")],
        [InlineKeyboardButton("🛡️ SHADOW DOM", callback_data="shadow")],
        [InlineKeyboardButton("🌐 API", callback_data="api")],
        [InlineKeyboardButton("📊 EXTRACT", callback_data="extract")],
        [InlineKeyboardButton("📸 SCREEN", callback_data="screen")],
        [InlineKeyboardButton("📊 STATUS", callback_data="status")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот - Сила Pydoll**\n\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"🍪 Кук: {len(COOKIES)}\n"
        f"🎮 Движок: {engine_mode}\n\n"
        f"⚡ **Доступные функции:**\n"
        f"🛡️ **Shadow DOM** - работа с веб-компонентами\n"
        f"🌐 **API** - перехват и выполнение запросов\n"
        f"📊 **Extract** - структурированное извлечение\n\n"
        f"📌 Нажми кнопку:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "shadow":
        await shadow_dom(update, context)
    elif query.data == "api":
        await api_request(update, context)
    elif query.data == "extract":
        await extract_data(update, context)
    elif query.data == "screen":
        await screen_cmd(update, context)
    elif query.data == "status":
        await status_cmd(update, context)
    elif query.data == "close":
        await close_cmd(update, context)

# ========== КОМАНДЫ /status, /screen, /close ==========
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Статус...")
    else:
        msg = await update.message.reply_text("⏳ Статус...")
    
    status_msg = "📊 **СТАТУС**\n\n"
    status_msg += f"🔐 Авторизован: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username'] and login_status['username'] != 'неизвестно':
        status_msg += f"👤 @{login_status['username']}\n"
    status_msg += f"🍪 auth_token: {'✅' if login_status['cookies_valid'] else '❌'}\n"
    status_msg += f"🍪 Всего кук: {len(COOKIES)}\n"
    status_msg += f"🕐 Проверка: {login_status['last_check'].strftime('%d.%m.%Y %H:%M:%S') if login_status['last_check'] else 'Никогда'}"
    
    await msg.edit_text(status_msg, parse_mode='Markdown')

async def screen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Делаю скриншот...")
    else:
        msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(photo=screenshot, caption="📸 Скриншот X.com")
            else:
                await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот X.com")
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:100]}")

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("shadow", shadow_dom))
    app.add_handler(CommandHandler("api", api_request))
    app.add_handler(CommandHandler("extract", extract_data))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("screen", screen_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("\n" + "="*50)
    print("✅ БОТ ЗАПУЩЕН - СИЛА PYDOLL")
    print("="*50)
    print(f"📦 Pydantic: ✅")
    print(f"📦 Asyncio: ✅")
    print(f"🎮 Движок: {engine_mode}")
    print(f"🍪 Кук: {len(COOKIES)}")
    print("\n🔥 СИЛЬНЫЕ СТОРОНЫ PYDOLL:")
    print("  🛡️ Shadow DOM - работа с веб-компонентами")
    print("  🌐 API - гибридная автоматизация")
    print("  📊 Extract - структурированное извлечение")
    print("\n📌 Команды:")
    print("  /start - главное меню")
    print("  /login - авторизация в X.com")
    print("  /shadow - исследование Shadow DOM")
    print("  /api - выполнение API запросов")
    print("  /extract - извлечение структурированных данных")
    print("  /status - статус авторизации")
    print("  /screen - скриншот")
    print("  /close - закрыть браузер")
    print("="*50)
    
    app.run_polling()

if __name__ == "__main__":
    main()