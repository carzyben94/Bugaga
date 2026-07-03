import os
import logging
import asyncio
import base64
import traceback
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Pydantic для структуры
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== PYDAВТИК МОДЕЛЬ ==========
class AuthResult(BaseModel):
    is_logged_in: bool
    username: str | None = None
    has_auth_token: bool = False
    has_ct0: bool = False
    timestamp: datetime = datetime.now()
    
    def get_status(self) -> str:
        if self.is_logged_in:
            return f"✅ АВТОРИЗОВАН!\n👤 @{self.username or 'unknown'}"
        return "❌ НЕ АВТОРИЗОВАН\nОбнови куки в коде"

# ========== КУКИ ==========
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
]

browser = None
tab = None
last_auth: AuthResult | None = None

# ========== БРАУЗЕР С ДЕТАЛЬНЫМ ЛОГИРОВАНИЕМ ==========
async def get_browser():
    global browser, tab
    logger.info("🔄 get_browser() вызван")
    
    if tab:
        try:
            logger.info("🔄 Проверка существующей вкладки...")
            await tab.execute_script('return 1')
            logger.info("✅ Существующая вкладка работает")
            return tab
        except Exception as e:
            logger.warning(f"⚠️ Вкладка не работает: {e}")
            await close_browser()
    
    try:
        logger.info("🚀 Импорт Pydoll...")
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        logger.info("✅ Pydoll импортирован")
        
        logger.info("🔧 Создание опций...")
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        logger.info("✅ Опции созданы")
        
        # Проверка Chromium
        chromium_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
        found = False
        for path in chromium_paths:
            if os.path.exists(path):
                logger.info(f"📍 Найден Chromium: {path}")
                options.binary_location = path
                found = True
                break
        
        if not found:
            logger.warning("⚠️ Chromium не найден в стандартных путях")
        
        logger.info("🚀 Создание браузера...")
        browser = Chrome(options=options)
        logger.info("✅ Браузер создан")
        
        logger.info("🚀 Запуск браузера...")
        tab = await browser.start()
        logger.info("✅ Браузер запущен")
        
        logger.info("🌐 Переход на X.com...")
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        logger.info("✅ Переход выполнен")
        
        logger.info(f"🍪 Установка {len(COOKIES)} кук...")
        for cookie in COOKIES:
            try:
                await tab.set_cookie(**cookie)
                logger.debug(f"🍪 Кука установлена: {cookie['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка установки {cookie['name']}: {e}")
        
        logger.info("✅ Браузер готов!")
        return tab
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта Pydoll: {e}")
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        logger.error(traceback.format_exc())
        return None

