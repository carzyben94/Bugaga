import os
import logging
import asyncio
import base64
import json
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from pydantic import BaseModel
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHROME_PATH = '/usr/bin/google-chrome'

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
user_menu_messages = {}
user_menu_state = {}  # Для отслеживания текущего меню

# ==================== МОДЕЛЬ ТВИТА ====================

class Tweet(ExtractionModel):
    text: str = Field(
        selector='div[data-testid="tweetText"]',
        default=""
    )
    author: str = Field(
        selector='div[data-testid="User-Name"] span',
        default=""
    )
    likes: str = Field(
        selector='[data-testid="like"]',
        default="0"
    )
    retweets: str = Field(
        selector='[data-testid="retweet"]',
        default="0"
    )
    replies: str = Field(
        selector='[data-testid="reply"]',
        default="0"
    )

# ==================== КУРСОР ====================

class CursorManager:
    def __init__(self):
        self.x = 500
        self.y = 300
        self.step = 30
        self.last_action = "Готов"

cursor_managers = {}

def get_cursor(user_id):
    if user_id not in cursor_managers:
        cursor_managers[user_id] = CursorManager()
    return cursor_managers[user_id]

def escape_markdown(text):
    if not text:
        return text
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# ==================== МЕНЮ ====================

def get_menu_text(user_id, status=None):
    cursor = get_cursor(user_id)
    if not status:
        status = cursor.last_action
    
    return (
        f"🤖 **X.com Controller**\n"
        f"┌─────────────────────┐\n"
        f"│ 📍 Статус: {status}\n"
        f"│ 🎯 ({cursor.x}, {cursor.y})\n"
        f"│ 📏 Шаг: {cursor.step}px\n"
        f"└─────────────────────┘\n\n"
        f"💡 **Управление:**\n"
        f"• Стрелки для навигации\n"
        f"• 🎯 центрирует курсор\n"
        f"• 🖱️ для клика"
    )

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖱️ Управление курсором", callback_data="menu_cursor")],
        [InlineKeyboardButton("📜 Скроллинг", callback_data="menu_scroll")],
        [InlineKeyboardButton("⚡ Действия", callback_data="menu_actions")],
        [InlineKeyboardButton("🔧 Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton("📊 Парсинг", callback_data="menu_parsing")],
        [InlineKeyboardButton("❌ Закрыть бота", callback_data="close_browser")],
    ])

def get_cursor_keyboard():
    """Меню управления курсором"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↖️", callback_data="diag_up_left"),
            InlineKeyboardButton("⬆️", callback_data="cursor_up"),
            InlineKeyboardButton("↗️", callback_data="diag_up_right"),
        ],
        [
            InlineKeyboardButton("⬅️", callback_data="cursor_left"),
            InlineKeyboardButton("🎯 Центр", callback_data="cursor_center"),
            InlineKeyboardButton("➡️", callback_data="cursor_right"),
        ],
        [
            InlineKeyboardButton("↙️", callback_data="diag_down_left"),
            InlineKeyboardButton("⬇️", callback_data="cursor_down"),
            InlineKeyboardButton("↘️", callback_data="diag_down_right"),
        ],
        [
            InlineKeyboardButton("🖱️ Клик", callback_data="mouse_click"),
            InlineKeyboardButton("📸 Скрин", callback_data="take_screenshot"),
        ],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="menu_main")],
    ])

def get_scroll_keyboard():
    """Меню скроллинга"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Вверх 300px", callback_data="scroll_up"),
            InlineKeyboardButton("⬇️ Вниз 300px", callback_data="scroll_down"),
        ],
        [
            InlineKeyboardButton("🏠 Наверх", callback_data="scroll_top"),
            InlineKeyboardButton("🏁 Вниз", callback_data="scroll_bottom"),
        ],
        [
            InlineKeyboardButton("⬆️ Вверх 100px", callback_data="scroll_up_small"),
            InlineKeyboardButton("⬇️ Вниз 100px", callback_data="scroll_down_small"),
        ],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="menu_main")],
    ])

