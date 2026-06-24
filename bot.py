# bot.py - полная асинхронная версия
import os
import subprocess
import logging
import json
import asyncio
import concurrent.futures
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
BROWSER_STATUS = {
    'installed': False,
    'installing': False
}

# ==================== УСТАНОВКА БРАУЗЕРА ====================
def install_browser_sync():
    """Синхронная установка браузера (для запуска в отдельном потоке)"""
    try:
        logger.info("🔄 Устанавливаю браузер для CloakBrowser...")
        
        # Устанавливаем playwright если его нет
        subprocess.run(
            ["pip", "install", "playwright"],
            check=True,
            capture_output=True
        )
        logger.info("✅ Playwright установлен")
        
        # Устанавливаем браузер
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("✅ Браузер Chromium установлен")
            BROWSER_STATUS['installed'] = True
            BROWSER_STATUS['installing'] = False
            return True
        else:
            logger.error(f"❌ Ошибка установки браузера: {result.stderr}")
            BROWSER_STATUS['installing'] = False
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        BROWSER_STATUS['installing'] = False
        return False

async def install_browser_async():
    """Асинхронная обертка для установки браузера"""
    if BROWSER_STATUS['installing']:
        return False
    
    BROWSER_STATUS['installing'] = True
    
    # Запускаем в отдельном потоке
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, install_browser_sync)
    
    return result

def check_browser():
    """Проверяет наличие браузера"""
    try:
        # Проверяем наличие папки с браузером
        home_dir = os.path.expanduser("~")
        import glob
        browser_paths = [
            f"{home_dir}/.cache/ms-playwright/chromium-*",
            f"{home_dir}/.cache/ms-playwright/chromium_headless_shell-*",
        ]
        
        for path in browser_paths:
            if glob.glob(path):
                BROWSER_STATUS['installed'] = True
                return True
        
        # Пробуем запустить через асинхронный API
        try:
            import asyncio
            from playwright.async_api import async_playwright
            
            async def test_browser():
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    await browser.close()
                    return True
            
            # Запускаем тест
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(test_browser())
            loop.close()
            
            if result:
                BROWSER_STATUS['installed'] = True
                return True
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки браузера: {e}")
        
        BROWSER_STATUS['installed'] = False
        return False
            
    except Exception as e:
        logger.warning(f"⚠️ Браузер не найден: {e}")
        BROWSER_STATUS['installed'] = False
        return False

# ==================== УСТАНОВКА CLOAKBROWSER ====================
def install_cloak():
    """Установка CloakBrowser через pip"""
    try:
        logger.info("Устанавливаю CloakBrowser...")
        subprocess.run(
            ["pip", "install", "cloakbrowser"],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info("✅ CloakBrowser установлен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка установки: {e}")
        return False

def check_cloak():
    """Проверяет доступность CloakBrowser"""
    try:
        import cloakbrowser
        return True
    except ImportError:
        return False

# Проверяем и устанавливаем CloakBrowser
CLOAK_AVAILABLE = check_cloak()

if not CLOAK_AVAILABLE:
    logger.warning("⚠️ CloakBrowser не найден, устанавливаю...")
    if install_cloak():
        CLOAK_AVAILABLE = check_cloak()
        if CLOAK_AVAILABLE:
            logger.info("✅ CloakBrowser успешно установлен")
        else:
            logger.error("❌ Не удалось импортировать CloakBrowser после установки")
else:
    logger.info("✅ CloakBrowser уже установлен")

# Проверяем браузер
check_browser()

logger.info(f"📊 CloakBrowser статус: {CLOAK_AVAILABLE}")
logger.info(f"📊 Браузер статус: {BROWSER_STATUS['installed']}")

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

# ==================== КОМАНДЫ БОТА ====================
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("menu", "📋 Открыть меню"),
        BotCommand("browse", "🌐 Открыть URL"),
        BotCommand("status", "📊 Статус"),
        BotCommand("cookies", "🍪 Управление куками"),
        BotCommand("help", "❓ Помощь"),
    ]
    await application.bot.set_my_commands(commands)

