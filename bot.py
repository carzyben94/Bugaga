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
    if not diagnostic_log:
        await update.message.reply_text("📋 Лог пуст.")
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
        
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await tab.set_cookie(**cookie)
                cookies_set += 1
                log_diagnostic(f"🍪 Кука: {cookie['name']}")
            except Exception as e:
                log_diagnostic(f"⚠️ Ошибка {cookie['name']}: {e}")
        
        log_diagnostic(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        return tab
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка: {e}")
        return None

async def close_browser():
    global browser, tab
    if browser:
        try:
            await browser.close()
            log_diagnostic("✅ Браузер закрыт")
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
        log_diagnostic(f"❌ Ошибка скриншота: {e}")
    return None

# ============================================================
# SHADOW DOM
# ============================================================
async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Исследую Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Исследую Shadow DOM...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        result = await page.execute_script('''
            function() {
                var elements = [];
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].shadowRoot) {
                        elements.push(all[i].tagName);
                    }
                }
                return elements;
            }
        ''')
        
        # Извлекаем результат правильно
        shadow_elements = result.get('result') if isinstance(result, dict) else result
        
        if shadow_elements and len(shadow_elements) > 0:
            await msg.edit_text(f"✅ Найдено {len(shadow_elements)} Shadow DOM элементов\n\n{', '.join(shadow_elements[:5])}")
        else:
            await msg.edit_text("❌ Shadow DOM элементы НЕ найдены")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# API
# ============================================================
async def api_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🌐 API запрос...")
    else:
        msg = await update.message.reply_text("🌐 API запрос...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
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
        
        # Извлекаем результат правильно
        cookies = cookies_data.get('result') if isinstance(cookies_data, dict) else cookies_data
        
        has_auth = 'auth_token' in cookies and cookies['auth_token'] and len(cookies['auth_token']) > 0
        
        report = "🌐 API\n\n"
        report += f"🍪 auth_token: {'✅' if has_auth else '❌'}\n"
        report += f"🍪 Всего кук: {len(cookies)}\n\n"
        
        if has_auth:
            report += "✅ Есть авторизация"
        else:
            report += "❌ Нет авторизации. Используй /login"
        
        await msg.edit_text(report)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# EXTRACT
# ============================================================
async def extract_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📊 Извлекаю данные...")
    else:
        msg = await update.message.reply_text("📊 Извлекаю данные...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Браузер не запущен")
            return
        
        tweets = await page.execute_script('''
            function() {
                var items = document.querySelectorAll('[data-testid="tweet"]');
                var result = [];
                var maxCount = Math.min(items.length, 10);
                
                for (var i = 0; i < maxCount; i++) {
                    var el = items[i];
                    var textEl = el.querySelector('[data-testid="tweetText"]');
                    var userEl = el.querySelector('[data-testid="User-Name"]');
                    
                    var text = textEl ? textEl.textContent : '';
                    var author = userEl ? userEl.textContent : '';
                    
                    if (text || author) {
                        result.push({
                            text: text.substring(0, 200),
                            author: author
                        });
                    }
                }
                return result;
            }
        ''')
        
        # Извлекаем результат правильно
        tweets_data = tweets.get('result') if isinstance(tweets, dict) else tweets
        
        if not tweets_data or len(tweets_data) == 0:
            await msg.edit_text("❌ Нет твитов на странице")
            return
        
        report = f"📊 EXTRACT\n\n✅ Извлечено {len(tweets_data)} твитов\n\n"
        
        for i, t in enumerate(tweets_data[:5], 1):
            report += f"{i}. {t.get('author', 'Unknown')}\n{t.get('text', '')[:100]}...\n\n"
        
        if len(tweets_data) > 5:
            report += f"... и еще {len(tweets_data) - 5} твитов"
        
        await msg.edit_text(report)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# LOGIN - ИСПРАВЛЕННЫЙ
# ============================================================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global login_status
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        # Проверяем куки
        cookies_result = await page.execute_script('''
            function() {
                var c = document.cookie.split(';');
                var hasAuth = false;
                var hasCt0 = false;
                var count = 0;
                for (var i = 0; i < c.length; i++) {
                    var parts = c[i].trim().split('=');
                    if (parts.length >= 2) {
                        count++;
                        if (parts[0] === 'auth_token' && parts[1] && parts[1].length > 0) {
                            hasAuth = true;
                        }
                        if (parts[0] === 'ct0' && parts[1] && parts[1].length > 0) {
                            hasCt0 = true;
                        }
                    }
                }
                return {
                    hasAuth: hasAuth,
                    hasCt0: hasCt0,
                    count: count
                };
            }
        ''')
        
        # Извлекаем результат правильно
        cookies_check = cookies_result.get('result') if isinstance(cookies_result, dict) else cookies_result
        
        # Ищем username
        username_result = await page.execute_script('''
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
        
        # Извлекаем username правильно
        username = username_result.get('result') if isinstance(username_result, dict) else username_result
        
        has_auth = cookies_check.get('hasAuth', False) if isinstance(cookies_check, dict) else False
        has_ct0 = cookies_check.get('hasCt0', False) if isinstance(cookies_check, dict) else False
        cookies_count = cookies_check.get('count', 0) if isinstance(cookies_check, dict) else 0
        
        log_diagnostic(f"🍪 auth_token: {'✅' if has_auth else '❌'}")
        log_diagnostic(f"🍪 ct0: {'✅' if has_ct0 else '❌'}")
        log_diagnostic(f"👤 Username: {username or 'не найден'}")
        
        # Сохраняем статус через Pydantic
        login_status = AuthStatus(
            is_logged_in=has_auth,
            username=username if username else None,
            has_auth_token=has_auth,
            has_ct0=has_ct0,
            cookies_count=cookies_count,
            last_check=datetime.now()
        )
        
        if has_auth:
            await msg.edit_text(f"✅ АВТОРИЗОВАН!\n👤 @{username or 'unknown'}")
        else:
            await msg.edit_text("❌ НЕ АВТОРИЗОВАН\n\nОбнови куки в коде")
        
        # Скриншот
        screenshot = await take_screenshot()
        if screenshot:
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(photo=screenshot)
            else:
                await update.message.reply_photo(photo=screenshot)
        
    except Exception as e:
        log_diagnostic(f"❌ Ошибка LOGIN: {e}")
        logger.error(traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# START
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
        [InlineKeyboardButton("📋 TEST", callback_data="test")],
    ]
    
    status = "✅" if login_status.is_logged_in else "❌"
    username = f" @{login_status.username}" if login_status.username else ""
    
    await update.message.reply_text(
        f"🤖 X.com Бот\n\n"
        f"Статус: {status}{username}\n"
        f"Кук: {login_status.cookies_count}\n"
        f"Движок: {engine_mode}\n\n"
        f"Нажми кнопку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================
# ОБРАБОТЧИК
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
# ВСПОМОГАТЕЛЬНЫЕ
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
    
    await msg.edit_text(status)

async def screen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Скриншот...")
    else:
        msg = await update.message.reply_text("⏳ Скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(photo=screenshot)
            else:
                await update.message.reply_photo(photo=screenshot)
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
    print("✅ БОТ ЗАПУЩЕН")
    print("="*50)
    print(f"🍪 Кук: {len(COOKIES)}")
    print(f"📦 Pydantic: ✅")
    print("\n📌 КОМАНДЫ:")
    print("  /start - меню")
    print("  /login - авторизация")
    print("  /shadow - Shadow DOM")
    print("  /api - API проверка")
    print("  /extract - извлечение")
    print("  /test - логи")
    print("  /status - статус")
    print("  /screen - скриншот")
    print("  /close - закрыть")
    print("="*50)
    
    app.run_polling()

if __name__ == "__main__":
    main()