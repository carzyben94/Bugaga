#!/usr/bin/env python3
"""
Telegram-бот для управления CloakBrowser + Playwright + Xvfb
Автоматически устанавливает все зависимости при первом запуске
"""

import os
import sys
import subprocess
import asyncio
import logging
import tempfile
import shutil
from pathlib import Path

# ===== АВТОУСТАНОВЩИК =====

def install_dependencies():
    """Автоматическая установка всех зависимостей"""
    
    print("🔧 Проверка и установка зависимостей...")
    
    # 1. Проверяем Python версию
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        sys.exit(1)
    
    # 2. Устанавливаем pip пакеты
    packages = [
        "python-telegram-bot>=21.5",
        "playwright>=1.56.0",
        "cloakbrowser>=0.1.0",
        "python-dotenv>=1.0.0",
    ]
    
    for pkg in packages:
        print(f"📦 Устанавливаю {pkg}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg],
            check=False
        )
    
    # 3. Устанавливаем Playwright браузеры
    print("🌐 Устанавливаю Playwright Chromium...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False
    )
    
    # 4. Проверяем Xvfb (только на Linux)
    if sys.platform == "linux":
        if not shutil.which("Xvfb"):
            print("⚠️ Xvfb не найден. Установите вручную: sudo apt-get install xvfb")
            print("⚠️ Или используйте headless=True")
        else:
            print("✅ Xvfb найден")
    
    print("✅ Все зависимости установлены!")
    print("=" * 50)

# Запускаем установку при первом импорте
if os.environ.get("SKIP_INSTALL") != "true":
    install_dependencies()

# ===== ИМПОРТЫ ПОСЛЕ УСТАНОВКИ =====

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    from playwright.async_api import async_playwright
    from cloakbrowser import launch
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("🔄 Перезапустите скрипт для повторной установки")
    sys.exit(1)

# ===== НАСТРОЙКИ =====

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не найден!")
    print("📝 Установите переменную окружения:")
    print("   export TELEGRAM_BOT_TOKEN='ваш_токен'")
    sys.exit(1)

PROXY_URL = os.environ.get('PROXY_URL', '')
HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'
DISPLAY = os.environ.get('DISPLAY', ':99')

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== БРАУЗЕРНАЯ ЛОГИКА =====

async def launch_browser():
    """Запускает CloakBrowser с правильными настройками"""
    try:
        return await launch(
            headless=HEADLESS,
            proxy=PROXY_URL if PROXY_URL else None,
            geoip=bool(PROXY_URL),
            humanize=True,
            timeout=60000,
            args=['--disable-blink-features=AutomationControlled']
        )
    except Exception as e:
        logger.error(f"Ошибка запуска браузера: {e}")
        return None

async def open_x_com():
    """Открыть X.com и вернуть информацию"""
    browser = await launch_browser()
    if not browser:
        return "❌ Не удалось запустить браузер"
    
    try:
        page = await browser.new_page()
        await page.goto('https://x.com', wait_until='networkidle', timeout=30000)
        title = await page.title()
        url = page.url
        await browser.close()
        return f"✅ X.com загружен\n📄 Заголовок: {title}\n🔗 URL: {url}"
    except Exception as e:
        await browser.close()
        return f"❌ Ошибка: {str(e)[:200]}"

async def take_screenshot():
    """Сделать скриншот и сохранить во временный файл"""
    browser = await launch_browser()
    if not browser:
        return None
    
    try:
        page = await browser.new_page()
        await page.goto('https://x.com', wait_until='networkidle', timeout=30000)
        
        # Сохраняем во временный файл
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        await page.screenshot(path=temp_file.name, full_page=True)
        await browser.close()
        return temp_file.name
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")
        await browser.close()
        return None

async def check_status():
    """Проверка статуса всех компонентов"""
    status = []
    status.append(f"🤖 Бот: ✅ работает")
    status.append(f"🐍 Python: {sys.version}")
    status.append(f"🖥️ DISPLAY: {DISPLAY}")
    status.append(f"🌐 Headless: {HEADLESS}")
    status.append(f"🔌 Proxy: {'✅ установлен' if PROXY_URL else '❌ не используется'}")
    
    # Проверяем Xvfb
    if sys.platform == "linux" and shutil.which("Xvfb"):
        status.append("🖥️ Xvfb: ✅ установлен")
    else:
        status.append("🖥️ Xvfb: ❌ не найден")
    
    return "\n".join(status)

# ===== КОМАНДЫ ТЕЛЕГРАМ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и главное меню"""
    keyboard = [
        [InlineKeyboardButton("🌐 Открыть X.com", callback_data='open_x')],
        [InlineKeyboardButton("📸 Сделать скриншот", callback_data='screenshot')],
        [InlineKeyboardButton("🔄 Проверить статус", callback_data='status')],
        [InlineKeyboardButton("📊 Помощь", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Бот управления браузером*\n\n"
        "Стек: Playwright + CloakBrowser + Xvfb\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'open_x':
        await query.edit_message_text("⏳ Открываю X.com... Это может занять 10-30 секунд")
        result = await open_x_com()
        await query.edit_message_text(result)
    
    elif data == 'screenshot':
        await query.edit_message_text("📸 Делаю скриншот X.com...")
        screenshot_path = await take_screenshot()
        if screenshot_path:
            await query.edit_message_text("✅ Скриншот готов!")
            with open(screenshot_path, 'rb') as photo:
                await query.message.reply_photo(photo=photo)
            os.unlink(screenshot_path)  # Удаляем временный файл
        else:
            await query.edit_message_text("❌ Не удалось сделать скриншот")
    
    elif data == 'status':
        status_text = await check_status()
        await query.edit_message_text(f"📊 *Статус системы*\n\n{status_text}", parse_mode='Markdown')
    
    elif data == 'help':
        help_text = """
📖 *Помощь*

*Команды:*
/start - Главное меню
/status - Статус системы

*Кнопки:*
🌐 Открыть X.com - проверяет доступность
📸 Сделать скриншот - фото главной страницы

*Настройка:*
• TELEGRAM_BOT_TOKEN - токен бота
• PROXY_URL - прокси (опционально)
• HEADLESS - true/false (по умолчанию false)

*Стек:* Playwright + CloakBrowser + Xvfb
        """
        await query.edit_message_text(help_text, parse_mode='Markdown')

# ===== ОБРАБОТЧИК ОШИБОК =====

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка глобальных ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Попробуйте снова позже."
        )

# ===== ЗАПУСК =====

def main():
    """Основная функция запуска"""
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🔑 Токен: {TOKEN[:10]}...")
    logger.info(f"🖥️ Headless: {HEADLESS}")
    logger.info(f"🔌 Proxy: {'✅' if PROXY_URL else '❌'}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()