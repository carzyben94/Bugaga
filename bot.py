# bot.py - исправленная версия с правильным запуском
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

# Глобальные переменные
browser_instance = None
browser_context = None
browser_page = None
last_url = None
_playwright = None

# ==================== УСТАНОВКА БРАУЗЕРА ====================
def install_browser_sync():
    """Синхронная установка браузера"""
    try:
        logger.info("🔄 Устанавливаю браузер...")
        
        subprocess.run(
            ["pip", "install", "playwright"],
            check=True,
            capture_output=True
        )
        logger.info("✅ Playwright установлен")
        
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("✅ Браузер Chromium установлен")
            return True
        else:
            logger.error(f"❌ Ошибка установки: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def install_browser_async():
    """Асинхронная установка браузера"""
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, install_browser_sync)
    
    if result:
        check_browser()
    
    return result

def check_browser():
    """Проверяет наличие браузера - синхронная версия"""
    try:
        # Пробуем импортировать playwright
        import playwright
        logger.info("✅ Playwright найден")
        
        # Проверяем наличие файлов браузера
        import glob
        home_dir = os.path.expanduser("~")
        browser_paths = [
            f"{home_dir}/.cache/ms-playwright/chromium-*",
            f"{home_dir}/.cache/ms-playwright/chromium_headless_shell-*",
        ]
        
        for path in browser_paths:
            found = glob.glob(path)
            if found:
                logger.info(f"✅ Найдены файлы браузера: {found[0]}")
                return True
        
        return False
        
    except ImportError:
        logger.warning("⚠️ Playwright не установлен")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки: {e}")
        return False

# ==================== УСТАНОВКА CLOAKBROWSER ====================
def install_cloak():
    try:
        logger.info("Устанавливаю CloakBrowser...")
        subprocess.run(["pip", "install", "cloakbrowser"], check=True, capture_output=True, text=True)
        logger.info("✅ CloakBrowser установлен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка установки: {e}")
        return False

def check_cloak():
    try:
        import cloakbrowser
        return True
    except ImportError:
        return False

# Первоначальная проверка
CLOAK_AVAILABLE = check_cloak()
if not CLOAK_AVAILABLE:
    if install_cloak():
        CLOAK_AVAILABLE = check_cloak()

BROWSER_AVAILABLE = check_browser()

logger.info(f"📊 CloakBrowser: {CLOAK_AVAILABLE}, Браузер: {BROWSER_AVAILABLE}")

# ==================== РАБОТА С КУКАМИ ====================
def load_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Ошибка загрузки кук: {e}")
        return []

def save_cookies(cookies):
    try:
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"✅ Сохранено {len(cookies)} кук")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения кук: {e}")
        return False

def cookies_to_string(cookies):
    if not cookies:
        return "❌ Куки не загружены"
    lines = []
    for i, cookie in enumerate(cookies[:20], 1):
        name = cookie.get('name', 'unknown')
        value = cookie.get('value', '')[:30]
        domain = cookie.get('domain', '')
        lines.append(f"{i}. {name}: {value}... ({domain})")
    if len(cookies) > 20:
        lines.append(f"... и еще {len(cookies) - 20} кук")
    return "\n".join(lines)

# ==================== УПРАВЛЕНИЕ БРАУЗЕРОМ ====================
async def init_browser(url=None):
    global browser_instance, browser_context, browser_page, last_url, _playwright
    
    try:
        from playwright.async_api import async_playwright
        
        if browser_instance is None:
            logger.info("🚀 Запускаю браузер...")
            
            cookies = load_cookies()
            
            _playwright = await async_playwright().start()
            browser_instance = await _playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            browser_context = await browser_instance.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            if cookies:
                try:
                    await browser_context.add_cookies(cookies)
                    logger.info(f"✅ Установлено {len(cookies)} кук")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка установки кук: {e}")
            
            browser_page = await browser_context.new_page()
            logger.info("✅ Браузер запущен")
        
        if url and url != last_url:
            logger.info(f"🌐 Перехожу на {url}")
            await browser_page.goto(url, timeout=30000)
            try:
                await browser_page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass
            last_url = url
        
        return browser_page
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации браузера: {e}")
        await close_browser()
        raise e

