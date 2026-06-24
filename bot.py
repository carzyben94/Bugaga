# bot.py
import os
import sys
import subprocess
import time
import logging
import json
import urllib.request
import shutil
import tempfile
import traceback
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Создаем файл лога с датой
log_filename = f"{LOG_DIR}/bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Настройка форматирования
log_format = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

# Создаем логгер
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Хендлер для файла
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(log_format, date_format))

# Хендлер для консоли
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', date_format))

# Добавляем хендлеры
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Отключаем лишние логи от библиотек
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

logger.info("=" * 80)
logger.info(f"ЗАПУСК БОТА: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"Лог-файл: {log_filename}")
logger.info("=" * 80)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN не установлен!")
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

logger.info(f"✅ TELEGRAM_BOT_TOKEN загружен (длина: {len(TELEGRAM_BOT_TOKEN)})")

CLOAK_DIR = "/app/cloak"
CLOAK_BINARY = f"{CLOAK_DIR}/cloak"
CLOAK_VERSION = "0.3.32"

logger.info(f"📁 Директория Cloak: {CLOAK_DIR}")
logger.info(f"📁 Бинарник Cloak: {CLOAK_BINARY}")

# ==================== ФУНКЦИИ УСТАНОВКИ ====================

def log_error_context(func_name, error, extra_info=""):
    """Логирование ошибки с контекстом"""
    logger.error(f"❌ ОШИБКА в {func_name}: {str(error)}")
    logger.error(f"📋 Доп.информация: {extra_info}")
    logger.error(f"📚 Трассировка:\n{traceback.format_exc()}")

def download_file(url, output, timeout=30):
    """Скачивание файла с повторными попытками"""
    logger.info(f"📥 Начинаю скачивание: {url}")
    logger.info(f"📁 Сохраняю в: {output}")
    
    for attempt in range(3):
        try:
            logger.info(f"🔄 Попытка {attempt+1}/3")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            req = urllib.request.Request(url, headers=headers)
            
            logger.debug(f"📤 Отправляю запрос с заголовками: {headers}")
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                logger.info(f"📊 Статус ответа: {response.getcode()}")
                logger.info(f"📊 Content-Type: {response.headers.get('Content-Type')}")
                logger.info(f"📊 Content-Length: {response.headers.get('Content-Length')}")
                
                content = response.read()
                logger.info(f"📊 Размер данных: {len(content)} байт")
                
                with open(output, 'wb') as f:
                    f.write(content)
                    logger.debug(f"💾 Данные записаны в файл")
            
            size = os.path.getsize(output)
            logger.info(f"✅ Файл сохранен, размер: {size} байт")
            
            if size > 100000:
                logger.info("✅ Файл прошел проверку размера")
                return True
            else:
                logger.warning(f"⚠️ Файл слишком маленький: {size} байт (ожидалось >100KB)")
                os.remove(output)
                logger.info(f"🗑️ Удален маленький файл: {output}")
                
        except urllib.error.HTTPError as e:
            logger.error(f"❌ HTTP ошибка: {e.code} - {e.reason}")
            logger.error(f"📋 URL: {url}")
            if hasattr(e, 'headers'):
                logger.debug(f"📋 Заголовки ответа: {e.headers}")
        except urllib.error.URLError as e:
            logger.error(f"❌ URL ошибка: {e.reason}")
        except Exception as e:
            log_error_context("download_file", e, f"URL: {url}")
        
        logger.info(f"⏳ Ожидание 3 секунды перед следующей попыткой...")
        time.sleep(3)
    
    logger.error("❌ Все попытки скачивания не удались")
    return False

def install_cloak_browser():
    """Полная установка CloakBrowser с нуля"""
    logger.info("=" * 60)
    logger.info("🚀 НАЧАЛО УСТАНОВКИ CloakBrowser")
    logger.info("=" * 60)
    
    try:
        # Создаем директорию
        logger.info(f"📁 Создаю директорию: {CLOAK_DIR}")
        os.makedirs(CLOAK_DIR, exist_ok=True)
        
        # Скачиваем CloakBrowser
        download_urls = [
            f"https://github.com/coder3101/cloak/releases/download/v{CLOAK_VERSION}/cloak-linux-amd64.tar.gz",
            "https://github.com/coder3101/cloak/releases/download/0.3.0/cloak-linux-amd64.tar.gz",
            "https://github.com/coder3101/cloak/releases/download/0.2.0/cloak-linux-amd64.tar.gz",
        ]
        
        downloaded = False
        for url in download_urls:
            logger.info(f"🌐 Пробую скачать: {url}")
            if download_file(url, f"{CLOAK_DIR}/cloak.tar.gz"):
                downloaded = True
                logger.info(f"✅ Успешно скачано с: {url}")
                break
            else:
                logger.warning(f"❌ Не удалось скачать с: {url}")
        
        if not downloaded:
            logger.error("❌ НЕ УДАЛОСЬ СКАЧАТЬ CLOAKBROWSER НИ С ОДНОГО URL")
            logger.info("🔄 Создаю заглушку...")
            return create_fallback_browser()
        
        # Распаковываем
        try:
            logger.info("📦 Распаковываю архив...")
            tar_path = f"{CLOAK_DIR}/cloak.tar.gz"
            logger.debug(f"📁 Путь к архиву: {tar_path}")
            logger.debug(f"📁 Размер архива: {os.path.getsize(tar_path)} байт")
            
            result = subprocess.run(
                ["tar", "-xzf", tar_path, "-C", CLOAK_DIR],
                capture_output=True,
                text=True,
                check=True
            )
            logger.debug(f"📤 stdout: {result.stdout}")
            if result.stderr:
                logger.debug(f"⚠️ stderr: {result.stderr}")
            
            logger.info("✅ Архив распакован")
            
            # Удаляем архив
            os.remove(tar_path)
            logger.info("🗑️ Архив удален")
            
        except subprocess.CalledProcessError as e:
            log_error_context("install_cloak_browser - распаковка", e, f"Команда: tar -xzf")
            return create_fallback_browser()
        except Exception as e:
            log_error_context("install_cloak_browser - распаковка", e)
            return create_fallback_browser()
        
        # Ищем бинарник
        logger.info("🔍 Ищу бинарник Cloak...")
        binary_found = False
        
        for root, dirs, files in os.walk(CLOAK_DIR):
            logger.debug(f"📂 Проверяю: {root}")
            logger.debug(f"📄 Файлы: {files}")
            for file in files:
                if file == "cloak" or file == "cloak-linux-amd64":
                    full_path = os.path.join(root, file)
                    logger.info(f"✅ Найден бинарник: {full_path}")
                    
                    if full_path != CLOAK_BINARY:
                        logger.info(f"📦 Перемещаю в: {CLOAK_BINARY}")
                        shutil.move(full_path, CLOAK_BINARY)
                    else:
                        logger.info("✅ Бинарник уже в нужном месте")
                    
                    binary_found = True
                    break
            if binary_found:
                break
        
        if not binary_found:
            logger.error("❌ Бинарник не найден после распаковки")
            logger.error(f"📂 Содержимое {CLOAK_DIR}:")
            for root, dirs, files in os.walk(CLOAK_DIR):
                logger.error(f"  📁 {root}")
                for file in files:
                    logger.error(f"    📄 {file}")
            return create_fallback_browser()
        
        # Делаем исполняемым
        logger.info(f"🔧 Делаю исполняемым: {CLOAK_BINARY}")
        os.chmod(CLOAK_BINARY, 0o755)
        logger.info("✅ Права установлены")
        
        # Проверяем работу
        logger.info("🧪 Проверяю работу CloakBrowser...")
        try:
            result = subprocess.run(
                [CLOAK_BINARY, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.info(f"📤 Код возврата: {result.returncode}")
            logger.info(f"📤 stdout: {result.stdout}")
            if result.stderr:
                logger.info(f"📤 stderr: {result.stderr}")
            
            if result.returncode == 0:
                logger.info(f"✅ CloakBrowser установлен и работает: {result.stdout.strip()}")
                logger.info("=" * 60)
                return True
            else:
                logger.error(f"❌ CloakBrowser вернул ошибку: {result.returncode}")
                return create_fallback_browser()
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Таймаут при проверке CloakBrowser")
            return create_fallback_browser()
        except Exception as e:
            log_error_context("install_cloak_browser - проверка", e)
            return create_fallback_browser()
            
    except Exception as e:
        log_error_context("install_cloak_browser", e)
        return create_fallback_browser()

def create_fallback_browser():
    """Создает заглушку CloakBrowser если установка не удалась"""
    logger.warning("=" * 60)
    logger.warning("⚠️ СОЗДАЮ ЗАГЛУШКУ CloakBrowser")
    logger.warning("=" * 60)
    
    try:
        os.makedirs(CLOAK_DIR, exist_ok=True)
        logger.info(f"📁 Создаю заглушку в: {CLOAK_BINARY}")
        
        with open(CLOAK_BINARY, 'w') as f:
            f.write('''#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse
import traceback

def open_url(url):
    """Открывает URL через простой HTTP запрос"""
    print(f"🔍 Открываю: {url}")
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        print(f"🌐 Запрос к: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            print(f"✅ URL открыт: {url}")
            print(f"📊 Статус: {response.getcode()}")
            print(f"📊 Размер: {len(content)} байт")
            return True
            
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP ошибка: {e.code} - {e.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"❌ URL ошибка: {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "open":
        print("Использование: cloak open <URL>")
        sys.exit(1)
    
    url = sys.argv[2]
    success = open_url(url)
    sys.exit(0 if success else 1)
''')
        
        os.chmod(CLOAK_BINARY, 0o755)
        logger.info("✅ Заглушка создана успешно")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        log_error_context("create_fallback_browser", e)
        return False

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

logger.info("=" * 60)
logger.info("🔧 ПРОВЕРКА УСТАНОВКИ CLOAKBROWSER")
logger.info("=" * 60)

if not os.path.exists(CLOAK_BINARY):
    logger.warning("⚠️ CloakBrowser не найден")
    logger.info("🔄 Запускаю установку...")
    if install_cloak_browser():
        logger.info("✅ CloakBrowser установлен успешно!")
    else:
        logger.error("❌ Не удалось установить CloakBrowser")
        logger.info("⚠️ Бот будет работать в режиме заглушки")
else:
    logger.info("✅ CloakBrowser уже установлен")
    # Проверяем работоспособность
    try:
        result = subprocess.run([CLOAK_BINARY, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info(f"✅ Версия: {result.stdout.strip()}")
        else:
            logger.warning(f"⚠️ CloakBrowser есть, но не работает. Код: {result.returncode}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки: {e}")

logger.info("=" * 60)
logger.info("🚀 ЗАПУСК БОТА")
logger.info("=" * 60)

# ==================== ФУНКЦИИ БОТА ====================

async def set_bot_commands(application: Application):
    try:
        logger.info("📝 Устанавливаю команды бота...")
        commands = [
            BotCommand("start", "🚀 Запустить бота"),
            BotCommand("menu", "📋 Открыть главное меню"),
            BotCommand("browse", "🌐 Открыть URL"),
            BotCommand("status", "📊 Статус CloakBrowser"),
            BotCommand("help", "❓ Помощь"),
            BotCommand("reinstall", "🔄 Переустановить CloakBrowser"),
            BotCommand("logs", "📄 Показать логи"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("✅ Команды установлены")
    except Exception as e:
        log_error_context("set_bot_commands", e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"📩 Команда /start от {update.effective_user.username} (ID: {update.effective_user.id})")
        
        keyboard = [
            [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("🔄 Переустановить", callback_data="reinstall")],
            [InlineKeyboardButton("📄 Логи", callback_data="logs")],
            [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        is_fallback = await is_fallback_mode()
        status = "🟢 Работает" if os.path.exists(CLOAK_BINARY) else "🔴 Не установлен"
        
        await update.message.reply_text(
            f"🤖 *CloakBrowser Bot*\n\n"
            f"Бот для безопасного просмотра веб-страниц.\n\n"
            f"📦 Статус: {status}\n"
            f"{'⚠️ Работает в режиме заглушки' if is_fallback else '✅ Полная версия'}\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        logger.info("✅ Ответ на /start отправлен")
        
    except Exception as e:
        log_error_context("start", e)
        await update.message.reply_text("❌ Произошла ошибка. Проверьте логи.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [
            [InlineKeyboardButton("🌐 Открыть сайт", callback_data="browse")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("🔄 Очистить кэш", callback_data="clear_cache")],
            [InlineKeyboardButton("🔄 Переустановить", callback_data="reinstall")],
            [InlineKeyboardButton("📄 Логи", callback_data="logs")],
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
        logger.info("✅ Меню отправлено")
    except Exception as e:
        log_error_context("menu", e)

async def is_fallback_mode():
    try:
        if not os.path.exists(CLOAK_BINARY):
            return True
        
        with open(CLOAK_BINARY, 'r') as f:
            content = f.read(100)
            return "заглушка" in content.lower()
    except Exception as e:
        log_error_context("is_fallback_mode", e)
        return True

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        logger.info(f"📩 Callback: {query.data} от {update.effective_user.username}")
        
        if query.data == "browse":
            await query.edit_message_text(
                "🌐 *Введите URL*\n\n"
                "Используйте команду:\n"
                "`/browse https://example.com`",
                parse_mode="Markdown"
            )
        
        elif query.data == "status":
            status_text = await get_status_text()
            await query.edit_message_text(
                f"📊 *Статус*\n\n{status_text}",
                parse_mode="Markdown"
            )
        
        elif query.data == "clear_cache":
            logger.info("🧹 Очистка кэша...")
            cache_dirs = [
                "/tmp/cloak_cache",
                os.path.expanduser("~/.cloak/cache"),
                os.path.expanduser("~/.cache/cloak")
            ]
            cleared = 0
            for dir_path in cache_dirs:
                if os.path.exists(dir_path):
                    logger.info(f"🗑️ Удаляю: {dir_path}")
                    subprocess.run(["rm", "-rf", dir_path])
                    cleared += 1
            
            if cleared > 0:
                await query.edit_message_text(f"✅ Очищено {cleared} кэш-директорий")
            else:
                await query.edit_message_text("ℹ️ Кэш не найден")
        
        elif query.data == "reinstall":
            await query.edit_message_text("⏳ Переустановка CloakBrowser...")
            logger.info("🔄 Переустановка CloakBrowser")
            
            if os.path.exists(CLOAK_DIR):
                logger.info(f"🗑️ Удаляю: {CLOAK_DIR}")
                shutil.rmtree(CLOAK_DIR)
            
            success = install_cloak_browser()
            
            if success:
                await query.edit_message_text("✅ CloakBrowser успешно переустановлен!")
            else:
                await query.edit_message_text(
                    "⚠️ Установка не удалась, но бот работает в режиме заглушки"
                )
        
        elif query.data == "logs":
            await send_logs(update, context)
        
        elif query.data == "info":
            is_fallback = await is_fallback_mode()
            size = "0 MB"
            if os.path.exists(CLOAK_BINARY):
                size_bytes = os.path.getsize(CLOAK_BINARY)
                size = f"{size_bytes / (1024*1024):.2f} MB"
            
            await query.edit_message_text(
                f"ℹ️ *Информация*\n\n"
                f"🤖 CloakBrowser Bot v3.1\n"
                f"📦 Статус: {'✅ Установлен' if os.path.exists(CLOAK_BINARY) else '❌ Не установлен'}\n"
                f"📌 Режим: {'⚠️ Заглушка' if is_fallback else '✅ Полный'}\n"
                f"📁 Путь: {CLOAK_BINARY}\n"
                f"📏 Размер: {size}\n"
                f"📄 Лог: {log_filename}\n"
                f"🌐 Платформа: Railway\n"
                f"🐍 Python: {sys.version.split()[0]}",
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
                "/logs - Показать логи\n"
                "/help - Эта справка\n\n"
                "📌 *Пример:*\n"
                "`/browse https://github.com`",
                parse_mode="Markdown"
            )
        
        elif query.data == "back_to_menu":
            await menu(update, context)
            
    except Exception as e:
        log_error_context("handle_callback", e, f"Callback: {query.data if hasattr(query, 'data') else 'unknown'}")

async def get_status_text():
    try:
        if not os.path.exists(CLOAK_BINARY):
            return "❌ CloakBrowser не установлен"
        
        is_fallback = await is_fallback_mode()
        
        try:
            result = subprocess.run(
                [CLOAK_BINARY, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version = result.stdout.strip() or "неизвестно"
                return f"""✅ CloakBrowser работает
Версия: {version}
Режим: {'⚠️ Заглушка' if is_fallback else '✅ Полный'}
Статус: Активен
Путь: {CLOAK_BINARY}"""
            else:
                return f"⚠️ Ошибка запуска\nКод: {result.returncode}"
                
        except subprocess.TimeoutExpired:
            return "⏰ Таймаут при проверке"
        except Exception as e:
            return f"⚠️ Ошибка: {str(e)[:100]}"
            
    except Exception as e:
        log_error_context("get_status_text", e)
        return f"⚠️ Ошибка: {str(e)[:100]}"

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        logger.info(f"🌐 Команда /browse от {user.username} (ID: {user.id})")
        
        if not context.args:
            await update.message.reply_text(
                "❌ *Укажите URL*\n\n"
                "Пример: `/browse https://example.com`",
                parse_mode="Markdown"
            )
            return
        
        if not os.path.exists(CLOAK_BINARY):
            await update.message.reply_text(
                "❌ CloakBrowser не установлен!\n"
                "Используйте /reinstall для установки"
            )
            return
        
        url = context.args[0]
        logger.info(f"🌐 URL для открытия: {url}")
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            logger.info(f"🔄 Добавлен протокол: {url}")
        
        msg = await update.message.reply_text(f"⏳ Открываю {url}...")
        
        try:
            logger.info(f"🚀 Запускаю: {CLOAK_BINARY} open {url}")
            process = subprocess.Popen(
                [CLOAK_BINARY, "open", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            time.sleep(2)
            stdout, stderr = process.communicate(timeout=15)
            
            logger.info(f"📤 Код возврата: {process.returncode}")
            if stdout:
                logger.debug(f"📤 stdout: {stdout[:200]}")
            if stderr:
                logger.debug(f"📤 stderr: {stderr[:200]}")
            
            if process.returncode == 0:
                keyboard = [
                    [InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")],
                    [InlineKeyboardButton("🌐 Открыть другой", callback_data="browse")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await msg.edit_text(
                    f"✅ *Страница открыта!*\n\n"
                    f"🌐 URL: {url}\n"
                    f"📊 Статус: Успешно",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                logger.info(f"✅ Страница открыта: {url}")
            else:
                error_msg = stderr[:300] if stderr else "Неизвестная ошибка"
                logger.warning(f"⚠️ Ошибка открытия: {error_msg}")
                await msg.edit_text(
                    f"⚠️ *Ошибка*\n\n"
                    f"```\n{error_msg}\n```",
                    parse_mode="Markdown"
                )
                
        except subprocess.TimeoutExpired:
            logger.error("⏰ Таймаут при открытии URL")
            process.kill()
            await msg.edit_text("⏰ Превышено время ожидания")
        except Exception as e:
            log_error_context("browse - выполнение", e, f"URL: {url}")
            await msg.edit_text(f"❌ *Ошибка*\n\n```\n{str(e)[:200]}\n```", parse_mode="Markdown")
            
    except Exception as e:
        log_error_context("browse", e)
        await update.message.reply_text("❌ Произошла ошибка. Проверьте логи.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"📊 Команда /status от {update.effective_user.username}")
        status_text = await get_status_text()
        await update.message.reply_text(
            f"📊 *Статус CloakBrowser*\n\n{status_text}",
            parse_mode="Markdown"
        )
    except Exception as e:
        log_error_context("status", e)

async def reinstall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"🔄 Команда /reinstall от {update.effective_user.username}")
        await update.message.reply_text("⏳ Переустановка CloakBrowser...")
        
        if os.path.exists(CLOAK_DIR):
            logger.info(f"🗑️ Удаляю: {CLOAK_DIR}")
            shutil.rmtree(CLOAK_DIR)
        
        success = install_cloak_browser()
        
        if success:
            await update.message.reply_text("✅ CloakBrowser успешно переустановлен!")
        else:
            await update.message.reply_text(
                "⚠️ Установка не удалась, но бот работает в режиме заглушки"
            )
    except Exception as e:
        log_error_context("reinstall", e)
        await update.message.reply_text("❌ Ошибка переустановки!")

async def send_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет логи бота"""
    try:
        logger.info(f"📄 Команда /logs от {update.effective_user.username}")
        
        # Если есть callback
        if update.callback_query:
            await update.callback_query.answer()
            message = update.callback_query.message
        else:
            message = update.message
        
        await message.reply_text("⏳ Собираю логи...")
        
        # Получаем последние 50 строк лога
        try:
            with open(log_filename, 'r') as f:
                lines = f.readlines()
                last_lines = lines[-50:] if len(lines) > 50 else lines
                
            log_text = "".join(last_lines)
            
            # Если лог слишком большой, обрезаем
            if len(log_text) > 4000:
                log_text = "...\n" + log_text[-4000:]
            
            # Отправляем лог
            await message.reply_text(
                f"📄 *Логи (последние {len(last_lines)} строк)*\n\n"
                f"```\n{log_text}\n```\n"
                f"📁 Полный лог: {log_filename}",
                parse_mode="Markdown"
            )
            logger.info("✅ Логи отправлены")
            
        except FileNotFoundError:
            await message.reply_text("❌ Лог-файл не найден")
        except Exception as e:
            log_error_context("send_logs - чтение файла", e)
            await message.reply_text(f"❌ Ошибка чтения лога: {str(e)[:100]}")
            
    except Exception as e:
        log_error_context("send_logs", e)
        await update.message.reply_text("❌ Ошибка отправки логов")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"❓ Команда /help от {update.effective_user.username}")
        await update.message.reply_text(
            "❓ *Помощь*\n\n"
            "📌 *Команды:*\n"
            "/start - Запустить бота\n"
            "/menu - Открыть меню\n"
            "/browse <URL> - Открыть сайт\n"
            "/status - Статус CloakBrowser\n"
            "/reinstall - Переустановить CloakBrowser\n"
            "/logs - Показать логи\n"
            "/help - Показать справку\n\n"
            "📌 *Пример:*\n"
            "`/browse https://example.com`",
            parse_mode="Markdown"
        )
    except Exception as e:
        log_error_context("help_command", e)

# ==================== ЗАПУСК БОТА ====================

def main():
    try:
        logger.info("=" * 80)
        logger.info("🚀 ИНИЦИАЛИЗАЦИЯ БОТА")
        logger.info("=" * 80)
        
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info("✅ Приложение создано")
        
        app.post_init = set_bot_commands
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("menu", menu))
        app.add_handler(CommandHandler("browse", browse))
        app.add_handler(CommandHandler("status", status))
        app.add_handler(CommandHandler("reinstall", reinstall))
        app.add_handler(CommandHandler("logs", send_logs))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CallbackQueryHandler(handle_callback))
        
        logger.info("✅ Все обработчики зарегистрированы")
        logger.info("=" * 80)
        logger.info("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
        logger.info("=" * 80)
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        log_error_context("main", e)
        logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: Бот не может запуститься!")
        sys.exit(1)

if __name__ == "__main__":
    main()