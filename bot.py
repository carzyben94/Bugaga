# ============================================
# БЛОК 1: ИМПОРТЫ И КОНФИГУРАЦИЯ
# ============================================
import os
import asyncio
import logging
import json
import base64
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем браузер из отдельного модуля
from bsw import StealthBrowser

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Константы
BROWSER_PORT = 9222
CHROME_PATH = "/usr/bin/chromium"


# ============================================
# БЛОК 2: КЛАСС БОТА С БРАУЗЕРОМ
# ============================================
class Bot:
    """Главный бот с браузером"""
    
    def __init__(self):
        self.browser = None
        self.is_ready = False
    
    async def start_browser(self):
        """Запуск браузера с маскировкой"""
        if not self.browser:
            logger.info("🚀 Запускаю браузер...")
            self.browser = await StealthBrowser.launch(
                headless=True,
                port=BROWSER_PORT,
                chrome_path=CHROME_PATH
            )
            self.is_ready = True
            logger.info("✅ Браузер готов!")
        return self
    
    async def go_to(self, url: str):
        """Переход на сайт"""
        await self.start_browser()
        logger.info(f"🌐 Перехожу на {url}")
        await StealthBrowser.go_to(self.browser, url)
    
    async def get_text(self, selector: str) -> str:
        """Получение текста по селектору"""
        await self.start_browser()
        return await StealthBrowser.get_text(self.browser, selector)
    
    async def click(self, selector: str, humanize: bool = True):
        """Клик с человеческим поведением"""
        await self.start_browser()
        await StealthBrowser.click(self.browser, selector, humanize)
    
    async def type_text(self, selector: str, text: str, humanize: bool = True):
        """Ввод текста с человеческим поведением"""
        await self.start_browser()
        await StealthBrowser.type_text(self.browser, selector, text, humanize)
    
    async def screenshot(self) -> bytes:
        """Сделать скриншот"""
        await self.start_browser()
        return await StealthBrowser.screenshot(self.browser)
    
    async def close(self):
        """Закрытие браузера"""
        if self.browser:
            await StealthBrowser.close(self.browser)
            self.browser = None
            self.is_ready = False


# ============================================
# БЛОК 3: СОЗДАНИЕ ГЛОБАЛЬНОГО ЭКЗЕМПЛЯРА
# ============================================
bot = Bot()


# ============================================
# БЛОК 4: ОБРАБОТЧИКИ TELEGRAM КОМАНД
# ============================================

# --- 4.1: Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и список команд"""
    await update.message.reply_text(
        "👋 Привет! Я бот с браузером.\n\n"
        "📋 Команды:\n"
        "/browser_start - запустить браузер\n"
        "/browser_status - статус браузера\n"
        "/browser_close - закрыть браузер\n"
        "/go_to <url> - перейти на сайт\n"
        "/get_text <selector> - получить текст\n"
        "/click <selector> - кликнуть\n"
        "/type <selector>|<text> - ввести текст\n"
        "/screenshot - сделать скриншот"
    )


# --- 4.2: Команда /browser_start ---
async def browser_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск браузера"""
    await update.message.reply_text("🔄 Запускаю браузер...")
    try:
        await bot.start_browser()
        await update.message.reply_text("✅ Браузер запущен с маскировкой!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# --- 4.3: Команда /browser_status ---
async def browser_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус браузера"""
    status = "✅ Работает" if bot.is_ready else "❌ Не запущен"
    await update.message.reply_text(f"📊 Статус браузера: {status}")


# --- 4.4: Команда /browser_close ---
async def browser_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрытие браузера"""
    await update.message.reply_text("🔄 Закрываю браузер...")
    await bot.close()
    await update.message.reply_text("✅ Браузер закрыт")


# --- 4.5: Команда /go_to ---
async def go_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход на сайт"""
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go_to https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🌐 Перехожу на {url}...")
    try:
        await bot.go_to(url)
        await update.message.reply_text("✅ Страница загружена!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# --- 4.6: Команда /get_text ---
async def get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста по селектору"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /get_text h1")
        return
    
    selector = context.args[0]
    await update.message.reply_text(f"🔍 Ищу '{selector}'...")
    try:
        text = await bot.get_text(selector)
        if text:
            await update.message.reply_text(f"📝 Текст: {text[:500]}")
        else:
            await update.message.reply_text("❌ Элемент не найден или пуст")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# --- 4.7: Команда /click ---
async def click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клик по элементу"""
    if not context.args:
        await update.message.reply_text("❌ Укажи селектор: /click button.submit")
        return
    
    selector = context.args[0]
    await update.message.reply_text(f"🖱️ Кликаю на '{selector}'...")
    try:
        await bot.click(selector, humanize=True)
        await update.message.reply_text("✅ Клик выполнен!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# --- 4.8: Команда /type ---
async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод текста"""
    if not context.args:
        await update.message.reply_text("❌ Укажи: /type selector|текст")
        return
    
    try:
        parts = ' '.join(context.args).split('|')
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: /type selector|текст")
            return
        
        selector, text = parts[0], parts[1]
        await update.message.reply_text(f"⌨️ Ввожу '{text}' в '{selector}'...")
        await bot.type_text(selector, text, humanize=True)
        await update.message.reply_text("✅ Текст введен!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# --- 4.9: Команда /screenshot ---
async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот страницы"""
    await update.message.reply_text("📸 Делаю скриншот...")
    try:
        image_data = await bot.screenshot()
        if image_data:
            await update.message.reply_photo(
                photo=BytesIO(image_data),
                caption="📸 Скриншот страницы"
            )
        else:
            await update.message.reply_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ============================================
# БЛОК 5: РЕГИСТРАЦИЯ КОМАНД И ЗАПУСК
# ============================================

def register_handlers(app: Application):
    """Регистрация всех обработчиков команд"""
    handlers = [
        CommandHandler("start", start),
        CommandHandler("browser_start", browser_start),
        CommandHandler("browser_status", browser_status),
        CommandHandler("browser_close", browser_close),
        CommandHandler("go_to", go_to),
        CommandHandler("get_text", get_text),
        CommandHandler("click", click),
        CommandHandler("type", type_text),
        CommandHandler("screenshot", screenshot),
    ]
    
    for handler in handlers:
        app.add_handler(handler)


def main():
    """Запуск бота"""
    logger.info("🤖 Запуск Telegram бота...")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    register_handlers(app)
    
    # Запускаем
    logger.info("✅ Бот готов! Начинаем polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# ============================================
# БЛОК 6: ТОЧКА ВХОДА
# ============================================

if __name__ == "__main__":
    main()