import os
import asyncio
import logging
import base64
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions

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

# Хранилище активных браузеров
active_sessions = {}

# Клавиатура управления с диагоналями
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
            InlineKeyboardButton("❌ Закрыть", callback_data="close_browser")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/open_browser - Открыть браузер\n"
        "/close_browser - Закрыть браузер"
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
        screenshot, browser, tab = await run_browser_task()
        
        active_sessions[user_id] = {
            "browser": browser,
            "tab": tab,
            "scroll_x": 0,
            "scroll_y": 0
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

# Обновление скриншота
async def update_screenshot(update: Update, tab, session):
    # Делаем скриншот
    screenshot_base64 = await tab.take_screenshot(
        path=None,
        as_base64=True,
        beyond_viewport=False
    )
    
    screenshot_bytes = base64.b64decode(screenshot_base64)
    screenshot_io = BytesIO(screenshot_bytes)
    screenshot_io.seek(0)
    
    # Обновляем сообщение
    await update.callback_query.edit_message_media(
        media=(
            screenshot_io,
            "photo",
            caption="✅ Браузер открыт и авторизован!"
        ),
        reply_markup=get_control_keyboard()
    )

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
    step = 200  # Шаг прокрутки
    
    try:
        # Выполняем действие
        if action == "up":
            await tab.scroll_by(0, -step)
            session["scroll_y"] -= step
        elif action == "down":
            await tab.scroll_by(0, step)
            session["scroll_y"] += step
        elif action == "left":
            await tab.scroll_by(-step, 0)
            session["scroll_x"] -= step
        elif action == "right":
            await tab.scroll_by(step, 0)
            session["scroll_x"] += step
        elif action == "up_left":
            await tab.scroll_by(-step, -step)
            session["scroll_x"] -= step
            session["scroll_y"] -= step
        elif action == "up_right":
            await tab.scroll_by(step, -step)
            session["scroll_x"] += step
            session["scroll_y"] -= step
        elif action == "down_left":
            await tab.scroll_by(-step, step)
            session["scroll_x"] -= step
            session["scroll_y"] += step
        elif action == "down_right":
            await tab.scroll_by(step, step)
            session["scroll_x"] += step
            session["scroll_y"] += step
        elif action == "refresh":
            # Обновляем страницу
            await tab.go_to('https://x.com/home')
            await asyncio.sleep(1)
            session["scroll_x"] = 0
            session["scroll_y"] = 0
        elif action == "close_browser":
            await session["browser"].stop()
            del active_sessions[user_id]
            await query.edit_message_text("✅ Браузер успешно закрыт!")
            return
        
        # Небольшая пауза для применения скролла
        await asyncio.sleep(0.5)
        
        # Обновляем скриншот
        await update_screenshot(update, tab, session)
        
        logger.info(f"Пользователь {user_id}: {action} -> позиция ({session['scroll_x']}, {session['scroll_y']})")
        
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
    
    logger.info("Делаю скриншот...")
    screenshot_base64 = await tab.take_screenshot(
        path=None,
        as_base64=True,
        beyond_viewport=False
    )
    
    screenshot_bytes = base64.b64decode(screenshot_base64)
    screenshot_io = BytesIO(screenshot_bytes)
    screenshot_io.seek(0)
    
    return screenshot_io, browser, tab

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
    application.add_handler(CommandHandler("open_browser", open_browser_command))
    application.add_handler(CommandHandler("close_browser", close_browser_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()