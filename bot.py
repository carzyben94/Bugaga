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

async def human_click(element):
    """Клик с эмуляцией"""
    try:
        if hasattr(element, 'click'):
            await element.click(humanize=True)
        else:
            await element.click()
        await asyncio.sleep(random_delay(0.2, 0.8))
    except Exception as e:
        logger.warning(f"Human click error: {e}")
        await element.click()

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
        await asyncio.sleep(3)
        
        logger.info("✅ Pydoll браузер готов!")
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

# ========== НОВАЯ ЛОГИКА ВХОДА С ЭМУЛЯЦИЕЙ ==========

async def set_cookies_with_js(page):
    """Установка кук через JS (самый надежный способ)"""
    logger.info("🍪 Устанавливаю куки через JS...")
    
    # Сначала удаляем все старые куки
    await page.execute_script('''
        document.cookie.split(";").forEach(function(c) {
            document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
        });
    ''')
    await asyncio.sleep(1)
    
    # Устанавливаем каждую куку через JS
    for cookie in COOKIES:
        try:
            js_code = f"""
                document.cookie = '{cookie['name']}={cookie['value']}; domain={cookie['domain']}; path={cookie['path']};';
            """
            await page.execute_script(js_code)
            logger.info(f"🍪 Установлена кука через JS: {cookie['name']}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка установки куки {cookie['name']}: {e}")
    
    # Проверяем установленные куки
    cookies_check = await page.execute_script('return document.cookie;')
    logger.info(f"📋 Куки в браузере: {cookies_check[:200]}...")
    
    if 'auth_token' in cookies_check:
        logger.info("✅ auth_token успешно установлен!")
        return True
    else:
        logger.warning("⚠️ auth_token НЕ найден в куках!")
        return False

async def emulate_human_login_flow(page):
    """Эмуляция поведения человека для активации сессии"""
    logger.info("🚶 Эмулирую поведение человека...")
    
    # 1. Ждем загрузки страницы
    await asyncio.sleep(random_delay(2, 4))
    
    # 2. Медленно скроллим вниз
    await human_scroll(page, 200)
    await asyncio.sleep(random_delay(1, 2))
    
    # 3. Скроллим вверх
    await page.execute_script('window.scrollTo(0, 0);')
    await asyncio.sleep(random_delay(1, 2))
    
    # 4. Наводим на разные элементы (эмуляция)
    await page.execute_script('''
        // Эмулируем движение мыши
        const events = ['mousemove', 'mouseover'];
        const elements = document.querySelectorAll('a, button, div[role="button"]');
        for (let i = 0; i < Math.min(3, elements.length); i++) {
            const el = elements[i];
            if (el && el.getBoundingClientRect) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const event = new MouseEvent('mousemove', {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y
                    });
                    el.dispatchEvent(event);
                }
            }
        }
    ''')
    await asyncio.sleep(random_delay(0.5, 1.5))
    
    # 5. Проверяем наличие кнопки "Твитнуть" и наводим на нее
    await page.execute_script('''
        const tweetBtn = document.querySelector('[data-testid="tweetButton"]') || 
                         document.querySelector('[data-testid="postButton"]');
        if (tweetBtn) {
            const rect = tweetBtn.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                const event = new MouseEvent('mousemove', {
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: rect.left + rect.width / 2,
                    clientY: rect.top + rect.height / 2
                });
                tweetBtn.dispatchEvent(event);
            }
        }
    ''')
    await asyncio.sleep(random_delay(1, 2))
    
    logger.info("✅ Эмуляция поведения завершена")

