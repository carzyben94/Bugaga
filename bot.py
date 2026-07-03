import os
import logging
import asyncio
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ========== КУКИ X.COM (ЗАМЕНИ НА СВОИ) ==========
COOKIES = [
    {"name": "auth_token", "value": "ТВОЙ_AUTH_TOKEN", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "ТВОЙ_CT0", "domain": ".x.com", "path": "/"},
]

# ========== ГЛОБАЛЬНЫЙ СТАТУС ==========
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None
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
        ]
        for path in chromium_paths:
            if os.path.exists(path):
                options.binary_location = path
                logger.info(f"📍 Использую: {path}")
                break
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        # Устанавливаем куки
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        for cookie in COOKIES:
            try:
                await tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain', '.x.com'),
                    path=cookie.get('path', '/')
                )
                logger.info(f"🍪 Кука установлена: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка куки {cookie['name']}: {e}")
        
        logger.info("✅ Браузер готов!")
        return tab
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
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

# ========== КОМАНДА /login ==========
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Авторизация в X.com"""
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
            status_msg += "\nОбновите куки в коде бота"
        
        await msg.edit_text(status_msg)
        
        # Делаем скриншот
        screenshot = await take_screenshot()
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 X.com - {'✅ Авторизован' if auth_status.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        else:
            await update.message.reply_text("⚠️ Не удалось сделать скриншот")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт"""
    await update.message.reply_text(
        f"🤖 Бот для X.com\n\n"
        f"📌 /login - авторизация и скриншот\n"
        f"📌 /status - проверить статус\n"
        f"📌 /close - закрыть браузер\n"
    )

# ========== КОМАНДА /status ==========
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус"""
    status_msg = "📊 СТАТУС\n\n"
    status_msg += f"🔐 Авторизован: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username'] and login_status['username'] != 'неизвестно':
        status_msg += f"👤 @{login_status['username']}\n"
    status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    await update.message.reply_text(status_msg)

# ========== КОМАНДА /close ==========
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть браузер"""
    await close_browser()
    await update.message.reply_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🚀 Бот запущен!")
    print("📌 /login - авторизация в X.com")
    print("📌 /status - статус")
    print("📌 /close - закрыть браузер")
    
    app.run_polling()

if __name__ == "__main__":
    main()