async def close_browser():
    global browser_instance, browser_context, browser_page, _playwright
    
    try:
        if browser_instance:
            await browser_instance.close()
            logger.info("🗑️ Браузер закрыт")
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

async def take_screenshot_from_page():
    global browser_page
    
    if not browser_page:
        raise Exception("Браузер не запущен")
    
    try:
        screenshot = await browser_page.screenshot(full_page=True, timeout=10000)
        return screenshot
    except:
        screenshot = await browser_page.screenshot(timeout=5000)
        return screenshot

# ==================== КОМАНДЫ БОТА ====================
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("menu", "📋 Открыть меню"),
        BotCommand("browse", "🌐 Открыть URL"),
        BotCommand("x", "🐦 Открыть X.COM"),
        BotCommand("screenshot", "📸 Сделать скриншот"),
        BotCommand("close", "🗑️ Закрыть браузер"),
        BotCommand("status", "📊 Статус"),
        BotCommand("cookies", "🍪 Куки"),
        BotCommand("help", "❓ Помощь"),
        BotCommand("check", "🔄 Обновить статус"),
    ]
    await application.bot.set_my_commands(commands)

async def get_main_keyboard():
    cloak_status = check_cloak()
    browser_status = check_browser()
    cookies_count = len(load_cookies())
    browser_active = "🟢" if browser_instance else "⚫"
    
    status_line = f"📦 Cloak: {'✅' if cloak_status else '❌'} | 🌐 Браузер: {'✅' if browser_status else '❌'} | {browser_active} | 🍪 {cookies_count}"
    
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("🐦 X.COM", callback_data="x_com")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screenshot")],
        [InlineKeyboardButton("🗑️ Закрыть браузер", callback_data="close_browser")],
        [InlineKeyboardButton("🔄 Обновить статус", callback_data="check_status")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Куки (" + str(cookies_count) + ")", callback_data="cookies")],
    ]
    
    if not browser_status:
        keyboard.append([InlineKeyboardButton("⬇️ Установить браузер", callback_data="install_browser")])
    
    keyboard.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="help")])
    
    return InlineKeyboardMarkup(keyboard), status_line

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup, status_line = await get_main_keyboard()
    await update.message.reply_text(
        f"🤖 *CloakBrowser Bot*\n\n"
        f"{status_line}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup, status_line = await get_main_keyboard()
    message = update.message if update.message else update.callback_query.message
    
    await message.reply_text(
        f"📋 *Главное меню*\n\n"
        f"{status_line}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ==================== ОБРАБОТЧИКИ ====================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "browse":
        await query.edit_message_text(
            "🌐 *Введите URL*\n\n"
            "Используйте команду:\n"
            "`/browse https://example.com`",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_url'] = True
    
    elif query.data == "x_com":
        await query.edit_message_text("⏳ Открываю X.COM...")
        await open_x_com(update, context)
    
    elif query.data == "screenshot":
        await query.edit_message_text("📸 Делаю скриншот...")
        await take_screenshot(update, context)
    
    elif query.data == "close_browser":
        await close_browser()
        await query.edit_message_text("🗑️ Браузер закрыт!")
        await asyncio.sleep(1)
        await menu(update, context)
    
    elif query.data == "check_status":
        await query.edit_message_text("🔄 Проверяю статус...")
        cloak_status = check_cloak()
        browser_status = check_browser()
        await query.edit_message_text(
            f"📊 *Статус обновлен*\n\n"
            f"📦 CloakBrowser: {'✅' if cloak_status else '❌'}\n"
            f"🌐 Браузер: {'✅' if browser_status else '❌'}\n\n"
            "🔙 /menu",
            parse_mode="Markdown"
        )
        await asyncio.sleep(1)
        await menu(update, context)
    
    elif query.data == "status":
        cloak_status = check_cloak()
        browser_status = check_browser()
        cookies = load_cookies()
        x_cookies = [c for c in cookies if '.x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')]
        browser_active = "🟢 Активен" if browser_instance else "⚫ Не активен"
        
        await query.edit_message_text(
            f"📊 *Статус*\n\n"
            f"📦 CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
            f"🌐 Браузер: {'✅ Установлен' if browser_status else '❌ Не установлен'}\n"
            f"🔄 Состояние: {browser_active}\n"
            f"🍪 Всего кук: {len(cookies)} шт.\n"
            f"🐦 Кук X.COM: {len(x_cookies)} шт.\n"
            f"📄 Последний URL: {last_url or 'Нет'}\n\n"
            "🔄 /check - обновить статус\n"
            "🔙 /menu",
            parse_mode="Markdown"
        )
    
    elif query.data == "cookies":
        cookies = load_cookies()
        cookies_text = cookies_to_string(cookies)
        x_cookies = [c for c in cookies if '.x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')]
        
        keyboard = [
            [InlineKeyboardButton("📥 Загрузить куки", callback_data="cookies_load")],
            [InlineKeyboardButton("🗑️ Очистить куки", callback_data="cookies_clear")],
            [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        await query.edit_message_text(
            f"🍪 *Куки*\n\nВсего: {len(cookies)}\n🐦 X.COM: {len(x_cookies)}\n\n```\n{cookies_text}\n```",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    elif query.data == "cookies_load":
        await query.edit_message_text(
            "📥 *Загрузка кук*\n\n"
            "Отправьте JSON с куками.\n\n"
            "Пример:\n"
            "```json\n"
            "[{\"name\":\"auth_token\",\"value\":\"token\",\"domain\":\".x.com\"}]\n"
            "```",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_cookies'] = True
    
    elif query.data == "cookies_clear":
        if save_cookies([]):
            await query.edit_message_text("✅ Куки очищены!")
            await menu(update, context)
    
    elif query.data == "cookies_show":
        cookies = load_cookies()
        if cookies:
            cookies_json = json.dumps(cookies, indent=2)
            if len(cookies_json) > 4000:
                with open("/tmp/cookies.json", 'w') as f:
                    json.dump(cookies, f, indent=2)
                with open("/tmp/cookies.json", 'rb') as f:
                    await query.message.reply_document(f, filename="cookies.json")
            else:
                await query.edit_message_text(f"```json\n{cookies_json}\n```", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Куки не найдены")
    
    elif query.data == "install_browser":
        await query.edit_message_text(
            "⏳ *Установка браузера...*\n\n"
            "Это может занять 2-3 минуты.\n"
            "Пожалуйста, подождите...",
            parse_mode="Markdown"
        )
        
        success = await install_browser_async()
        browser_status = check_browser()
        
        if success and browser_status:
            await query.edit_message_text(
                "✅ *Браузер успешно установлен!*\n\n"
                f"📊 Статус: {'✅ Работает' if browser_status else '❌ Не работает'}\n\n"
                "🔄 Обновите меню: /menu",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ *Ошибка установки браузера*\n\n"
                "Попробуйте:\n"
                "1. /check - обновить статус\n"
                "2. Перезапустите бота\n"
                "3. Попробуйте позже",
                parse_mode="Markdown"
            )
        
        await asyncio.sleep(2)
        await menu(update, context)
    
    elif query.data == "reinstall":
        await query.edit_message_text("⏳ Переустановка CloakBrowser...")
        try:
            subprocess.run(["pip", "uninstall", "cloakbrowser", "-y"], capture_output=True)
        except:
            pass
        if install_cloak() and check_cloak():
            await query.edit_message_text("✅ CloakBrowser переустановлен!")
        else:
            await query.edit_message_text("❌ Ошибка переустановки")
        await menu(update, context)
    
    elif query.data == "help":
        await query.edit_message_text(
            "❓ *Помощь*\n\n"
            "📌 *Команды:*\n"
            "/browse <URL> - Открыть сайт\n"
            "/x - Открыть X.COM\n"
            "/screenshot - Скриншот\n"
            "/close - Закрыть браузер\n"
            "/cookies - Управление куками\n"
            "/check - Обновить статус\n"
            "/status - Показать статус\n\n"
            "📌 *Если браузер не виден:*\n"
            "1. Нажмите '🔄 Обновить статус'\n"
            "2. Или /check\n"
            "3. Статус обновится автоматически\n\n"
            "🔙 /menu",
            parse_mode="Markdown"
        )
    
    elif query.data == "back_to_menu":
        await menu(update, context)

# ==================== X.COM ====================
async def open_x_com(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_url
    
    if not check_cloak():
        await update.callback_query.message.reply_text("❌ CloakBrowser не установлен!")
        return
    
    if not check_browser():
        await update.callback_query.message.reply_text(
            "❌ Браузер не установлен!\n"
            "Нажмите '⬇️ Установить браузер' в меню"
        )
        return
    
    msg = await update.callback_query.message.edit_text("⏳ Открываю X.COM...")
    
    try:
        page = await init_browser("https://x.com")
        last_url = "https://x.com"
        
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
            current_url = page.url
            if 'login' in current_url or 'i/flow/login' in current_url:
                status = "⚠️ Не авторизован"
                message = "Требуется авторизация на X.COM"
            else:
                timeline = await page.query_selector('[data-testid="primaryColumn"]')
                if timeline:
                    status = "✅ Авторизован"
                    message = "Лента X.COM загружена!"
                else:
                    status = "✅ Страница загружена"
                    message = "X.COM открыт"
        except:
            status = "✅ Страница загружена"
            message = "X.COM открыт"
        
        await msg.edit_text("📸 Делаю скриншот...")
        screenshot = await take_screenshot_from_page()
        
        photo = BytesIO(screenshot)
        photo.name = f"x_{datetime.now().strftime('%H%M%S')}.png"
        await update.callback_query.message.reply_photo(
            photo=photo,
            caption=f"🐦 *X.COM*\n\n{status}\n{message}"
        )
        await update.callback_query.message.reply_text("🔙 /menu")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}\n\n🔙 /menu")

# ==================== СКРИНШОТ ====================
async def take_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_url
    
    if not browser_page:
        url = context.user_data.get('last_url', 'https://google.com')
        try:
            await init_browser(url)
            last_url = url
        except Exception as e:
            await update.callback_query.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")
            return
    
    try:
        screenshot = await take_screenshot_from_page()
        
        photo = BytesIO(screenshot)
        photo.name = f"screenshot_{datetime.now().strftime('%H%M%S')}.png"
        await update.callback_query.message.edit_text("📸 *Скриншот*")
        await update.callback_query.message.reply_photo(
            photo=photo,
            caption=f"🌐 {last_url or 'Текущая страница'}\n🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await update.callback_query.message.reply_text("🔙 /menu")
        
    except Exception as e:
        await update.callback_query.message.edit_text(f"❌ Ошибка: {str(e)[:200]}\n\n🔙 /menu")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_cookies'):
        try:
            cookies = json.loads(update.message.text)
            if isinstance(cookies, list) and len(cookies) > 0:
                if save_cookies(cookies):
                    x_count = len([c for c in cookies if '.x.com' in c.get('domain', '')])
                    await update.message.reply_text(f"✅ Загружено {len(cookies)} кук!\n🐦 X.COM: {x_count}")
                else:
                    await update.message.reply_text("❌ Ошибка сохранения")
            else:
                await update.message.reply_text("❌ Неверный формат")
            context.user_data['waiting_for_cookies'] = False
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    elif context.user_data.get('waiting_for_url'):
        url = update.message.text
        if url.startswith(("http://", "https://")):
            context.user_data['waiting_for_url'] = False
            context.user_data['last_url'] = url
            await browse(update, context)
        else:
            await update.message.reply_text("❌ Неверный URL")

# ==================== КОМАНДЫ ====================
async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_url
    
    if hasattr(update, 'message') and update.message:
        if not context.args:
            await update.message.reply_text("❌ Укажите URL: /browse https://example.com")
            return
        url = context.args[0]
        msg_obj = update.message
    else:
        url = update
        msg_obj = context.user_data.get('message_obj')
        if not msg_obj:
            return
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    context.user_data['last_url'] = url
    last_url = url
    
    if not check_cloak():
        await msg_obj.reply_text("❌ CloakBrowser не установлен!")
        return
    
    if not check_browser():
        await msg_obj.reply_text(
            "❌ Браузер не установлен!\n"
            "Нажмите '⬇️ Установить браузер' в меню"
        )
        return
    
    msg = await msg_obj.reply_text(f"⏳ Открываю {url}...")
    
    try:
        await init_browser(url)
        
        await msg.edit_text("📸 Делаю скриншот...")
        screenshot = await take_screenshot_from_page()
        
        photo = BytesIO(screenshot)
        photo.name = f"browse_{datetime.now().strftime('%H%M%S')}.png"
        await msg_obj.reply_photo(photo=photo, caption=f"✅ {url}")
        await msg_obj.reply_text("🔙 /menu")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}\n\n🔙 /menu")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю статус...")
    
    cloak_status = check_cloak()
    browser_status = check_browser()
    
    await update.message.reply_text(
        f"📊 *Статус обновлен*\n\n"
        f"📦 CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
        f"🌐 Браузер: {'✅ Установлен' if browser_status else '❌ Не установлен'}\n\n"
        "🔄 Если браузер не виден, нажмите '⬇️ Установить браузер'\n"
        "🔙 /menu",
        parse_mode="Markdown"
    )

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        def __init__(self, msg):
            self.message = msg
        async def answer(self):
            pass
    update.callback_query = FakeQuery(update.message)
    await open_x_com(update, context)

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class FakeQuery:
        def __init__(self, msg):
            self.message = msg
        async def answer(self):
            pass
    update.callback_query = FakeQuery(update.message)
    await take_screenshot(update, context)

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await close_browser()
    await update.message.reply_text("🗑️ Браузер закрыт!\n\n🔙 /menu")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cloak_status = check_cloak()
    browser_status = check_browser()
    cookies = load_cookies()
    x_cookies = [c for c in cookies if '.x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')]
    browser_active = "🟢 Активен" if browser_instance else "⚫ Не активен"
    
    await update.message.reply_text(
        f"📊 *Статус*\n\n"
        f"📦 CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
        f"🌐 Браузер: {'✅ Установлен' if browser_status else '❌ Не установлен'}\n"
        f"🔄 Состояние: {browser_active}\n"
        f"🍪 Всего кук: {len(cookies)} шт.\n"
        f"🐦 Кук X.COM: {len(x_cookies)} шт.\n"
        f"📄 Последний URL: {last_url or 'Нет'}\n\n"
        "🔄 /check - обновить статус\n"
        "🔙 /menu",
        parse_mode="Markdown"
    )

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = load_cookies()
    x_cookies = [c for c in cookies if '.x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', '')]
    
    keyboard = [
        [InlineKeyboardButton("📥 Загрузить", callback_data="cookies_load")],
        [InlineKeyboardButton("🗑️ Очистить", callback_data="cookies_clear")],
        [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    await update.message.reply_text(
        f"🍪 *Куки*\n\nВсего: {len(cookies)}\n🐦 X.COM: {len(x_cookies)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "📌 *Команды:*\n"
        "/browse <URL> - Открыть сайт\n"
        "/x - Открыть X.COM\n"
        "/screenshot - Скриншот\n"
        "/close - Закрыть браузер\n"
        "/cookies - Управление куками\n"
        "/check - Обновить статус\n"
        "/status - Показать статус\n\n"
        "📌 *Если браузер не виден:*\n"
        "1. Нажмите '🔄 Обновить статус'\n"
        "2. Или /check\n"
        "3. Статус обновится автоматически\n\n"
        "🔙 /menu",
        parse_mode="Markdown"
    )

# ==================== ЗАПУСК ====================
def main():
    """Главная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Устанавливаем команды
        application.post_init = set_bot_commands
        
        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(CommandHandler("browse", browse))
        application.add_handler(CommandHandler("x", x_command))
        application.add_handler(CommandHandler("screenshot", screenshot_command))
        application.add_handler(CommandHandler("close", close_command))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("cookies", cookies_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CallbackQueryHandler(handle_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("🚀 Бот запущен!")
        
        # Запускаем бота (синхронно)
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()