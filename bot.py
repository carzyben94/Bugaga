# bot.py - финальная рабочая версия
import os
import subprocess
import logging
import json
import asyncio
import concurrent.futures
from io import BytesIO
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

COOKIES_FILE = "/app/cookies.json"

# ==================== ПРЕДУСТАНОВЛЕННЫЕ КУКИ X.COM ====================
DEFAULT_COOKIES = [
    {"domain": ".x.com", "name": "__cuid", "path": "/", "sameSite": "None", "secure": True, "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "name": "lang", "path": "/", "sameSite": "None", "secure": True, "value": "ru"},
    {"domain": ".x.com", "name": "dnt", "path": "/", "sameSite": "None", "secure": True, "value": "1"},
    {"domain": ".x.com", "name": "guest_id", "path": "/", "sameSite": "None", "secure": True, "value": "v1%3A178232552081152335"},
    {"domain": ".x.com", "name": "guest_id_marketing", "path": "/", "sameSite": "None", "secure": True, "value": "v1%3A178232552081152335"},
    {"domain": ".x.com", "name": "guest_id_ads", "path": "/", "sameSite": "None", "secure": True, "value": "v1%3A178232552081152335"},
    {"domain": ".x.com", "name": "personalization_id", "path": "/", "sameSite": "None", "secure": True, "value": "\"v1_WrN9cfSG2zvM3RbiT1ZEkw==\""},
    {"domain": ".x.com", "name": "twid", "path": "/", "sameSite": "None", "secure": True, "value": "u%3D2067347503503052800"},
    {"domain": ".x.com", "name": "auth_token", "path": "/", "sameSite": "None", "secure": True, "value": "9437c2dd7e6dd3b655cd4166f1fe303365f56d91"},
    {"domain": ".x.com", "name": "ct0", "path": "/", "sameSite": "None", "secure": True, "value": "6348cd308326bbc75e48654d2a7488c58d9d34f10712b0f1b3d7bde9e67a028c46de54fbbbace15ab6a518f71b27945510c1dc91b2ef7c9360aaf009883b0c5e326f4196c02e32c930a7c2222c4af9ff"},
    {"domain": ".x.com", "name": "__cf_bm", "path": "/", "sameSite": "None", "secure": True, "value": "MSqy6sN4SBKGB01jS5J9kMVNMhstxZpmOHTROPi0h.k-1782336858.164416-1.0.1.1-P4VpKQHYjEzOxbnxiZN1sShNBgI_Tif0FK3kE5EbmXwarTPq._otJs.DQZ_QszNMejE66S0Kb4Y1NHqWRMgk5bhXxz8QOxKCmKSdh0usZVeadHt5mcqIshRiWexQqFn."}
]

# Глобальные переменные
browser_instance = None
browser_context = None
browser_page = None
_playwright = None
browser_ready = False

# ==================== УСТАНОВКА БРАУЗЕРА ====================
def install_browser_sync():
    try:
        logger.info("🔄 Устанавливаю браузер...")
        subprocess.run(["pip", "install", "playwright"], check=True, capture_output=True)
        result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("✅ Браузер Chromium установлен")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def install_browser_async():
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, install_browser_sync)
    if result:
        check_browser()
    return result

def check_browser():
    try:
        import glob
        home_dir = os.path.expanduser("~")
        for path in [f"{home_dir}/.cache/ms-playwright/chromium-*"]:
            if glob.glob(path):
                return True
        return False
    except:
        return False

