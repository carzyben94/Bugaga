import os
import logging
import asyncio
import base64
import json
import re
import zipfile
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
CHROME_PATH = '/usr/bin/chromium'

agnes_client = None
if AGNES_API_KEY:
    agnes_client = AsyncOpenAI(api_key=AGNES_API_KEY, base_url="https://apihub.agnes-ai.com/v1")

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

def get_menu_text():
    return (
        "🤖 Бот для X.com\n\n"
        "📂 /savepage — сохранить страницу в ZIP\n"
        "📊 /pageinfo — информация о странице\n"
        "🔍 /analyze — AI анализ страницы\n"
        "👇 Используй кнопки ниже для управления"
    )

def get_control_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↖️", callback_data="diag_up_left"),
            InlineKeyboardButton("⬆️", callback_data="cursor_up"),
            InlineKeyboardButton("↗️", callback_data="diag_up_right"),
        ],
        [
            InlineKeyboardButton("⬅️", callback_data="cursor_left"),
            InlineKeyboardButton("🔄 Центр", callback_data="cursor_center"),
            InlineKeyboardButton("➡️", callback_data="cursor_right"),
        ],
        [
            InlineKeyboardButton("↙️", callback_data="diag_down_left"),
            InlineKeyboardButton("⬇️", callback_data="cursor_down"),
            InlineKeyboardButton("↘️", callback_data="diag_down_right"),
        ],
        [
            InlineKeyboardButton("⬆️ Скролл", callback_data="scroll_up"),
            InlineKeyboardButton("⬇️ Скролл", callback_data="scroll_down"),
        ],
        [
            InlineKeyboardButton("🔝 Наверх", callback_data="scroll_top"),
            InlineKeyboardButton("🔽 Вниз", callback_data="scroll_bottom"),
        ],
        [
            InlineKeyboardButton("📊 Extract", callback_data="extract_tweets"),
            InlineKeyboardButton("🔄 Обновить", callback_data="refresh_screen"),
        ],
        [
            InlineKeyboardButton("🖱️ Клик", callback_data="mouse_click"),
            InlineKeyboardButton("📸 Скрин", callback_data="take_screenshot"),
        ],
        [
            InlineKeyboardButton("🔵 Шаг 30", callback_data="step_30"),
            InlineKeyboardButton("🔴 Шаг 60", callback_data="step_60"),
            InlineKeyboardButton("🟢 Шаг 100", callback_data="step_100"),
        ],
        [
            InlineKeyboardButton("⚡ Eval", callback_data="do_eval"),
            InlineKeyboardButton("🔐 Вход", callback_data="do_login"),
        ],
        [
            InlineKeyboardButton("📂 Save Page", callback_data="do_savepage"),
        ],
        [
            InlineKeyboardButton("❌ Закрыть", callback_data="close_browser"),
        ],
    ])

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

async def send_or_update_menu(update, user_id, caption=None):
    if user_id not in user_browsers:
        menu_text = get_menu_text()
        if user_id in user_menu_messages:
            try:
                await update.effective_message.edit_text(menu_text)
            except:
                await update.message.reply_text(menu_text)
        else:
            msg = await update.message.reply_text(menu_text)
            user_menu_messages[user_id] = msg.message_id
        return

    img_data, x, y = await get_screenshot_with_cursor(user_id)
    
    menu_text = get_menu_text()
    if caption:
        menu_text = f"{caption}\n\n{menu_text}"
    
    cursor_obj = get_cursor(user_id)
    full_caption = f"{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor_obj.step}px"

    if user_id in user_menu_messages:
        try:
            await update.effective_message.edit_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_control_keyboard()
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать: {e}")
    
    msg = await update.message.reply_photo(
        photo=img_data,
        caption=full_caption,
        reply_markup=get_control_keyboard()
    )
    user_menu_messages[user_id] = msg.message_id

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_or_update_menu(update, update.effective_user.id)

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
        await send_or_update_menu(update, user_id, "✅ Вход выполнен!")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        try:
            await msg1.delete()
        except:
            pass
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

# ==================== КОМАНДА /savepage ====================

async def savepage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет текущую страницу в ZIP архив"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("📂 Сохраняю страницу...")
        
        filename = f'page_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        
        # Сохраняем страницу
        await tab.save_bundle(filename)
        
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Страница сохранена\n📁 Файл: {filename}\n📊 Размер: {os.path.getsize(filename) // 1024} KB"
                )
            
            os.remove(filename)
        else:
            await update.message.reply_text("❌ Не удалось сохранить страницу")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

# ==================== КОМАНДА /pageinfo ====================

