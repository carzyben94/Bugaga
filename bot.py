import os
import sys
import asyncio
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я проверяю браузер на незаметность.\n\n"
        "Доступные команды:\n"
        "/check_browser - проверить браузер\n"
        "/check_install - проверить установленные компоненты\n"
        "/diagnostic - полная диагностика системы"
    )

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
    
    # 3. Проверка Chromium
    report += "\n**🌐 Chromium:**\n"
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/root/.cache/banana-browser/chrome/linux-129.0.6668.89/chrome-linux64/chrome'
    ]
    found = False
    for path in chromium_paths:
        if os.path.exists(path):
            report += f"✅ Найден: {path}\n"
            found = True
            break
    if not found:
        report += "❌ Chromium не найден в стандартных путях\n"
    
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

async def diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная диагностика с проверкой браузера через browser-harness"""
    await update.message.reply_text("🔄 Запускаю полную диагностику...")
    
    try:
        # Проверяем импорт
        from browser_harness import BrowserSession
        
        report = "🔬 **Диагностика browser-harness**\n\n"
        
        # Проверяем версию
        import browser_harness
        report += f"📦 Версия browser-harness: {browser_harness.__version__}\n\n"
        
        # Проверяем запуск браузера
        report += "🔄 Пытаюсь запустить браузер...\n"
        
        try:
            async with BrowserSession() as session:
                await session.start()
                report += "✅ Браузер успешно запущен\n"
                
                # Проверяем, что можем открыть страницу
                page = await session.new_page()
                await page.goto("about:blank")
                report += "✅ Страница открыта\n"
                
                # Проверяем navigator.webdriver
                webdriver = await page.evaluate("navigator.webdriver")
                report += f"✅ navigator.webdriver = {webdriver}\n"
                
                if webdriver is False:
                    report += "🎉 **Браузер НЕОТЛИЧИМ от обычного!**\n"
                else:
                    report += "⚠️ Браузер обнаруживается как бот\n"
                
                await session.close()
                
        except Exception as e:
            report += f"❌ Ошибка при запуске: {str(e)[:150]}\n"
        
        await update.message.reply_text(report)
        
    except ImportError as e:
        await update.message.reply_text(
            f"❌ browser-harness не установлен!\n"
            f"Ошибка: {str(e)[:100]}\n\n"
            "Установите: pip install browser-harness"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка диагностики: {str(e)[:200]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет браузер на признаки автоматизации"""
    await update.message.reply_text("🔄 Запускаю проверку браузера...")

    try:
        # Сначала проверим установку
        try:
            from browser_harness import BrowserSession
        except ImportError:
            await update.message.reply_text(
                "❌ browser-harness не установлен!\n"
                "Используй /check_install для диагностики"
            )
            return
        
        async with BrowserSession() as session:
            await session.start()
            page = await session.new_page()
            
            # Открываем тестовый сайт
            await page.goto("https://bot.sannysoft.com")
            await asyncio.sleep(3)
            
            # Делаем скриншот
            screenshot = await page.screenshot()
            await update.message.reply_photo(
                photo=screenshot,
                caption="📸 Проверка браузера"
            )
            
            # Извлекаем метрики
            result = await page.evaluate("""
                () => {
                    return {
                        webdriver: navigator.webdriver,
                        userAgent: navigator.userAgent,
                        platform: navigator.platform,
                        languages: navigator.languages,
                        webgl: !!document.createElement('canvas').getContext('webgl')
                    }
                }
            """)
            
            # Формируем отчет
            verdict = "✅ **Браузер выглядит как обычный!**" if not result['webdriver'] else "⚠️ **Браузер похож на бота!**"
            
            report = f"""
🔍 **Результат проверки**

{verdict}

**Ключевые метрики:**
• `navigator.webdriver`: `{result['webdriver']}` 
• `navigator.platform`: `{result['platform']}`
• `navigator.languages`: `{', '.join(result['languages'][:2])}`
• WebGL: {'✅ Доступен' if result['webgl'] else '❌ Недоступен'}
• User-Agent: `{result['userAgent'][:60]}...`

💡 **Вывод:** Если `webdriver = false` и есть WebGL — браузер неотличим от обычного.
"""
            await update.message.reply_text(report)
            
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_browser", check_browser))
    app.add_handler(CommandHandler("check_install", check_install))
    app.add_handler(CommandHandler("diagnostic", diagnostic))
    
    print("🤖 Бот запущен! Доступные команды:")
    print("  /start - приветствие")
    print("  /check_browser - проверить браузер")
    print("  /check_install - проверить установку")
    print("  /diagnostic - полная диагностика")
    
    app.run_polling()

if __name__ == "__main__":
    main()