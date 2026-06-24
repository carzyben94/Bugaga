# bot.py - исправленная версия с правильным импортом
import os
import subprocess
import logging
import json
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

# ==================== УСТАНОВКА CLOAKBROWSER ====================
def install_cloak():
    """Установка CloakBrowser через pip"""
    try:
        logger.info("Устанавливаю CloakBrowser...")
        result = subprocess.run(
            ["pip", "install", "cloakbrowser"],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"✅ CloakBrowser установлен")
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

# Проверяем и устанавливаем
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

logger.info(f"📊 CloakBrowser статус: {CLOAK_AVAILABLE}")

# ==================== РАБОТА С КУКАМИ ====================
def load_cookies():
    """Загружает куки из файла"""
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Ошибка загрузки кук: {e}")
        return []

def save_cookies(cookies):
    """Сохраняет куки в файл"""
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
    """Преобразует куки в строку для отображения"""
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
        BotCommand("reinstall", "🔄 Переустановить"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cloak_status = check_cloak()
    
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Куки", callback_data="cookies")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        [InlineKeyboardButton("🔄 Переустановить", callback_data="reinstall")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ Доступен" if cloak_status else "❌ Недоступен"
    cookies_count = len(load_cookies())
    
    await update.message.reply_text(
        f"🤖 *CloakBrowser Bot*\n\n"
        f"Бот для безопасного просмотра веб-страниц.\n\n"
        f"📦 Статус: {status}\n"
        f"🍪 Куки: {cookies_count} шт.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🍪 Куки", callback_data="cookies")],
        [InlineKeyboardButton("🔄 Переустановить", callback_data="reinstall")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = update.message if update.message else update.callback_query.message
    
    await message.reply_text(
        "📋 *Главное меню*\n\nВыберите опцию:",
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
            "`/browse https://example.com`",
            parse_mode="Markdown"
        )
    
    elif query.data == "status":
        cloak_status = check_cloak()
        cookies = load_cookies()
        await query.edit_message_text(
            f"📊 *Статус*\n\n"
            f"CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
            f"🍪 Куки: {len(cookies)} шт.",
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
            "Отправьте куки в формате JSON одним сообщением.\n\n"
            "Пример формата:\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"name\": \"cookie_name\",\n"
            "    \"value\": \"cookie_value\",\n"
            "    \"domain\": \".example.com\"\n"
            "  }\n"
            "]\n"
            "```\n\n"
            "Просто отправьте JSON файл или текст с куками.",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_cookies'] = True
    
    elif query.data == "cookies_clear":
        if save_cookies([]):
            await query.edit_message_text("✅ Все куки очищены!")
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
                    "Куки сохранены в файл. Скачайте его:",
                    parse_mode="Markdown"
                )
                with open("/tmp/cookies_export.json", 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="cookies.json",
                        caption="🍪 Все куки в формате JSON"
                    )
            else:
                await query.edit_message_text(
                    f"📋 *Все куки*\n\n"
                    f"```json\n{cookies_json}\n```",
                    parse_mode="Markdown"
                )
        else:
            await query.edit_message_text("❌ Куки не найдены")
    
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
    
    elif query.data == "info":
        version = "Неизвестно"
        try:
            import pkg_resources
            version = pkg_resources.get_distribution("cloakbrowser").version
        except:
            pass
        
        cloak_status = check_cloak()
        cookies = load_cookies()
        
        await query.edit_message_text(
            f"ℹ️ *Информация*\n\n"
            f"🤖 CloakBrowser Bot v5.0\n"
            f"📦 Статус: {'✅ Установлен' if cloak_status else '❌ Не установлен'}\n"
            f"📌 Версия: {version}\n"
            f"🍪 Куки: {len(cookies)} шт.\n"
            f"🌐 Платформа: Railway\n"
            f"🐍 Python: 3.9+",
            parse_mode="Markdown"
        )
    
    elif query.data == "help":
        await query.edit_message_text(
            "❓ *Помощь*\n\n"
            "📌 *Команды:*\n"
            "/start - Запустить бота\n"
            "/menu - Открыть меню\n"
            "/browse <URL> - Открыть сайт\n"
            "/status - Статус CloakBrowser\n"
            "/cookies - Управление куками\n"
            "/reinstall - Переустановить CloakBrowser\n"
            "/help - Эта справка\n\n"
            "📌 *Примеры:*\n"
            "`/browse https://github.com`\n"
            "`/cookies` - управление куками",
            parse_mode="Markdown"
        )
    
    elif query.data == "back_to_menu":
        await menu(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для загрузки кук"""
    if context.user_data.get('waiting_for_cookies'):
        try:
            text = update.message.text
            cookies = json.loads(text)
            
            if isinstance(cookies, list) and len(cookies) > 0:
                if save_cookies(cookies):
                    await update.message.reply_text(
                        f"✅ Загружено {len(cookies)} кук!\n\n"
                        f"Первая кука: {cookies[0].get('name', 'unknown')}"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка сохранения кук")
            else:
                await update.message.reply_text("❌ Неверный формат: ожидается массив кук")
            
            context.user_data['waiting_for_cookies'] = False
            
        except json.JSONDecodeError as e:
            await update.message.reply_text(
                f"❌ Ошибка парсинга JSON: {str(e)}\n\n"
                "Проверьте формат и попробуйте снова."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажите URL*\n\n"
            "Пример: `/browse https://example.com`",
            parse_mode="Markdown"
        )
        return
    
    if not check_cloak():
        await update.message.reply_text(
            "❌ CloakBrowser не установлен!\n"
            "Используйте /reinstall для установки"
        )
        return
    
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        # Импортируем через playwright.async_api (CloakBrowser использует тот же API)
        from playwright.async_api import async_playwright
        
        # Загружаем куки
        cookies = load_cookies()
        logger.info(f"🍪 Загружено {len(cookies)} кук для {url}")
        
        # Используем асинхронный контекстный менеджер
        async with async_playwright() as p:
            # Запускаем браузер (CloakBrowser подменяет стандартный playwright)
            logger.info(f"🚀 Запускаю CloakBrowser для {url}")
            browser = await p.chromium.launch(headless=True)
            context_browser = await browser.new_context()
            page = await context_browser.new_page()
            
            # Устанавливаем куки
            if cookies:
                try:
                    await context_browser.add_cookies(cookies)
                    logger.info(f"✅ Установлено {len(cookies)} кук")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка установки кук: {e}")
            
            # Открываем URL
            logger.info(f"🌐 Перехожу по адресу: {url}")
            await page.goto(url, timeout=30000)
            
            # Получаем заголовки
            user_agent = await page.evaluate("() => navigator.userAgent")
            logger.info(f"📱 User-Agent: {user_agent}")
            
            # Закрываем браузер
            await browser.close()
            logger.info(f"✅ Страница открыта: {url}")
            
            keyboard = [
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")],
                [InlineKeyboardButton("🌐 Открыть другой", callback_data="browse")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await msg.edit_text(
                f"✅ *Страница открыта!*\n\n"
                f"🌐 URL: {url}\n"
                f"🍪 Кук использовано: {len(cookies)}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта playwright: {e}")
        await msg.edit_text(
            "❌ *Ошибка*\n\n"
            "Playwright не установлен. Устанавливаю...\n"
            "Попробуйте снова через минуту.",
            parse_mode="Markdown"
        )
        # Устанавливаем playwright если его нет
        subprocess.run(["pip", "install", "playwright"], check=False)
        subprocess.run(["playwright", "install", "chromium"], check=False)
        
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"❌ Ошибка открытия {url}: {error_msg}")
        await msg.edit_text(
            f"❌ *Ошибка*\n\n```\n{error_msg}\n```",
            parse_mode="Markdown"
        )

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /cookies"""
    cookies = load_cookies()
    cookies_text = cookies_to_string(cookies)
    
    keyboard = [
        [InlineKeyboardButton("📥 Загрузить куки", callback_data="cookies_load")],
        [InlineKeyboardButton("🗑️ Очистить куки", callback_data="cookies_clear")],
        [InlineKeyboardButton("📋 Показать все", callback_data="cookies_show")],
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
    cookies = load_cookies()
    await update.message.reply_text(
        f"📊 *Статус CloakBrowser*\n\n"
        f"Состояние: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
        f"📦 Пакет: {'установлен' if cloak_status else 'не установлен'}\n"
        f"🍪 Куки: {len(cookies)} шт.",
        parse_mode="Markdown"
    )

async def reinstall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Переустановка CloakBrowser...")
    
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
            await update.message.reply_text("✅ CloakBrowser переустановлен!")
        else:
            await update.message.reply_text("❌ Ошибка импорта после установки")
    else:
        await update.message.reply_text("❌ Ошибка переустановки")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "📌 *Команды:*\n"
        "/start - Запустить бота\n"
        "/menu - Открыть меню\n"
        "/browse <URL> - Открыть сайт\n"
        "/status - Статус CloakBrowser\n"
        "/cookies - Управление куками\n"
        "/reinstall - Переустановить CloakBrowser\n"
        "/help - Показать справку\n\n"
        "📌 *Примеры:*\n"
        "`/browse https://github.com`\n"
        "`/cookies` - управление куками\n\n"
        "📌 *Как загрузить куки:*\n"
        "1. Нажмите '🍪 Куки' в меню\n"
        "2. Выберите '📥 Загрузить куки'\n"
        "3. Отправьте JSON с куками",
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
    app.add_handler(CommandHandler("reinstall", reinstall))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()