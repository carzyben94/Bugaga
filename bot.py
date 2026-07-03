import os
import logging
import asyncio
import base64
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ========== КУКИ X.COM (ИЗ ПРИМЕРА) ==========
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

logger.info(f"🍪 Загружено {len(COOKIES)} кук для X.com")

# ========== ГЛОБАЛЬНЫЙ СТАТУС ==========
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== PYDOLL БРАУЗЕР ==========
browser = None
tab = None

async def get_browser():
    """Получить Pydoll браузер"""
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
        
        # Путь к Chromium (для Railway)
        chromium_paths = [
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable'
        ]
        found_path = None
        for path in chromium_paths:
            if os.path.exists(path):
                found_path = path
                break
        
        if found_path:
            options.binary_location = found_path
            logger.info(f"📍 Использую Chromium по пути: {found_path}")
        else:
            logger.warning("⚠️ Chromium не найден, пробую без указания пути")
        
        browser = Chrome(options=options)
        tab = await browser.start()
        logger.info("✅ Браузер запущен")
        
        # Переход на X.com и установка кук
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        cookies_set = 0
        for cookie in COOKIES:
            try:
                await tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain', '.x.com'),
                    path=cookie.get('path', '/')
                )
                cookies_set += 1
                logger.debug(f"🍪 Кука установлена: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка куки {cookie['name']}: {e}")
                # Пробуем через JS
                try:
                    js_cookie = f"document.cookie='{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '.x.com')}; path={cookie.get('path', '/')}'"
                    await tab.execute_script(js_cookie)
                    cookies_set += 1
                    logger.debug(f"🍪 Кука установлена через JS: {cookie['name']}")
                except Exception as e2:
                    logger.warning(f"⚠️ Не удалось установить куку {cookie['name']}: {e2}")
        
        logger.info(f"🍪 Установлено {cookies_set} из {len(COOKIES)} кук")
        
        # Проверяем куки
        try:
            check_cookies = await tab.execute_script('document.cookie')
            logger.info(f"📋 Куки в браузере: {check_cookies[:200]}...")
            if 'auth_token' in check_cookies:
                logger.info("✅ auth_token найден в куках!")
            else:
                logger.warning("⚠️ auth_token НЕ найден в куках!")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки кук: {e}")
        
        return tab
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        return None

async def close_browser():
    """Закрыть браузер"""
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
    """Сделать скриншот"""
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

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое меню с кнопками"""
    logger.info(f"📩 Команда /start от {update.effective_user.username}")
    
    keyboard = [
        [
            InlineKeyboardButton("🔐 Авторизация", callback_data="login"),
            InlineKeyboardButton("📸 Скриншот", callback_data="screen"),
        ],
        [
            InlineKeyboardButton("📊 Статус", callback_data="status"),
            InlineKeyboardButton("🍪 Обновить куки", callback_data="cookies"),
        ],
        [
            InlineKeyboardButton("❌ Закрыть браузер", callback_data="close"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"🍪 Кук загружено: {len(COOKIES)}\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"📌 **Нажмите кнопку для выполнения:**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "login":
        await login(update, context)
    elif callback_data == "screen":
        await screen(update, context)
    elif callback_data == "status":
        await status(update, context)
    elif callback_data == "cookies":
        await cookies_menu(update, context)
    elif callback_data == "close":
        await close(update, context)

# ========== КОМАНДА /login ==========
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Захожу в X.com через Pydoll...")
    else:
        msg = await update.message.reply_text("⏳ Захожу в X.com через Pydoll...")
    
    try:
        page = await get_browser()
        if not page:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        # Проверяем авторизацию через JS
        auth_status = await page.execute_script('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                
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
                
                const isLoggedIn = hasAuthToken;
                
                return {
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    username: username || 'неизвестно',
                    isLoggedIn: isLoggedIn
                };
            }
        ''')
        
        if not auth_status:
            await msg.edit_text("❌ Не удалось проверить авторизацию")
            return
        
        # Обновляем статус
        login_status['is_logged_in'] = auth_status.get('isLoggedIn', False)
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status.get('hasAuthToken', False)
        
        # Формируем ответ
        status_msg = f"✅ X.com (Pydoll)\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status.get('hasCt0') else '❌'}\n\n"
        
        if auth_status.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username') and auth_status.get('username') != 'неизвестно':
                status_msg += f"👤 @{auth_status['username']}\n"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
            status_msg += "\nИспользуйте кнопку '🍪 Обновить куки'"
        
        await msg.edit_text(status_msg)
        
        # Делаем скриншот
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
        else:
            await update.message.reply_text("⚠️ Не удалось сделать скриншот")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /screen ==========
async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Делаю скриншот...")
    else:
        msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            if hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=screenshot,
                    caption="📸 Скриншот X.com"
                )
            else:
                await update.message.reply_photo(
                    photo=screenshot,
                    caption="📸 Скриншот X.com"
                )
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /status ==========
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Проверяю статус...")
    else:
        msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    status_msg = "📊 **СТАТУС**\n\n"
    status_msg += f"🔐 Авторизован: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username'] and login_status['username'] != 'неизвестно':
        status_msg += f"👤 @{login_status['username']}\n"
    status_msg += f"🍪 Куки валидны: {'✅' if login_status['cookies_valid'] else '❌'}\n"
    status_msg += f"🍪 Всего кук: {len(COOKIES)}\n"
    status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    await msg.edit_text(status_msg, parse_mode='Markdown')

# ========== МЕНЮ ОБНОВЛЕНИЯ КУК ==========
async def cookies_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню обновления кук"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("📋 Показать текущие куки", callback_data="show_cookies")],
        [InlineKeyboardButton("🔄 Вставить новые куки", callback_data="set_cookies")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🍪 **Управление куками**\n\n"
        f"📦 Всего кук: {len(COOKIES)}\n"
        f"🔐 auth_token: {'✅' if any(c['name'] == 'auth_token' for c in COOKIES) else '❌'}\n"
        f"🔐 ct0: {'✅' if any(c['name'] == 'ct0' for c in COOKIES) else '❌'}\n\n"
        f"📌 Выберите действие:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущие куки"""
    query = update.callback_query
    
    cookie_text = "📋 **Текущие куки:**\n\n"
    for cookie in COOKIES[:5]:
        cookie_text += f"• {cookie['name']}: {cookie['value'][:30]}...\n"
    if len(COOKIES) > 5:
        cookie_text += f"\n... и еще {len(COOKIES) - 5} кук"
    
    cookie_text += "\n\nДля обновления нажмите 'Вставить новые куки'"
    
    await query.edit_message_text(
        cookie_text,
        parse_mode='Markdown'
    )

