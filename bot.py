import os
import logging
import asyncio
import base64
import json
import re
import random
from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

from openai import AsyncOpenAI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

agnes_client = None
if AGNES_API_KEY:
    agnes_client = AsyncOpenAI(
        api_key=AGNES_API_KEY,
        base_url="https://apihub.agnes-ai.com/v1"
    )

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

# ==================== КУРСОР ====================

class CursorManager:
    def __init__(self):
        self.x = 500
        self.y = 300
        self.step = 10
        self.mode = 1
    
    def move(self, dx, dy):
        self.x += dx * self.step
        self.y += dy * self.step
        return self.x, self.y
    
    def set_mode(self, mode):
        if mode == 1:
            self.step = 10
            self.mode = 1
        elif mode == 2:
            self.step = 40
            self.mode = 2
    
    def get_mode(self):
        return self.mode, self.step
    
    def get_position(self):
        return self.x, self.y

cursor_managers = {}

def get_cursor(user_id):
    if user_id not in cursor_managers:
        cursor_managers[user_id] = CursorManager()
    return cursor_managers[user_id]

# ==================== РИСОВАНИЕ КУРСОРА ====================

def draw_cursor_on_screenshot(screenshot_bytes, cursor_x, cursor_y):
    try:
        image = Image.open(BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(image)
        
        size = 15
        draw.line([(cursor_x - size, cursor_y), (cursor_x + size, cursor_y)], fill='red', width=3)
        draw.line([(cursor_x, cursor_y - size), (cursor_x, cursor_y + size)], fill='red', width=3)
        draw.ellipse([(cursor_x - 3, cursor_y - 3), (cursor_x + 3, cursor_y + 3)], fill='red')
        
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
    except:
        return screenshot_bytes

# ==================== КНОПКИ ДЖОЙСТИКА ====================

def get_joystick_keyboard(user_id=None):
    keyboard = [
        [
            InlineKeyboardButton("⬆️", callback_data="up"),
        ],
        [
            InlineKeyboardButton("⬅️", callback_data="left"),
            InlineKeyboardButton("🔄", callback_data="reset"),
            InlineKeyboardButton("➡️", callback_data="right"),
        ],
        [
            InlineKeyboardButton("⬇️", callback_data="down"),
        ],
        [
            InlineKeyboardButton("🖱️ Клик", callback_data="click"),
            InlineKeyboardButton("📸 Скрин", callback_data="screenshot"),
        ],
        [
            InlineKeyboardButton("🏠 Home", callback_data="go_home"),
            InlineKeyboardButton("🔍 Explore", callback_data="go_explore"),
            InlineKeyboardButton("👤 Профиль", callback_data="go_profile"),
        ],
        [
            InlineKeyboardButton("🔎 Поиск", callback_data="go_search"),
        ],
        [
            InlineKeyboardButton("👁️ Что видишь?", callback_data="ai_what_see"),
            InlineKeyboardButton("🧠 AI Найти", callback_data="ai_find"),
        ],
        [
            InlineKeyboardButton("🧠 AI Клик", callback_data="ai_click"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="refresh"),
        ],
        [
            InlineKeyboardButton("🔵 Шаг 10", callback_data="mode_1"),
            InlineKeyboardButton("🔴 Шаг 40", callback_data="mode_2"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ОТПРАВКА СКРИНА + КНОПОК ====================

async def send_screen_with_buttons(update, user_id, caption="🎮 Джойстик X.com"):
    if user_id not in user_browsers:
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.edit_message_text("❌ Сначала выполни /login")
        else:
            await update.message.reply_text("❌ Сначала выполни /login")
        return None
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    x, y = cursor.get_position()
    mode, step = cursor.get_mode()
    
    try:
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        image_with_cursor = draw_cursor_on_screenshot(screenshot_bytes, x, y)
        
        caption_text = f"{caption}\n🖱️ Курсор: ({x}, {y}) | Шаг: {step}px"
        
        if isinstance(update, Update) and update.callback_query:
            try:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(
                        media=image_with_cursor,
                        caption=caption_text
                    ),
                    reply_markup=get_joystick_keyboard(user_id)
                )
            except Exception as e:
                try:
                    await update.callback_query.message.delete()
                except:
                    pass
                await update.effective_message.reply_photo(
                    photo=image_with_cursor,
                    caption=caption_text,
                    reply_markup=get_joystick_keyboard(user_id)
                )
        else:
            await update.message.reply_photo(
                photo=image_with_cursor,
                caption=caption_text,
                reply_markup=get_joystick_keyboard(user_id)
            )
        
        return image_with_cursor
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        error_text = f"❌ Ошибка: {str(e)[:300]}"
        if isinstance(update, Update) and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    error_text,
                    reply_markup=get_joystick_keyboard()
                )
            except:
                try:
                    await update.callback_query.message.delete()
                except:
                    pass
                await update.effective_message.reply_text(
                    error_text,
                    reply_markup=get_joystick_keyboard()
                )
        else:
            await update.message.reply_text(
                error_text,
                reply_markup=get_joystick_keyboard()
            )
        return None

# ==================== МЕНЮ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 Бот для X.com\n\n"
        "🎮 Джойстик\n"
        "/joystick — Открыть джойстик\n\n"
        "🔐 Авторизация\n"
        "/login X.com\n"
        "/close Закрыть браузер\n\n"
        "📸 Скриншот\n"
        "/screen Скриншот\n\n"
        "🔍 Поиск\n"
        "/search Запрос\n\n"
        "📸 Фото\n"
        "/getbaby Случайное фото\n\n"
        "⌨️ Ввод\n"
        "/type <текст> — Ввести текст\n\n"
        "🧠 AI-зрение\n"
        "/ai_find <что> — Найти элемент через AI\n"
        "/ai_click <что> — Найти и кликнуть через AI\n"
        "/click_num <номер> — Кликнуть по элементу из списка\n\n"
        "⚡ JavaScript\n"
        "/eval <js> — Выполнить JavaScript\n"
        "/ai Любая команда (умный eval)"
    )
    await update.message.reply_text(menu)

# ==================== ЛОГИН ====================

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
        
        cursor = get_cursor(user_id)
        try:
            viewport = await tab.execute_script("return { width: window.innerWidth, height: window.innerHeight }")
            cursor.x = viewport['width'] // 2
            cursor.y = viewport['height'] // 2
        except:
            cursor.x, cursor.y = 500, 300
        
        await update.message.reply_text("✅ Вход выполнен!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

# ==================== ЗАКРЫТЬ БРАУЗЕР ====================

async def close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Браузер уже закрыт или не был открыт")
            return
        
        browser, tab = user_browsers[user_id]
        
        await update.message.reply_text("🔄 Закрываю браузер...")
        
        await browser.close()
        
        del user_browsers[user_id]
        
        if user_id in cursor_managers:
            del cursor_managers[user_id]
        
        await update.message.reply_text("✅ Браузер закрыт! Сессия очищена.")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== СКРИНШОТ ====================

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("📸 Делаю скриншот...")
        
        _, tab = user_browsers[user_id]
        cursor = get_cursor(user_id)
        x, y = cursor.get_position()
        
        await asyncio.sleep(1)
        
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        image_with_cursor = draw_cursor_on_screenshot(screenshot_bytes, x, y)
        
        await update.message.reply_photo(
            photo=image_with_cursor,
            caption=f"🖼️ Скриншот\n🖱️ Курсор: ({x}, {y})"
        )
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Скриншот занимает слишком много времени. Попробуй ещё раз.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== ДЖОЙСТИК ====================

async def joystick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_browsers:
        await send_screen_with_buttons(update, user_id, "🎮 Джойстик X.com")
    else:
        await update.message.reply_text(
            "❌ Сначала выполни /login",
            reply_markup=get_joystick_keyboard()
        )

# ==================== МОДЕЛИ ====================

class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )

class TweetPhoto(ExtractionModel):
    photo: str = Field(
        selector='img[src*="media"]',
        attribute='src',
        default=""
    )

# ==================== ФУНКЦИИ ====================

def fix_text(text):
    text = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', text)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([А-ЯЁ])([А-ЯЁ][а-яё])', r'\1 \2', text)
    text = re.sub(r'([«»"\'])([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'([А-Яа-яA-Za-z])([«»"\'])', r'\1 \2', text)
    text = re.sub(r'([—–])([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'([А-Яа-яA-Za-z])([—–])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ==================== ПАРСИНГ ОТВЕТА AI ====================

def parse_ai_response(text):
    """Парсит ответ AI и извлекает элементы с координатами"""
    elements = []
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Ищем координаты (X, Y)
        coord_match = re.search(r'\((\d+),\s*(\d+)\)', line)
        if coord_match:
            x = int(coord_match.group(1))
            y = int(coord_match.group(2))
            
            # Извлекаем название (все что до координат)
            name = re.sub(r'\s*\([\d,\s]+\)\s*$', '', line).strip()
            name = re.sub(r'^[^\w\sа-яА-Я]+\s*', '', name)
            name = re.sub(r'\s*[→➡️]\s*$', '', name)
            
            if name:
                elements.append({
                    'id': len(elements) + 1,
                    'name': name,
                    'x': x,
                    'y': y
                })
    
    return elements

# ==================== ОБРАБОТЧИК ДЖОЙСТИКА ====================

async def joystick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    if user_id not in user_browsers:
        await query.edit_message_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    
    try:
        if action == "up":
            cursor.move(0, -1)
            await send_screen_with_buttons(update, user_id, "⬆️ Вверх")
        
        elif action == "down":
            cursor.move(0, 1)
            await send_screen_with_buttons(update, user_id, "⬇️ Вниз")
        
        elif action == "left":
            cursor.move(-1, 0)
            await send_screen_with_buttons(update, user_id, "⬅️ Влево")
        
        elif action == "right":
            cursor.move(1, 0)
            await send_screen_with_buttons(update, user_id, "➡️ Вправо")
        
        elif action == "reset":
            try:
                viewport = await tab.execute_script("return { width: window.innerWidth, height: window.innerHeight }")
                cursor.x = viewport['width'] // 2
                cursor.y = viewport['height'] // 2
            except:
                cursor.x, cursor.y = 500, 300
            await send_screen_with_buttons(update, user_id, "🔄 Курсор сброшен")
        
        elif action == "click":
            try:
                await tab.mouse.click(cursor.x, cursor.y, humanize=True)
                await send_screen_with_buttons(update, user_id, f"🖱️ Клик по ({cursor.x}, {cursor.y})")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        elif action == "screenshot":
            await send_screen_with_buttons(update, user_id, "📸 Скриншот")
        
        # ===== НАВИГАЦИЯ =====
        elif action == "go_home":
            try:
                await tab.mouse.click(60, 80, humanize=True)
                await asyncio.sleep(1)
                await send_screen_with_buttons(update, user_id, "🏠 Перешёл на Home")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        elif action == "go_explore":
            try:
                await tab.mouse.click(60, 140, humanize=True)
                await asyncio.sleep(1)
                await send_screen_with_buttons(update, user_id, "🔍 Перешёл на Explore")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        elif action == "go_profile":
            try:
                await tab.mouse.click(60, 380, humanize=True)
                await asyncio.sleep(1)
                await send_screen_with_buttons(update, user_id, "👤 Перешёл в Профиль")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        # ===== ПОИСК =====
        elif action == "go_search":
            try:
                await tab.mouse.click(60, 140, humanize=True)
                await asyncio.sleep(1)
                await tab.mouse.click(380, 40, humanize=True)
                await asyncio.sleep(0.5)
                await send_screen_with_buttons(update, user_id, "🔎 Поле поиска активно\nВведите текст через /type")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        # ===== AI ЧТО ВИДИШЬ? =====
        elif action == "ai_what_see":
            try:
                await query.message.delete()
                await query.message.reply_text("👁️ Анализирую страницу...")
                
                screenshot_base64 = await tab.take_screenshot(as_base64=True)
                
                response = await asyncio.wait_for(
                    agnes_client.chat.completions.create(
                        model="agnes-2.0-flash",
                        messages=[
                            {"role": "system", "content": "Ты — эксперт по анализу интерфейсов. Определяй ТОЧНЫЙ ЦЕНТР каждого элемента."},
                            {"role": "user", "content": [
                                {"type": "text", "text": """
                                Перечисли что видишь на скриншоте X.com.
                                
                                Формат (каждый элемент с новой строки):
                                Название → (X, Y)
                                
                                Где X, Y - это ТОЧНЫЙ ЦЕНТР элемента.
                                Центр = (левая_граница + правая_граница) / 2, (верхняя + нижняя) / 2
                                
                                Например:
                                Логотип X → (70, 60)
                                Главная → (70, 190)
                                Поиск → (70, 280)
                                Уведомления → (70, 370)
                                Сообщения → (70, 460)
                                Профиль → (70, 550)
                                Написать твит → (500, 700)
                                
                                Найди все основные элементы на странице.
                                Только список. Без лишнего текста.
                                Без JSON.
                                """},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                            ]}
                        ],
                        max_tokens=500,
                        temperature=0.1
                    ),
                    timeout=25.0
                )
                
                result = response.choices[0].message.content
                
                # Парсим ответ AI
                elements = parse_ai_response(result)
                
                if elements:
                    context.user_data['ai_elements'] = elements
                    
                    reply = "👁️ Что вижу на странице (центры элементов):\n\n"
                    for el in elements:
                        reply += f"{el['name']} → ({el['x']}, {el['y']})\n"
                    
                    reply += f"\n📊 Всего: {len(elements)} элементов"
                    reply += "\n💡 /click_num <номер> - кликнуть"
                    
                    await query.message.reply_text(reply)
                else:
                    # Если не удалось распарсить - показываем как есть
                    await query.message.reply_text(f"👁️ Что вижу на странице:\n\n{result}")
                    
            except asyncio.TimeoutError:
                await query.message.reply_text("⏰ AI не ответил за 25 секунд. Попробуй ещё раз.")
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        
        elif action == "ai_find":
            try:
                await query.message.delete()
                await query.message.reply_text("📸 Делаю скриншот и анализирую...")
                
                screenshot_base64 = await tab.take_screenshot(as_base64=True)
                
                response = await agnes_client.chat.completions.create(
                    model="agnes-2.0-flash",
                    messages=[
                        {"role": "system", "content": "Ты — эксперт по анализу скриншотов. Верни ТОЛЬКО JSON с координатами."},
                        {"role": "user", "content": [
                            {"type": "text", "text": """
                            Проанализируй скриншот X.com.
                            Найди: кнопку лайка, ретвита, поле поиска, кнопку твита.
                            Верни ТОЛЬКО JSON: {"like": [x, y], "retweet": [x, y], "search": [x, y], "tweet": [x, y]}
                            """},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                        ]}
                    ],
                    max_tokens=500
                )
                
                coords = json.loads(response.choices[0].message.content)
                
                reply = "🧠 AI нашёл элементы:\n\n"
                for name, coord in coords.items():
                    reply += f"• {name}: ({coord[0]}, {coord[1]})\n"
                
                await query.message.reply_text(reply)
                
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка AI: {str(e)[:200]}")
        
        elif action == "ai_click":
            try:
                await query.message.delete()
                await query.message.reply_text("📸 Делаю скриншот...")
                
                screenshot_base64 = await tab.take_screenshot(as_base64=True)
                
                await query.message.reply_text("🧠 Ищу кнопку лайка...")
                
                response = await agnes_client.chat.completions.create(
                    model="agnes-2.0-flash",
                    messages=[
                        {"role": "system", "content": "Ты — эксперт по анализу скриншотов. Верни ТОЛЬКО два числа: x и y координаты центра кнопки, разделённые запятой."},
                        {"role": "user", "content": [
                            {"type": "text", "text": "Найди на этом скриншоте кнопку лайка (❤️). Верни координаты центра кнопки в формате x, y."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                        ]}
                    ],
                    max_tokens=100
                )
                
                result = response.choices[0].message.content.strip()
                
                # Очищаем результат от лишних символов
                result = re.sub(r'[\[\]\(\)"\']', '', result)
                result = re.sub(r'координаты[:]?\s*', '', result, flags=re.IGNORECASE)
                result = result.strip()
                
                # Извлекаем все числа
                numbers = re.findall(r'\d+', result)
                
                if len(numbers) >= 2:
                    x, y = int(numbers[0]), int(numbers[1])
                    
                    cursor = get_cursor(user_id)
                    cursor.x, cursor.y = x, y
                    
                    await tab.mouse.click(x, y, humanize=True)
                    await send_screen_with_buttons(update, user_id, f"🧠 AI клик по лайку! ({x}, {y})")
                else:
                    await query.message.reply_text(f"❌ Не удалось распознать координаты: {result}")
                
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        
        elif action == "refresh":
            await query.edit_message_text("🔄 Обновляю страницу...")
            await tab.refresh()
            await asyncio.sleep(2)
            await send_screen_with_buttons(update, user_id, "✅ Страница обновлена")
        
        elif action == "mode_1":
            cursor.set_mode(1)
            await send_screen_with_buttons(update, user_id, "🔵 Режим: Шаг 10px")
        
        elif action == "mode_2":
            cursor.set_mode(2)
            await send_screen_with_buttons(update, user_id, "🔴 Режим: Шаг 40px")
        
        else:
            await send_screen_with_buttons(update, user_id, "❌ Неизвестная команда")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:300]}")

# ==================== /click_num ====================

async def click_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кликает по элементу по номеру из списка"""
    if not context.args:
        await update.message.reply_text("❌ Укажи номер элемента\nПример: /click_num 1")
        return
    
    try:
        num = int(context.args[0])
        user_id = update.effective_user.id
        
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        if 'ai_elements' not in context.user_data:
            await update.message.reply_text("❌ Сначала нажми '👁️ Что видишь?'")
            return
        
        elements = context.user_data['ai_elements']
        
        target = None
        for el in elements:
            if el.get('id') == num:
                target = el
                break
        
        if not target:
            await update.message.reply_text(f"❌ Элемент с номером {num} не найден")
            return
        
        x, y = target.get('x'), target.get('y')
        name = target.get('name', 'элемент')
        
        _, tab = user_browsers[user_id]
        cursor = get_cursor(user_id)
        cursor.x, cursor.y = x, y
        
        await tab.mouse.click(x, y, humanize=True)
        await update.message.reply_text(f"✅ Клик по элементу {num}: {name} → ({x}, {y})")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== КОМАНДЫ ====================

async def type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи текст для ввода\nПример: /type python")
        return
    
    text = ' '.join(context.args)
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await tab.type(text, humanize=True)
        await update.message.reply_text(f"✅ Введён текст: {text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи запрос\nПример: /search python")
        return
    
    query = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text(f"🔍 Ищу: {query}")
        
        _, tab = user_browsers[user_id]
        
        await tab.go_to(f'https://x.com/search?q={query}&src=typed_query')
        await asyncio.sleep(3)
        
        tweets = await tab.extract_all(
            Tweet,
            scope='article[data-testid="tweet"]',
            timeout=10
        )
        
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🔍 Результаты поиска: {query}"
        )
        
        if tweets:
            count = len(tweets)
            reply = f"📊 Найдено {count} твитов\n\n"
            
            for i, tweet in enumerate(tweets[:20], 1):
                text = fix_text(tweet.text)
                if len(text) > 600:
                    text = text[:600] + '...'
                reply += f"{i}. {text}\n\n"
            
            if count > 20:
                reply += f"... и ещё {count - 20} твитов"
            
            if len(reply) > 4096:
                parts = []
                current = ""
                for line in reply.split('\n'):
                    if len(current) + len(line) + 1 > 4000:
                        parts.append(current)
                        current = ""
                    current += line + '\n'
                if current:
                    parts.append(current)
                
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(reply)
        else:
            await update.message.reply_text("😕 Твиты не найдены")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def getbaby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    PROFILES = [
        'babesdailyyy',
        'beautyshowcase',
        'EuGirlsDom'
    ]
    
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("📸 Ищу фото...")
        
        _, tab = user_browsers[user_id]
        
        random.shuffle(PROFILES)
        
        all_photos = []
        
        for username in PROFILES:
            try:
                await tab.go_to(f'https://x.com/{username}')
                await asyncio.sleep(3)
                
                photos = await tab.extract_all(
                    TweetPhoto,
                    scope='article[data-testid="tweet"]',
                    timeout=5
                )
                
                for photo_obj in photos[:10]:
                    if photo_obj.photo:
                        all_photos.append(photo_obj.photo)
                
                if not photos:
                    photos_js = await tab.execute_script("""
                        (function() {
                            const images = document.querySelectorAll('img[src*="media"]');
                            const result = [];
                            images.forEach(img => {
                                const src = img.src || img.getAttribute('src');
                                if (src && src.includes('media')) {
                                    result.push(src);
                                }
                            });
                            return result;
                        })()
                    """)
                    for photo in photos_js[:10]:
                        all_photos.append(photo)
                
                if len(all_photos) >= 15:
                    break
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке {username}: {e}")
                continue
        
        if all_photos:
            random.shuffle(all_photos)
            selected = random.choice(all_photos)
            
            await update.message.reply_photo(photo=selected)
            
            await update.message.reply_text(f"📊 Найдено {len(all_photos)} фото")
            
        else:
            await update.message.reply_text("😕 Фото не найдены")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

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
        
        if isinstance(result, dict):
            if 'result' in result and isinstance(result['result'], dict):
                if 'value' in result['result']:
                    result = result['result']['value']
            elif 'value' in result:
                result = result['value']
        
        if isinstance(result, (list, dict)):
            result = json.dumps(result, ensure_ascii=False, indent=2)
        
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text(
            "❌ Agnes API ключ не найден.\n"
            "Добавь AGNES_API_KEY в переменные окружения."
        )
        return
    
    if not agnes_client:
        await update.message.reply_text(
            "❌ Ошибка инициализации Agnes AI клиента."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 Умный /eval\n\n"
            "Просто скажи что хочешь сделать:\n"
            "/ai найди твиты про войну\n"
            "/ai лайкни первый твит\n"
            "/ai сколько подписчиков\n"
            "/ai фото красивых девушек\n"
            "/ai прокрути вниз\n"
            "/ai статистика"
        )
        return
    
    command = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        await update.message.reply_text("🧠 Генерирую код через Agnes AI...")
        
        _, tab = user_browsers[user_id]
        
        try:
            current_url = await tab.current_url
        except:
            current_url = ''
        
        if 'x.com' not in current_url and 'twitter.com' not in current_url:
            await update.message.reply_text("🔄 Перехожу на X.com...")
            await tab.go_to('https://x.com')
            await asyncio.sleep(3)
        
        page_info = await tab.execute_script("""
            (function() {
                const ids = {};
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const id = el.dataset.testid;
                    if (id) {
                        ids[id] = (ids[id] || 0) + 1;
                    }
                });
                return {
                    url: window.location.href,
                    title: document.title,
                    testids: ids,
                    tweet_count: document.querySelectorAll('article[data-testid="tweet"]').length
                };
            })()
        """)
        
        if len(page_info.get('testids', {})) == 0:
            await update.message.reply_text(
                "❌ Не найдено элементов на странице.\n"
                "Попробуй выполнить /login заново"
            )
            return
        
        prompt = f"""
        Ты — агент по автоматизации X.com (Twitter).
        
        СТРАНИЦА:
        URL: {page_info.get('url', 'неизвестно')}
        Твитов на странице: {page_info.get('tweet_count', 0)}
        Доступные data-testid: {json.dumps(page_info.get('testids', {}), ensure_ascii=False)}
        
        ЗАДАЧА: {command}
        
        Сгенерируй ТОЛЬКО JavaScript код для выполнения этой задачи.
        - Если нужно вернуть данные — используй return
        - Если нужно выполнить действие — просто выполни код
        - Используй доступные data-testid из контекста
        - НЕ используй комментарии
        - Верни ТОЛЬКО код, без пояснений и markdown.
        """
        
        response = await asyncio.wait_for(
            agnes_client.chat.completions.create(
                model="agnes-2.0-flash",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по JavaScript. Отвечай ТОЛЬКО кодом. НИКАКИХ комментариев."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            ),
            timeout=20.0
        )
        
        js_code = response.choices[0].message.content
        
        js_code = re.sub(r'```javascript\n?', '', js_code)
        js_code = re.sub(r'```json\n?', '', js_code)
        js_code = re.sub(r'```\n?', '', js_code)
        
        lines = js_code.split('\n')
        clean_lines = []
        for line in lines:
            if line.strip().startswith('//'):
                continue
            if line.strip().startswith('/*') or line.strip().startswith('*'):
                continue
            if line.strip() == '':
                continue
            clean_lines.append(line)
        js_code = '\n'.join(clean_lines).strip()
        
        if not js_code or len(js_code) < 5:
            await update.message.reply_text(
                "⚠️ Не удалось сгенерировать код.\n"
                "Попробуй переформулировать команду."
            )
            return
        
        await update.message.reply_text(
            f"⚡ Выполняю код:\n"
            f"{js_code[:400]}\n"
            f"(показано первых 400 символов)"
        )
        
        try:
            result = await asyncio.wait_for(
                tab.execute_script(js_code),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("⚠️ Выполнение кода заняло слишком много времени.")
            return
        
        if isinstance(result, (list, dict)):
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            result_str = str(result)
        
        if len(result_str) > 1000:
            result_str = result_str[:1000] + '...'
        
        if not result_str or result_str == '""' or result_str == "''" or result_str == '[]':
            await update.message.reply_text("⚠️ Результат пустой.")
        else:
            await update.message.reply_text(f"📊 Результат:\n{result_str[:500]}")
        
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Agnes AI не ответил вовремя. Попробуй позже.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК ОШИБОК ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== MAIN ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("close", close_browser))
    application.add_handler(CommandHandler("joystick", joystick))
    application.add_handler(CommandHandler("screen", screen))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("getbaby", getbaby))
    application.add_handler(CommandHandler("type", type_text))
    application.add_handler(CommandHandler("eval", evaluate_js))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("click_num", click_num))
    
    application.add_handler(CallbackQueryHandler(joystick_callback))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()