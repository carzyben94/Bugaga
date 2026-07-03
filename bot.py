import os
import logging
import asyncio
import base64
import random
import json
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Pydantic
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== МОДЕЛИ PYDAВТИК ==========
class TweetExtract(BaseModel):
    text: str = ""
    author: str = ""
    time: str = ""
    likes: str = "0"
    retweets: str = "0"

class ShadowElement(BaseModel):
    tag: str
    id: str = ""
    class_name: str = ""
    shadow_children: int = 0

class ApiResult(BaseModel):
    status: int = 0
    ok: bool = False
    error: Optional[str] = None
    data: Optional[Dict] = None

class AuthStatus(BaseModel):
    is_logged_in: bool = False
    username: Optional[str] = None
    has_auth_token: bool = False
    has_ct0: bool = False
    cookies_count: int = 0
    last_check: Optional[datetime] = None

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
engine_mode = "pydoll"
login_status = AuthStatus()

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
diagnostic_log = []

# ========== ДИАГНОСТИКА ==========
def log_diagnostic(message: str):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    diagnostic_log.append(log_entry)
    logger.info(log_entry)

async def send_diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить лог диагностики в чат"""
    if not diagnostic_log:
        await update.message.reply_text("📋 Лог пуст. Выполни команды /shadow, /api, /extract сначала.")
        return
    
    log_text = "📋 ЛОГ ДИАГНОСТИКИ\n\n" + "\n".join(diagnostic_log[-50:])
    
    if len(log_text) > 4000:
        filename = f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(diagnostic_log))
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"📄 Лог диагностики ({len(diagnostic_log)} записей)"
        )
    else:
        await update.message.reply_text(log_text)

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
        
        log_diagnostic("🚀 Запускаю Pydoll браузер...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        
        chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
        for path in chromium_paths:
            if os.path.exists(path):
                options.binary_location = path
                log_diagnostic(f"📍 Использую Chromium: {path}")
                break
        
        browser = Chrome(options=options)
        tab = await browser.start()
        log_diagnostic("✅ Браузер запущен")
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        # Устанавливаем все куки
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await tab.set_cookie(**cookie)
                cookies_set += 1
                log_diagnostic(f"🍪 Кука установлена: {cookie['name']}")
            except Exception as e:
                log_diagnostic(f"⚠️ Ошибка установки {cookie['name']}: {e}")
                # Пробуем через JS
                try:
                    js_cookie = f"document.cookie='{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '.x.com')}; path={cookie.get('path', '/')}'"
                    await tab.execute_script(js_cookie)
                    cookies_set += 1
                    log_diagnostic(f"🍪 Кука установлена через JS: {cookie['name']}")
                except Exception as e2:
                    log_diagnostic(f"⚠️ Не удалось установить куку {cookie['name']}: {e2}")
        
        log_diagnostic(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        
        # Проверяем куки в браузере
        try:
            check_cookies = await tab.execute_script('document.cookie')
            log_diagnostic(f"📋 Куки в браузере: {check_cookies[:200]}...")
            if 'auth_token' in check_cookies:
                log_diagnostic("✅ auth_token найден в куках!")
            else:
                log_diagnostic("⚠️ auth_token НЕ найден в куках!")
        except Exception as e:
            log_diagnostic(f"❌ Ошибка проверки кук: {e}")
        
        return tab
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка запуска браузера: {e}")
        logger.error(traceback.format_exc())
        return None

async def close_browser():
    global browser, tab
    if browser:
        try:
            await browser.close()
            log_diagnostic("✅ Браузер закрыт")
        except Exception as e:
            log_diagnostic(f"⚠️ Ошибка закрытия: {e}")
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
        log_diagnostic(f"❌ Ошибка скриншота: {e}")
    return None

# ============================================================
# SHADOW DOM - С ПОЛНОЙ ДИАГНОСТИКОЙ
# ============================================================
async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Исследую Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    log_diagnostic("🛡️ === SHADOW DOM START ===")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен. Используй /login")
            return
        
        # Ищем элементы с shadowRoot
        result = await page.execute_script('''
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
        
        log_diagnostic(f"📊 Найдено элементов с Shadow DOM: {len(result) if result else 0}")
        
        # Формируем отчет
        report = "🛡️ SHADOW DOM\n\n"
        
        if result and len(result) > 0:
            report += f"✅ Найдено {len(result)} элементов с Shadow DOM:\n\n"
            for el in result[:5]:
                report += f"📦 {el.get('tag', '')}"
                if el.get('id'):
                    report += f" id={el.get('id')}"
                if el.get('class'):
                    report += f" class={el.get('class')}"
                report += f"\n   Дочерних в shadow: {len(el.get('shadowChildren', []))}\n\n"
                
                # Логируем каждый элемент
                log_diagnostic(f"  📦 {el.get('tag', '')} id={el.get('id', '')} shadow_children={len(el.get('shadowChildren', []))}")
        else:
            report += "❌ Shadow DOM элементы НЕ найдены\n\n"
            report += "💡 Что такое Shadow DOM?\n"
            report += "Это изолированная часть DOM, скрытая от основного документа.\n\n"
            report += "Где искать:\n"
            report += "1. Веб-компоненты\n"
            report += "2. Сложные UI элементы\n"
            report += "3. Сторонние виджеты"
        
        log_diagnostic("🛡️ === SHADOW DOM END ===")
        await msg.edit_text(report)
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка SHADOW: {e}")
        logger.error(traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# API - С ПОЛНОЙ ДИАГНОСТИКОЙ
# ============================================================
async def api_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🌐 Выполняю API запрос...")
    else:
        msg = await update.message.reply_text("🌐 Выполняю API запрос...")
    
    log_diagnostic("🌐 === API START ===")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен. Используй /login")
            return
        
        # Проверяем куки
        cookies_data = await page.execute_script('''
            function() {
                var c = document.cookie.split(';');
                var result = {};
                for (var i = 0; i < c.length; i++) {
                    var parts = c[i].trim().split('=');
                    if (parts.length >= 2) {
                        result[parts[0]] = parts[1];
                    }
                }
                return result;
            }
        ''')
        
        has_auth_token = 'auth_token' in cookies_data and cookies_data['auth_token'] and len(cookies_data['auth_token']) > 0
        has_ct0 = 'ct0' in cookies_data and cookies_data['ct0'] and len(cookies_data['ct0']) > 0
        
        log_diagnostic(f"🍪 auth_token: {'✅' if has_auth_token else '❌'}")
        log_diagnostic(f"🍪 ct0: {'✅' if has_ct0 else '❌'}")
        log_diagnostic(f"🍪 Всего кук: {len(cookies_data)}")
        
        # Пробуем сделать API запрос если есть авторизация
        api_result = None
        if has_auth_token:
            try:
                api_result = await page.execute_script('''
                    async function() {
                        try {
                            var response = await fetch('https://x.com/i/api/1.1/onboarding/task.json', {
                                method: 'GET',
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json'
                                }
                            });
                            var data = await response.json();
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
                    }
                ''')
                log_diagnostic(f"📊 API запрос: статус {api_result.get('status') if api_result else 'None'}")
            except Exception as e:
                log_diagnostic(f"⚠️ API запрос не удался: {e}")
        
        # Формируем отчет
        report = "🌐 API - ГИБРИДНАЯ АВТОМАТИЗАЦИЯ\n\n"
        
        report += "🍪 Куки в сессии:\n"
        report += f"  auth_token: {'✅' if has_auth_token else '❌'}\n"
        report += f"  ct0: {'✅' if has_ct0 else '❌'}\n"
        report += f"  Всего: {len(cookies_data)}\n\n"
        
        if api_result and not api_result.get('error'):
            report += f"📊 API Запрос:\n"
            report += f"  Статус: {api_result.get('status', 0)}\n"
            report += f"  Успешно: {'✅' if api_result.get('ok') else '❌'}\n"
            if api_result.get('data'):
                data_str = json.dumps(api_result['data'], indent=2, ensure_ascii=False)[:200]
                report += f"\n📝 Данные:\n{data_str}..."
        elif has_auth_token:
            report += "⚠️ API запрос не удался\n"
            report += f"  Ошибка: {api_result.get('error', 'Неизвестно') if api_result else 'Нет ответа'}"
        else:
            report += "❌ Нет авторизации. Используй /login"
        
        log_diagnostic("🌐 === API END ===")
        await msg.edit_text(report)
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка API: {e}")
        logger.error(traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# EXTRACT - С ПОЛНОЙ ДИАГНОСТИКОЙ
# ============================================================
async def extract_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📊 Извлекаю данные...")
    else:
        msg = await update.message.reply_text("📊 Извлекаю данные...")
    
    log_diagnostic("📊 === EXTRACT START ===")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен. Используй /login")
            return
        
        # Извлекаем твиты с полной информацией
        tweets = await page.execute_script('''
            function() {
                var items = document.querySelectorAll('[data-testid="tweet"]');
                var result = [];
                var maxCount = Math.min(items.length, 10);
                
                for (var i = 0; i < maxCount; i++) {
                    var el = items[i];
                    var textEl = el.querySelector('[data-testid="tweetText"]');
                    var userEl = el.querySelector('[data-testid="User-Name"]');
                    var timeEl = el.querySelector('time');
                    var likeEl = el.querySelector('[data-testid="like"]');
                    var retweetEl = el.querySelector('[data-testid="retweet"]');
                    
                    var text = textEl ? textEl.textContent : '';
                    var author = userEl ? userEl.textContent : '';
                    var time = timeEl ? timeEl.getAttribute('datetime') : '';
                    var likes = likeEl ? likeEl.textContent : '0';
                    var retweets = retweetEl ? retweetEl.textContent : '0';
                    
                    if (text || author) {
                        result.push({
                            text: text.substring(0, 500),
                            author: author,
                            time: time,
                            likes: likes,
                            retweets: retweets
                        });
                    }
                }
                return result;
            }
        ''')
        
        log_diagnostic(f"📊 Найдено твитов: {len(tweets) if tweets else 0}")
        
        if not tweets or len(tweets) == 0:
            await msg.edit_text("❌ Нет твитов на странице\n\nПерейди на страницу с твитами")
            return
        
        # Конвертируем в Pydantic модели
        extracted_tweets = []
        for tweet in tweets:
            try:
                extracted_tweets.append(TweetExtract(**tweet))
                log_diagnostic(f"  ✅ Твит от {tweet.get('author', 'unknown')[:30]}")
            except Exception as e:
                log_diagnostic(f"  ⚠️ Ошибка валидации: {e}")
        
        # Формируем отчет
        report = f"📊 EXTRACT - СТРУКТУРИРОВАННЫЕ ДАННЫЕ\n\n"
        report += f"✅ Извлечено {len(extracted_tweets)} твитов\n\n"
        
        for i, tweet in enumerate(extracted_tweets[:5], 1):
            report += f"{i}. {tweet.author}\n"
            report += f"   {tweet.text[:100]}...\n"
            if tweet.time:
                report += f"   🕐 {tweet.time[:10]}\n"
            if tweet.likes != '0':
                report += f"   ❤️ {tweet.likes} | 🔄 {tweet.retweets}\n"
            report += "\n"
        
        if len(extracted_tweets) > 5:
            report += f"... и еще {len(extracted_tweets) - 5} твитов"
        
        # Сохраняем в JSON
        if extracted_tweets:
            filename = f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([t.dict() for t in extracted_tweets], f, indent=2, ensure_ascii=False)
            log_diagnostic(f"📁 Сохранено в {filename}")
            
            await msg.edit_text(report)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 {len(extracted_tweets)} твитов"
            )
        else:
            await msg.edit_text(report)
        
        log_diagnostic("📊 === EXTRACT END ===")
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка EXTRACT: {e}")
        logger.error(traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# КОМАНДА /login
# ============================================================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global login_status
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text(f"⏳ Захожу в X.com...")
    
    log_diagnostic("🔐 === LOGIN START ===")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        # Проверяем куки
        cookies_data = await page.execute_script('''
            function() {
                var c = document.cookie.split(';');
                var result = {};
                for (var i = 0; i < c.length; i++) {
                    var parts = c[i].trim().split('=');
                    if (parts.length >= 2) {
                        result[parts[0]] = parts[1];
                    }
                }
                return result;
            }
        ''')
        
        has_auth_token = 'auth_token' in cookies_data and cookies_data['auth_token'] and len(cookies_data['auth_token']) > 0
        has_ct0 = 'ct0' in cookies_data and cookies_data['ct0'] and len(cookies_data['ct0']) > 0
        
        log_diagnostic(f"🍪 auth_token: {'✅' if has_auth_token else '❌'}")
        log_diagnostic(f"🍪 ct0: {'✅' if has_ct0 else '❌'}")
        log_diagnostic(f"🍪 Всего кук: {len(cookies_data)}")
        
        # Ищем username
        username = await page.execute_script('''
            function() {
                var link = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (link) {
                    var href = link.getAttribute('href');
                    if (href) {
                        var match = href.match(/^\\/([^\\/]+)/);
                        if (match) return match[1];
                    }
                }
                return null;
            }
        ''')
        
        log_diagnostic(f"👤 Username: {username or 'не найден'}")
        
        # Обновляем статус через Pydantic
        login_status = AuthStatus(
            is_logged_in=has_auth_token,
            username=username,
            has_auth_token=has_auth_token,
            has_ct0=has_ct0,
            cookies_count=len(cookies_data),
            last_check=datetime.now()
        )
        
        if has_auth_token:
            await msg.edit_text(f"✅ АВТОРИЗОВАН!\n👤 @{username or 'unknown'}")
            log_diagnostic("✅ АВТОРИЗОВАН")
        else:
            await msg.edit_text("❌ НЕ АВТОРИЗОВАН\n\nОбнови куки в коде")
            log_diagnostic("❌ НЕ АВТОРИЗОВАН")
        
        # Скриншот
        screenshot = await take_screenshot()
        if screenshot:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(photo=screenshot)
            else:
                await update.message.reply_photo(photo=screenshot)
            log_diagnostic("📸 Скриншот отправлен")
        
        log_diagnostic("🔐 === LOGIN END ===")
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка LOGIN: {e}")
        logger.error(traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# КОМАНДА /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 LOGIN", callback_data="login")],
        [InlineKeyboardButton("🛡️ SHADOW", callback_data="shadow")],
        [InlineKeyboardButton("🌐 API", callback_data="api")],
        [InlineKeyboardButton("📊 EXTRACT", callback_data="extract")],
        [InlineKeyboardButton("📸 SCREEN", callback_data="screen")],
        [InlineKeyboardButton("📊 STATUS", callback_data="status")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="close")],
        [InlineKeyboardButton("📋 TEST (лог)", callback_data="test")],
    ]
    
    status = "✅ Авторизован" if login_status.is_logged_in else "❌ Не авторизован"
    username = f" @{login_status.username}" if login_status.username else ""
    
    await update.message.reply_text(
        f"🤖 X.com Бот\n\n"
        f"Статус: {status}{username}\n"
        f"Кук: {login_status.cookies_count}\n"
        f"Движок: {engine_mode}\n\n"
        f"📋 Нажми /test для логов\n\n"
        f"Нажми кнопку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================
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
    elif query.data == "test":
        await send_diagnostic(update, context)

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ КОМАНДЫ
# ============================================================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Статус...")
    else:
        msg = await update.message.reply_text("⏳ Статус...")
    
    status = f"📊 СТАТУС\n\n"
    status += f"🔐 Авторизован: {'✅' if login_status.is_logged_in else '❌'}\n"
    if login_status.username:
        status += f"👤 @{login_status.username}\n"
    status += f"🍪 auth_token: {'✅' if login_status.has_auth_token else '❌'}\n"
    status += f"🍪 ct0: {'✅' if login_status.has_ct0 else '❌'}\n"
    status += f"🍪 Всего кук: {login_status.cookies_count}\n"
    status += f"🕐 Проверка: {login_status.last_check.strftime('%d.%m.%Y %H:%M:%S') if login_status.last_check else 'Никогда'}"
    
    await msg.edit_text(status)

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
                await update.callback_query.message.reply_photo(photo=screenshot)
            else:
                await update.message.reply_photo(photo=screenshot)
            log_diagnostic("📸 Скриншот отправлен")
        else:
            await msg.edit_text("❌ Не удалось")
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:100]}")

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт")

# ============================================================
# ЗАПУСК
# ============================================================
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
    app.add_handler(CommandHandler("test", send_diagnostic))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("\n" + "="*50)
    print("✅ БОТ ЗАПУЩЕН С PYDAВТИК")
    print("="*50)
    print(f"🍪 Кук: {len(COOKIES)}")
    print(f"📦 Pydantic: ✅")
    print("\n📌 КОМАНДЫ:")
    print("  /start - меню")
    print("  /login - авторизация")
    print("  /shadow - Shadow DOM")
    print("  /api - API проверка")
    print("  /extract - извлечение твитов")
    print("  /test - логи диагностики")
    print("  /status - статус")
    print("  /screen - скриншот")
    print("  /close - закрыть браузер")
    print("="*50)
    
    app.run_polling()

if __name__ == "__main__":
    main()