import os
import asyncio
import logging
import base64
from io import BytesIO
from datetime import datetime
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field
from PIL import Image, ImageDraw
from pydantic import BaseModel
import validex

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Дополнительный логгер для файла
file_logger = logging.getLogger('file_logger')
file_logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler('bot_debug.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
file_logger.addHandler(file_handler)

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

# Модель для обычного извлечения
class Tweet(ExtractionModel):
    text: str = Field(selector='div[data-testid="tweetText"]', default='')
    author: Optional[str] = Field(selector='div[data-testid="User-Name"] a', default='')
    likes: Optional[str] = Field(selector='button[data-testid="like"] span', default='0')
    retweets: Optional[str] = Field(selector='button[data-testid="retweet"] span', default='0')

# Модель для ValidEx
class TweetData(BaseModel):
    text: str

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

# Команда /logs
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /logs от пользователя {user_id}")
    
    status_msg = await update.message.reply_text("📊 Собираю логи...")
    
    try:
        log_file = "bot_debug.log"
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            system_info = f"""
=== СИСТЕМНАЯ ИНФОРМАЦИЯ ===
Время запроса: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Пользователь: {user_id}
Активных сессий: {len(active_sessions)}
Размер лога: {len(log_content)} символов

=== ЛОГИ БОТА ===
{log_content}
"""
            
            log_io = BytesIO(system_info.encode('utf-8'))
            log_io.name = f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            await status_msg.delete()
            
            await update.message.reply_document(
                document=log_io,
                caption=f"📋 Логи бота за {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            file_logger.info(f"Логи отправлены пользователю {user_id}")
        else:
            await status_msg.edit_text("❌ Файл логов не найден")
            
    except Exception as e:
        file_logger.error(f"Ошибка при отправке логов: {e}")
        await status_msg.edit_text(f"❌ Ошибка при отправке логов:\n\n{str(e)}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /start от пользователя {user_id}")
    
    await update.message.reply_text(
        "/open_browser - Открыть браузер\n"
        "/close_browser - Закрыть браузер\n"
        "/tweets - Извлечь твиты\n"
        "/search <запрос> - Поиск по Twitter\n"
        "/p <username> - Перейти в профиль\n"
        "/validex - Извлечь через ValidEx\n"
        "/logs - Отправить файл с логами"
    )

# Команда /open_browser
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /open_browser от пользователя {user_id}")
    
    if user_id in active_sessions:
        await update.message.reply_text(
            "⚠️ У вас уже есть активный браузер.\n"
            "Используйте /close_browser чтобы закрыть его."
        )
        return
    
    status_msg = await update.message.reply_text("🔄 Запускаю браузер, подождите...")
    
    try:
        file_logger.debug(f"Запуск браузера для пользователя {user_id}")
        screenshot, browser, tab, cursor_pos = await run_browser_task()
        
        active_sessions[user_id] = {
            "browser": browser,
            "tab": tab,
            "cursor_x": cursor_pos[0],
            "cursor_y": cursor_pos[1]
        }
        
        file_logger.info(f"Браузер успешно запущен для пользователя {user_id}")
        
        await status_msg.delete()
        
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ Браузер открыт и авторизован!",
            reply_markup=get_control_keyboard()
        )
    except Exception as e:
        file_logger.error(f"Ошибка запуска браузера для {user_id}: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при запуске браузера:\n\n{str(e)}"
        )

# КОМАНДА /VALIDEX
async def validex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /validex от пользователя {user_id}")
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ Нет активного браузера. Используйте /open_browser"
        )
        return
    
    status_msg = await update.message.reply_text("🧠 Извлекаю через ValidEx...")
    
    try:
        session = active_sessions[user_id]
        tab = session["tab"]
        
        html = await tab.execute_script('return document.documentElement.outerHTML;')
        
        if isinstance(html, dict):
            html = str(html)
            file_logger.warning(f"HTML получен как словарь, конвертирован в строку")
        
        if len(html) > 50000:
            html = html[:50000]
            file_logger.debug("HTML обрезан до 50000 символов")
        
        app = validex.App()
        app.add(html)
        
        tweets = app.extract_all(TweetData)
        
        if not tweets:
            await status_msg.edit_text("❌ ValidEx не нашел твитов")
            return
        
        tweets = tweets[:5]
        
        response = "🧠 ValidEx извлек данные:\n\n"
        for i, tweet in enumerate(tweets, 1):
            if hasattr(tweet, 'text'):
                text = tweet.text[:200] + "..." if len(tweet.text) > 200 else tweet.text
                response += f"{i}. {text}\n\n"
            elif isinstance(tweet, dict) and 'text' in tweet:
                text = tweet['text'][:200] + "..." if len(tweet['text']) > 200 else tweet['text']
                response += f"{i}. {text}\n\n"
            else:
                response += f"{i}. {str(tweet)[:200]}...\n\n"
        
        file_logger.info(f"ValidEx извлек {len(tweets)} твитов")
        
        await status_msg.delete()
        await update.message.reply_text(response)
        
    except Exception as e:
        file_logger.error(f"Ошибка ValidEx: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка ValidEx:\n\n{str(e)}"
        )

