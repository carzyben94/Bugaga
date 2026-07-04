import os
import logging
import asyncio
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CHROME_PATH = '/usr/bin/chromium'

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

user_browsers = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 *Бот для X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n\n"
        "⚡ *JavaScript*\n"
        "/eval <js> — Выполнить JavaScript"
    )
    await update.message.reply_text(menu, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        await tab.set_cookies(X_COOKIES)
        await asyncio.sleep(1)
        
        await tab.refresh()
        await asyncio.sleep(5)
        
        user_browsers[user_id] = (browser, tab)
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи JS код\n"
            "Пример: /eval document.title"
        )
        return
    
    js_code = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        result = await tab.execute_script(js_code)
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("eval", evaluate_js))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()