async def get_main_keyboard():
    """Создает главную клавиатуру"""
    cloak_status = check_cloak()
    browser_status = check_browser()
    cookies_count = len(load_cookies())
    
    # Статусная строка
    status_line = f"📦 CloakBrowser: {'✅' if cloak_status else '❌'} | 🌐 Браузер: {'✅' if browser_status else '❌'} | 🍪 {cookies_count}"
    
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Куки (" + str(cookies_count) + ")", callback_data="cookies")],
    ]
    
    # Кнопка установки браузера если он не установлен
    if not browser_status:
        keyboard.append([InlineKeyboardButton("⬇️ Установить браузер", callback_data="install_browser")])
    
    keyboard.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="help")])
    
    # Добавляем кнопку переустановки только если что-то не работает
    if not cloak_status:
        keyboard.append([InlineKeyboardButton("🔄 Переустановить CloakBrowser", callback_data="reinstall")])
    
    return InlineKeyboardMarkup(keyboard), status_line

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup, status_line = await get_main_keyboard()
    
    await update.message.reply_text(
        f"🤖 *CloakBrowser Bot*\n\n"
        f"Бот для безопасного просмотра веб-страниц.\n\n"
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

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "browse":
        await query.edit_message_text(
            "🌐 *Введите URL*\n\n"
            "Используйте команду:\n"
            "`/browse https://example.com`\n\n"
            "Или просто отправьте ссылку в чат.",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_url'] = True
    
    elif query.data == "status":
        cloak_status = check_cloak()
        browser_status = check_browser()
        cookies = load_cookies()
        
        status_text = f"""📊 *Статус*

📦 CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}
🌐 Браузер: {'✅ Установлен' if browser_status else '❌ Не установлен'}
🍪 Куки: {len(cookies)} шт.

⬇️ Установка браузера: /install_browser
🔄 Переустановка: /reinstall"""
        
        await query.edit_message_text(
            status_text,
            parse_mode="Markdown"
        )
        await query.message.reply_text(
            "🔙 Вернуться в меню: /menu",
            parse_mode="Markdown"
        )
    
    elif query.data == "cookies":
        cookies = load_cookies()
        cookies_text = cookies_to_string(cookies)
        
        keyboard = [
            [InlineKeyboardButton("📥 Загрузить куки", callback_data="cookies_load")],
            [InlineKeyboardButton("🗑️ Очистить куки", callback_data="cookies_clear")],
            [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🍪 *Управление куками*\n\n"
            f"Всего кук: {len(cookies)}\n\n"
            f"```\n{cookies_text}\n```",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif query.data == "cookies_load":
        await query.edit_message_text(
            "📥 *Загрузка кук*\n\n"
            "Отправьте куки в формате JSON.\n\n"
            "Пример:\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"name\": \"cookie_name\",\n"
            "    \"value\": \"cookie_value\",\n"
            "    \"domain\": \".example.com\"\n"
            "  }\n"
            "]\n"
            "```\n\n"
            "Просто отправьте JSON текст или файл.",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_cookies'] = True
    
    elif query.data == "cookies_clear":
        if save_cookies([]):
            await query.edit_message_text("✅ Все куки очищены!")
            await asyncio.sleep(1)
            await menu(update, context)
        else:
            await query.edit_message_text("❌ Ошибка очистки кук")
    
    elif query.data == "cookies_show":
        cookies = load_cookies()
        if cookies:
            cookies_json = json.dumps(cookies, indent=2)
            if len(cookies_json) > 4000:
                with open("/tmp/cookies_export.json", 'w') as f:
                    json.dump(cookies, f, indent=2)
                await query.edit_message_text(
                    "📋 *Все куки*\n\n"
                    "Куки сохранены в файл:",
                    parse_mode="Markdown"
                )
                with open("/tmp/cookies_export.json", 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="cookies.json",
                        caption="🍪 Все куки в формате JSON"
                    )
                await query.message.reply_text("🔙 Вернуться в меню: /menu")
            else:
                await query.edit_message_text(
                    f"📋 *Все куки*\n\n"
                    f"```json\n{cookies_json}\n```",
                    parse_mode="Markdown"
                )
                await query.message.reply_text("🔙 Вернуться в меню: /menu")
        else:
            await query.edit_message_text("❌ Куки не найдены")
    
    elif query.data == "install_browser":
        await query.edit_message_text(
            "⏳ *Установка браузера...*\n\n"
            "Это может занять 2-3 минуты.\n"
            "Пожалуйста, подождите...",
            parse_mode="Markdown"
        )
        
        # Устанавливаем браузер
        success = await install_browser_async()
        
        if success:
            await query.edit_message_text(
                "✅ *Браузер успешно установлен!*\n\n"
                "Теперь можно открывать сайты:\n"
                "`/browse https://example.com`",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ *Ошибка установки браузера*\n\n"
                "Попробуйте позже или вручную:\n"
                "`playwright install chromium`",
                parse_mode="Markdown"
            )
        
        # Обновляем меню
        await asyncio.sleep(1)
        await menu(update, context)
    
    elif query.data == "reinstall":
        await query.edit_message_text("⏳ Переустановка CloakBrowser...")
        
        try:
            subprocess.run(
                ["pip", "uninstall", "cloakbrowser", "-y"],
                check=True,
                capture_output=True
            )
            logger.info("🗑️ CloakBrowser удален")
        except:
            pass
        
        if install_cloak():
            if check_cloak():
                await query.edit_message_text("✅ CloakBrowser переустановлен!")
            else:
                await query.edit_message_text("❌ Ошибка импорта после установки")
        else:
            await query.edit_message_text("❌ Ошибка переустановки")
        
        await asyncio.sleep(1)
        await menu(update, context)
    
    elif query.data == "help":
        await query.edit_message_text(
            "❓ *Помощь*\n\n"
            "📌 *Основные команды:*\n"
            "/start - Запустить бота\n"
            "/menu - Открыть меню\n"
            "/browse <URL> - Открыть сайт\n"
            "/status - Статус\n"
            "/cookies - Управление куками\n\n"
            "📌 *Как открыть сайт:*\n"
            "1. Нажмите '🌐 Открыть сайт'\n"
            "2. Введите URL: `/browse https://example.com`\n\n"
            "📌 *Как загрузить куки:*\n"
            "1. Нажмите '🍪 Куки'\n"
            "2. Выберите '📥 Загрузить куки'\n"
            "3. Отправьте JSON с куками\n\n"
            "📌 *Советы:*\n"
            "• Если браузер не установлен - нажмите '⬇️ Установить браузер'\n"
            "• Если что-то не работает - нажмите '🔄 Переустановить'\n"
            "• Статус обновляется автоматически",
            parse_mode="Markdown"
        )
    
    elif query.data == "back_to_menu":
        await menu(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка загрузки кук
    if context.user_data.get('waiting_for_cookies'):
        try:
            text = update.message.text
            cookies = json.loads(text)
            
            if isinstance(cookies, list) and len(cookies) > 0:
                if save_cookies(cookies):
                    await update.message.reply_text(
                        f"✅ Загружено {len(cookies)} кук!\n"
                        f"Первая кука: {cookies[0].get('name', 'unknown')}\n\n"
                        "🔙 Вернуться в меню: /menu"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка сохранения кук")
            else:
                await update.message.reply_text("❌ Неверный формат: ожидается массив кук")
            
            context.user_data['waiting_for_cookies'] = False
            
        except json.JSONDecodeError as e:
            await update.message.reply_text(
                f"❌ Ошибка парсинга JSON: {str(e)}\n\n"
                "Проверьте формат и попробуйте снова.\n"
                "Или отправьте файл .json"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    # Обработка открытия URL
    elif context.user_data.get('waiting_for_url'):
        url = update.message.text
        if url.startswith(("http://", "https://")):
            context.user_data['waiting_for_url'] = False
            # Вызываем /browse с этим URL
            await browse(update, context)
        else:
            await update.message.reply_text(
                "❌ Неверный формат URL\n"
                "Пример: https://example.com"
            )
    
    # Обработка файлов с куками
    elif update.message.document:
        try:
            file = await update.message.document.get_file()
            file_path = f"/tmp/{update.message.document.file_name}"
            await file.download_to_drive(file_path)
            
            with open(file_path, 'r') as f:
                cookies = json.load(f)
            
            if isinstance(cookies, list) and len(cookies) > 0:
                if save_cookies(cookies):
                    await update.message.reply_text(
                        f"✅ Загружено {len(cookies)} кук из файла!\n\n"
                        "🔙 Вернуться в меню: /menu"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка сохранения кук")
            else:
                await update.message.reply_text("❌ Неверный формат: ожидается массив кук")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка загрузки файла: {str(e)}")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Определяем источник вызова
    if hasattr(update, 'message') and update.message:
        if not context.args:
            await update.message.reply_text(
                "❌ *Укажите URL*\n\n"
                "Пример: `/browse https://example.com`",
                parse_mode="Markdown"
            )
            return
        
        url = context.args[0]
        msg_obj = update.message
    else:
        # Вызвано из handle_message
        url = update
        msg_obj = context.user_data.get('message_obj')
        if not msg_obj:
            return
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    # Проверяем CloakBrowser
    if not check_cloak():
        await msg_obj.reply_text(
            "❌ CloakBrowser не установлен!\n"
            "Используйте /reinstall для установки"
        )
        return
    
    # Проверяем браузер
    if not check_browser():
        await msg_obj.reply_text(
            "❌ Браузер не установлен!\n"
            "Нажмите '⬇️ Установить браузер' в меню"
        )
        return
    
    msg = await msg_obj.reply_text(f"⏳ Открываю {url}...")
    
    try:
        from playwright.async_api import async_playwright
        
        cookies = load_cookies()
        logger.info(f"🍪 Загружено {len(cookies)} кук для {url}")
        
        async with async_playwright() as p:
            logger.info(f"🚀 Запускаю браузер для {url}")
            browser = await p.chromium.launch(headless=True)
            context_browser = await browser.new_context()
            page = await context_browser.new_page()
            
            if cookies:
                try:
                    await context_browser.add_cookies(cookies)
                    logger.info(f"✅ Установлено {len(cookies)} кук")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка установки кук: {e}")
            
            logger.info(f"🌐 Перехожу по адресу: {url}")
            await page.goto(url, timeout=30000)
            
            # Получаем заголовки
            user_agent = await page.evaluate("() => navigator.userAgent")
            title = await page.evaluate("() => document.title")
            logger.info(f"📱 User-Agent: {user_agent}")
            logger.info(f"📄 Title: {title}")
            
            await browser.close()
            logger.info(f"✅ Страница открыта: {url}")
            
            await msg.edit_text(
                f"✅ *Страница открыта!*\n\n"
                f"🌐 URL: {url}\n"
                f"📄 Заголовок: {title[:100]}\n"
                f"🍪 Кук использовано: {len(cookies)}",
                parse_mode="Markdown"
            )
            await msg_obj.reply_text(
                "🔙 Вернуться в меню: /menu",
                parse_mode="Markdown"
            )
        
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"❌ Ошибка открытия {url}: {error_msg}")
        await msg.edit_text(
            f"❌ *Ошибка*\n\n"
            f"```\n{error_msg}\n```\n\n"
            "🔙 Вернуться в меню: /menu",
            parse_mode="Markdown"
        )

async def install_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /install_browser"""
    await update.message.reply_text(
        "⏳ *Установка браузера...*\n\n"
        "Это может занять 2-3 минуты.\n"
        "Пожалуйста, подождите...",
        parse_mode="Markdown"
    )
    
    success = await install_browser_async()
    
    if success:
        await update.message.reply_text(
            "✅ *Браузер успешно установлен!*\n\n"
            "Теперь можно открывать сайты:\n"
            "`/browse https://example.com`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ *Ошибка установки браузера*\n\n"
            "Попробуйте позже или вручную:\n"
            "`playwright install chromium`",
            parse_mode="Markdown"
        )
    
    await menu(update, context)

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies = load_cookies()
    cookies_text = cookies_to_string(cookies)
    
    keyboard = [
        [InlineKeyboardButton("📥 Загрузить куки", callback_data="cookies_load")],
        [InlineKeyboardButton("🗑️ Очистить куки", callback_data="cookies_clear")],
        [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🍪 *Управление куками*\n\n"
        f"Всего кук: {len(cookies)}\n\n"
        f"```\n{cookies_text}\n```",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cloak_status = check_cloak()
    browser_status = check_browser()
    cookies = load_cookies()
    
    await update.message.reply_text(
        f"📊 *Статус*\n\n"
        f"📦 CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
        f"🌐 Браузер: {'✅ Установлен' if browser_status else '❌ Не установлен'}\n"
        f"🍪 Куки: {len(cookies)} шт.\n\n"
        "🔙 Вернуться в меню: /menu",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "📌 *Основные команды:*\n"
        "/start - Запустить бота\n"
        "/menu - Открыть меню\n"
        "/browse <URL> - Открыть сайт\n"
        "/status - Статус\n"
        "/cookies - Управление куками\n\n"
        "📌 *Как открыть сайт:*\n"
        "1. Нажмите '🌐 Открыть сайт'\n"
        "2. Введите URL: `/browse https://example.com`\n\n"
        "📌 *Как загрузить куки:*\n"
        "1. Нажмите '🍪 Куки'\n"
        "2. Выберите '📥 Загрузить куки'\n"
        "3. Отправьте JSON с куками\n\n"
        "📌 *Советы:*\n"
        "• Если браузер не установлен - нажмите '⬇️ Установить браузер'\n"
        "• Если что-то не работает - нажмите '🔄 Переустановить'\n"
        "• Статус обновляется автоматически\n\n"
        "🔙 Вернуться в меню: /menu",
        parse_mode="Markdown"
    )

# ==================== ЗАПУСК БОТА ====================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.post_init = set_bot_commands
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("install_browser", install_browser_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()