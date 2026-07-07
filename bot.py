import os
import asyncio
import logging
import base64
from io import BytesIO
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field
from PIL import Image, ImageDraw

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

# Модель только для текста твита
class Tweet(ExtractionModel):
    text: str = Field(selector='div[data-testid="tweetText"]')

# Хранилище активных браузеров
active_sessions = {}

# Клавиатура управления
def get_control_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("↖️", callback_data="up_left"),
            InlineKeyboardButton("⬆️", callback_data="up"),
            InlineKeyboardButton("↗️", callback_data="up_right")
        ],
        [
            InlineKeyboardButton("⬅️", callback_data="left"),
            InlineKeyboardButton("🔄", callback_data="refresh"),
            InlineKeyboardButton("➡️", callback_data="right")
        ],
        [
            InlineKeyboardButton("↙️", callback_data="down_left"),
            InlineKeyboardButton("⬇️", callback_data="down"),
            InlineKeyboardButton("↘️", callback_data="down_right")
        ],
        [
            InlineKeyboardButton("📝 Твиты", callback_data="extract_tweets")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Рисуем курсор на изображении
def draw_cursor_on_image(image_bytes, cursor_x, cursor_y):
    image = Image.open(BytesIO(image_bytes))
    draw = ImageDraw.Draw(image)
    
    cursor_size = 20
    
    points = [
        (cursor_x, cursor_y),
        (cursor_x - cursor_size//2, cursor_y + cursor_size),
        (cursor_x + cursor_size//2, cursor_y + cursor_size),
    ]
    draw.polygon(points, fill="red", outline="black")
    
    draw.ellipse(
        [(cursor_x - 3, cursor_y - 3), (cursor_x + 3, cursor_y + 3)],
        fill="black"
    )
    
    output = BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    return output

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/open_browser - Открыть браузер\n"
        "/close_browser - Закрыть браузер\n"
        "/tweets - Извлечь твиты"
    )

# Команда /open_browser
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in active_sessions:
        await update.message.reply_text(
            "⚠️ У вас уже есть активный браузер.\n"
            "Используйте /close_browser чтобы закрыть его."
        )
        return
    
    status_msg = await update.message.reply_text("🔄 Запускаю браузер, подождите...")
    
    try:
        screenshot, browser, tab, cursor_pos = await run_browser_task()
        
        active_sessions[user_id] = {
            "browser": browser,
            "tab": tab,
            "cursor_x": cursor_pos[0],
            "cursor_y": cursor_pos[1]
        }
        
        await status_msg.delete()
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Браузер открыт и авторизован!",
            reply_markup=get_control_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка браузера: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при запуске браузера:\n\n{str(e)}"
        )

# Команда /tweets - только текст
async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ Нет активного браузера. Используйте /open_browser"
        )
        return
    
    status_msg = await update.message.reply_text("🔄 Извлекаю твиты...")
    
    try:
        session = active_sessions[user_id]
        tab = session["tab"]
        
        tweets = await extract_tweets_from_page(tab)
        
        if not tweets:
            await status_msg.edit_text("❌ Твиты не найдены на странице")
            return
        
        # Формируем ответ только с текстом
        response = "📝 Твиты:\n\n"
        for i, tweet in enumerate(tweets[:10], 1):
            text = tweet.text.replace('\n', ' ').strip()
            if len(text) > 200:
                text = text[:200] + "..."
            response += f"{i}. {text}\n\n"
        
        if len(tweets) > 10:
            response += f"И ещё {len(tweets) - 10} твитов..."
        
        await status_msg.delete()
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Ошибка извлечения твитов: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при извлечении твитов:\n\n{str(e)}"
        )

# Команда /close_browser
async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ У вас нет активного браузера.\n"
            "Используйте /open_browser чтобы открыть его."
        )
        return
    
    try:
        session = active_sessions[user_id]
        await session["browser"].stop()
        del active_sessions[user_id]
        
        await update.message.reply_text("✅ Браузер успешно закрыт!")
        logger.info(f"Браузер закрыт для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при закрытии браузера: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при закрытии браузера:\n\n{str(e)}"
        )

# Получение скриншота с курсором
async def get_screenshot_with_cursor(tab, cursor_x, cursor_y):
    screenshot_base64 = await tab.take_screenshot(
        as_base64=True,
        quality=100,
        beyond_viewport=False
    )
    
    screenshot_bytes = base64.b64decode(screenshot_base64)
    image_with_cursor = draw_cursor_on_image(screenshot_bytes, cursor_x, cursor_y)
    
    return image_with_cursor