async def check_login_status_detailed(page):
    """Расширенная проверка статуса авторизации"""
    js_code = """
        () => {
            // 1. Проверяем куки
            const cookies = document.cookie.split(';').reduce((acc, c) => {
                const [key, val] = c.trim().split('=');
                acc[key] = val;
                return acc;
            }, {});
            
            const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
            const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
            const hasGuestId = !!cookies.guest_id && cookies.guest_id.length > 0;
            
            // 2. Проверяем DOM элементы
            const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
            const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                !!document.querySelector('[data-testid="postButton"]');
            const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
            
            // 3. Проверяем наличие кнопок входа
            const hasLoginBtn = !!document.querySelector('[data-testid="loginButton"]');
            const hasSignupBtn = !!document.querySelector('[data-testid="signupButton"]');
            const hasLoginLink = !!document.querySelector('a[href="/login"]');
            const hasSignupLink = !!document.querySelector('a[href="/signup"]');
            
            // 4. Проверяем редирект
            const isOnLoginPage = window.location.href.includes('/login') || 
                                  window.location.href.includes('/i/flow/login');
            
            // 5. Ищем username
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
            
            // 6. Итоговый статус
            const hasUserElements = hasProfileLink || hasTweetBtn || hasSideNav;
            const hasLoginElements = hasLoginBtn || hasSignupBtn || hasLoginLink || hasSignupLink;
            const isLoggedIn = hasAuthToken && hasUserElements && !hasLoginElements && !isOnLoginPage;
            
            return {
                isLoggedIn: isLoggedIn,
                username: username || null,
                hasAuthToken: hasAuthToken,
                hasCt0: hasCt0,
                hasGuestId: hasGuestId,
                hasProfileLink: hasProfileLink,
                hasTweetBtn: hasTweetBtn,
                hasSideNav: hasSideNav,
                hasLoginBtn: hasLoginBtn,
                hasSignupBtn: hasSignupBtn,
                hasLoginLink: hasLoginLink,
                hasSignupLink: hasSignupLink,
                isOnLoginPage: isOnLoginPage,
                url: window.location.href,
                hasUserElements: hasUserElements,
                hasLoginElements: hasLoginElements
            };
        }
    """
    
    result = await page.execute_script(js_code)
    return result

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная авторизация с эмуляцией человека"""
    logger.info(f"📩 /login от {update.effective_user.username}")
    
    await send_message_safe(update, "🚀 Запускаю браузер...")
    
    try:
        # 1. Получаем браузер
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Не удалось запустить браузер.")
            return
        
        # 2. Переходим на X.com
        await send_message_safe(update, "🌐 Захожу на X.com...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(3)
        
        # 3. Устанавливаем куки через JS
        await send_message_safe(update, "🍪 Устанавливаю куки...")
        cookies_set = await set_cookies_with_js(page)
        
        if not cookies_set:
            await send_message_safe(update, "⚠️ Не удалось установить куки. Попробуйте /setcookies")
            return
        
        # 4. Эмулируем поведение человека
        await send_message_safe(update, "🚶 Эмулирую поведение человека...")
        await emulate_human_login_flow(page)
        
        # 5. Обновляем страницу
        await send_message_safe(update, "🔄 Обновляю страницу...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(3)
        
        # 6. Проверяем авторизацию
        await send_message_safe(update, "🔍 Проверяю авторизацию...")
        status_data = await check_login_status_detailed(page)
        
        global login_status
        login_status['is_logged_in'] = status_data.get('isLoggedIn', False)
        login_status['username'] = status_data.get('username')
        login_status['last_check'] = datetime.now()
        
        # 7. Формируем подробный отчет
        response = f"📊 **СТАТУС АВТОРИЗАЦИИ**\n\n"
        response += f"📍 URL: {status_data.get('url', 'unknown')}\n\n"
        
        response += f"🍪 **Куки:**\n"
        response += f"  auth_token: {'✅' if status_data.get('hasAuthToken') else '❌'}\n"
        response += f"  ct0: {'✅' if status_data.get('hasCt0') else '❌'}\n"
        response += f"  guest_id: {'✅' if status_data.get('hasGuestId') else '❌'}\n\n"
        
        response += f"👤 **Элементы пользователя:**\n"
        response += f"  Профиль: {'✅' if status_data.get('hasProfileLink') else '❌'}\n"
        response += f"  Твитнуть: {'✅' if status_data.get('hasTweetBtn') else '❌'}\n"
        response += f"  Меню: {'✅' if status_data.get('hasSideNav') else '❌'}\n\n"
        
        response += f"🔐 **Элементы входа:**\n"
        response += f"  Кнопка входа: {'✅' if status_data.get('hasLoginBtn') else '❌'}\n"
        response += f"  Ссылка на вход: {'✅' if status_data.get('hasLoginLink') else '❌'}\n"
        response += f"  Страница логина: {'✅' if status_data.get('isOnLoginPage') else '❌'}\n\n"
        
        if status_data.get('isLoggedIn'):
            response += f"✅ **ВЫ АВТОРИЗОВАНЫ!**\n"
            if status_data.get('username'):
                response += f"👤 @{status_data['username']}\n"
            response += "\n💡 Бот готов к работе!"
        else:
            response += f"❌ **НЕ АВТОРИЗОВАН**\n\n"
            
            if status_data.get('isOnLoginPage'):
                response += "⚠️ Перенаправлен на страницу входа\n"
                response += "📌 Куки устарели или недействительны\n"
                response += "📌 Используйте /setcookies для обновления\n"
            elif not status_data.get('hasAuthToken'):
                response += "⚠️ auth_token отсутствует\n"
                response += "📌 Обновите куки через /setcookies\n"
            elif status_data.get('hasLoginBtn') or status_data.get('hasLoginLink'):
                response += "⚠️ Есть кнопка входа (сессия не активирована)\n"
                response += "📌 Попробуйте повторить /login\n"
            elif not status_data.get('hasUserElements'):
                response += "⚠️ Нет элементов пользователя\n"
                response += "📌 Страница не загрузилась полностью\n"
                response += "📌 Попробуйте /login еще раз\n"
            else:
                response += "⚠️ Неизвестный статус\n"
                response += "📌 Попробуйте /diagnos для диагностики"
        
        await send_message_safe(update, response)
        
        # 8. Делаем скриншот
        await send_message_safe(update, "📸 Делаю скриншот...")
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(
                update,
                screenshot,
                f"📸 X.com - {'✅ Авторизован' if status_data.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка login: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_photo_safe(update, photo, caption=""):
    """Безопасная отправка фото"""
    try:
        if update.callback_query:
            await update.callback_query.message.reply_photo(photo=photo, caption=caption)
        elif update.message:
            await update.message.reply_photo(photo=photo, caption=caption)
        else:
            logger.error("❌ Нет способа отправить фото")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")

async def send_message_safe(update, text, parse_mode=None, reply_markup=None):
    """Безопасная отправка сообщения"""
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            logger.error("❌ Нет способа отправить сообщение")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

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

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот"""
    logger.info(f"📩 /screen от {update.effective_user.username}")
    
    await send_message_safe(update, "📸 Делаю скриншот...")
    
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Скриншот X.com")
        else:
            await send_message_safe(update, "❌ Не удалось сделать скриншот")
    except Exception as e:
        logger.error(f"❌ Ошибка screen: {e}")
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус бота"""
    logger.info(f"📩 /status от {update.effective_user.username}")
    
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
    
    await send_message_safe(update, status_text, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрытие браузера"""
    logger.info(f"📩 /close от {update.effective_user.username}")
    
    await send_message_safe(update, "⏳ Закрываю браузер...")
    await close_pydoll_browser()
    await send_message_safe(update, "✅ Браузер закрыт!")

async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление кук"""
    global COOKIES
    
    await update.message.reply_text(
        "🍪 **Обновление кук X.com**\n\n"
        "Отправьте новые куки в JSON формате:\n"
        "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\",\"path\":\"/\"}]`\n\n"
        "Или отправьте /cancel для отмены",
        parse_mode='Markdown'
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
            await close_pydoll_browser()
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