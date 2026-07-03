import os
import logging
import asyncio
import base64
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Pydantic для структуры
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== PYDAВТИК МОДЕЛЬ ==========
class AuthStatusModel(BaseModel):
    is_logged_in: bool = False
    username: str | None = None
    has_auth_token: bool = False
    has_ct0: bool = False
    last_check: datetime | None = None
    cookies_valid: bool = False

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
engine_mode = "pydoll"
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== КУКИ ==========
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
]

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
        
        # Путь к Chromium для Railway
        chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
        for path in chromium_paths:
            if os.path.exists(path):
                options.binary_location = path
                logger.info(f"📍 Использую: {path}")
                break
        
        browser = Chrome(options=options)
        tab = await browser.start()
        logger.info("✅ Браузер запущен")
        
        # Устанавливаем куки
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        for cookie in COOKIES:
            try:
                await tab.set_cookie(**cookie)
                logger.debug(f"🍪 Кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка {cookie['name']}: {e}")
        
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
# КОМАНДА /login (РАБОЧАЯ ВЕРСИЯ)
# ============================================================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com с эмуляцией"""
    logger.info(f"📩 Команда /login от {update.effective_user.username}")
    
    # Определяем откуда пришел вызов (из кнопки или из чата)
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com...")
    else:
        msg = await update.message.reply_text(f"⏳ Захожу в X.com через {engine_mode}...")
    
    try:
        # 1. Получаем браузер
        page = await get_browser()
        if page is None:
            await msg.edit_text(f"❌ Не удалось запустить {engine_mode} браузер")
            return
        
        # 2. Переходим на X.com с эмуляцией
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(random_delay(2.0, 4.0))
        
        # 3. Проверяем авторизацию через JS
        auth_status = await execute_js('''
            () => {
                // Проверяем куки
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                
                // Проверяем наличие кнопок входа
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const hasSignupLink = !!document.querySelector('a[href="/signup"]');
                const hasLoginButton = !!document.querySelector('[data-testid="loginButton"]');
                
                // Проверяем элементы авторизованного пользователя
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                
                // Ищем username
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
        
        # 4. Обновляем глобальный статус
        global login_status
        login_status['is_logged_in'] = auth_status.get('isLoggedIn', False)
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False)
        
        # 5. Формируем ответ
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
            status_msg += "\nИспользуйте /setcookies для обновления кук"
        
        await msg.edit_text(status_msg)
        
        # 6. Делаем скриншот
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
        [InlineKeyboardButton("📸 SCREEN", callback_data="screen")],
        [InlineKeyboardButton("📊 STATUS", callback_data="status")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 X.com Бот\n\n"
        f"Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"Движок: {engine_mode}\n"
        f"🍪 Кук: {len(COOKIES)}\n\n"
        f"Нажми кнопку:",
        reply_markup=reply_markup
    )

# ========== КОМАНДА /status ==========
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Статус...")
    else:
        msg = await update.message.reply_text("⏳ Статус...")
    
    status_msg = "📊 СТАТУС\n\n"
    status_msg += f"🔐 Авторизован: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username'] and login_status['username'] != 'неизвестно':
        status_msg += f"👤 @{login_status['username']}\n"
    status_msg += f"🍪 auth_token: {'✅' if login_status['cookies_valid'] else '❌'}\n"
    status_msg += f"🍪 Всего кук: {len(COOKIES)}\n"
    status_msg += f"🕐 Проверка: {login_status['last_check'].strftime('%d.%m.%Y %H:%M:%S') if login_status['last_check'] else 'Никогда'}"
    
    await msg.edit_text(status_msg)

# ========== КОМАНДА /screen ==========
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

# ========== КОМАНДА /close ==========
async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "screen":
        await screen_cmd(update, context)
    elif query.data == "status":
        await status_cmd(update, context)
    elif query.data == "close":
        await close_cmd(update, context)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("screen", screen_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("\n" + "="*50)
    print("✅ БОТ ЗАПУЩЕН")
    print("="*50)
    print(f"📦 Pydantic: ✅")
    print(f"📦 Asyncio: ✅")
    print(f"🎮 Движок: {engine_mode}")
    print(f"🍪 Кук: {len(COOKIES)}")
    print("\n📌 Команды:")
    print("  /start - главное меню")
    print("  /login - авторизация в X.com")
    print("  /status - статус авторизации")
    print("  /screen - скриншот")
    print("  /close - закрыть браузер")
    print("="*50)
    
    app.run_polling()

if __name__ == "__main__":
    main()