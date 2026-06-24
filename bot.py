# bot.py
import os
import subprocess
import sys
import time
import logging
import urllib.request
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CLOAK_DIR = "/app/cloak"
CLOAK_BINARY = f"{CLOAK_DIR}/cloak"

def download_with_retry(url, output, max_retries=3):
    """Скачивание с повторными попытками"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка {attempt + 1}/{max_retries} скачать {url}")
            
            # Используем urllib вместо wget
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=30) as response:
                with open(output, 'wb') as f:
                    f.write(response.read())
            
            logger.info(f"Скачано: {output}")
            return True
            
        except Exception as e:
            logger.warning(f"Ошибка загрузки (попытка {attempt+1}): {e}")
            time.sleep(5)
    
    return False

def get_latest_release_url():
    """Получает URL последнего релиза через GitHub API"""
    try:
        api_url = "https://api.github.com/repos/coder3101/cloak/releases/latest"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            
            # Ищем asset для linux-amd64
            for asset in data.get('assets', []):
                if 'linux-amd64' in asset['name']:
                    return asset['browser_download_url']
            
            # Если не нашли, берем первый tar.gz
            for asset in data.get('assets', []):
                if asset['name'].endswith('.tar.gz'):
                    return asset['browser_download_url']
                    
    except Exception as e:
        logger.error(f"Ошибка получения релиза: {e}")
    
    return None

def install_cloak():
    """Автоматическая установка CloakBrowser"""
    logger.info("Начинаю установку CloakBrowser...")
    
    os.makedirs(CLOAK_DIR, exist_ok=True)
    
    # Пробуем получить URL через API
    download_url = get_latest_release_url()
    
    # Резервные URL если API не работает
    fallback_urls = [
        "https://github.com/coder3101/cloak/releases/download/v0.3.0/cloak-linux-amd64.tar.gz",
        "https://github.com/coder3101/cloak/releases/download/v0.2.0/cloak-linux-amd64.tar.gz",
    ]
    
    downloaded = False
    
    # Пробуем скачать
    if download_url:
        logger.info(f"Скачиваю с: {download_url}")
        if download_with_retry(download_url, f"{CLOAK_DIR}/cloak.tar.gz"):
            downloaded = True
    
    # Если не скачалось, пробуем резервные URL
    if not downloaded:
        for url in fallback_urls:
            logger.info(f"Пробую резервный URL: {url}")
            if download_with_retry(url, f"{CLOAK_DIR}/cloak.tar.gz"):
                downloaded = True
                break
    
    if not downloaded:
        logger.error("Не удалось скачать CloakBrowser")
        return False
    
    # Распаковываем
    try:
        subprocess.run([
            "tar", "-xzf", f"{CLOAK_DIR}/cloak.tar.gz",
            "-C", CLOAK_DIR
        ], check=True, capture_output=True)
        
        os.chmod(CLOAK_BINARY, 0o755)
        logger.info("CloakBrowser успешно установлен!")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка распаковки: {e}")
        return False

# Проверяем и устанавливаем Cloak при запуске
if not os.path.exists(CLOAK_BINARY):
    install_cloak()
else:
    logger.info("CloakBrowser уже установлен")

# Функции бота
async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("menu", "📋 Открыть главное меню"),
        BotCommand("browse", "🌐 Открыть URL"),
        BotCommand("status", "📊 Статус CloakBrowser"),
        BotCommand("help", "❓ Помощь"),
        BotCommand("install", "🔧 Переустановить CloakBrowser"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🔧 Переустановить", callback_data="reinstall")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *CloakBrowser Bot*\n\n"
        "Бот для безопасного просмотра веб-страниц.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("🔄 Очистить кэш", callback_data="clear_cache")],
        [InlineKeyboardButton("🔧 Переустановить", callback_data="reinstall")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = update.message if update.message else update.callback_query.message
    
    await message.reply_text(
        "📋 *Главное меню*\n\n"
        "Выберите нужную опцию:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "browse":
        await query.edit_message_text(
            "🌐 *Введите URL для открытия*\n\n"
            "Используйте команду:\n"
            "`/browse https://example.com`\n\n"
            "Или отправьте ссылку в чат.",
            parse_mode="Markdown"
        )
    
    elif query.data == "status":
        if not os.path.exists(CLOAK_BINARY):
            await query.edit_message_text("❌ CloakBrowser не установлен!")
            return
            
        try:
            result = subprocess.run(
                [CLOAK_BINARY, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout.strip() or "неизвестно"
            status_text = f"✅ CloakBrowser работает\nВерсия: {version}"
        except Exception as e:
            status_text = f"⚠️ Ошибка: {str(e)[:100]}"
        
        await query.edit_message_text(
            f"📊 *Статус*\n\n{status_text}",
            parse_mode="Markdown"
        )
    
    elif query.data == "clear_cache":
        cache_dir = "/tmp/cloak_cache"
        if os.path.exists(cache_dir):
            subprocess.run(["rm", "-rf", cache_dir])
            await query.edit_message_text("✅ Кэш CloakBrowser очищен!")
        else:
            await query.edit_message_text("ℹ️ Кэш не найден")
    
    elif query.data == "reinstall":
        await query.edit_message_text("⏳ Переустановка CloakBrowser...")
        
        # Удаляем старую версию
        if os.path.exists(CLOAK_DIR):
            subprocess.run(["rm", "-rf", CLOAK_DIR])
        
        # Устанавливаем заново
        success = install_cloak()
        
        if success:
            await query.edit_message_text("✅ CloakBrowser успешно переустановлен!")
        else:
            await query.edit_message_text("❌ Ошибка переустановки!")
    
    elif query.data == "info":
        size = "0 MB"
        if os.path.exists(CLOAK_BINARY):
            size_bytes = os.path.getsize(CLOAK_BINARY)
            size = f"{size_bytes / (1024*1024):.2f} MB"
        
        await query.edit_message_text(
            f"ℹ️ *Информация*\n\n"
            f"🤖 CloakBrowser Bot v1.1\n"
            f"📦 CloakBrowser: {'✅ Установлен' if os.path.exists(CLOAK_BINARY) else '❌ Не установлен'}\n"
            f"📁 Путь: {CLOAK_BINARY}\n"
            f"📏 Размер: {size}\n"
            f"🌐 Платформа: Railway",
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
            "/install - Переустановить CloakBrowser\n"
            "/help - Эта справка\n\n"
            "📌 *Как использовать:*\n"
            "1. Нажмите 'Открыть сайт'\n"
            "2. Введите команду /browse с URL\n"
            "3. Бот откроет страницу через CloakBrowser\n\n"
            "Пример: `/browse https://github.com`",
            parse_mode="Markdown"
        )

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ *Укажите URL*\n\n"
            "Пример: `/browse https://example.com`",
            parse_mode="Markdown"
        )
        return
    
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        process = subprocess.Popen(
            [CLOAK_BINARY, "open", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        time.sleep(3)
        stdout, stderr = process.communicate(timeout=10)
        
        if stderr:
            await msg.edit_text(f"⚠️ *Ошибка*\n\n```\n{stderr[:300]}\n```", parse_mode="Markdown")
        else:
            keyboard = [
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")],
                [InlineKeyboardButton("🌐 Открыть другой", callback_data="browse")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await msg.edit_text(
                f"✅ *Успешно открыто!*\n\n"
                f"🌐 URL: {url}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
    except subprocess.TimeoutExpired:
        process.kill()
        await msg.edit_text("⏰ Превышено время ожидания")
    except Exception as e:
        await msg.edit_text(f"❌ *Ошибка*\n\n```\n{str(e)[:200]}\n```", parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(CLOAK_BINARY):
        await update.message.reply_text("❌ CloakBrowser не установлен!")
        return
        
    try:
        result = subprocess.run(
            [CLOAK_BINARY, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version = result.stdout.strip() or "неизвестно"
        
        await update.message.reply_text(
            f"📊 *Статус CloakBrowser*\n\n"
            f"✅ Состояние: Активен\n"
            f"📦 Версия: {version}\n"
            f"📁 Путь: {CLOAK_BINARY}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)[:100]}")

async def install_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для переустановки"""
    await update.message.reply_text("⏳ Установка CloakBrowser...")
    
    if os.path.exists(CLOAK_DIR):
        subprocess.run(["rm", "-rf", CLOAK_DIR])
    
    success = install_cloak()
    
    if success:
        await update.message.reply_text("✅ CloakBrowser успешно установлен!")
    else:
        await update.message.reply_text("❌ Ошибка установки!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "📌 *Основные команды:*\n"
        "/start - Запустить бота\n"
        "/menu - Открыть главное меню\n"
        "/browse <URL> - Открыть сайт\n"
        "/status - Статус CloakBrowser\n"
        "/install - Переустановить CloakBrowser\n"
        "/help - Показать справку\n\n"
        "📌 *Пример:*\n"
        "`/browse https://example.com`",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.post_init = set_bot_commands
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("install", install_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()