def get_actions_keyboard():
    """Меню действий"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Перейти в профиль", callback_data="go_profile")],
        [InlineKeyboardButton("⚡ Выполнить JS код", callback_data="do_eval")],
        [InlineKeyboardButton("🔐 Вход в X.com", callback_data="do_login")],
        [InlineKeyboardButton("🔄 Обновить страницу", callback_data="refresh_screen")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="menu_main")],
    ])

def get_settings_keyboard():
    """Меню настроек"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 30px", callback_data="step_30"),
            InlineKeyboardButton("🔴 60px", callback_data="step_60"),
            InlineKeyboardButton("🟢 100px", callback_data="step_100"),
        ],
        [
            InlineKeyboardButton("🟣 150px", callback_data="step_150"),
            InlineKeyboardButton("⚪ 200px", callback_data="step_200"),
        ],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="menu_main")],
    ])

def get_parsing_keyboard():
    """Меню парсинга"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Извлечь твиты", callback_data="extract_tweets")],
        [InlineKeyboardButton("📊 Извлечь с прокруткой", callback_data="extract_tweets_scroll")],
        [InlineKeyboardButton("📈 Статистика страницы", callback_data="page_stats")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="menu_main")],
    ])

def get_keyboard_by_state(state: str):
    """Возвращает клавиатуру по состоянию меню"""
    keyboards = {
        "main": get_main_keyboard,
        "cursor": get_cursor_keyboard,
        "scroll": get_scroll_keyboard,
        "actions": get_actions_keyboard,
        "settings": get_settings_keyboard,
        "parsing": get_parsing_keyboard,
    }
    return keyboards.get(state, get_main_keyboard)()

# ==================== БРАУЗЕР ====================

async def get_screenshot_with_cursor(user_id):
    try:
        _, tab = user_browsers[user_id]
        cursor = get_cursor(user_id)

        try:
            await tab.execute_script("return 1")
        except:
            browser, _ = user_browsers[user_id]
            tab = await browser.new_tab()
            await tab.go_to('https://x.com')
            await asyncio.sleep(2)
            user_browsers[user_id] = (browser, tab)

        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        _, tab = user_browsers[user_id]
        await tab.refresh()
        await asyncio.sleep(3)
        screenshot_base64 = await tab.take_screenshot(as_base64=True)
    except Exception as e:
        _, tab = user_browsers[user_id]
        try:
            screenshot_base64 = await tab.execute_script("""
                (function() {
                    return document.documentElement.outerHTML;
                })()
            """, return_by_value=True)
            raise e
        except:
            raise e

    screenshot_bytes = base64.b64decode(screenshot_base64)
    image = Image.open(BytesIO(screenshot_bytes))
    draw = ImageDraw.Draw(image)
    x, y = cursor.x, cursor.y
    size = 15
    draw.line([(x - size, y), (x + size, y)], fill='red', width=3)
    draw.line([(x, y - size), (x, y + size)], fill='red', width=3)
    draw.ellipse([(x - 3, y - 3), (x + 3, y + 3)], fill='red')

    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), x, y

async def send_or_update_menu(update, user_id, caption=None, state="main"):
    """Обновляет меню с учетом состояния"""
    user_menu_state[user_id] = state
    
    if user_id not in user_browsers:
        menu_text = get_menu_text(user_id, "❌ Браузер не открыт")
        if user_id in user_menu_messages:
            try:
                await update.effective_message.edit_text(
                    menu_text,
                    reply_markup=get_keyboard_by_state(state)
                )
            except:
                await update.message.reply_text(menu_text)
        else:
            msg = await update.message.reply_text(
                menu_text,
                reply_markup=get_keyboard_by_state(state)
            )
            user_menu_messages[user_id] = msg.message_id
        return

    img_data, x, y = await get_screenshot_with_cursor(user_id)
    cursor = get_cursor(user_id)
    
    status = caption if caption else cursor.last_action
    menu_text = get_menu_text(user_id, status)

    if user_id in user_menu_messages:
        try:
            await update.effective_message.edit_media(
                media=InputMediaPhoto(media=img_data, caption=menu_text),
                reply_markup=get_keyboard_by_state(state)
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать: {e}")
    
    msg = await update.message.reply_photo(
        photo=img_data,
        caption=menu_text,
        reply_markup=get_keyboard_by_state(state)
    )
    user_menu_messages[user_id] = msg.message_id

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_menu_state[user_id] = "main"
    await send_or_update_menu(update, user_id, "👋 Бот запущен", "main")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        msg1 = await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
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
        
        try:
            await msg1.delete()
        except:
            pass
        
        await update.message.reply_text("✅ Вход выполнен! Размер окна: 1024x768")
        await send_or_update_menu(update, user_id, "✅ Вход выполнен", "main")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        try:
            await msg1.delete()
        except:
            pass
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def go_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, username=None):
    user_id = update.effective_user.id
    
    if not username:
        context.user_data['waiting_for_profile'] = True
        await update.message.reply_text(
            "👤 **Введи username профиля**\n\n"
            "Например: `elonmusk`\n"
            "Или с @: `@billgates`\n\n"
            "Просто напиши имя в чат",
            parse_mode='Markdown'
        )
        return
    
    if username.startswith('@'):
        username = username[1:]
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала нажми '🔐 Вход'")
        return
    
    try:
        _, tab = user_browsers[user_id]
        profile_url = f"https://x.com/{username}"
        
        await update.message.reply_text(f"🔄 Перехожу в профиль @{username}...")
        await tab.go_to(profile_url)
        await asyncio.sleep(3)
        
        await send_or_update_menu(
            update, 
            user_id, 
            f"✅ Профиль @{username}",
            user_menu_state.get(user_id, "main")
        )
        
    except Exception as e:
        logger.error(f"Ошибка перехода в профиль: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК КНОПОК ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    logger.info(f"Нажата кнопка: {action} от пользователя {user_id}")
    
    # === Обработка переходов между меню ===
    if action == "menu_main":
        await send_or_update_menu(update, user_id, "📋 Главное меню", "main")
        return
    
    if action == "menu_cursor":
        await send_or_update_menu(update, user_id, "🖱️ Управление курсором", "cursor")
        return
    
    if action == "menu_scroll":
        await send_or_update_menu(update, user_id, "📜 Скроллинг", "scroll")
        return
    
    if action == "menu_actions":
        await send_or_update_menu(update, user_id, "⚡ Действия", "actions")
        return
    
    if action == "menu_settings":
        await send_or_update_menu(update, user_id, "🔧 Настройки", "settings")
        return
    
    if action == "menu_parsing":
        await send_or_update_menu(update, user_id, "📊 Парсинг", "parsing")
        return
    
    # === Специальные действия ===
    if action == "go_profile":
        context.user_data['waiting_for_profile'] = True
        await query.message.reply_text(
            "👤 **Введи username профиля**\n\n"
            "Например: `elonmusk`\n"
            "Или с @: `@billgates`\n\n"
            "Просто напиши имя в чат",
            parse_mode='Markdown'
        )
        await query.answer("👤 Введи username")
        return
    
    if action == "do_eval":
        context.user_data['waiting_for_eval'] = True
        await query.message.reply_text(
            "⚡ **Введи JS код для выполнения**\n\n"
            "Примеры:\n"
            "`document.title`\n"
            "`window.scrollBy(0, 300)`\n"
            "`document.querySelectorAll('article').length`",
            parse_mode='Markdown'
        )
        await query.answer("⚡ Введи код")
        return
    
    if action == "do_login":
        await query.message.delete()
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat_id = chat_id
            async def reply_text(self, *args, **kwargs):
                return await update.effective_message.reply_text(*args, **kwargs)
            async def delete(self):
                pass
        
        fake_update = update
        fake_update.message = FakeMessage(update.effective_chat.id)
        await login(fake_update, context)
        return
    
    # === Проверка браузера ===
    if user_id not in user_browsers:
        await query.edit_message_text("❌ Сначала нажми '🔐 Вход'")
        return
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    step = cursor.step
    current_state = user_menu_state.get(user_id, "main")
    
    captions = ""
    
    try:
        # === Движение курсора ===
        if action == "cursor_up":
            cursor.y -= step
            captions = "⬆️ Курсор вверх"
        elif action == "cursor_down":
            cursor.y += step
            captions = "⬇️ Курсор вниз"
        elif action == "cursor_left":
            cursor.x -= step
            captions = "⬅️ Курсор влево"
        elif action == "cursor_right":
            cursor.x += step
            captions = "➡️ Курсор вправо"
        elif action == "diag_up_left":
            cursor.x -= step
            cursor.y -= step
            captions = "↖️ Диагональ вверх-влево"
        elif action == "diag_up_right":
            cursor.x += step
            cursor.y -= step
            captions = "↗️ Диагональ вверх-вправо"
        elif action == "diag_down_left":
            cursor.x -= step
            cursor.y += step
            captions = "↙️ Диагональ вниз-влево"
        elif action == "diag_down_right":
            cursor.x += step
            cursor.y += step
            captions = "↘️ Диагональ вниз-вправо"
        elif action == "cursor_center":
            viewport = await tab.execute_script("return { width: window.innerWidth, height: window.innerHeight }")
            cursor.x = viewport['width'] // 2
            cursor.y = viewport['height'] // 2
            captions = "🎯 Курсор в центр"
        
        # === Настройки ===
        elif action == "step_30":
            cursor.step = 30
            captions = "🔵 Шаг 30px"
        elif action == "step_60":
            cursor.step = 60
            captions = "🔴 Шаг 60px"
        elif action == "step_100":
            cursor.step = 100
            captions = "🟢 Шаг 100px"
        elif action == "step_150":
            cursor.step = 150
            captions = "🟣 Шаг 150px"
        elif action == "step_200":
            cursor.step = 200
            captions = "⚪ Шаг 200px"
        
        # === Скроллинг ===
        elif action == "scroll_up":
            await tab.execute_script("window.scrollBy(0, -300)")
            captions = "⬆️ Скролл вверх на 300px"
        elif action == "scroll_down":
            await tab.execute_script("window.scrollBy(0, 300)")
            captions = "⬇️ Скролл вниз на 300px"
        elif action == "scroll_up_small":
            await tab.execute_script("window.scrollBy(0, -100)")
            captions = "⬆️ Скролл вверх на 100px"
        elif action == "scroll_down_small":
            await tab.execute_script("window.scrollBy(0, 100)")
            captions = "⬇️ Скролл вниз на 100px"
        elif action == "scroll_top":
            await tab.scroll.to_top(smooth=True)
            captions = "🏠 Наверх страницы"
        elif action == "scroll_bottom":
            await tab.scroll.to_bottom(smooth=True)
            captions = "🏁 Вниз страницы"
        
        # === Действия ===
        elif action == "mouse_click":
            await tab.mouse.click(cursor.x, cursor.y, humanize=True)
            captions = f"🖱️ Клик по ({cursor.x}, {cursor.y})"
        
        elif action == "take_screenshot":
            img_data, x, y = await get_screenshot_with_cursor(user_id)
            menu_text = get_menu_text(user_id, "📸 Скриншот")
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_data, caption=menu_text),
                reply_markup=get_keyboard_by_state(current_state)
            )
            return
        
        elif action == "refresh_screen":
            img_data, x, y = await get_screenshot_with_cursor(user_id)
            menu_text = get_menu_text(user_id, "🔄 Обновлено")
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_data, caption=menu_text),
                reply_markup=get_keyboard_by_state(current_state)
            )
            return
        
        # === Парсинг ===
        elif action == "extract_tweets":
            try:
                await query.message.reply_text("📊 Извлекаю твиты...")
                
                for _ in range(3):
                    await tab.execute_script("window.scrollBy(0, 600)")
                    await asyncio.sleep(1.5)
                
                tweets = await asyncio.wait_for(
                    tab.extract_all(
                        Tweet,
                        scope='article[data-testid="tweet"]',
                        timeout=12,
                        limit=30
                    ),
                    timeout=18.0
                )

                if not tweets or len(tweets) == 0:
                    await query.message.reply_text("😕 Твиты не найдены на странице")
                    return

                reply = f"📊 **Найдено {len(tweets)} твитов:**\n\n"
                parts = []
                current_part = reply
                
                for i, tweet in enumerate(tweets, 1):
                    text = tweet.text
                    text = re.sub(r'https?://t\.co/\w+', '', text)
                    text = re.sub(r'https?://\S+', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    
                    author = escape_markdown(tweet.author) if tweet.author else "Неизвестно"
                    if text:
                        text = escape_markdown(text)
                        if len(text) > 200:
                            text = text[:200] + '...'
                    
                    tweet_text = f"**{i}.** "
                    tweet_text += f"{author}\n"
                    
                    if text:
                        tweet_text += f"📝 {text}\n"
                    
                    tweet_text += f"❤️ {tweet.likes} | 🔁 {tweet.retweets} | 💬 {tweet.replies}\n\n"
                    
                    if len(current_part) + len(tweet_text) > 4000:
                        parts.append(current_part)
                        current_part = ""
                    
                    current_part += tweet_text

                if current_part:
                    parts.append(current_part)

                for part in parts:
                    await query.message.reply_text(part, parse_mode='Markdown')
                
                await query.answer("✅ Твиты выгружены")
                
            except asyncio.TimeoutError:
                await query.message.reply_text("⏰ Поиск твитов занял слишком много времени. Попробуй обновить страницу.")
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
        
        elif action == "extract_tweets_scroll":
            try:
                await query.message.reply_text("📊 Извлекаю твиты с прокруткой...")
                
                # Прокручиваем 5 раз для загрузки больше контента
                for i in range(5):
                    await tab.execute_script("window.scrollBy(0, 800)")
                    await asyncio.sleep(2)
                
                tweets = await asyncio.wait_for(
                    tab.extract_all(
                        Tweet,
                        scope='article[data-testid="tweet"]',
                        timeout=15,
                        limit=50
                    ),
                    timeout=20.0
                )

                if not tweets:
                    await query.message.reply_text("😕 Твиты не найдены")
                    return

                reply = f"📊 **Найдено {len(tweets)} твитов:**\n\n"
                # ... аналогично предыдущему парсингу ...
                await query.message.reply_text(f"✅ Извлечено {len(tweets)} твитов")
                
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
        
        elif action == "page_stats":
            try:
                stats = await tab.execute_script("""
                    return {
                        title: document.title,
                        url: window.location.href,
                        tweets: document.querySelectorAll('article[data-testid="tweet"]').length,
                        images: document.querySelectorAll('img').length,
                        links: document.querySelectorAll('a[href]').length
                    }
                """)
                
                stats_text = (
                    f"📈 **Статистика страницы**\n\n"
                    f"📝 Заголовок: {stats.get('title', 'N/A')}\n"
                    f"🔗 URL: {stats.get('url', 'N/A')}\n"
                    f"📊 Твитов: {stats.get('tweets', 0)}\n"
                    f"🖼️ Изображений: {stats.get('images', 0)}\n"
                    f"🔗 Ссылок: {stats.get('links', 0)}"
                )
                await query.message.reply_text(stats_text, parse_mode='Markdown')
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
        
        elif action == "close_browser":
            if user_id in user_browsers:
                browser, _ = user_browsers[user_id]
                await browser.close()
                del user_browsers[user_id]
                if user_id in user_menu_messages:
                    del user_menu_messages[user_id]
                await query.edit_message_text("✅ Браузер закрыт")
                await send_or_update_menu(update, user_id, "❌ Браузер закрыт", "main")
            else:
                await query.edit_message_text("❌ Браузер не открыт")
            return
        else:
            await query.edit_message_text("❌ Неизвестная команда")
            return
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
        return
    
    # Обновляем последнее действие
    cursor.last_action = captions
    
    # Показываем обновленный экран
    img_data, x, y = await get_screenshot_with_cursor(user_id)
    menu_text = get_menu_text(user_id, captions)
    
    await query.edit_message_media(
        media=InputMediaPhoto(media=img_data, caption=menu_text),
        reply_markup=get_keyboard_by_state(current_state)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Обработка ввода username для профиля
    if context.user_data.get('waiting_for_profile'):
        logger.info(f"Получен username для профиля: {text}")
        context.user_data['waiting_for_profile'] = False
        
        if text.startswith('/'):
            await update.message.reply_text("❌ Это команда, а не username")
            return
        
        await go_to_profile(update, context, username=text)
        return
    
    # Обработка eval
    if context.user_data.get('waiting_for_eval'):
        context.user_data['waiting_for_eval'] = False
        
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала нажми '🔐 Вход'")
            return
        
        _, tab = user_browsers[user_id]
        
        try:
            raw = await tab.execute_script(text, return_by_value=True)
            if isinstance(raw, dict) and 'result' in raw:
                raw = raw['result']
            if isinstance(raw, dict) and 'value' in raw:
                result = raw['value']
            else:
                result = raw

            if isinstance(result, str):
                await update.message.reply_text(f"✅ Результат:\n\n{result[:4096]}")
            elif isinstance(result, (list, dict)):
                await update.message.reply_text(f"✅ Результат:\n\n{json.dumps(result, ensure_ascii=False, indent=2)[:4096]}")
            else:
                await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:4096]}")

            current_state = user_menu_state.get(user_id, "main")
            await send_or_update_menu(update, user_id, "⚡ Код выполнен", current_state)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")
        return
    
    # Если просто текст - отправляем в чат
    await update.message.reply_text("Используй кнопки для управления ботом")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("go", go_to_profile))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()