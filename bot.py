import os
import sys
import asyncio
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# АВТОМАТИЧЕСКИЙ ПОИСК БРАУЗЕРА
# ============================================

def find_chrome():
    """Ищет Chrome, установленный banana-browser/agent-browser"""
    logger.info("🔍 Поиск браузера...")
    
    # 1. Проверяем переменную окружения
    env_path = os.environ.get('CHROMIUM_PATH')
    if env_path and os.path.exists(env_path):
        logger.info(f"✅ Найден из CHROMIUM_PATH: {env_path}")
        return env_path
    
    # 2. Проверяем стандартные пути
    possible_paths = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"✅ Найден браузер: {path}")
            return path
    
    # 3. 🔥 Ищем через agent-browser (ОСНОВНОЙ ПУТЬ)
    agent_dirs = [
        "/root/.agent-browser/browsers",
        "/root/.agent-browser",
        "/home/.agent-browser/browsers"
    ]
    
    for agent_dir in agent_dirs:
        if os.path.exists(agent_dir):
            logger.info(f"📁 Проверяем: {agent_dir}")
            try:
                # Рекурсивно ищем chrome
                for root, dirs, files in os.walk(agent_dir):
                    if "chrome" in files:
                        chrome_path = os.path.join(root, "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден agent-browser Chrome: {chrome_path}")
                            return chrome_path
                    # Проверяем подпапки chrome-linux64
                    if "chrome-linux64" in dirs:
                        chrome_path = os.path.join(root, "chrome-linux64", "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден agent-browser Chrome: {chrome_path}")
                            return chrome_path
            except Exception as e:
                logger.warning(f"⚠️ Ошибка поиска в {agent_dir}: {e}")
    
    # 4. Ищем через banana-browser (старые пути)
    cache_dirs = [
        "/root/.cache/banana-browser/chrome",
        "/root/.cache/banana-browser/chromium",
        "/home/.cache/banana-browser/chrome",
        "/root/.cache/banana-browser"
    ]
    
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            logger.info(f"📁 Проверяем: {cache_dir}")
            try:
                for root, dirs, files in os.walk(cache_dir):
                    if "chrome" in files:
                        chrome_path = os.path.join(root, "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден banana-browser Chrome: {chrome_path}")
                            return chrome_path
                    if "chrome-linux64" in dirs:
                        chrome_path = os.path.join(root, "chrome-linux64", "chrome")
                        if os.path.exists(chrome_path) and os.access(chrome_path, os.X_OK):
                            logger.info(f"✅ Найден banana-browser Chrome: {chrome_path}")
                            return chrome_path
            except Exception as e:
                logger.warning(f"⚠️ Ошибка поиска в {cache_dir}: {e}")
    
    # 5. Ищем через системную команду find (в обоих местах)
    try:
        logger.info("🔍 Ищем через find в /root/.agent-browser...")
        result = subprocess.run(
            ['find', '/root/.agent-browser', '-name', 'chrome', '-type', 'f'],
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
        logger.warning(f"⚠️ Ошибка find в .agent-browser: {e}")
    
    try:
        logger.info("🔍 Ищем через find в /root/.cache/banana-browser...")
        result = subprocess.run(
            ['find', '/root/.cache/banana-browser', '-name', 'chrome', '-type', 'f'],
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
        logger.warning(f"⚠️ Ошибка find в .cache/banana-browser: {e}")
    
    # 6. Проверяем через which
    try:
        result = subprocess.run(
            ['which', 'chromium', 'chromium-browser', 'google-chrome'],
            capture_output=True,
            text=True,
            timeout=3
        )
        paths = result.stdout.strip().split('\n')
        for path in paths:
            if path and os.path.exists(path):
                logger.info(f"✅ Найден через which: {path}")
                return path
    except:
        pass
    
    logger.error("❌ Браузер НЕ НАЙДЕН!")
    return None

# Находим браузер при старте
CHROME_PATH = find_chrome()
if CHROME_PATH:
    os.environ['CHROMIUM_PATH'] = CHROME_PATH
    os.environ['AGENT_BROWSER_ENGINE'] = 'patchright'
    logger.info(f"✅ Установлен CHROMIUM_PATH={CHROME_PATH}")
else:
    logger.warning("⚠️ Браузер не найден! Проверь установку.")

# ============================================
# ТЕЛЕГРАМ БОТ
# ============================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    await update.message.reply_text(
        "👋 Привет! Я проверяю браузер на незаметность.\n\n"
        "📋 **Доступные команды:**\n"
        "/check_browser - проверить браузер\n"
        "/check_install - проверить установленные компоненты\n"
        "/diagnostic - полная диагностика системы\n"
        "/browser_info - информация о браузере\n"
        "/find_browser - найти браузер в системе"
    )

async def find_browser_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет реальный путь к браузеру"""
    await update.message.reply_text("🔍 Ищу браузер...")
    
    report = "🔎 **Поиск браузера**\n\n"
    
    # 1. Ищем через find в .agent-browser
    try:
        result = subprocess.run(
            ['find', '/root/.agent-browser', '-name', 'chrome', '-type', 'f'],
            capture_output=True,
            text=True,
            timeout=10
        )
        paths = result.stdout.strip().split('\n')
        if paths and paths[0]:
            report += "**Найденные пути в .agent-browser:**\n"
            for i, path in enumerate(paths[:5], 1):
                report += f"{i}. `{path}`\n"
                if os.path.exists(path):
                    report += f"   ✅ Существует\n"
                    if os.access(path, os.X_OK):
                        report += f"   ✅ Исполняемый\n"
        else:
            report += "❌ Chrome не найден в /root/.agent-browser/\n"
    except Exception as e:
        report += f"⚠️ Ошибка поиска: {e}\n"
    
    # 2. Ищем через find в .cache/banana-browser
    try:
        result = subprocess.run(
            ['find', '/root/.cache/banana-browser', '-name', 'chrome', '-type', 'f'],
            capture_output=True,
            text=True,
            timeout=10
        )
        paths = result.stdout.strip().split('\n')
        if paths and paths[0]:
            report += "\n**Найденные пути в .cache/banana-browser:**\n"
            for i, path in enumerate(paths[:5], 1):
                report += f"{i}. `{path}`\n"
                if os.path.exists(path):
                    report += f"   ✅ Существует\n"
                    if os.access(path, os.X_OK):
                        report += f"   ✅ Исполняемый\n"
        else:
            report += "\n❌ Chrome не найден в /root/.cache/banana-browser/\n"
    except Exception as e:
        report += f"⚠️ Ошибка поиска: {e}\n"
    
    # 3. Проверяем все возможные папки
    report += "\n**Проверка папок:**\n"
    for dir_path in [
        '/root/.agent-browser/browsers',
        '/root/.agent-browser',
        '/root/.cache/banana-browser/chrome',
        '/root/.cache/banana-browser'
    ]:
        if os.path.exists(dir_path):
            report += f"✅ Существует: {dir_path}\n"
            try:
                items = os.listdir(dir_path)
                report += f"   Содержимое: {', '.join(items[:5])}\n"
            except:
                pass
        else:
            report += f"❌ Не существует: {dir_path}\n"
    
    # 4. Текущий CHROMIUM_PATH
    report += f"\n**Текущий CHROMIUM_PATH:**\n"
    current = os.environ.get('CHROMIUM_PATH', 'не установлен')
    report += f"`{current}`\n"
    if current and os.path.exists(current):
        report += "✅ Путь существует\n"
    else:
        report += "❌ Путь НЕ существует\n"
    
    await update.message.reply_text(report)

async def check_install(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет установленные компоненты"""
    report = "🔍 **Проверка установленных компонентов**\n\n"
    
    # 1. Проверка Python пакетов
    report += "**📦 Python пакеты:**\n"
    packages = ['browser_harness', 'playwright', 'telegram']
    for pkg in packages:
        try:
            __import__(pkg.replace('-', '_'))
            report += f"✅ {pkg} - установлен\n"
        except ImportError:
            report += f"❌ {pkg} - НЕ установлен\n"
    
    # 2. Проверка banana-browser
    report += "\n**🍌 banana-browser:**\n"
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
    
    # 3. Проверка браузера
    report += "\n**🌐 Браузер:**\n"
    if CHROME_PATH and os.path.exists(CHROME_PATH):
        report += f"✅ Найден: {CHROME_PATH}\n"
        # Проверяем версию
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
    
    # 4. Проверка переменных окружения
    report += "\n**🔧 Переменные окружения:**\n"
    env_vars = ['AGENT_BROWSER_ENGINE', 'CHROMIUM_PATH', 'BU_CDP_URL']
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            report += f"✅ {var} = {value[:50]}...\n"
        else:
            report += f"⚠️ {var} - не установлена\n"
    
    # 5. Проверка xvfb
    report += "\n**🖥️ xvfb (графический эмулятор):**\n"
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
    
    await update.message.reply_text(report)

async def browser_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о браузере"""
    if not CHROME_PATH or not os.path.exists(CHROME_PATH):
        await update.message.reply_text("❌ Браузер не найден!")
        return
    
    report = f"📊 **Информация о браузере**\n\n"
    report += f"📁 Путь: `{CHROME_PATH}`\n"
    
    # Версия
    try:
        result = subprocess.run(
            [CHROME_PATH, '--version'],
            capture_output=True,
            text=True,
            timeout=3
        )
        if result.returncode == 0:
            report += f"📌 Версия: `{result.stdout.strip()}`\n"
    except:
        pass
    
    # Проверка прав
    try:
        stat = os.stat(CHROME_PATH)
        report += f"🔑 Права: `{oct(stat.st_mode)[-3:]}`\n"
        report += f"📏 Размер: `{stat.st_size // 1024} KB`\n"
    except:
        pass
    
    # Переменные окружения
    report += f"\n**Переменные:**\n"
    report += f"`AGENT_BROWSER_ENGINE` = {os.environ.get('AGENT_BROWSER_ENGINE', 'не установлена')}\n"
    report += f"`CHROMIUM_PATH` = {os.environ.get('CHROMIUM_PATH', 'не установлена')}\n"
    
    await update.message.reply_text(report)

async def diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная диагностика с запуском браузера"""
    await update.message.reply_text("🔄 Запускаю полную диагностику...")
    
    try:
        # Проверяем импорт
        from browser_harness import BrowserSession
        
        report = "🔬 **Диагностика browser-harness**\n\n"
        
        # Версия
        try:
            import browser_harness
            report += f"📦 Версия: {browser_harness.__version__}\n\n"
        except:
            pass
        
        # Проверяем браузер
        report += "🔄 Запуск браузера...\n"
        
        try:
            async with BrowserSession() as session:
                await session.start()
                report += "✅ Браузер запущен\n"
                
                # Открываем страницу
                page = await session.new_page()
                await page.goto("about:blank")
                report += "✅ Страница открыта\n"
                
                # Проверяем navigator.webdriver
                webdriver = await page.evaluate("navigator.webdriver")
                report += f"✅ navigator.webdriver = {webdriver}\n\n"
                
                if webdriver is False:
                    report += "🎉 **Браузер НЕОТЛИЧИМ от обычного!**\n"
                else:
                    report += "⚠️ Браузер обнаруживается как бот\n"
                
                await session.close()
                
        except Exception as e:
            report += f"❌ Ошибка: {str(e)[:200]}\n"
        
        await update.message.reply_text(report)
        
    except ImportError as e:
        await update.message.reply_text(
            f"❌ browser-harness не установлен!\n"
            f"Ошибка: {str(e)[:100]}\n\n"
            "Установите: pip install browser-harness"
        )
    except Exception as e:
        logger.error(f"Диагностика ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет браузер на сайте bot.sannysoft.com"""
    await update.message.reply_text("🔄 Запускаю проверку браузера...")

    try:
        # Проверяем установку
        try:
            from browser_harness import BrowserSession
        except ImportError:
            await update.message.reply_text(
                "❌ browser-harness не установлен!\n"
                "Используй /check_install для диагностики"
            )
            return
        
        # Проверяем браузер
        if not CHROME_PATH or not os.path.exists(CHROME_PATH):
            await update.message.reply_text(
                f"❌ Браузер не найден по пути: {CHROME_PATH}\n"
                "Используй /check_install для диагностики"
            )
            return
        
        # Запускаем браузер
        try:
            async with BrowserSession() as session:
                await session.start()
                page = await session.new_page()
                
                # Открываем тестовый сайт
                await page.goto("https://bot.sannysoft.com")
                await asyncio.sleep(5)
                
                # Делаем скриншот
                screenshot = await page.screenshot()
                await update.message.reply_photo(
                    photo=screenshot,
                    caption="📸 Проверка браузера"
                )
                
                # Извлекаем метрики
                result = await page.evaluate("""
                    () => {
                        const canvas = document.createElement('canvas');
                        return {
                            webdriver: navigator.webdriver,
                            userAgent: navigator.userAgent,
                            platform: navigator.platform,
                            languages: navigator.languages,
                            webgl: !!canvas.getContext('webgl'),
                            canvas: !!canvas.getContext('2d')
                        }
                    }
                """)
                
                # Формируем отчет
                if not result['webdriver']:
                    verdict = "✅ **Браузер выглядит как обычный!**"
                else:
                    verdict = "⚠️ **Браузер похож на бота!**"
                
                report = f"""
🔍 **Результат проверки**

{verdict}

**Ключевые метрики:**
• `navigator.webdriver`: `{result['webdriver']}` 
• `navigator.platform`: `{result['platform']}`
• `navigator.languages`: `{', '.join(result['languages'][:2])}`
• WebGL: {'✅ Доступен' if result['webgl'] else '❌ Недоступен'}
• Canvas 2D: {'✅ Доступен' if result['canvas'] else '❌ Недоступен'}
• User-Agent: `{result['userAgent'][:60]}...`

💡 **Вывод:** Если `webdriver = false` — браузер неотличим от обычного.
"""
                await update.message.reply_text(report)
                
        except Exception as e:
            logger.error(f"Ошибка проверки: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    """Запуск бота"""
    app = Application.builder().token(TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_browser", check_browser))
    app.add_handler(CommandHandler("check_install", check_install))
    app.add_handler(CommandHandler("diagnostic", diagnostic))
    app.add_handler(CommandHandler("browser_info", browser_info))
    app.add_handler(CommandHandler("find_browser", find_browser_path))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Доступные команды:")
    logger.info("  /start - приветствие")
    logger.info("  /check_browser - проверить браузер")
    logger.info("  /check_install - проверить установку")
    logger.info("  /diagnostic - полная диагностика")
    logger.info("  /browser_info - информация о браузере")
    logger.info("  /find_browser - найти браузер в системе")
    
    app.run_polling()

if __name__ == "__main__":
    main()