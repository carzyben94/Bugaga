# bot.py
import os
import subprocess
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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

# ==================== КОМАНДЫ БОТА ====================
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("menu", "📋 Открыть меню"),
        BotCommand("browse", "🌐 Открыть URL"),
        BotCommand("status", "📊 Статус"),
        BotCommand("help", "❓ Помощь"),
        BotCommand("reinstall", "🔄 Переустановить"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем актуальный статус
    cloak_status = check_cloak()
    
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        [InlineKeyboardButton("🔄 Переустановить", callback_data="reinstall")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ Доступен" if cloak_status else "❌ Недоступен"
    
    await update.message.reply_text(
        f"🤖 *CloakBrowser Bot*\n\n"
        f"Бот для безопасного просмотра веб-страниц.\n\n"
        f"📦 Статус: {status}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
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
        await query.edit_message_text(
            f"📊 *Статус*\n\n"
            f"CloakBrowser: {'✅ Доступен' if cloak_status else '❌ Недоступен'}",
            parse_mode="Markdown"
        )
    
    elif query.data == "reinstall":
        await query.edit_message_text("⏳ Переустановка CloakBrowser...")
        
        # Удаляем старую версию
        try:
            subprocess.run(
                ["pip", "uninstall", "cloakbrowser", "-y"],
                check=True,
                capture_output=True
            )
            logger.info("🗑️ CloakBrowser удален")
        except:
            pass
        
        # Устанавливаем заново
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
        
        await query.edit_message_text(
            f"ℹ️ *Информация*\n\n"
            f"🤖 CloakBrowser Bot v4.2\n"
            f"📦 Статус: {'✅ Установлен' if cloak_status else '❌ Не установлен'}\n"
            f"📌 Версия: {version}\n"
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
            "/reinstall - Переустановить CloakBrowser\n"
            "/help - Эта справка\n\n"
            "📌 *Пример:*\n"
            "`/browse https://github.com`",
            parse_mode="Markdown"
        )
    
    elif query.data == "back_to_menu":
        await menu(update, context)

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажите URL*\n\n"
            "Пример: `/browse https://example.com`",
            parse_mode="Markdown"
        )
        return
    
    # Проверяем статус перед использованием
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
        from cloakbrowser import launch
        
        # Запускаем браузер
        logger.info(f"🚀 Запускаю CloakBrowser для {url}")
        browser = launch(headless=True)
        page = browser.new_page()
        
        # Открываем URL
        logger.info(f"🌐 Перехожу по адресу: {url}")
        page.goto(url, timeout=30000)
        
        # Закрываем браузер
        browser.close()
        logger.info(f"✅ Страница открыта: {url}")
        
        keyboard = [
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")],
            [InlineKeyboardButton("🌐 Открыть другой", callback_data="browse")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"✅ *Страница открыта!*\n\n"
            f"🌐 URL: {url}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"❌ Ошибка открытия {url}: {error_msg}")
        await msg.edit_text(
            f"❌ *Ошибка*\n\n```\n{error_msg}\n```",
            parse_mode="Markdown"
        )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cloak_status = check_cloak()
    await update.message.reply_text(
        f"📊 *Статус CloakBrowser*\n\n"
        f"Состояние: {'✅ Доступен' if cloak_status else '❌ Недоступен'}\n"
        f"📦 Пакет: {'установлен' if cloak_status else 'не установлен'}",
        parse_mode="Markdown"
    )

async def reinstall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Переустановка CloakBrowser...")
    
    # Удаляем старую версию
    try:
        subprocess.run(
            ["pip", "uninstall", "cloakbrowser", "-y"],
            check=True,
            capture_output=True
        )
        logger.info("🗑️ CloakBrowser удален")
    except:
        pass
    
    # Устанавливаем заново
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
        "/reinstall - Переустановить CloakBrowser\n"
        "/help - Показать справку\n\n"
        "📌 *Пример:*\n"
        "`/browse https://example.com`",
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
    app.add_handler(CommandHandler("reinstall", reinstall))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()