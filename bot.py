import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
import random
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ПРОВЕРКА CHROMIUM ==========
CHROMIUM_PATH = None
CHROMIUM_INSTALLED = False

def check_chromium():
    global CHROMIUM_PATH, CHROMIUM_INSTALLED
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    for path in chromium_paths:
        if os.path.exists(path):
            CHROMIUM_PATH = path
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден: {path}")
            return True
    return False

check_chromium()

# ========== ПРОВЕРКА PYDOLL ==========
PYDOLL_AVAILABLE = False

try:
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions
    PYDOLL_AVAILABLE = True
    logger.info("✅ Pydoll загружен")
except ImportError as e:
    logger.warning(f"⚠️ Pydoll не найден: {e}")

# ========== КУКИ X.COM ==========
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ БРАУЗЕРА ==========
pydoll_browser = None
pydoll_tab = None
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None
}

# ========== БРАУЗЕРНАЯ ЛОГИКА ==========

def random_delay(min_sec=0.5, max_sec=2.0):
    return random.uniform(min_sec, max_sec)

async def human_goto(page, url):
    """Переход с эмуляцией"""
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)

async def human_scroll(page, amount=300):
    """Прокрутка с эмуляцией"""
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
    except Exception as e:
        logger.warning(f"Human scroll error: {e}")
        await page.execute_script(f'window.scrollBy(0, {amount})')

async def get_pydoll_browser():
    """Получение Pydoll браузера и вкладки"""
    global pydoll_browser, pydoll_tab
    
    # Проверяем существующий браузер
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            logger.info("✅ Существующий браузер работает")
            return pydoll_tab
        except Exception as e:
            logger.warning(f"⚠️ Браузер не отвечает: {e}")
            await close_pydoll_browser()
    
    if not PYDOLL_AVAILABLE:
        logger.error("❌ Pydoll не установлен")
        return None
    
    if not CHROMIUM_INSTALLED:
        logger.error("❌ Chromium не найден")
        return None
    
    try:
        logger.info("🚀 Создаю Pydoll браузер...")
        
        options = ChromiumOptions()
        options.binary_location = CHROMIUM_PATH
        
        # Headless режим для Railway
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        
        logger.info("⏳ Запуск браузера...")
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        logger.info("✅ Браузер запущен!")
        
        # Переход на X.com
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        # Установка кук
        logger.info(f"🍪 Устанавливаю {len(COOKIES)} кук...")
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
                logger.debug(f"🍪 Установлена кука: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка установки куки {cookie['name']}: {e}")
        
        # Обновляем страницу для применения кук
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        logger.info("✅ Pydoll браузер полностью готов!")
        return pydoll_tab
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Pydoll: {e}", exc_info=True)
        return None

async def close_pydoll_browser():
    """Закрытие Pydoll браузера"""
    global pydoll_browser, pydoll_tab
    logger.info("📌 Закрываю Pydoll браузер...")
    
    if pydoll_browser:
        try:
            await pydoll_browser.close()
            logger.info("✅ Браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка закрытия: {e}")
        pydoll_browser = None
        pydoll_tab = None

async def get_browser():
    """Универсальное получение браузера"""
    return await get_pydoll_browser()

async def execute_js(script):
    """Выполнение JavaScript в браузере"""
    page = await get_browser()
    if page is None:
        logger.error("❌ Страница не получена")
        return None
    
    try:
        if hasattr(page, 'execute_script'):
            return await page.execute_script(script)
        else:
            logger.error(f"❌ Нет метода execute_script у {type(page)}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения JS: {e}")
        return None

async def take_screenshot():
    """Создание скриншота"""
    page = await get_browser()
    if page is None:
        return None
    
    try:
        if hasattr(page, 'take_screenshot'):
            screenshot_base64 = await page.take_screenshot(as_base64=True)
            if screenshot_base64:
                return base64.b64decode(screenshot_base64)
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        return None

