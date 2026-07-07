import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pydoll.browser.chromium import Chrome  # Изменен импорт
from pydoll.browser.options import ChromiumOptions  # Для настроек
from pydoll.constants import PageLoadState

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

# Путь к Chrome
CHROME_PATH = '/usr/bin/google-chrome'

# Куки для X.com
X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "0lyNYlKnbjXejqIk_blw2x20TfMRtW3SWJ_jmpay.t4-1783123617.0158947-1.0.1.1-1rnugK6C5Aw5r.126FQ3rJYZTCG2WhtPATFYO5Ip0QukW40cCR0qDNfacg6VRv3vRh3w.4Un_NQ6hOnxQfvhm68Grg1hZiLbF6HAyxvxzmS06Q8AzQkKu_i248B5sxj7", "domain": ".x.com", "path": "/"}
]

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/browser - Запустить браузер и открыть X.com"
    )

# Команда /browser
async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю браузер, подождите...")
    try:
        result = await run_browser_task()
        await update.message.reply_text(
            f"✅ Браузер выполнил задачу!\n\n"
            f"Результат: {result}"
        )
    except Exception as e:
        logger.error(f"Ошибка браузера: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при запуске браузера:\n{str(e)}"
        )

# Асинхронная задача для браузера
async def run_browser_task():
    # Настройка опций браузера согласно документации [citation:5]
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH  # Указываем путь к Chrome
    options.headless = True  # Запуск в фоновом режиме
    options.start_timeout = 30  # Увеличиваем таймаут для надежности
    # Добавляем аргументы для совместимости с Railway
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    # Используем контекстный менеджер для автоматического управления [citation:1][citation:7]
    async with Chrome(options=options) as browser:
        # Создаем новую вкладку
        tab = await browser.start()
        
        # Устанавливаем куки через NetworkCommands [citation:6][citation:8]
        # В новой версии куки устанавливаются через tab.set_cookies()
        for cookie_data in X_COOKIES:
            await tab.set_cookies([{
                'name': cookie_data['name'],
                'value': cookie_data['value'],
                'domain': cookie_data['domain'],
                'path': cookie_data['path']
            }])
        
        # Переходим на сайт
        await tab.go_to('https://x.com')
        await asyncio.sleep(3)
        
        # Получаем заголовок
        title = await tab.title
        
        # Получаем текущий URL
        current_url = await tab.get_current_url()
        
        return f"Заголовок: {title}\nURL: {current_url}\nСтатус: Авторизация выполнена"

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже."
        )

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("browser", browser_command))
    application.add_error_handler(error_handler)
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()