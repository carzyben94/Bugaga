import os
import sys
import asyncio
import logging
import subprocess
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# АВТОМАТИЧЕСКИЙ ПОИСК БРАУЗЕРА И АДАПТЕРА
# ============================================

def find_chrome():
    """Ищет Chrome, установленный banana-browser/agent-browser"""
    logger.info("🔍 Поиск браузера...")
    
    # 1. Проверяем переменную окружения
    env_path = os.environ.get('CHROMIUM_PATH')
    if env_path and os.path.exists(env_path):
        logger.info(f"✅ Найден из CHROMIUM_PATH: {env_path}")
        return env_path
    
    # 2. Ищем через agent-browser
    agent_dirs = [
        "/root/.agent-browser/browsers",
        "/root/.agent-browser",
        "/home/.agent-browser/browsers"
    ]
    
    for agent_dir in agent_dirs:
        if os.path.exists(agent_dir):
            logger.info(f"📁 Проверяем: {agent_dir}")
            try:
                for root, dirs, files in os.walk(agent_dir):
                    if "chrome" in files:
                        chrome_path = os.path.join(root, "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден agent-browser Chrome: {chrome_path}")
                            return chrome_path
                    if "chrome-linux64" in dirs:
                        chrome_path = os.path.join(root, "chrome-linux64", "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден agent-browser Chrome: {chrome_path}")
                            return chrome_path
            except Exception as e:
                logger.warning(f"⚠️ Ошибка поиска в {agent_dir}: {e}")
    
    # 3. Ищем через find
    try:
        logger.info("🔍 Ищем через find...")
        for search_path in ["/root/.agent-browser", "/root/.cache/banana-browser"]:
            if os.path.exists(search_path):
                result = subprocess.run(
                    ['find', search_path, '-name', 'chrome', '-type', 'f'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                paths = result.stdout.strip().split('\n')
                for path in paths:
                    if path and os.path.exists(path) and os.access(path, os.X_OK):
                        logger.info(f"✅ Найден через find: {path}")
                        return path
    except Exception as e:
        logger.warning(f"⚠️ Ошибка find: {e}")
    
    logger.error("❌ Браузер НЕ НАЙДЕН!")
    return None

def find_patchright_adapter():
    """Ищет patchright-adapter в файловой системе banana-browser"""
    logger.info("🔍 Поиск patchright-adapter...")
    
    # Возможные пути
    possible_paths = [
        # Адаптер внутри banana-browser
        "/usr/local/lib/node_modules/banana-browser/node_modules/@agent-browser/patchright-adapter/dist/index.js",
        "/usr/local/lib/node_modules/banana-browser/node_modules/@agent-browser/patchright-adapter/index.js",
        "/usr/local/lib/node_modules/banana-browser/dist/adapters/patchright-adapter/index.js",
        # Адаптер внутри agent-browser
        "/usr/local/lib/node_modules/agent-browser/node_modules/@agent-browser/patchright-adapter/dist/index.js",
        "/usr/local/lib/node_modules/agent-browser/dist/adapters/patchright-adapter/index.js",
        # Временные пути
        "/tmp/banana-browser/adapters/patchright-adapter/index.js",
        "/root/.agent-browser/adapters/patchright-adapter/index.js",
        "/root/.agent-browser/adapters/patchright-adapter/dist/index.js"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"✅ Найден patchright-adapter: {path}")
            return path
    
    # Ищем через find
    try:
        logger.info("🔍 Ищем через find...")
        result = subprocess.run(
            ['find', '/usr/local/lib/node_modules', '-name', 'patchright-adapter', '-type', 'd'],
            capture_output=True,
            text=True,
            timeout=10
        )
        paths = result.stdout.strip().split('\n')
        for path in paths:
            if path:
                # Проверяем разные варианты
                for subpath in ['dist/index.js', 'index.js']:
                    full_path = os.path.join(path, subpath)
                    if os.path.exists(full_path):
                        logger.info(f"✅ Найден patchright-adapter через find: {full_path}")
                        return full_path
    except Exception as e:
        logger.warning(f"⚠️ Ошибка find: {e}")
    
    logger.warning("⚠️ patchright-adapter не найден!")
    return None

# Находим браузер при старте
CHROME_PATH = find_chrome()
if CHROME_PATH:
    os.environ['CHROMIUM_PATH'] = CHROME_PATH
    os.environ['AGENT_BROWSER_ENGINE'] = 'patchright'
    logger.info(f"✅ Установлен CHROMIUM_PATH={CHROME_PATH}")
else:
    logger.warning("⚠️ Браузер не найден! Проверь установку.")

# Находим адаптер
PATCHRIGHT_PATH = find_patchright_adapter()
if PATCHRIGHT_PATH:
    os.environ['PATCHRIGHT_ADAPTER_PATH'] = PATCHRIGHT_PATH
    logger.info(f"✅ Установлен PATCHRIGHT_ADAPTER_PATH={PATCHRIGHT_PATH}")

# ============================================
# ТЕЛЕГРАМ БОТ
# ============================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# --- КНОПКИ ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить браузер", callback_data="start_browser")],
        [InlineKeyboardButton("🔍 Проверить браузер", callback_data="check_browser")],
        [InlineKeyboardButton("📊 Статус системы", callback_data="check_install")],
        [InlineKeyboardButton("🔄 Полная диагностика", callback_data="diagnostic")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я проверяю браузер на незаметность.\n\n"
        "Выбери действие на клавиатуре ниже:",
        reply_markup=get_main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_browser":
        await start_browser(query, context)
    elif query.data == "check_browser":
        await check_browser_button(query, context)
    elif query.data == "check_install":
        await check_install_button(query, context)
    elif query.data == "diagnostic":
        await diagnostic_button(query, context)

async def start_browser(query, context):
    await query.edit_message_text("🔄 Запускаю браузер...")
    
    try:
        if not CHROME_PATH or not os.path.exists(CHROME_PATH):
            await query.edit_message_text(
                "❌ Браузер не найден!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Запускаем banana-browser
        env = os.environ.copy()
        if PATCHRIGHT_PATH:
            env['PATCHRIGHT_ADAPTER_PATH'] = PATCHRIGHT_PATH
        
        process = subprocess.Popen(
            ['banana-browser', 'start', '--remote-debugging-port=9222'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env
        )
        
        context.bot_data['browser_pid'] = process.pid
        
        await query.edit_message_text(
            f"✅ **Браузер запущен!**\n\n"
            f"📁 Путь: `{CHROME_PATH}`\n"
            f"🆔 PID: `{process.pid}`\n"
            f"🔌 Порт: `9222`\n\n"
            f"Используй /check_browser для проверки.",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка запуска браузера: {e}")
        await query.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}",
            reply_markup=get_main_keyboard()
        )

async def check_browser_button(query, context):
    await query.edit_message_text("🔄 Проверяю браузер...")
    
    try:
        if not CHROME_PATH or not os.path.exists(CHROME_PATH):
            await query.edit_message_text(
                "❌ Браузер не найден!",
                reply_markup=get_main_keyboard()
            )
            return
        
        env = os.environ.copy()
        if PATCHRIGHT_PATH:
            env['PATCHRIGHT_ADAPTER_PATH'] = PATCHRIGHT_PATH
        
        await query.edit_message_text("🌐 Открываю тестовую страницу...")
        
        # Используем banana-browser для скриншота
        cmd = [
            'banana-browser', 'screenshot',
            'https://bot.sannysoft.com',
            '-o', '/tmp/screenshot.png',
            '--wait', '5000'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        
        if result.returncode == 0 and os.path.exists('/tmp/screenshot.png'):
            with open('/tmp/screenshot.png', 'rb') as photo:
                await query.message.reply_photo(
                    photo=photo,
                    caption="📸 Скриншот проверки браузера"
                )
            
            # Проверяем webdriver
            check_cmd = [
                'banana-browser', 'eval',
                'navigator.webdriver',
                '--url', 'https://bot.sannysoft.com'
            ]
            
            result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            webdriver = result.stdout.strip().lower()
            
            if webdriver == 'false':
                verdict = "✅ **Браузер НЕОТЛИЧИМ от обычного!**"
            else:
                verdict = "⚠️ **Браузер обнаруживается как бот**"
            
            await query.message.reply_text(
                f"🔍 **Результат проверки**\n\n"
                f"{verdict}\n\n"
                f"• `navigator.webdriver` = `{webdriver}`\n\n"
                f"💡 Если `false` — браузер неотличим.",
                reply_markup=get_main_keyboard()
            )
            
        else:
            error_msg = result.stderr[:200] if result.stderr else "Неизвестная ошибка"
            await query.edit_message_text(
                f"❌ Не удалось проверить браузер.\n"
                f"Ошибка: {error_msg}",
                reply_markup=get_main_keyboard()
            )
            
    except subprocess.TimeoutExpired:
        await query.edit_message_text(
            "⏰ Таймаут проверки (30 сек)",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        await query.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}",
            reply_markup=get_main_keyboard()
        )

async def check_install_button(query, context):
    await query.edit_message_text("🔍 Проверяю установку...")
    
    report = "🔍 **Проверка установленных компонентов**\n\n"
    
    # banana-browser
    report += "**🍌 banana-browser:**\n"
    try:
        result = subprocess.run(
            ['banana-browser', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            report += f"✅ Установлен: {version}\n"
        else:
            report += "❌ banana-browser не отвечает\n"
    except FileNotFoundError:
        report += "❌ banana-browser НЕ установлен\n"
    except Exception as e:
        report += f"⚠️ Ошибка: {str(e)[:50]}\n"
    
    # patchright-adapter
    report += "\n**🔌 patchright-adapter:**\n"
    if PATCHRIGHT_PATH:
        report += f"✅ Найден: {PATCHRIGHT_PATH}\n"
    else:
        report += "❌ patchright-adapter НЕ НАЙДЕН\n"
        report += "   (Это нормально, banana-browser использует встроенный адаптер)\n"
    
    # Браузер
    report += "\n**🌐 Браузер:**\n"
    if CHROME_PATH and os.path.exists(CHROME_PATH):
        report += f"✅ Найден: {CHROME_PATH}\n"
        try:
            result = subprocess.run(
                [CHROME_PATH, '--version'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                report += f"   Версия: {result.stdout.strip()[:50]}\n"
        except:
            pass
    else:
        report += "❌ Браузер НЕ НАЙДЕН\n"
    
    # Переменные
    report += "\n**🔧 Переменные окружения:**\n"
    env_vars = ['AGENT_BROWSER_ENGINE', 'CHROMIUM_PATH', 'PATCHRIGHT_ADAPTER_PATH']
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            report += f"✅ {var} = {value[:50]}...\n"
        else:
            report += f"⚠️ {var} - не установлена\n"
    
    # xvfb
    report += "\n**🖥️ xvfb:**\n"
    try:
        result = subprocess.run(
            ['which', 'xvfb-run'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            report += "✅ xvfb установлен\n"
        else:
            report += "❌ xvfb НЕ установлен\n"
    except:
        report += "❌ xvfb НЕ установлен\n"
    
    await query.edit_message_text(
        report,
        reply_markup=get_main_keyboard()
    )

async def diagnostic_button(query, context):
    await query.edit_message_text("🔄 Запускаю диагностику...")
    
    report = "🔬 **Диагностика**\n\n"
    
    # banana-browser
    try:
        env = os.environ.copy()
        if PATCHRIGHT_PATH:
            env['PATCHRIGHT_ADAPTER_PATH'] = PATCHRIGHT_PATH
        
        result = subprocess.run(
            ['banana-browser', '--version'],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        
        if result.returncode == 0:
            report += f"✅ banana-browser: {result.stdout.strip()}\n"
        else:
            report += "❌ banana-browser не отвечает\n"
    except Exception as e:
        report += f"❌ Ошибка: {str(e)[:50]}\n"
    
    # Браузер
    report += f"\n**Браузер:**\n"
    if CHROME_PATH and os.path.exists(CHROME_PATH):
        report += f"✅ Путь: `{CHROME_PATH}`\n"
        try:
            result = subprocess.run(
                [CHROME_PATH, '--version'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                report += f"✅ Версия: {result.stdout.strip()}\n"
        except:
            pass
    else:
        report += "❌ Браузер не найден\n"
    
    # patchright-adapter
    report += f"\n**patchright-adapter:**\n"
    if PATCHRIGHT_PATH:
        report += f"✅ {PATCHRIGHT_PATH}\n"
    else:
        report += "⚠️ Не найден (используется встроенный)\n"
    
    # Проверка через banana-browser demo
    report += f"\n**Тест banana-browser:**\n"
    try:
        env = os.environ.copy()
        if PATCHRIGHT_PATH:
            env['PATCHRIGHT_ADAPTER_PATH'] = PATCHRIGHT_PATH
        
        result = subprocess.run(
            ['banana-browser', 'demo'],
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        
        if result.returncode == 0:
            report += "✅ demo запущен успешно\n"
            if "PASS" in result.stdout:
                report += "✅ Все тесты пройдены\n"
        else:
            report += f"⚠️ Ошибка: {result.stderr[:100]}\n"
    except subprocess.TimeoutExpired:
        report += "⏰ Таймаут 30 сек\n"
    except Exception as e:
        report += f"❌ Ошибка: {str(e)[:50]}\n"
    
    await query.edit_message_text(
        report,
        reply_markup=get_main_keyboard()
    )

async def check_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 Проверяю браузер...",
        reply_markup=get_main_keyboard()
    )

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_browser", check_browser_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Доступные команды:")
    logger.info("  /start - главное меню")
    logger.info("  /check_browser - проверить браузер")
    
    app.run_polling()

if __name__ == "__main__":
    main()