async def check_login_status():
    """Проверка авторизации через JS"""
    page = await get_browser()
    if page is None:
        return {'is_logged_in': False, 'username': None}
    
    js_code = """
        () => {
            // Проверяем куки
            const cookies = document.cookie.split(';').reduce((acc, c) => {
                const [key, val] = c.trim().split('=');
                acc[key] = val;
                return acc;
            }, {});
            
            const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
            
            // Проверяем элементы интерфейса
            const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
            const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                !!document.querySelector('[data-testid="postButton"]');
            const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
            
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
            
            const isLoggedIn = hasAuthToken && (hasProfileLink || hasTweetBtn || hasSideNav);
            
            return {
                isLoggedIn: isLoggedIn,
                username: username || null,
                hasAuthToken: hasAuthToken,
                hasProfileLink: hasProfileLink,
                hasTweetBtn: hasTweetBtn
            };
        }
    """
    
    result = await page.execute_script(js_code)
    return result

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("🔐 Авторизация", callback_data="login")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screen")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("❌ Закрыть браузер", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        f"📌 **Нажмите кнопку:**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "screen":
        await screen(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "close":
        await close(update, context)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com"""
    logger.info(f"📩 /login от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Запускаю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Запускаю браузер...")
    
    try:
        # Запускаем браузер
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Не удалось запустить браузер. Проверьте установку Pydoll и Chromium.")
            return
        
        await msg.edit_text("🌐 Захожу на X.com...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(2)
        
        # Проверяем авторизацию
        await msg.edit_text("🔍 Проверяю авторизацию...")
        status_data = await check_login_status()
        
        global login_status
        login_status['is_logged_in'] = status_data.get('isLoggedIn', False)
        login_status['username'] = status_data.get('username')
        login_status['last_check'] = datetime.now()
        
        # Формируем ответ
        response = f"✅ **Проверка X.com**\n\n"
        response += f"🍪 auth_token: {'✅' if status_data.get('hasAuthToken') else '❌'}\n"
        response += f"👤 Профиль: {'✅' if status_data.get('hasProfileLink') else '❌'}\n"
        response += f"📝 Твитнуть: {'✅' if status_data.get('hasTweetBtn') else '❌'}\n\n"
        
        if status_data.get('isLoggedIn'):
            response += f"✅ **ВЫ АВТОРИЗОВАНЫ!**\n"
            if status_data.get('username'):
                response += f"👤 @{status_data['username']}\n"
            response += "\n💡 Теперь можете использовать бота."
        else:
            response += f"❌ **НЕ АВТОРИЗОВАН**\n\n"
            response += f"📌 Обновите куки через /setcookies\n"
            response += f"📌 Или установите актуальные значения в COOKIES"
        
        await msg.edit_text(response)
        
        # Делаем скриншот
        await msg.edit_text("📸 Делаю скриншот...")
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if status_data.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот"""
    logger.info(f"📩 /screen от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📸 Делаю скриншот...")
    else:
        msg = await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await msg.delete()
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Скриншот X.com"
            )
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        logger.error(f"❌ Ошибка screen: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус бота"""
    logger.info(f"📩 /status от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Проверяю статус...")
    else:
        msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    status_text = f"📊 **СТАТУС БОТА**\n\n"
    status_text += f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username']:
        status_text += f"👤 @{login_status['username']}\n"
    status_text += f"🕐 Последняя проверка: {login_status['last_check'] or 'Никогда'}\n\n"
    status_text += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
    status_text += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
    status_text += f"🌐 Браузер: {'✅' if pydoll_browser else '❌'}\n"
    status_text += f"📄 Вкладка: {'✅' if pydoll_tab else '❌'}\n\n"
    status_text += f"🍪 Кук загружено: {len(COOKIES)}"
    
    await msg.edit_text(status_text, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрытие браузера"""
    logger.info(f"📩 /close от {update.effective_user.username}")
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_pydoll_browser()
    await msg.edit_text("✅ Браузер закрыт!")

async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление кук"""
    global COOKIES
    
    await update.message.reply_text(
        "🍪 **Обновление кук X.com**\n\n"
        "Отправьте новые куки в JSON формате:\n"
        "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\",\"path\":\"/\"}]`\n\n"
        "Или отправьте /cancel для отмены"
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенных кук"""
    global COOKIES
    
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
            COOKIES = new_cookies
            context.user_data['waiting_for_cookies'] = False
            await close_pydoll_browser()  # Перезапускаем браузер с новыми куками
            await update.message.reply_text(
                f"✅ **Куки обновлены!**\n\n"
                f"📦 Всего: {len(COOKIES)} кук\n"
                f"🍪 Включены: {', '.join([c['name'] for c in COOKIES])}\n\n"
                f"Используйте /login для авторизации"
            )
        else:
            await update.message.reply_text("❌ Не удалось распознать куки")
            
    except json.JSONDecodeError as e:
        await update.message.reply_text(f"❌ Ошибка JSON: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== ЗАПУСК ==========

def main():
    logger.info("🚀 Запуск бота...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n✅ Бот запущен!")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды:")
    print("  /start - Главное меню")
    print("  /login - Авторизация в X.com")
    print("  /screen - Скриншот")
    print("  /status - Статус")
    print("  /close - Закрыть браузер")
    print("  /setcookies - Обновить куки")
    print("  /cancel - Отмена")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()