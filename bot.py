import os
import logging
import asyncio
import base64
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# Модель для парсинга цитат
class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

# Путь к браузеру
CHROME_PATH = '/usr/bin/chromium'

# Куки для X.com (с domain и path)
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

# Храним браузер и вкладку для каждого пользователя
user_browsers = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное меню"""
    await update.message.reply_text(
        "📋 Доступные команды:\n"
        "/login - Войти в X.com\n"
        "/parse - Получить цитаты\n"
        "/go <url> - Открыть любой сайт\n"
        "/screen - Сделать скриншот\n"
        "/cookie {\"name\":\"value\"} - Установить куки"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматический вход на X.com с куками"""
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        # Создаём браузер
        browser = Chrome(options=options)
        tab = await browser.start()
        
        # Сначала переходим на X.com (для установки домена)
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        # Устанавливаем куки
        await tab.set_cookies(X_COOKIES)
        await asyncio.sleep(1)
        
        # Обновляем страницу через refresh
        await tab.refresh()
        await asyncio.sleep(5)
        
        # Проверяем куки
        cookies = await tab.get_cookies()
        logger.info(f"Установлено кук: {len(cookies)}")
        
        # Сохраняем браузер
        user_browsers[user_id] = (browser, tab)
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        
        # Делаем скриншот для подтверждения
        await update.message.reply_text("📸 Делаю скриншот...")
        
        try:
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            screenshot_bytes = base64.b64decode(screenshot_base64)
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption="🖼️ Ты авторизован на X.com!"
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Не удалось сделать скриншот, но вход выполнен.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает любой сайт"""
    if not context.args:
        await update.message.reply_text("❌ Укажи URL после команды\nПример: /go https://example.com")
        return
    
    url = context.args[0]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text(f"🌐 Открываю: {url}")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        if user_id in user_browsers:
            browser, tab = user_browsers[user_id]
            await tab.go_to(url)
            await asyncio.sleep(3)
            await update.message.reply_text(f"✅ Перешёл на {url}")
        else:
            browser = Chrome(options=options)
            tab = await browser.start()
            await tab.go_to(url)
            await asyncio.sleep(3)
            user_browsers[user_id] = (browser, tab)
            await update.message.reply_text(f"✅ Открыл: {url}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает скриншот текущей страницы"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        
        await asyncio.sleep(1)
        
        try:
            screenshot_base64 = await asyncio.wait_for(
                tab.take_screenshot(as_base64=True),
                timeout=30.0
            )
            
            screenshot_bytes = base64.b64decode(screenshot_base64)
            
            await update.message.reply_photo(
                photo=screenshot_bytes,
                caption="🖼️ Скриншот страницы"
            )
            
        except asyncio.TimeoutError:
            await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка кук из JSON"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Передай JSON с куками\n"
            "Пример: /cookie {\"auth_token\":\"123\",\"ct0\":\"456\"}"
        )
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        json_str = ' '.join(context.args)
        cookies_data = json.loads(json_str)
        
        cookies_list = [
            {"name": name, "value": value}
            for name, value in cookies_data.items()
        ]
        
        await tab.set_cookies(cookies_list)
        await update.message.reply_text(f"✅ Установлено {len(cookies_list)} кук!")
        
    except json.JSONDecodeError:
        await update.message.reply_text(
            "❌ Неправильный JSON формат\n"
            "Пример: /cookie {\"auth_token\":\"123\",\"ct0\":\"456\"}"
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсит цитаты с quotes.toscrape.com"""
    await update.message.reply_text("⏳ Начинаю парсинг...")
    
    try:
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        async with Chrome(options=options) as browser:
            tab = await browser.start()
            await tab.go_to('https://quotes.toscrape.com')
            
            await asyncio.sleep(3)
            
            quotes = await tab.extract_all(
                Quote,
                scope=".quote",
                timeout=10
            )
            
            if quotes:
                reply = "📚 Цитаты:\n\n"
                for i, q in enumerate(quotes[:5], 1):
                    reply += f"{i}. \"{q.text}\"\n   — {q.author}\n   🏷️ {q.tags}\n\n"
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("😕 Ничего не найдено")
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("go", go))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("cookie", cookie))
    application.add_handler(CommandHandler("parse", parse))
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()