# ==================== УСТАНОВКА CLOAKBROWSER ====================
def install_cloak():
    try:
        logger.info("Устанавливаю CloakBrowser...")
        subprocess.run(["pip", "install", "cloakbrowser"], check=True, capture_output=True)
        logger.info("✅ CloakBrowser установлен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def check_cloak():
    try:
        import cloakbrowser
        return True
    except:
        return False

# Инициализация
CLOAK_AVAILABLE = check_cloak()
if not CLOAK_AVAILABLE:
    if install_cloak():
        CLOAK_AVAILABLE = check_cloak()

BROWSER_AVAILABLE = check_browser()
logger.info(f"CloakBrowser: {CLOAK_AVAILABLE}, Браузер: {BROWSER_AVAILABLE}")

# ==================== КУКИ ====================
def load_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
                # Нормализуем куки для Playwright
                for c in cookies:
                    if 'sameSite' in c:
                        if c['sameSite'] in ['unspecified', 'no_restriction', '']:
                            c['sameSite'] = 'None'
                    else:
                        c['sameSite'] = 'None'
                    c['secure'] = True
                return cookies
        return DEFAULT_COOKIES
    except:
        return DEFAULT_COOKIES

def save_cookies(cookies):
    try:
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        return True
    except:
        return False

# Сохраняем куки при первом запуске
if not os.path.exists(COOKIES_FILE):
    save_cookies(DEFAULT_COOKIES)

# ==================== ЗАПУСК БРАУЗЕРА ====================
async def start_browser():
    """Запускает браузер с куками"""
    global browser_instance, browser_context, browser_page, _playwright, browser_ready
    
    if browser_ready and browser_instance:
        return True
    
    try:
        from playwright.async_api import async_playwright
        
        logger.info("🚀 Запускаю браузер...")
        
        # Загружаем куки
        cookies = load_cookies()
        logger.info(f"🍪 Загружено {len(cookies)} кук")
        
        # Запускаем Playwright
        _playwright = await async_playwright().start()
        
        # Запускаем браузер
        browser_instance = await _playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        
        # Создаем контекст
        browser_context = await browser_instance.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Устанавливаем куки
        try:
            await browser_context.add_cookies(cookies)
            logger.info(f"✅ Установлено {len(cookies)} кук")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка установки кук: {e}")
            # Пробуем по одной
            for cookie in cookies:
                try:
                    await browser_context.add_cookies([cookie])
                except:
                    pass
        
        # Создаем страницу
        browser_page = await browser_context.new_page()
        browser_ready = True
        
        logger.info("✅ Браузер готов")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска браузера: {e}")
        return False

async def close_browser():
    global browser_instance, browser_context, browser_page, _playwright, browser_ready
    
    try:
        if browser_instance:
            await browser_instance.close()
    except:
        pass
    try:
        if _playwright:
            await _playwright.stop()
    except:
        pass
    
    browser_instance = None
    browser_context = None
    browser_page = None
    _playwright = None
    browser_ready = False
    logger.info("🗑️ Браузер закрыт")

# ==================== КОМАНДА /GO ====================
async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /go - открывает URL с куками"""
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL\n\n"
            "Пример: `/go x.com`\n"
            "Или: `/go https://example.com`",
            parse_mode="Markdown"
        )
        return
    
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    # Проверяем CloakBrowser
    if not check_cloak():
        await msg.edit_text("❌ CloakBrowser не установлен!\nИспользуйте /install")
        return
    
    # Проверяем браузер
    if not check_browser():
        await msg.edit_text("❌ Браузер не установлен!\nИспользуйте /install_browser")
        return
    
    # Запускаем браузер если не запущен
    if not browser_ready:
        success = await start_browser()
        if not success:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
    
    try:
        global browser_page
        
        # Переходим по URL
        logger.info(f"🌐 Перехожу на {url}")
        await browser_page.goto(url, timeout=45000)
        
        # Ждем загрузку
        try:
            await browser_page.wait_for_load_state('networkidle', timeout=15000)
        except:
            await browser_page.wait_for_load_state('domcontentloaded', timeout=10000)
        
        # Проверяем авторизацию для X.COM
        is_x = 'x.com' in url or 'twitter.com' in url
        auth_status = "✅ Страница загружена"
        
        if is_x:
            try:
                # Проверяем наличие ленты
                timeline = await browser_page.query_selector('[data-testid="primaryColumn"]')
                if timeline:
                    auth_status = "✅ Авторизован! Лента X.COM загружена"
                else:
                    # Проверяем наличие профиля
                    profile = await browser_page.query_selector('[data-testid="UserCell"]')
                    if profile:
                        auth_status = "✅ Авторизован! Профиль обнаружен"
                    else:
                        # Проверяем URL
                        current_url = browser_page.url
                        if 'login' in current_url or 'i/flow/login' in current_url:
                            auth_status = "⚠️ Не авторизован. Требуется вход"
                        else:
                            auth_status = "✅ X.COM открыт"
            except:
                auth_status = "✅ X.COM открыт"
        
        # Делаем скриншот
        await msg.edit_text("📸 Делаю скриншот...")
        screenshot = await browser_page.screenshot(full_page=True)
        
        # Отправляем скриншот
        photo = BytesIO(screenshot)
        photo.name = f"go_{datetime.now().strftime('%H%M%S')}.png"
        
        await update.message.reply_photo(
            photo=photo,
            caption=f"🌐 *{url}*\n\n{auth_status}\n\n🍪 Кук: {len(load_cookies())}",
            parse_mode="Markdown"
        )
        
        await msg.delete()
        await update.message.reply_text("🔙 /menu")
        
    except Exception as e:
        error = str(e)[:200]
        await msg.edit_text(f"❌ Ошибка: {error}\n\n🔙 /menu")

# ==================== ОСТАЛЬНЫЕ КОМАНДЫ ====================
async def start_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start_browser - запускает браузер"""
    await update.message.reply_text("⏳ Запускаю браузер...")
    success = await start_browser()
    if success:
        await update.message.reply_text("✅ Браузер запущен!\n\nИспользуйте /go <URL>")
    else:
        await update.message.reply_text("❌ Ошибка запуска")

async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await close_browser()
    await update.message.reply_text("🗑️ Браузер закрыт!\n\n🔙 /menu")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cloak = check_cloak()
    browser = check_browser()
    cookies = load_cookies()
    x_cookies = len([c for c in cookies if 'x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')])
    
    await update.message.reply_text(
        f"📊 *Статус*\n\n"
        f"📦 CloakBrowser: {'✅' if cloak else '❌'}\n"
        f"🌐 Браузер: {'✅' if browser else '❌'}\n"
        f"🔄 Состояние: {'🟢 Активен' if browser_ready else '⚫ Не активен'}\n"
        f"🍪 Кук: {len(cookies)} (🐦 {x_cookies} X.COM)\n\n"
        "🔙 /menu",
        parse_mode="Markdown"
    )