async def close_browser():
    global browser, tab
    logger.info("🔄 Закрытие браузера...")
    if browser:
        try:
            await browser.close()
            logger.info("✅ Браузер закрыт")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка закрытия: {e}")
        browser = None
        tab = None

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 LOGIN", callback_data="login")],
        [InlineKeyboardButton("🌐 API", callback_data="api")],
        [InlineKeyboardButton("🛡️ SHADOW", callback_data="shadow")],
        [InlineKeyboardButton("📊 EXTRACT", callback_data="extract")],
        [InlineKeyboardButton("📸 SCREEN", callback_data="screen")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="close")],
    ]
    await update.message.reply_text(
        "🤖 X.com Бот\nНажми кнопку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await cmd_login(update, context)
    elif query.data == "api":
        await cmd_api(update, context)
    elif query.data == "shadow":
        await cmd_shadow(update, context)
    elif query.data == "extract":
        await cmd_extract(update, context)
    elif query.data == "screen":
        await cmd_screen(update, context)
    elif query.data == "close":
        await close_browser()
        await query.edit_message_text("✅ Браузер закрыт")

# ========== LOGIN С ДЕТАЛЬНЫМИ ОШИБКАМИ ==========
async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_auth
    query = update.callback_query
    await query.edit_message_text("⏳ Захожу...")
    
    try:
        logger.info("🔐 Команда /login")
        
        page = await get_browser()
        if not page:
            error_msg = "❌ Ошибка браузера\n\n"
            error_msg += "Возможные причины:\n"
            error_msg += "1. Pydoll не установлен\n"
            error_msg += "2. Chromium не найден\n"
            error_msg += "3. Ошибка в коде\n\n"
            error_msg += "Проверь логи в консоли"
            await query.edit_message_text(error_msg)
            return
        
        logger.info("🌐 Переход на X.com...")
        await page.go_to('https://x.com')
        await asyncio.sleep(3)
        
        logger.info("📊 Проверка авторизации...")
        result = await page.execute_script('''
            function() {
                try {
                    var cookies = document.cookie.split(';').reduce(function(acc, c) {
                        var parts = c.trim().split('=');
                        acc[parts[0]] = parts[1];
                        return acc;
                    }, {});
                    
                    var hasAuth = !!cookies.auth_token && cookies.auth_token.length > 0;
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
                        isLoggedIn: hasAuth,
                        username: username,
                        hasAuthToken: hasAuth,
                        hasCt0: hasCt0
                    };
                } catch(e) {
                    return {error: e.message};
                }
            }
        ''')
        
        logger.info(f"📊 Результат: {result}")
        
        if result and result.get('error'):
            await query.edit_message_text(f"❌ Ошибка JS: {result['error']}")
            return
        
        # Сохраняем через Pydantic
        last_auth = AuthResult(**result)
        
        await query.edit_message_text(last_auth.get_status())
        
        # Скриншот
        logger.info("📸 Делаю скриншот...")
        screenshot = await page.take_screenshot(as_base64=True)
        if screenshot:
            await query.message.reply_photo(photo=base64.b64decode(screenshot), caption="📸 X.com")
            logger.info("✅ Скриншот отправлен")
        else:
            logger.warning("⚠️ Скриншот не удался")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        logger.error(traceback.format_exc())
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== API ==========
async def cmd_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("⏳ API запрос...")
    
    try:
        page = await get_browser()
        if not page:
            await query.edit_message_text("❌ Браузер не запущен")
            return
        
        result = await page.execute_script('''
            async function() {
                try {
                    var r = await fetch('https://x.com/i/api/1.1/onboarding/task.json', {
                        credentials: 'include'
                    });
                    return {status: r.status, ok: r.ok};
                } catch(e) {
                    return {error: e.message};
                }
            }
        ''')
        
        if result and result.get('ok'):
            await query.edit_message_text(f"✅ API работает\nСтатус: {result.get('status')}")
        else:
            await query.edit_message_text(f"❌ API не работает\n{result}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ {str(e)[:100]}")

# ========== SHADOW ==========
async def cmd_shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("⏳ Ищу Shadow DOM...")
    
    try:
        page = await get_browser()
        if not page:
            await query.edit_message_text("❌ Браузер не запущен")
            return
        
        result = await page.execute_script('''
            function() {
                var found = [];
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].shadowRoot) {
                        found.push(all[i].tagName);
                    }
                }
                return found;
            }
        ''')
        
        if result and len(result) > 0:
            await query.edit_message_text(f"✅ Найдено {len(result)} Shadow DOM элементов\n{', '.join(result[:5])}")
        else:
            await query.edit_message_text("❌ Shadow DOM элементов НЕ найдено")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ {str(e)[:100]}")

# ========== EXTRACT ==========
async def cmd_extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("⏳ Извлекаю данные...")
    
    try:
        page = await get_browser()
        if not page:
            await query.edit_message_text("❌ Браузер не запущен")
            return
        
        if not last_auth or not last_auth.is_logged_in:
            await query.edit_message_text("❌ Сначала авторизуйся! /login")
            return
        
        tweets = await page.execute_script('''
            function() {
                var items = document.querySelectorAll('[data-testid="tweet"]');
                var result = [];
                for (var i = 0; i < Math.min(items.length, 5); i++) {
                    var text = items[i].querySelector('[data-testid="tweetText"]');
                    var author = items[i].querySelector('[data-testid="User-Name"]');
                    result.push({
                        text: text ? text.textContent.slice(0, 100) : '',
                        author: author ? author.textContent : ''
                    });
                }
                return result;
            }
        ''')
        
        if tweets and len(tweets) > 0:
            msg = f"✅ Найдено {len(tweets)} твитов:\n\n"
            for i, t in enumerate(tweets, 1):
                msg += f"{i}. {t.get('author', 'unknown')}: {t.get('text', '')[:50]}...\n"
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ Нет твитов на странице\nПерейди на страницу с твитами")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ {str(e)[:100]}")

# ========== SCREEN ==========
async def cmd_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("⏳ Делаю скриншот...")
    
    try:
        page = await get_browser()
        if not page:
            await query.edit_message_text("❌ Браузер не запущен")
            return
        
        screenshot = await page.take_screenshot(as_base64=True)
        if screenshot:
            await query.delete_message()
            await query.message.reply_photo(photo=base64.b64decode(screenshot), caption="📸 Скриншот")
        else:
            await query.edit_message_text("❌ Не удалось")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ {str(e)[:100]}")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("\n" + "="*50)
    print("✅ БОТ ЗАПУЩЕН")
    print("="*50)
    print(f"📦 Pydantic: ✅")
    print(f"📦 Asyncio: ✅")
    print(f"🍪 Кук: {len(COOKIES)}")
    print("\n📌 /start - меню")
    print("\nКнопки:")
    print("  🔐 LOGIN - проверить авторизацию")
    print("  🌐 API - проверить API")
    print("  🛡️ SHADOW - найти Shadow DOM")
    print("  📊 EXTRACT - извлечь твиты")
    print("  📸 SCREEN - скриншот")
    print("  ❌ CLOSE - закрыть браузер")
    print("="*50)
    print("\n📋 Смотри логи выше для отладки!")
    
    app.run_polling()

if __name__ == "__main__":
    main()