async def pageinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о текущей странице"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        info = await tab.execute_script("""
            (function() {
                return {
                    url: window.location.href,
                    title: document.title,
                    tweets: document.querySelectorAll('article[data-testid="tweet"]').length,
                    testids: Array.from(document.querySelectorAll('[data-testid]'))
                        .map(el => el.getAttribute('data-testid'))
                        .filter((v,i,a) => a.indexOf(v) === i)
                        .slice(0, 20)
                };
            })()
        """, return_by_value=True)
        
        reply = f"📊 **Информация о странице:**\n\n"
        reply += f"🔗 URL: {info.get('url', 'неизвестно')}\n"
        reply += f"📝 Заголовок: {info.get('title', 'неизвестно')}\n"
        reply += f"🐦 Твитов: {info.get('tweets', 0)}\n\n"
        reply += "📋 **Доступные data-testid:**\n"
        for testid in info.get('testids', [])[:15]:
            reply += f"• `{testid}`\n"
        
        await update.message.reply_text(reply, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== КОМАНДА /analyze ====================

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI анализ структуры страницы"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    if not agnes_client:
        await update.message.reply_text("❌ Agnes AI не инициализирован")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("📊 Анализирую структуру страницы...")
        
        # Получаем HTML
        html = await tab.execute_script("""
            (function() {
                return document.documentElement.outerHTML;
            })()
        """, return_by_value=True)
        
        # Отправляем в AI
        response = await agnes_client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {"role": "system", "content": "Ты — эксперт по парсингу X.com. Проанализируй HTML и предложи селекторы для извлечения твитов."},
                {"role": "user", "content": f"""
                HTML страницы (первые 10000 символов):
                {html[:10000]}
                
                Найди селекторы для:
                1. Текст твита
                2. Имя автора
                3. Username
                4. Лайки
                5. Ретвиты
                6. Ответы
                7. Время
                
                Верни JSON с селекторами.
                """}
            ],
            max_tokens=1000,
            temperature=0.1
        )
        
        result = response.choices[0].message.content
        result = re.sub(r'```json\n?', '', result)
        result = re.sub(r'```\n?', '', result)
        result = result.strip()
        
        try:
            selectors = json.loads(result)
            
            reply = "🧠 **AI анализ структуры:**\n\n"
            for key, value in selectors.items():
                if key not in ['confidence', 'notes']:
                    reply += f"• {key}: `{value}`\n"
            
            if selectors.get('confidence'):
                reply += f"\n📊 Уверенность: {selectors['confidence'] * 100}%"
            if selectors.get('notes'):
                reply += f"\n📝 {selectors['notes']}"
            
            await update.message.reply_text(reply, parse_mode='Markdown')
            
        except json.JSONDecodeError:
            await update.message.reply_text(f"⚠️ Ошибка парсинга JSON:\n{result[:500]}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК КНОПОК ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    if action == "do_login":
        await query.message.delete()
        await login(update, context)
        return
    
    if action == "do_eval":
        await query.message.delete()
        await query.message.reply_text(
            "⚡ Введи JS код для выполнения\n\n"
            "Примеры:\n"
            "document.title\n"
            "window.scrollBy(0, 300)\n"
            "document.querySelectorAll('article').length"
        )
        context.user_data['waiting_for_eval'] = True
        return
    
    if action == "do_savepage":
        await query.message.delete()
        await savepage_command(update, context)
        return
    
    if user_id not in user_browsers:
        await query.edit_message_text("❌ Сначала нажми '🔐 Вход'")
        return
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    step = cursor.step
    
    captions = ""
    
    try:
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
            captions = "🔄 Курсор в центр"
        elif action == "step_30":
            cursor.step = 30
            captions = "🔵 Шаг 30px"
        elif action == "step_60":
            cursor.step = 60
            captions = "🔴 Шаг 60px"
        elif action == "step_100":
            cursor.step = 100
            captions = "🟢 Шаг 100px"
        elif action == "scroll_up":
            await tab.execute_script("window.scrollBy(0, -300)")
            captions = "⬆️ Скролл вверх на 300px"
        elif action == "scroll_down":
            await tab.execute_script("window.scrollBy(0, 300)")
            captions = "⬇️ Скролл вниз на 300px"
        elif action == "scroll_top":
            await tab.scroll.to_top(smooth=True)
            captions = "🔝 Наверх страницы"
        elif action == "scroll_bottom":
            await tab.scroll.to_bottom(smooth=True)
            captions = "🔽 Вниз страницы"
        elif action == "mouse_click":
            await tab.mouse.click(cursor.x, cursor.y, humanize=True)
            captions = f"🖱️ Клик по ({cursor.x}, {cursor.y})"
        elif action == "take_screenshot":
            img_data, x, y = await get_screenshot_with_cursor(user_id)
            menu_text = get_menu_text()
            full_caption = f"📸 Скриншот\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_control_keyboard()
            )
            return
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
        elif action == "refresh_screen":
            img_data, x, y = await get_screenshot_with_cursor(user_id)
            menu_text = get_menu_text()
            full_caption = f"🔄 Обновлено\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_control_keyboard()
            )
            return
        elif action == "close_browser":
            if user_id in user_browsers:
                browser, _ = user_browsers[user_id]
                await browser.close()
                del user_browsers[user_id]
                if user_id in user_menu_messages:
                    del user_menu_messages[user_id]
                await query.edit_message_text("✅ Браузер закрыт")
                await send_or_update_menu(update, user_id)
            else:
                await query.edit_message_text("❌ Браузер не открыт")
            return
        else:
            await query.edit_message_text("❌ Неизвестная команда")
            return
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
        return
    
    img_data, x, y = await get_screenshot_with_cursor(user_id)
    menu_text = get_menu_text()
    full_caption = f"{captions}\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
    
    await query.edit_message_media(
        media=InputMediaPhoto(media=img_data, caption=full_caption),
        reply_markup=get_control_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
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

            await send_or_update_menu(update, user_id, "⚡ Код выполнен")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")
        return

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("savepage", savepage_command))
    app.add_handler(CommandHandler("pageinfo", pageinfo_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()