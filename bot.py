import os
import logging
import asyncio
import base64
import json
import re
from io import BytesIO
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
CHROME_PATH = '/usr/bin/chromium'

agnes_client = None
if AGNES_API_KEY:
    agnes_client = AsyncOpenAI(api_key=AGNES_API_KEY, base_url="https://apihub.agnes-ai.com/v1")

# ==================== ПОЛНЫЕ КУКИ ====================

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

# ==================== КУРСОР ====================

class CursorManager:
    def __init__(self):
        self.x = 500
        self.y = 300

cursor_managers = {}

def get_cursor(user_id):
    if user_id not in cursor_managers:
        cursor_managers[user_id] = CursorManager()
    return cursor_managers[user_id]

def draw_cursor(screenshot_bytes, x, y):
    try:
        image = Image.open(BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(image)
        size = 15
        draw.line([(x - size, y), (x + size, y)], fill='red', width=3)
        draw.line([(x, y - size), (x, y + size)], fill='red', width=3)
        draw.ellipse([(x - 3, y - 3), (x + 3, y + 3)], fill='red')
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
    except:
        return screenshot_bytes

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для X.com\n\n"
        "/login — войти в X.com\n"
        "/close — закрыть браузер\n\n"
        "После входа используй:\n"
        "/ai <команда> — выполнить команду в браузере\n\n"
        "Примеры:\n"
        "/ai найди лайк\n"
        "/ai собери твиты\n"
        "/ai прокрути вниз"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1024,768")
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
        
        cursor = get_cursor(user_id)
        try:
            viewport = await tab.execute_script("return { width: window.innerWidth, height: window.innerHeight }")
            cursor.x = viewport['width'] // 2
            cursor.y = viewport['height'] // 2
        except:
            cursor.x, cursor.y = 500, 300
        
        await update.message.reply_text("✅ Вход выполнен! Размер окна: 1024x768")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_browsers:
        browser, _ = user_browsers[user_id]
        await browser.close()
        del user_browsers[user_id]
        await update.message.reply_text("✅ Браузер закрыт")
    else:
        await update.message.reply_text("❌ Браузер не открыт")

# ==================== AI БРАУЗЕР ====================

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи команду\n"
            "Пример: /ai найди лайк"
        )
        return
    
    user_id = update.effective_user.id
    command = ' '.join(context.args)
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    
    await update.message.reply_text(f"🧠 AI: {command}")
    await update.message.reply_text("⚡ Генерирую код...")
    
    try:
        response = await agnes_client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {"role": "system", "content": """
                Ты — эксперт по JavaScript для автоматизации X.com.
                Верни ТОЛЬКО код. Без пояснений.
                
                ВАЖНО: Всегда возвращай результат:
                - Если ищешь элемент → верни {x, y}
                - Если собираешь данные → верни список
                - Если выполняешь действие → верни "ok" или результат
                - НИКОГДА не возвращай undefined
                
                Используй return в конце кода.
                """},
                {"role": "user", "content": f"""
                Команда: {command}
                
                Примеры:
                - "найди лайк" → найти кнопку лайка и вернуть {{x, y}}
                - "собери твиты" → собрать тексты всех твитов в список
                - "прокрути вниз" → window.scrollBy(0, 300); return 'ok'
                - "кликни поиск" → найти и кликнуть на поле поиска; return 'clicked'
                
                Верни ТОЛЬКО код. Оберни в функцию.
                ВСЕГДА возвращай результат через return.
                """}
            ],
            max_tokens=500,
            temperature=0.1
        )
        
        js_code = response.choices[0].message.content
        js_code = re.sub(r'```javascript\n?', '', js_code)
        js_code = re.sub(r'```\n?', '', js_code)
        js_code = js_code.strip()
        
        await update.message.reply_text(f"⚡ Выполняю...\n```javascript\n{js_code[:300]}\n```", parse_mode='Markdown')
        
        result = await tab.execute_script(js_code)
        
        # Если результат undefined или None
        if result is None or result == {}:
            await update.message.reply_text("✅ Команда выполнена (без возврата данных)")
            return
        
        if isinstance(result, dict) and 'x' in result:
            x, y = result['x'], result['y']
            cursor.x, cursor.y = x, y
            await update.message.reply_text(f"🎯 Найдено → ({x}, {y})")
            screenshot = await tab.take_screenshot(as_base64=True)
            img = draw_cursor(base64.b64decode(screenshot), cursor.x, cursor.y)
            await update.message.reply_photo(
                photo=img,
                caption=f"📍 ({cursor.x}, {cursor.y})"
            )
        elif isinstance(result, list):
            reply = f"📊 Результат ({len(result)} элементов):\n\n"
            for i, item in enumerate(result[:10], 1):
                reply += f"{i}. {str(item)[:150]}\n"
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(f"✅ Результат:\n{str(result)[:500]}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        if 'js_code' in locals():
            await update.message.reply_text(f"📄 Код:\n{js_code[:500]}")

# ==================== ЗАПУСК ====================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("close", close_browser))
    app.add_handler(CommandHandler("ai", ai_command))
    app.run_polling()

if __name__ == "__main__":
    main() 