async def install_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Установка браузера (2-3 мин)...")
    success = await install_browser_async()
    if success:
        await update.message.reply_text("✅ Браузер установлен!\n\nИспользуйте /start_browser")
    else:
        await update.message.reply_text("❌ Ошибка установки")

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = load_cookies()
    x_cookies = [c for c in cookies if 'x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')]
    
    keyboard = [
        [InlineKeyboardButton("📥 Загрузить куки", callback_data="cookies_load")],
        [InlineKeyboardButton("🔄 Сбросить X.COM", callback_data="cookies_reset")],
        [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    
    await update.message.reply_text(
        f"🍪 *Куки*\n\nВсего: {len(cookies)}\n🐦 X.COM: {len(x_cookies)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def reset_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_cookies(DEFAULT_COOKIES)
    await update.message.reply_text(f"✅ Сброшены куки X.COM!\nЗагружено {len(DEFAULT_COOKIES)} кук\n\n🔙 /menu")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 /go <URL>", callback_data="go")],
        [InlineKeyboardButton("🐦 /go x.com", callback_data="go_x")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screenshot")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Куки", callback_data="cookies")],
        [InlineKeyboardButton("🚀 Запустить браузер", callback_data="start_browser")],
        [InlineKeyboardButton("🗑️ Закрыть браузер", callback_data="close_browser")],
    ]
    
    if not check_browser():
        keyboard.append([InlineKeyboardButton("⬇️ Установить браузер", callback_data="install_browser")])
    
    cookies = load_cookies()
    x_cookies = len([c for c in cookies if 'x.com' in c.get('domain', '')])
    status = f"🟢 Браузер: {'✅' if browser_ready else '❌'} | 🍪 {len(cookies)} (🐦{x_cookies})"
    
    await update.message.reply_text(
        f"📋 *Меню*\n\n{status}\n\n"
        "Команды:\n"
        "/go <URL> - открыть сайт\n"
        "/go x.com - открыть X.COM\n"
        "/start_browser - запустить браузер\n"
        "/close - закрыть браузер\n"
        "/status - статус\n"
        "/cookies - куки",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "go":
        await query.edit_message_text(
            "🌐 Введите URL:\n"
            "/go https://example.com\n"
            "/go x.com"
        )
    
    elif query.data == "go_x":
        # Создаем фейковое сообщение для команды /go
        class FakeMessage:
            def __init__(self, chat):
                self.chat = chat
            async def reply_text(self, text, **kwargs):
                return await query.message.reply_text(text, **kwargs)
        
        class FakeUpdate:
            def __init__(self, chat):
                self.message = FakeMessage(chat)
                self.effective_message = self.message
        
        fake_update = FakeUpdate(query.message.chat)
        fake_update.message.text = "/go"
        fake_update.message.chat = query.message.chat
        fake_update.message.reply_text = query.message.reply_text
        
        await go(fake_update, ContextTypes.DEFAULT_TYPE())
    
    elif query.data == "screenshot":
        if not browser_ready:
            await query.edit_message_text("❌ Браузер не запущен!\nИспользуйте /start_browser")
            return
        
        try:
            screenshot = await browser_page.screenshot(full_page=True)
            photo = BytesIO(screenshot)
            photo.name = f"screenshot_{datetime.now().strftime('%H%M%S')}.png"
            await query.message.reply_photo(photo=photo, caption="📸 Скриншот")
            await query.delete()
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    
    elif query.data == "status":
        await status_command(update, context)
    
    elif query.data == "cookies":
        cookies = load_cookies()
        x_cookies = [c for c in cookies if 'x.com' in c.get('domain', '')]
        keyboard = [
            [InlineKeyboardButton("🔄 Сбросить X.COM", callback_data="cookies_reset")],
            [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        await query.edit_message_text(
            f"🍪 *Куки*\n\nВсего: {len(cookies)}\n🐦 X.COM: {len(x_cookies)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif query.data == "cookies_reset":
        save_cookies(DEFAULT_COOKIES)
        await query.edit_message_text(f"✅ Сброшены куки X.COM!\nЗагружено {len(DEFAULT_COOKIES)} кук\n\n🔙 /menu")
    
    elif query.data == "cookies_show":
        cookies = load_cookies()
        if cookies:
            text = json.dumps(cookies, indent=2)
            if len(text) > 4000:
                with open("/tmp/cookies.json", 'w') as f:
                    json.dump(cookies, f, indent=2)
                with open("/tmp/cookies.json", 'rb') as f:
                    await query.message.reply_document(f, filename="cookies.json")
            else:
                await query.edit_message_text(f"```json\n{text}\n```", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Куки не найдены")
    
    elif query.data == "start_browser":
        await query.edit_message_text("⏳ Запускаю браузер...")
        success = await start_browser()
        if success:
            await query.edit_message_text("✅ Браузер запущен!\n\nИспользуйте /go <URL>")
        else:
            await query.edit_message_text("❌ Ошибка запуска")
    
    elif query.data == "close_browser":
        await close_browser()
        await query.edit_message_text("🗑️ Браузер закрыт!\n\n🔙 /menu")
    
    elif query.data == "install_browser":
        await query.edit_message_text("⏳ Установка браузера (2-3 мин)...")
        success = await install_browser_async()
        if success:
            await query.edit_message_text("✅ Браузер установлен!\n\nИспользуйте /start_browser")
        else:
            await query.edit_message_text("❌ Ошибка установки")
    
    elif query.data == "back_to_menu":
        await menu_command(update, context)

# ==================== ЗАПУСК ====================
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", menu_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("start_browser", start_browser_command))
    application.add_handler(CommandHandler("close", close_browser_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cookies", cookies_command))
    application.add_handler(CommandHandler("reset_cookies", reset_cookies_command))
    application.add_handler(CommandHandler("install_browser", install_browser_command))
    
    # Callback
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🍪 Предустановлено {len(DEFAULT_COOKIES)} кук X.COM")
    logger.info("📌 Используйте /go x.com для открытия X.COM")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()