# Команда /p - переход в профиль
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = ' '.join(context.args)
    
    file_logger.info(f"Команда /p от {user_id}, username: {username}")
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ Нет активного браузера. Используйте /open_browser"
        )
        return
    
    if not username:
        await update.message.reply_text(
            "❌ Укажите username.\n"
            "Пример: /p elonmusk"
        )
        return
    
    username = username.replace('@', '')
    
    status_msg = await update.message.reply_text(f"👤 Перехожу в профиль @{username}...")
    
    try:
        session = active_sessions[user_id]
        tab = session["tab"]
        
        profile_url = f"https://x.com/{username}"
        file_logger.debug(f"Переход в профиль: {profile_url}")
        
        await tab.go_to(profile_url)
        await asyncio.sleep(5)
        
        tweets = await extract_tweets_from_page(tab, timeout=10)
        
        response = f"👤 Профиль @{username}\n\n"
        
        if tweets:
            valid_tweets = [t for t in tweets if t.text and t.text.strip()]
            
            if valid_tweets:
                response += f"📝 Последние твиты:\n\n"
                for i, tweet in enumerate(valid_tweets[:5], 1):
                    text = tweet.text.replace('\n', ' ').strip()
                    if len(text) > 200:
                        text = text[:200] + "..."
                    response += f"{i}. {text}\n"
                    if tweet.author:
                        response += f"   👤 {tweet.author}"
                    if tweet.likes:
                        response += f"  ❤️ {tweet.likes}"
                    if tweet.retweets:
                        response += f"  🔄 {tweet.retweets}"
                    response += "\n\n"
                
                if len(valid_tweets) > 5:
                    response += f"И ещё {len(valid_tweets) - 5} твитов..."
            else:
                response += "❌ Твиты не найдены"
        else:
            response += "❌ Твиты не найдены"
        
        file_logger.info(f"Извлечено {len(tweets)} твитов из профиля @{username}")
        
        await status_msg.delete()
        await update.message.reply_text(response)
        
        cursor_x = session.get("cursor_x", 960)
        cursor_y = session.get("cursor_y", 540)
        screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
        
        await update.message.reply_photo(
            photo=screenshot_io,
            caption=f"👤 Профиль @{username}",
            reply_markup=get_control_keyboard()
        )
        
    except Exception as e:
        file_logger.error(f"Ошибка перехода в профиль @{username}: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при переходе в профиль:\n\n{str(e)}"
        )

