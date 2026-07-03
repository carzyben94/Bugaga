import os
import logging
import asyncio
import base64
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Pydantic для валидации данных
from pydantic import BaseModel, Field, validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не задан!")
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== PYDAВТИК МОДЕЛИ ==========
class CookieData(BaseModel):
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    domain: str = Field(default=".x.com")
    path: str = Field(default="/")

class UserData(BaseModel):
    user_id: int = Field(..., gt=0)
    username: Optional[str] = None
    first_name: str = Field(..., min_length=1)
    last_name: Optional[str] = None
    is_bot: bool = False
    language_code: Optional[str] = None

class AuthStatus(BaseModel):
    is_logged_in: bool = False
    username: Optional[str] = None
    has_auth_token: bool = False
    has_ct0: bool = False
    last_check: Optional[datetime] = None
    cookies_count: int = 0

# ========== ПРОВЕРКА EXTRACTOR ==========
EXTRACTOR_AVAILABLE = False
try:
    from pydoll.extractor import ExtractionModel, Field as ExtractField
    EXTRACTOR_AVAILABLE = True
    logger.info("✅ Pydoll Extractor доступен!")
except ImportError:
    logger.warning("⚠️ Pydoll Extractor не доступен")

# ========== КУКИ X.COM ==========
COOKIES: List[CookieData] = [
    CookieData(name="__cuid", value="55d2d7c5-4888-430a-b024-dd785da46ef4"),
    CookieData(name="lang", value="ru"),
    CookieData(name="dnt", value="1"),
    CookieData(name="guest_id", value="v1%3A178267838599411411"),
    CookieData(name="guest_id_marketing", value="v1%3A178267838599411411"),
    CookieData(name="guest_id_ads", value="v1%3A178267838599411411"),
    CookieData(name="personalization_id", value="\"v1_DKrxLZAC902dMFdd1QrVYg==\""),
    CookieData(name="twid", value="u%3D2067347503503052800"),
    CookieData(name="auth_token", value="c9d83e923e1ad6cf67d19a0bc4f9877a49087936"),
    CookieData(name="ct0", value="39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"),
]

logger.info(f"🍪 Загружено {len(COOKIES)} кук")

# ========== ГЛОБАЛЬНЫЙ СТАТУС ==========
login_status = AuthStatus(
    is_logged_in=False,
    username=None,
    has_auth_token=False,
    has_ct0=False,
    last_check=None,
    cookies_count=len(COOKIES)
)
users: Dict[int, UserData] = {}
browser = None
tab = None

# ========== PYDOLL БРАУЗЕР ==========
async def get_browser():
    global browser, tab
    
    if tab:
        try:
            await tab.execute_script('1')
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
        
        for cookie in COOKIES:
            try:
                await tab.set_cookie(
                    name=cookie.name,
                    value=cookie.value,
                    domain=cookie.domain,
                    path=cookie.path
                )
                logger.debug(f"🍪 Кука: {cookie.name}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка {cookie.name}: {e}")
        
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
        except Exception as e:
            logger.warning(f"⚠️ Ошибка: {e}")
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
        logger.error(f"❌ Ошибка: {e}")
    return None

# ========== SHADOW DOM ==========
async def shadow_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        shadow_elements = await page.execute_script('''
            function() {
                var elements = [];
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    if (el.shadowRoot) {
                        var shadowChildren = [];
                        var children = el.shadowRoot.childNodes;
                        for (var j = 0; j < children.length; j++) {
                            var child = children[j];
                            if (child.nodeType === 1) {
                                shadowChildren.push({
                                    tag: child.tagName,
                                    id: child.id || '',
                                    class: child.className || ''
                                });
                            }
                        }
                        elements.push({
                            tag: el.tagName,
                            id: el.id || '',
                            class: el.className || '',
                            shadowChildren: shadowChildren
                        });
                    }
                }
                return elements;
            }
        ''')
        
        report = "🛡️ SHADOW DOM - МОЩЬ PYDOLL\n\n"
        
        if shadow_elements and len(shadow_elements) > 0:
            report += f"✅ Найдено {len(shadow_elements)} элементов с Shadow DOM:\n\n"
            for el in shadow_elements[:3]:
                report += f"📦 {el.get('tag', '')}"
                if el.get('id'):
                    report += f" id={el.get('id')}"
                report += f"\n   Дочерних: {len(el.get('shadowChildren', []))}\n\n"
        else:
            report += "ℹ️ На X.com нет Shadow DOM элементов\n\n"
        
        report += "💡 Как Pydoll работает с Shadow DOM:\n"
        report += "host = await tab.find('#shadow-host')\n"
        report += "shadow_root = await host.get_shadow_root()\n"
        report += "inner = await shadow_root.query('.inner-class')"
        
        await msg.edit_text(report)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== API ==========
