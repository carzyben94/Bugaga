import asyncio
import logging
import os
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Путь к браузеру Google Chrome
CHROME_PATH = "/usr/bin/google-chrome"

# Глобальная переменная для хранения экземпляра браузера
browser_instance = None
tab_instance = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def normalize_url(url: str) -> str:
    """Добавляет https:// если протокол не указан"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 3):
    """Удаляет сообщение через указанную задержку"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")

async def send_and_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, delay: int = 3):
    """Отправляет сообщение и удаляет его через delay секунд"""
    message = await update.message.reply_text(text)
    asyncio.create_task(delete_message_after_delay(context, update.effective_chat.id, message.message_id, delay))
    return message

async def send_photo_and_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, photo: bytes, caption: str = "", delay: int = 10):
    """Отправляет фото и удаляет его через delay секунд"""
    message = await update.message.reply_photo(photo, caption=caption)
    asyncio.create_task(delete_message_after_delay(context, update.effective_chat.id, message.message_id, delay))
    return message

async def delete_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, delay: int = 1):
    """Удаляет сообщение пользователя"""
    try:
        await asyncio.sleep(delay)
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения пользователя: {e}")

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БРАУЗЕРОМ ---

def get_browser_options():
    """Создает и возвращает настроенный объект ChromiumOptions"""
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    """Открывает браузер и создает новую вкладку"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер успешно открыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже открыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при открытии браузера: {e}")
        return False

async def close_browser():
    """Закрывает браузер"""
    global browser_instance, tab_instance
    
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер успешно закрыт")
            return True
        else:
            logger.info("ℹ️ Браузер уже закрыт")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии браузера: {e}")
        return False

async def take_screenshot():
    """Делает скриншот всей страницы"""
    global tab_instance
    
    try:
        if tab_instance is None:
            return None, "❌ Браузер не открыт. Используйте /open_bw"
        
        screenshot_data = await tab_instance.take_screenshot(
            beyond_viewport=True,
            as_base64=True
        )
        
        logger.info("📸 Скриншот всей страницы сделан")
        return screenshot_data, None
    except Exception as e:
        logger.error(f"❌ Ошибка при создании скриншота: {e}")
        return None, str(e)

def get_browser_status():
    """Возвращает статус браузера"""
    global browser_instance, tab_instance
    
    if browser_instance is not None and tab_instance is not None:
        return "🟢 Включен"
    else:
        return "🔴 Выключен"

# --- КОМАНДЫ БОТА ---

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    await send_and_delete(
        update,
        context,
        "/status - Статус браузера\n"
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/screen - Скриншот всей страницы\n"
        "/go <URL> - Перейти на сайт",
        delay=10
    )

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус браузера"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    status = get_browser_status()
    await send_and_delete(update, context, f"📊 Статус браузера: {status}", delay=5)

# Команда /open_bw
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает браузер"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    await send_and_delete(update, context, "🌐 Открываю браузер...", delay=0)
    
    success = await open_browser()
    if success:
        await send_and_delete(update, context, "✅ Браузер успешно открыт!", delay=3)
    else:
        await send_and_delete(update, context, "❌ Не удалось открыть браузер. Проверьте логи.", delay=5)

# Команда /close_bw
async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    await send_and_delete(update, context, "❌ Закрываю браузер...", delay=0)
    
    success = await close_browser()
    if success:
        await send_and_delete(update, context, "✅ Браузер успешно закрыт!", delay=3)
    else:
        await send_and_delete(update, context, "❌ Не удалось закрыть браузер. Проверьте логи.", delay=5)

# Команда /screen
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот всей страницы"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    await send_and_delete(update, context, "📸 Делаю скриншот всей страницы...", delay=0)
    
    screenshot_data, error = await take_screenshot()
    
    if error:
        await send_and_delete(update, context, f"❌ {error}", delay=5)
    elif screenshot_data:
        try:
            if isinstance(screenshot_data, str):
                screenshot_bytes = base64.b64decode(screenshot_data)
            else:
                screenshot_bytes = screenshot_data
            
            await send_photo_and_delete(
                update,
                context,
                screenshot_bytes,
                caption="📸 Скриншот всей страницы",
                delay=10
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке скриншота: {e}")
            await send_and_delete(update, context, f"❌ Ошибка при отправке скриншота: {str(e)}", delay=5)
    else:
        await send_and_delete(update, context, "❌ Не удалось сделать скриншот", delay=5)

# Команда /go
async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переходит на указанный URL"""
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_user_message(update, context))
    
    if not context.args:
        await send_and_delete(
            update,
            context,
            "❌ Укажите URL.\nПример: /go https://example.com",
            delay=5
        )
        return
    
    url = normalize_url(context.args[0])
    
    await send_and_delete(update, context, f"🔗 Перехожу на {url}...", delay=0)
    
    try:
        if tab_instance is None:
            await send_and_delete(
                update,
                context,
                "❌ Браузер не открыт. Используйте /open_bw",
                delay=5
            )
            return
        
        await tab_instance.go_to(url)
        title = await tab_instance.title
        await send_and_delete(
            update,
            context,
            f"✅ Перешел на {url}\n📄 Заголовок: {title}",
            delay=5
        )
    except Exception as e:
        logger.error(f"Ошибка при переходе: {e}")
        await send_and_delete(update, context, f"❌ Ошибка: {str(e)}", delay=5)

# --- ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ---

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция запуска бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()

        # Регистрируем команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info(f"📁 Используемый браузер: {CHROME_PATH}")
        logger.info("ℹ️ Доступные команды: /start, /status, /open_bw, /close_bw, /screen, /go")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()