# Команда /search
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query_text = ' '.join(context.args)
    
    file_logger.info(f"Команда /search от {user_id}, запрос: {query_text}")
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ Нет активного браузера. Используйте /open_browser"
        )
        return
    
    if not query_text:
        await update.message.reply_text(
            "❌ Укажите поисковый запрос.\n"
            "Пример: /search Python"
        )
        return
    
    status_msg = await update.message.reply_text(f"🔍 Ищу: {query_text}...")
    
    try:
        session = active_sessions[user_id]
        tab = session["tab"]
        
        search_url = f"https://x.com/search?q={query_text.replace(' ', '%20')}&src=typed_query"
        file_logger.debug(f"Поиск: {search_url}")
        
        await tab.go_to(search_url)
        await asyncio.sleep(5)
        
        tweets = await extract_tweets_from_page(tab, timeout=10)
        
        if not tweets:
            await status_msg.edit_text(f"❌ По запросу '{query_text}' ничего не найдено")
            return
        
        valid_tweets = [t for t in tweets if t.text and t.text.strip()]
        
        if not valid_tweets:
            await status_msg.edit_text(f"❌ По запросу '{query_text}' нет текстовых твитов")
            return
        
        response = f"🔍 Результаты поиска: {query_text}\n\n"
        for i, tweet in enumerate(valid_tweets[:5], 1):
            text = tweet.text.replace('\n', ' ').strip()
            if len(text) > 200:
                text = text[:200] + "..."
            response += f"{i}. {text}\n"
            if tweet.author:
                response += f"   👤 {tweet.author}"
            if tweet.likes:
                response += f"  ❤️ {tweet.likes}"
            if tweet.retweets:
                response += f"  🔄 {tweet.retweets}"
            response += "\n\n"
        
        if len(valid_tweets) > 5:
            response += f"И ещё {len(valid_tweets) - 5} твитов..."
        
        file_logger.info(f"Найдено {len(valid_tweets)} твитов по запросу '{query_text}'")
        
        await status_msg.delete()
        await update.message.reply_text(response)
        
        cursor_x = session.get("cursor_x", 960)
        cursor_y = session.get("cursor_y", 540)
        screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
        
        await update.message.reply_photo(
            photo=screenshot_io,
            caption="🔍 Результаты поиска на странице",
            reply_markup=get_control_keyboard()
        )
        
    except Exception as e:
        file_logger.error(f"Ошибка поиска '{query_text}': {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при поиске:\n\n{str(e)}"
        )

# Команда /tweets
async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /tweets от пользователя {user_id}")
    
    if user_id not in active_sessions:
        await update.message.reply_text(
            "❌ Нет активного браузера. Используйте /open_browser"
        )
        return
    
    status_msg = await update.message.reply_text("🔄 Извлекаю твиты...")
    
    try:
        session = active_sessions[user_id]
        tab = session["tab"]
        
        tweets = await extract_tweets_from_page(tab, timeout=10)
        
        if not tweets:
            await status_msg.edit_text("❌ Твиты не найдены на странице")
            return
        
        valid_tweets = [t for t in tweets if t.text and t.text.strip()]
        
        if not valid_tweets:
            await status_msg.edit_text("❌ Твиты не найдены (пустые)")
            return
        
        response = "📝 Твиты:\n\n"
        for i, tweet in enumerate(valid_tweets[:10], 1):
            text = tweet.text.replace('\n', ' ').strip()
            if len(text) > 200:
                text = text[:200] + "..."
            response += f"{i}. {text}\n"
            if tweet.author:
                response += f"   👤 {tweet.author}"
            if tweet.likes:
                response += f"  ❤️ {tweet.likes}"
            if tweet.retweets:
                response += f"  🔄 {tweet.retweets}"
            response += "\n\n"
        
        if len(valid_tweets) > 10:
            response += f"И ещё {len(valid_tweets) - 10} твитов..."
        
        file_logger.info(f"Извлечено {len(valid_tweets)} твитов")
        
        await status_msg.delete()
        await update.message.reply_text(response)
        
    except Exception as e:
        file_logger.error(f"Ошибка извлечения твитов: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка при извлечении твитов:\n\n{str(e)}"
        )

# Команда /close_browser
async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file_logger.info(f"Команда /close_browser от пользователя {user_id}")
    
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
        
        file_logger.info(f"Браузер закрыт для пользователя {user_id}")
        
        await update.message.reply_text("✅ Браузер успешно закрыт!")
    except Exception as e:
        file_logger.error(f"Ошибка закрытия браузера для {user_id}: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при закрытии браузера:\n\n{str(e)}"
        )