async def api_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌐 Выполняю API запрос...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        api_url = "https://x.com/i/api/1.1/onboarding/task.json"
        
        js_code = """
            (async () => {
                try {
                    const response = await fetch('""" + api_url + """', {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json'
                        }
                    });
                    
                    const data = await response.json();
                    return {
                        status: response.status,
                        ok: response.ok,
                        data: data
                    };
                } catch (e) {
                    return {
                        error: e.message,
                        status: 0
                    };
                }
            })()
        """
        
        result = await page.execute_script(js_code)
        
        cookies_check = await page.execute_script('''
            function() {
                var cookies = document.cookie.split(';').reduce(function(acc, c) {
                    var parts = c.trim().split('=');
                    acc[parts[0]] = parts[1];
                    return acc;
                }, {});
                return {
                    has_auth_token: !!cookies.auth_token,
                    has_ct0: !!cookies.ct0,
                    cookies_count: Object.keys(cookies).length
                };
            }
        ''')
        
        report = "🌐 API - МОЩЬ PYDOLL\n\n"
        
        report += "🍪 Куки:\n"
        report += f"  auth_token: {'✅' if cookies_check.get('has_auth_token') else '❌'}\n"
        report += f"  ct0: {'✅' if cookies_check.get('has_ct0') else '❌'}\n"
        report += f"  Всего: {cookies_check.get('cookies_count', 0)}\n\n"
        
        if result and not result.get('error'):
            report += f"📊 API Запрос:\n"
            report += f"  Статус: {result.get('status', 0)}\n"
            report += f"  Успешно: {'✅' if result.get('ok') else '❌'}\n\n"
        else:
            report += "❌ API не работает\n"
        
        report += "💡 Преимущества Pydoll:\n"
        report += "  - Автоматическая авторизация\n"
        report += "  - Перехват запросов\n"
        report += "  - Эмуляция браузера"
        
        await msg.edit_text(report)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== EXTRACT ==========