# Обновление скриншота
async def update_screenshot(query, tab, session):
    cursor_x = session.get("cursor_x", 500)
    cursor_y = session.get("cursor_y", 300)
    
    screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
    
    media = InputMediaPhoto(
        media=screenshot_io,
        caption="✅ Браузер открыт и авторизован!"
    )
    
    await query.edit_message_media(
        media=media,
        reply_markup=get_control_keyboard()
    )

# Извлечение только текста твитов
async def extract_tweets_from_page(tab):
    try:
        await asyncio.sleep(2)
        
        tweets = await tab.extract_all(
            Tweet,
            scope='article[data-testid="tweet"]',
            timeout=5
        )
        
        logger.info(f"Извлечено {len(tweets)} твитов")
        return tweets
    except Exception as e:
        logger.error(f"Ошибка извлечения твитов: {e}")
        return []

# Обработка нажатий кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    if user_id not in active_sessions:
        await query.edit_message_text(
            "❌ Браузер не активен. Используйте /open_browser"
        )
        return
    
    session = active_sessions[user_id]
    tab = session["tab"]
    step = 200
    
    try:
        if action == "extract_tweets":
            await query.edit_message_text("🔄 Извлекаю твиты...")
            
            tweets = await extract_tweets_from_page(tab)
            
            if not tweets:
                await query.edit_message_text("❌ Твиты не найдены на странице")
                return
            
            response = "📝 Твиты:\n\n"
            for i, tweet in enumerate(tweets[:5], 1):
                text = tweet.text.replace('\n', ' ').strip()
                if len(text) > 150:
                    text = text[:150] + "..."
                response += f"{i}. {text}\n\n"
            
            if len(tweets) > 5:
                response += f"И ещё {len(tweets) - 5} твитов..."
            
            await query.edit_message_text(response)
            return
        
        # Прокрутка
        cursor_x = session.get("cursor_x", 500)
        cursor_y = session.get("cursor_y", 300)
        js_code = ""
        
        if action == "up":
            cursor_y = max(0, cursor_y - step)
            js_code = f'window.scrollBy(0, -{step});'
        elif action == "down":
            cursor_y = min(1080, cursor_y + step)
            js_code = f'window.scrollBy(0, {step});'
        elif action == "left":
            cursor_x = max(0, cursor_x - step)
            js_code = f'window.scrollBy(-{step}, 0);'
        elif action == "right":
            cursor_x = min(1920, cursor_x + step)
            js_code = f'window.scrollBy({step}, 0);'
        elif action == "up_left":
            cursor_x = max(0, cursor_x - step)
            cursor_y = max(0, cursor_y - step)
            js_code = f'window.scrollBy(-{step}, -{step});'
        elif action == "up_right":
            cursor_x = min(1920, cursor_x + step)
            cursor_y = max(0, cursor_y - step)
            js_code = f'window.scrollBy({step}, -{step});'
        elif action == "down_left":
            cursor_x = max(0, cursor_x - step)
            cursor_y = min(1080, cursor_y + step)
            js_code = f'window.scrollBy(-{step}, {step});'
        elif action == "down_right":
            cursor_x = min(1920, cursor_x + step)
            cursor_y = min(1080, cursor_y + step)
            js_code = f'window.scrollBy({step}, {step});'
        elif action == "refresh":
            cursor_x = 960
            cursor_y = 540
            js_code = 'window.location.reload();'
        
        if js_code:
            await tab.execute_script(js_code)
            await asyncio.sleep(0.5)
        
        session["cursor_x"] = cursor_x
        session["cursor_y"] = cursor_y
        
        await update_screenshot(query, tab, session)
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении действия {action}: {e}")
        await query.edit_message_text(
            f"❌ Ошибка:\n\n{str(e)}"
        )

# Запуск браузера со скриншотом
async def run_browser_task():
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.headless = True
    options.start_timeout = 30
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    browser = Chrome(options=options)
    await browser.start()
    
    tab = await browser.start()
    
    logger.info("Устанавливаю куки...")
    await tab.set_cookies(X_COOKIES)
    
    logger.info("Перехожу на https://x.com...")
    await tab.go_to('https://x.com')
    await asyncio.sleep(3)
    
    cursor_x, cursor_y = 960, 540
    
    logger.info("Делаю скриншот...")
    screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
    
    return screenshot_io, browser, tab, (cursor_x, cursor_y)

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже."
        )

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("open_browser", open_browser_command))
    application.add_handler(CommandHandler("close_browser", close_browser_command))
    application.add_handler(CommandHandler("tweets", tweets_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()