# Получение скриншота с курсором
async def get_screenshot_with_cursor(tab, cursor_x, cursor_y):
    file_logger.debug(f"Создание скриншота с курсором ({cursor_x}, {cursor_y})")
    
    # Исправленный метод получения скриншота
    screenshot_base64 = await tab.take_screenshot(
        path=None,
        as_base64=True,
        beyond_viewport=False
    )
    
    screenshot_bytes = base64.b64decode(screenshot_base64)
    image_with_cursor = draw_cursor_on_image(screenshot_bytes, cursor_x, cursor_y)
    
    return image_with_cursor

# Обновление скриншота
async def update_screenshot(query, tab, session):
    cursor_x = session.get("cursor_x", 500)
    cursor_y = session.get("cursor_y", 300)
    
    file_logger.debug(f"Обновление скриншота для пользователя {query.from_user.id}")
    
    screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
    
    media = InputMediaPhoto(
        media=screenshot_io,
        caption="✅ Браузер открыт и авторизован!"
    )
    
    await query.edit_message_media(
        media=media,
        reply_markup=get_control_keyboard()
    )

# Извлечение твитов
async def extract_tweets_from_page(tab, timeout=10):
    try:
        file_logger.debug(f"Начинаю извлечение твитов (таймаут: {timeout}с)")
        
        await asyncio.sleep(3)
        
        tweets = await tab.extract_all(
            Tweet,
            scope='article[data-testid="tweet"]',
            timeout=timeout
        )
        
        file_logger.debug(f"Извлечено {len(tweets)} твитов")
        return tweets
    except Exception as e:
        file_logger.error(f"Ошибка извлечения твитов: {e}")
        return []

# Обработка нажатий кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    action = query.data
    
    file_logger.info(f"Кнопка {action} от пользователя {user_id}")
    
    await query.answer()
    
    if user_id not in active_sessions:
        await query.edit_message_text(
            "❌ Браузер не активен. Используйте /open_browser"
        )
        return
    
    session = active_sessions[user_id]
    tab = session["tab"]
    step = 200
    
    try:
        cursor_x = session.get("cursor_x", 500)
        cursor_y = session.get("cursor_y", 300)
        js_code = ""
        
        file_logger.debug(f"Действие: {action}, позиция курсора: ({cursor_x}, {cursor_y})")
        
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
            file_logger.debug(f"Выполняю JS: {js_code}")
            await tab.execute_script(js_code)
            await asyncio.sleep(0.5)
        
        session["cursor_x"] = cursor_x
        session["cursor_y"] = cursor_y
        
        await update_screenshot(query, tab, session)
        
    except Exception as e:
        file_logger.error(f"Ошибка выполнения действия {action}: {e}")
        await query.edit_message_text(
            f"❌ Ошибка:\n\n{str(e)}"
        )

# Запуск браузера со скриншотом
async def run_browser_task():
    file_logger.debug("Запуск браузера")
    
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.headless = True
    options.start_timeout = 30
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    file_logger.debug("Создание экземпляра Chrome")
    browser = Chrome(options=options)
    await browser.start()
    
    file_logger.debug("Создание вкладки")
    tab = await browser.start()
    
    file_logger.info("Устанавливаю куки...")
    await tab.set_cookies(X_COOKIES)
    
    file_logger.info("Перехожу на https://x.com...")
    await tab.go_to('https://x.com')
    await asyncio.sleep(5)
    
    cursor_x, cursor_y = 960, 540
    
    file_logger.debug("Делаю скриншот...")
    screenshot_io = await get_screenshot_with_cursor(tab, cursor_x, cursor_y)
    
    file_logger.info("Браузер успешно запущен")
    return screenshot_io, browser, tab, (cursor_x, cursor_y)

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update and update.effective_user else "unknown"
    error = context.error
    
    file_logger.error(f"Глобальная ошибка для пользователя {user_id}: {error}")
    
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
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("p", profile_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("validex", validex_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    file_logger.info("🚀 Бот запущен и готов к работе!")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()