async def extract_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📊 Извлекаю данные...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        # Сначала проверяем авторизацию
        check_login = await page.execute_script('''
            function() {
                var cookies = document.cookie.split(';').reduce(function(acc, c) {
                    var parts = c.trim().split('=');
                    acc[parts[0]] = parts[1];
                    return acc;
                }, {});
                return !!cookies.auth_token;
            }
        ''')
        
        if not check_login:
            await msg.edit_text("❌ Вы не авторизованы!\nИспользуйте /login")
            return
        
        # Проверяем твиты
        check_tweets = await page.execute_script('''
            function() {
                var tweets = document.querySelectorAll('[data-testid="tweet"]');
                return {
                    count: tweets.length,
                    hasData: tweets.length > 0
                };
            }
        ''')
        
        if not check_tweets.get('hasData', False):
            await msg.edit_text("❌ Нет твитов на странице!\nПерейдите на страницу с твитами")
            return
        
        js_extract = """
            function() {
                var tweets = [];
                var elements = document.querySelectorAll('[data-testid="tweet"]');
                for (var i = 0; i < elements.length && i < 10; i++) {
                    var el = elements[i];
                    var textEl = el.querySelector('[data-testid="tweetText"]');
                    var userEl = el.querySelector('[data-testid="User-Name"]');
                    var timeEl = el.querySelector('time');
                    
                    tweets.push({
                        text: textEl ? textEl.textContent : '',
                        author: userEl ? userEl.textContent : '',
                        time: timeEl ? timeEl.getAttribute('datetime') : ''
                    });
                }
                return tweets;
            }
        """
        
        extracted = await page.execute_script(js_extract)
        
        if not extracted or len(extracted) == 0:
            await msg.edit_text("⚠️ Данные не извлечены")
            return
        
        report = f"📊 EXTRACT - МОЩЬ PYDOLL\n\n"
        report += f"✅ Извлечено {len(extracted)} твитов\n\n"
        
        for i, tweet in enumerate(extracted[:5], 1):
            author = tweet.get('author', 'Unknown')
            text = tweet.get('text', '')[:150]
            report += f"{i}. {author}\n"
            report += f"{text}\n\n"
        
        if len(extracted) > 5:
            report += f"... и еще {len(extracted) - 5} твитов"
        
        filename = f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(extracted, f, indent=2, ensure_ascii=False)
        
        await msg.edit_text(report)
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"📄 {len(extracted)} твитов"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /login ==========
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global login_status
    
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        auth_data = await page.execute_script('''
            function() {
                var cookies = document.cookie.split(';').reduce(function(acc, c) {
                    var parts = c.trim().split('=');
                    acc[parts[0]] = parts[1];
                    return acc;
                }, {});
                
                var hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                var hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                
                var username = null;
                var profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    var href = profileLink.getAttribute('href');
                    if (href) {
                        var match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                return {
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    username: username || 'неизвестно',
                    isLoggedIn: hasAuthToken
                };
            }
        ''')
        
        if not auth_data:
            await msg.edit_text("❌ Не удалось проверить авторизацию")
            return
        
        login_status = AuthStatus(
            is_logged_in=auth_data.get('isLoggedIn', False),
            username=auth_data.get('username'),
            has_auth_token=auth_data.get('hasAuthToken', False),
            has_ct0=auth_data.get('hasCt0', False),
            last_check=datetime.now(),
            cookies_count=len(COOKIES)
        )
        
        status_msg = "✅ X.com\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_data.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_data.get('hasCt0') else '❌'}\n\n"
        
        if login_status.is_logged_in:
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if login_status.username and login_status.username != 'неизвестно':
                status_msg += f"👤 @{login_status.username}\n"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if login_status.is_logged_in else '❌ Не авторизован'}"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        user_data = UserData(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            is_bot=user.is_bot,
            language_code=user.language_code
        )
        users[user.id] = user_data
        logger.info(f"✅ Пользователь: {user_data.first_name}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    
    keyboard = [
        [InlineKeyboardButton("🔐 Авторизация", callback_data="login")],
        [InlineKeyboardButton("🛡️ Shadow DOM", callback_data="shadow")],
        [InlineKeyboardButton("🌐 API Запрос", callback_data="api")],
        [InlineKeyboardButton("📊 Extract Данные", callback_data="extract")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screen")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Обновить куки", callback_data="cookies")],
        [InlineKeyboardButton("❌ Закрыть браузер", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status.is_logged_in else "❌"
    username_text = f" @{login_status.username}" if login_status.username else ""
    
    await update.message.reply_text(
        f"🤖 X.com Бот - Сила Pydoll\n\n"
        f"🔐 Статус: {status_emoji} {login_status.is_logged_in and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"🍪 Кук: {login_status.cookies_count}\n"
        f"👤 Пользователей: {len(users)}\n\n"
        f"⚡ Сильные стороны Pydoll:\n"
        f"🛡️ Shadow DOM - работа с веб-компонентами\n"
        f"🌐 API - перехват и выполнение запросов\n"
        f"📊 Extract - структурированное извлечение\n\n"
        f"📌 Выберите действие:",
        reply_markup=reply_markup
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "shadow":
        await shadow_power(update, context)
    elif query.data == "api":
        await api_power(update, context)
    elif query.data == "extract":
        await extract_power(update, context)
    elif query.data == "screen":
        await screen(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "cookies":
        await cookies_menu(update, context)
    elif query.data == "close":
        await close(update, context)

# ========== ДРУГИЕ КОМАНДЫ ==========
async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Проверяю статус...")
    else:
        msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    status_msg = "📊 СТАТУС\n\n"
    status_msg += f"🔐 Авторизован: {'✅' if login_status.is_logged_in else '❌'}\n"
    if login_status.username and login_status.username != 'неизвестно':
        status_msg += f"👤 @{login_status.username}\n"
    status_msg += f"🍪 auth_token: {'✅' if login_status.has_auth_token else '❌'}\n"
    status_msg += f"🍪 ct0: {'✅' if login_status.has_ct0 else '❌'}\n"
    status_msg += f"🍪 Всего кук: {login_status.cookies_count}\n"
    status_msg += f"👤 Пользователей: {len(users)}\n"
    status_msg += f"⚡ Extractor: {'✅' if EXTRACTOR_AVAILABLE else '❌'}\n"
    status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    await msg.edit_text(status_msg)

async def cookies_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("📋 Показать куки", callback_data="show_cookies")],
        [InlineKeyboardButton("🔄 Вставить новые", callback_data="set_cookies")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🍪 Управление куками", reply_markup=reply_markup)

async def show_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "📋 Текущие куки:\n\n"
    for cookie in COOKIES[:5]:
        text += f"  {cookie.name}: {cookie.value[:30]}...\n"
    if len(COOKIES) > 5:
        text += f"\n... и еще {len(COOKIES) - 5} кук"
    await query.edit_message_text(text)

async def set_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text(
        "🍪 Введите новые куки\n\n"
        "JSON формат:\n"
        '[{"name":"auth_token","value":"токен"}]\n\n'
        "Или /cancel для отмены"
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_cookies'):
        return
    
    text = update.message.text.strip()
    if text.lower() == '/cancel':
        context.user_data['waiting_for_cookies'] = False
        await update.message.reply_text("❌ Отменено")
        return
    
    try:
        data = json.loads(text)
        new_cookies = []
        
        if isinstance(data, list):
            for cookie in data:
                if 'name' in cookie and 'value' in cookie:
                    new_cookies.append(CookieData(**cookie))
        elif isinstance(data, dict):
            for name, value in data.items():
                if value:
                    new_cookies.append(CookieData(name=name, value=value))
        
        if new_cookies:
            global COOKIES, login_status
            COOKIES = new_cookies
            login_status.cookies_count = len(COOKIES)
            context.user_data['waiting_for_cookies'] = False
            await close_browser()
            await update.message.reply_text(f"✅ Обновлено {len(COOKIES)} кук!\nИспользуйте /login")
        else:
            await update.message.reply_text("❌ Не удалось распознать куки")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("shadow", shadow_power))
    app.add_handler(CommandHandler("api", api_power))
    app.add_handler(CommandHandler("extract", extract_power))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(login|shadow|api|extract|screen|status|cookies|close)$"))
    app.add_handler(CallbackQueryHandler(show_cookies, pattern="^show_cookies$"))
    app.add_handler(CallbackQueryHandler(set_cookies, pattern="^set_cookies$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(cookies_menu, pattern="^cookies_menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n⚡ БОТ ЗАПУЩЕН - СИЛА PYDOLL!")
    print(f"🍪 Кук: {len(COOKIES)}")
    print(f"📦 Extractor: {'✅' if EXTRACTOR_AVAILABLE else '❌'}")
    print("\n🔥 СИЛЬНЫЕ СТОРОНЫ:")
    print("  /shadow - Shadow DOM")
    print("  /api - API запросы")
    print("  /extract - Извлечение данных")
    print("\n📌 Остальные команды:")
    print("  /start - меню")
    print("  /login - авторизация")
    print("  /screen - скриншот")
    print("  /status - статус")
    print("  /close - закрыть браузер")
    
    app.run_polling()

if __name__ == "__main__":
    main()