async def set_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать ввод новых кук"""
    query = update.callback_query
    await query.edit_message_text(
        "🍪 **Введите новые куки**\n\n"
        "Отправьте куки в JSON формате:\n"
        "```json\n"
        "[{\"name\":\"auth_token\",\"value\":\"ваш_токен\",\"domain\":\".x.com\",\"path\":\"/\"}]\n"
        "```\n\n"
        "Или отправьте:\n"
        "```json\n"
        "{\"auth_token\":\"ваш_токен\",\"ct0\":\"ваш_ct0\"}\n"
        "```\n\n"
        "📌 Отправьте /cancel для отмены",
        parse_mode='Markdown'
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенных кук"""
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
                    new_cookies.append({
                        "name": cookie['name'],
                        "value": cookie['value'],
                        "domain": cookie.get('domain', '.x.com'),
                        "path": cookie.get('path', '/')
                    })
        elif isinstance(data, dict):
            for name, value in data.items():
                if value:
                    new_cookies.append({
                        "name": name,
                        "value": value,
                        "domain": ".x.com",
                        "path": "/"
                    })
        
        if new_cookies:
            global COOKIES
            COOKIES = new_cookies
            context.user_data['waiting_for_cookies'] = False
            
            # Закрываем браузер чтобы применить новые куки
            await close_browser()
            
            await update.message.reply_text(
                f"✅ **Куки обновлены!**\n\n"
                f"📦 Всего: {len(COOKIES)} кук\n"
                f"🍪 Включены: {', '.join([c['name'] for c in COOKIES][:5])}\n\n"
                f"Используйте /login для проверки"
            )
        else:
            await update.message.reply_text("❌ Не удалось распознать куки")
            
    except json.JSONDecodeError as e:
        await update.message.reply_text(f"❌ Ошибка JSON: {e}\n\nОтправьте /cancel для отмены")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ========== КОМАНДА /close ==========
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть браузер"""
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== КОМАНДА /cancel ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(login|screen|status|cookies|close)$"))
    app.add_handler(CallbackQueryHandler(show_cookies, pattern="^show_cookies$"))
    app.add_handler(CallbackQueryHandler(set_cookies, pattern="^set_cookies$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(cookies_menu, pattern="^cookies_menu$"))
    
    # Обработчик ввода кук
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n✅ Бот запущен!")
    print("📌 /start - главное меню")
    print("📌 /login - авторизация")
    print("📌 /screen - скриншот")
    print("📌 /status - статус")
    print("📌 /close - закрыть браузер")
    print("📌 /cancel - отменить ввод кук")
    print("\n🍪 Куки загружены из примера!")
    
    app.run_polling()

if __name__ == "__main__":
    main()