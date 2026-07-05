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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

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

# ==================== МОДЕЛЬ ТВИТА ДЛЯ EXTRACTOR ====================

class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default="[текст не найден]"
    )

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
            InlineKeyboardButton("📍 Клик по координатам", callback_data="click_coords"),
        ],
        [
            InlineKeyboardButton("📊 Extract", callback_data="extract"),
            InlineKeyboardButton("🔍 Найти твиты", callback_data="find_tweets"),
        ],
        [
            InlineKeyboardButton("🔍 Поиск (Extractor)", callback_data="search_extractor"),
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
        "📍 Координаты\n"
        "/click <x> <y> — Клик по координатам"
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
                await send_screen_with_buttons(update, user_id, "🔎 Поле поиска активно")
            except Exception as e:
                await send_screen_with_buttons(update, user_id, f"❌ Ошибка: {str(e)[:100]}")
        
        # ===== КЛИК ПО КООРДИНАТАМ =====
        elif action == "click_coords":
            try:
                await query.message.delete()
                await query.message.reply_text(
                    "📍 Введи координаты в чат в формате: X Y\n"
                    "Пример: 520 310\n"
                    "Или /click 520 310"
                )
                context.user_data['waiting_for_coords'] = True
                
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        
        # ===== EXTRACT - ИЗВЛЕЧЬ ДАННЫЕ ПОД КУРСОРОМ =====
        elif action == "extract":
            try:
                await query.message.delete()
                
                x, y = cursor.get_position()
                
                await query.message.reply_text(f"📊 Извлекаю данные под курсором ({x}, {y})...")
                
                result = await tab.execute_script(f"""
                    (function() {{
                        const el = document.elementFromPoint({x}, {y});
                        if (!el) return null;
                        
                        const data = {{
                            tag: el.tagName,
                            text: el.textContent?.trim().slice(0, 200) || '',
                            testid: el.getAttribute('data-testid') || '',
                            href: el.href || '',
                            src: el.src || '',
                            alt: el.alt || '',
                            aria_label: el.getAttribute('aria-label') || '',
                            role: el.getAttribute('role') || '',
                            coords: {{ x: {x}, y: {y} }}
                        }};
                        
                        const tweet = el.closest('article[data-testid="tweet"]');
                        if (tweet) {{
                            const textEl = tweet.querySelector('div[data-testid="tweetText"]');
                            data.tweet_text = textEl ? textEl.textContent.trim() : '';
                            
                            const authorEl = tweet.querySelector('div[data-testid="User-Name"]');
                            if (authorEl) {{
                                const spans = authorEl.querySelectorAll('span');
                                data.author = spans.length > 0 ? spans[0].textContent.trim() : '';
                                data.username = spans.length > 1 ? spans[1].textContent.trim() : '';
                            }}
                            
                            const timeEl = tweet.querySelector('time');
                            data.time = timeEl ? timeEl.getAttribute('datetime') : '';
                            
                            const linkEl = tweet.querySelector('a[href*="/status/"]');
                            data.url = linkEl ? linkEl.href : '';
                        }}
                        
                        return data;
                    }})()
                """)
                
                if result and isinstance(result, dict):
                    reply = f"📊 Данные под курсором ({x}, {y}):\n\n"
                    for key, value in result.items():
                        if value and key != 'coords':
                            if key in ['tweet_text', 'text']:
                                reply += f"📝 {key}: {str(value)[:150]}...\n"
                            elif key in ['url', 'href', 'src']:
                                reply += f"🔗 {key}: {str(value)[:100]}\n"
                            else:
                                reply += f"• {key}: {value}\n"
                    
                    await query.message.reply_text(reply)
                else:
                    await query.message.reply_text(f"❌ Нет элемента по координатам ({x}, {y})")
                    
            except Exception as e:
                logger.error(f"Ошибка extract: {e}")
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        
        # ===== НАЙТИ ТВИТЫ (JAVASCRIPT) =====
        elif action == "find_tweets":
            try:
                await query.message.delete()
                await query.message.reply_text("🔍 Ищу твиты на странице...")
                
                _, tab = user_browsers[user_id]
                
                tweets = await tab.execute_script("""
                    (function() {
                        const tweets = document.querySelectorAll('article[data-testid="tweet"]');
                        const result = [];
                        
                        tweets.forEach((tweet, index) => {
                            const data = {};
                            data.id = index + 1;
                            
                            const textEl = tweet.querySelector('div[data-testid="tweetText"]');
                            data.text = textEl ? textEl.textContent.trim() : '';
                            
                            const authorEl = tweet.querySelector('div[data-testid="User-Name"]');
                            if (authorEl) {
                                const spans = authorEl.querySelectorAll('span');
                                data.author = spans.length > 0 ? spans[0].textContent.trim() : '';
                                data.username = spans.length > 1 ? spans[1].textContent.trim() : '';
                            }
                            
                            const timeEl = tweet.querySelector('time');
                            data.time = timeEl ? timeEl.getAttribute('datetime') : '';
                            
                            const stats = {};
                            const statItems = tweet.querySelectorAll('[data-testid$="-count"]');
                            statItems.forEach(el => {
                                const testid = el.getAttribute('data-testid');
                                if (testid) {
                                    const count = el.textContent.trim();
                                    if (testid.includes('reply')) stats.replies = count;
                                    else if (testid.includes('retweet')) stats.retweets = count;
                                    else if (testid.includes('like')) stats.likes = count;
                                    else if (testid.includes('view')) stats.views = count;
                                }
                            });
                            data.stats = stats;
                            
                            const rect = tweet.getBoundingClientRect();
                            data.coords = {
                                x: Math.round(rect.left + rect.width / 2),
                                y: Math.round(rect.top + rect.height / 2)
                            };
                            
                            const buttons = {};
                            ['like', 'retweet', 'reply'].forEach(name => {
                                const btn = tweet.querySelector(`[data-testid="${name}"]`);
                                if (btn) {
                                    const r = btn.getBoundingClientRect();
                                    buttons[name] = {
                                        x: Math.round(r.left + r.width / 2),
                                        y: Math.round(r.top + r.height / 2)
                                    };
                                }
                            });
                            data.buttons = buttons;
                            
                            result.push(data);
                        });
                        
                        return result.slice(0, 10);
                    })()
                """)
                
                if tweets and len(tweets) > 0:
                    reply = f"🔍 Найдено {len(tweets)} твитов:\n\n"
                    
                    for t in tweets:
                        reply += f"**{t.get('id')}. {t.get('author', 'Неизвестно')}**"
                        if t.get('username'):
                            reply += f" (@{t['username']})"
                        reply += "\n"
                        
                        text = t.get('text', '')
                        if text:
                            if len(text) > 120:
                                text = text[:120] + '...'
                            reply += f"📝 {text}\n"
                        
                        stats = t.get('stats', {})
                        if stats:
                            parts = []
                            if stats.get('likes'): parts.append(f"❤️ {stats['likes']}")
                            if stats.get('retweets'): parts.append(f"🔁 {stats['retweets']}")
                            if stats.get('replies'): parts.append(f"💬 {stats['replies']}")
                            if parts:
                                reply += f"📊 {' | '.join(parts)}\n"
                        
                        coords = t.get('coords', {})
                        if coords:
                            reply += f"📍 ({coords.get('x', '?')}, {coords.get('y', '?')})\n"
                        
                        buttons = t.get('buttons', {})
                        if buttons:
                            cmd = []
                            if buttons.get('like'):
                                cmd.append(f"❤️ /click {buttons['like']['x']} {buttons['like']['y']}")
                            if buttons.get('retweet'):
                                cmd.append(f"🔁 /click {buttons['retweet']['x']} {buttons['retweet']['y']}")
                            if buttons.get('reply'):
                                cmd.append(f"💬 /click {buttons['reply']['x']} {buttons['reply']['y']}")
                            if cmd:
                                reply += f"💡 {' | '.join(cmd)}\n"
                        
                        reply += "\n"
                    
                    await query.message.reply_text(reply, parse_mode='Markdown')
                else:
                    await query.message.reply_text("😕 Не найдено твитов")
                    
            except Exception as e:
                logger.error(f"Ошибка find_tweets: {e}")
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
        
        # ===== ПОИСК ТВИТОВ ЧЕРЕЗ PYDOLL EXTRACTOR =====
        elif action == "search_extractor":
            try:
                await query.message.delete()
                await query.message.reply_text("🔍 Ищу твиты через Pydoll Extractor...")
                
                _, tab = user_browsers[user_id]
                
                try:
                    tweets = await asyncio.wait_for(
                        tab.extract_all(
                            Tweet,
                            scope='article[data-testid="tweet"]',
                            timeout=15
                        ),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    await query.message.reply_text(
                        "⏰ Поиск твитов через Extractor занял слишком много времени.\n\n"
                        "Попробуй использовать '🔍 Найти твиты' (JavaScript) - это быстрее!"
                    )
                    return
                except Exception as e:
                    await query.message.reply_text(
                        f"❌ Ошибка Extractor: {str(e)[:200]}\n\n"
                        "Попробуй использовать '🔍 Найти твиты' (JavaScript)"
                    )
                    return
                
                screenshot_base64 = await tab.take_screenshot(as_base64=True)
                screenshot_bytes = base64.b64decode(screenshot_base64)
                
                if tweets and len(tweets) > 0:
                    await query.message.reply_photo(
                        photo=screenshot_bytes,
                        caption=f"🔍 Найдено {len(tweets)} твитов (Extractor)"
                    )
                    
                    reply = f"📊 Найдено {len(tweets)} твитов:\n\n"
                    for i, tweet in enumerate(tweets[:20], 1):
                        text = fix_text(tweet.text)
                        if len(text) > 200:
                            text = text[:200] + '...'
                        reply += f"{i}. {text}\n\n"
                    
                    if len(reply) > 4000:
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
                            await query.message.reply_text(part)
                    else:
                        await query.message.reply_text(reply)
                else:
                    await query.message.reply_text("😕 Твиты не найдены")
                    
            except Exception as e:
                logger.error(f"Ошибка search_extractor: {e}")
                await query.message.reply_text(
                    f"❌ Ошибка: {str(e)[:200]}\n\n"
                    "💡 Рекомендую использовать '🔍 Найти твиты' - это быстрее и надежнее!"
                )
        
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

# ==================== КОМАНДА /click ====================

async def click_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клик по координатам"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Укажи координаты\n"
            "Пример: /click 520 310"
        )
        return
    
    try:
        x = int(context.args[0])
        y = int(context.args[1])
        
        user_id = update.effective_user.id
        
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        cursor = get_cursor(user_id)
        cursor.x, cursor.y = x, y
        
        await tab.mouse.click(x, y, humanize=True)
        await update.message.reply_text(f"✅ Клик по координатам: ({x}, {y})")
        
        await send_screen_with_buttons(update, user_id, f"📍 Клик по ({x}, {y})")
        
    except ValueError:
        await update.message.reply_text("❌ Введи два числа через пробел\nПример: /click 520 310")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== КОМАНДА /cancel ====================

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущее ожидание"""
    context.user_data['waiting_for_coords'] = False
    await update.message.reply_text("✅ Ожидание отменено")

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Если ждем координаты
    if context.user_data.get('waiting_for_coords'):
        try:
            parts = text.split()
            if len(parts) >= 2:
                x = int(parts[0])
                y = int(parts[1])
                
                if user_id not in user_browsers:
                    await update.message.reply_text("❌ Сначала выполни /login")
                    context.user_data['waiting_for_coords'] = False
                    return
                
                _, tab = user_browsers[user_id]
                cursor = get_cursor(user_id)
                cursor.x, cursor.y = x, y
                
                await tab.mouse.click(x, y, humanize=True)
                await update.message.reply_text(f"✅ Клик по координатам: ({x}, {y})")
                
                await send_screen_with_buttons(update, user_id, f"📍 Клик по ({x}, {y})")
                
                context.user_data['waiting_for_coords'] = False
            else:
                await update.message.reply_text(
                    "❌ Введи два числа через пробел\n"
                    "Пример: 520 310\n"
                    "Или /cancel чтобы отменить"
                )
        except ValueError:
            await update.message.reply_text("❌ Введи два числа через пробел\nПример: 520 310")
        return

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
    application.add_handler(CommandHandler("click", click_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    application.add_handler(CallbackQueryHandler(joystick_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()