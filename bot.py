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

# ==================== НАСТРОЙКИ ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
CHROME_PATH = '/usr/bin/google-chrome'  # ИЗМЕНИТЕ ПОД СВОЙ ПУТЬ

agnes_client = None
if AGNES_API_KEY:
    agnes_client = AsyncOpenAI(api_key=AGNES_API_KEY, base_url="https://apihub.agnes-ai.com/v1")

# ==================== КУКИ ДЛЯ X.COM ====================
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

# ==================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ====================
user_browsers = {}  # user_id -> (browser, tab)
user_menu_messages = {}  # user_id -> message_id
cursor_managers = {}  # user_id -> CursorManager
user_modes = {}  # user_id -> 'x' or 'krea'

# ==================== МОДЕЛЬ ТВИТА ====================
class Tweet(ExtractionModel):
    text: str = Field(selector='div[data-testid="tweetText"]', default="")
    author: str = Field(selector='div[data-testid="User-Name"] span', default="")
    likes: str = Field(selector='[data-testid="like"]', default="0")
    retweets: str = Field(selector='[data-testid="retweet"]', default="0")
    replies: str = Field(selector='[data-testid="reply"]', default="0")

# ==================== КУРСОР ====================
class CursorManager:
    def __init__(self):
        self.x = 500
        self.y = 300
        self.step = 30

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

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_x_menu_text():
    return (
        "🐦 **X.com Бот**\n\n"
        "📂 /savepage — сохранить страницу в ZIP\n"
        "📊 /pageinfo — информация о странице\n"
        "🔍 /analyze — AI анализ страницы\n"
        "🎨 /krea_menu — переключиться на Krea.ai"
    )

def get_krea_menu_text():
    return (
        "🎨 **Krea.ai Редактор**\n\n"
        "🔍 /explore_krea — исследовать DOM\n"
        "🧪 /test_krea — тест селекторов\n"
        "📤 /krea_upload — загрузить фото\n"
        "📝 /krea_prompt — ввести промт\n"
        "🤖 /krea_model — выбрать модель\n"
        "🚀 /krea_generate — запустить генерацию\n"
        "📥 /krea_download — скачать результат\n"
        "🐦 /x_menu — переключиться на X.com"
    )

def get_x_keyboard():
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

def get_krea_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Upload", callback_data="krea_upload"),
            InlineKeyboardButton("📝 Промт", callback_data="krea_prompt"),
        ],
        [
            InlineKeyboardButton("🤖 Модель", callback_data="krea_model"),
            InlineKeyboardButton("🚀 Generate", callback_data="krea_generate"),
        ],
        [
            InlineKeyboardButton("📥 Download", callback_data="krea_download"),
            InlineKeyboardButton("🔄 Обновить", callback_data="krea_refresh"),
        ],
        [
            InlineKeyboardButton("🔍 Найти элементы", callback_data="krea_explore"),
            InlineKeyboardButton("🧪 Тест", callback_data="krea_test"),
        ],
        [
            InlineKeyboardButton("📸 Скрин", callback_data="krea_screenshot"),
            InlineKeyboardButton("❌ Закрыть", callback_data="krea_close"),
        ],
        [
            InlineKeyboardButton("🐦 X.com", callback_data="switch_to_x"),
        ],
    ])

# ==================== ФУНКЦИИ ДЛЯ СКРИНШОТОВ ====================
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
        menu_text = get_x_menu_text()
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
    
    menu_text = get_x_menu_text()
    if caption:
        menu_text = f"{caption}\n\n{menu_text}"
    
    cursor_obj = get_cursor(user_id)
    full_caption = f"{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor_obj.step}px"

    if user_id in user_menu_messages:
        try:
            await update.effective_message.edit_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_x_keyboard()
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать: {e}")
    
    msg = await update.message.reply_photo(
        photo=img_data,
        caption=full_caption,
        reply_markup=get_x_keyboard()
    )
    user_menu_messages[user_id] = msg.message_id

# ==================== X.COM КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_modes[user_id] = 'x'
    await send_or_update_menu(update, user_id)

async def x_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_modes[user_id] = 'x'
    await send_or_update_menu(update, user_id)

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
        user_modes[user_id] = 'x'
        
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

async def savepage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("📂 Сохраняю страницу...")
        
        filename = f'page_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        
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

async def pageinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        html = await tab.execute_script("""
            (function() {
                return document.documentElement.outerHTML;
            })()
        """, return_by_value=True)
        
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

# ==================== KREA.AI КОМАНДЫ ====================

async def krea_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в Krea.ai"""
    user_id = update.effective_user.id
    
    try:
        msg1 = await update.message.reply_text("🎨 Запускаю Krea.ai...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")
        options.binary_location = CHROME_PATH
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        await tab.go_to('https://www.krea.ai/edit')
        await asyncio.sleep(8)
        
        user_browsers[user_id] = (browser, tab)
        user_modes[user_id] = 'krea'
        
        cursor = get_cursor(user_id)
        try:
            viewport = await tab.execute_script("return { width: window.innerWidth, height: window.innerHeight }")
            cursor.x = viewport['width'] // 2
            cursor.y = viewport['height'] // 2
        except:
            cursor.x, cursor.y = 500, 300
        
        await msg1.delete()
        await update.message.reply_text("✅ Krea.ai загружен!")
        await krea_menu(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def krea_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    _, tab = user_browsers[user_id]
    user_modes[user_id] = 'krea'
    
    try:
        screenshot_base64 = await tab.take_screenshot(as_base64=True)
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        image = Image.open(BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(image)
        cursor = get_cursor(user_id)
        x, y = cursor.x, cursor.y
        size = 15
        draw.line([(x - size, y), (x + size, y)], fill='red', width=3)
        draw.line([(x, y - size), (x, y + size)], fill='red', width=3)
        draw.ellipse([(x - 3, y - 3), (x + 3, y + 3)], fill='red')
        
        output = BytesIO()
        image.save(output, format='PNG')
        img_data = output.getvalue()
        
        caption = f"{get_krea_menu_text()}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
        
        if user_id in user_menu_messages:
            try:
                await update.effective_message.edit_media(
                    media=InputMediaPhoto(media=img_data, caption=caption),
                    reply_markup=get_krea_keyboard()
                )
                return
            except:
                pass
        
        msg = await update.message.reply_photo(
            photo=img_data,
            caption=caption,
            reply_markup=get_krea_keyboard()
        )
        user_menu_messages[user_id] = msg.message_id
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ГЛАВНАЯ КОМАНДА /explore_krea ====================

async def explore_krea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное исследование krea.ai/edit с помощью PyDoll"""
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Начинаю исследование Krea.ai/edit...\nЭто займет ~15 секунд")

    # 1. Запускаем браузер, если его нет
    if user_id not in user_browsers:
        try:
            options = ChromiumOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.binary_location = CHROME_PATH

            browser = Chrome(options=options)
            tab = await browser.start()
            await tab.go_to('https://www.krea.ai/edit')
            await asyncio.sleep(8)
            user_browsers[user_id] = (browser, tab)
            user_modes[user_id] = 'krea'
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка запуска: {e}")
            return
    else:
        _, tab = user_browsers[user_id]
        current_url = await tab.execute_script("return window.location.href;")
        if 'krea.ai/edit' not in current_url:
            await tab.go_to('https://www.krea.ai/edit')
            await asyncio.sleep(8)

    _, tab = user_browsers[user_id]

    # 2. Собираем данные через PyDoll
    status_msg = await update.message.reply_text("📊 Собираю структуру страницы...")

    try:
        research_data = await tab.execute_script("""
            (function() {
                // ===== 1. БАЗОВАЯ ИНФОРМАЦИЯ =====
                const info = {
                    url: window.location.href,
                    title: document.title,
                    viewport: { width: window.innerWidth, height: window.innerHeight },
                    totalElements: document.querySelectorAll('*').length
                };

                // ===== 2. ВСЕ ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ =====
                const interactiveSelectors = [
                    'button', 'input', 'textarea', 'select',
                    '[role="button"]', '[role="listbox"]', '[role="option"]',
                    '[contenteditable="true"]',
                    '[data-testid]', '[data-action]', '[data-state]',
                    '[class*="upload"]', '[class*="download"]',
                    '[class*="generate"]', '[class*="prompt"]', '[class*="model"]',
                    'a[download]'
                ];
                
                const elements = document.querySelectorAll(interactiveSelectors.join(','));
                const elementsData = [];
                const seen = new Set();

                elements.forEach(el => {
                    const id = el.id || el.className || el.tagName;
                    if (seen.has(id)) return;
                    seen.add(id);

                    const rect = el.getBoundingClientRect();
                    const styles = window.getComputedStyle(el);
                    const isVisible = rect.width > 0 && rect.height > 0;

                    elementsData.push({
                        tag: el.tagName,
                        id: el.id || null,
                        className: el.className || null,
                        type: el.type || null,
                        text: (el.textContent || '').trim().slice(0, 100),
                        placeholder: el.placeholder || null,
                        value: el.value || null,
                        visible: isVisible,
                        display: styles.display,
                        opacity: styles.opacity,
                        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                        attributes: Array.from(el.attributes).reduce((acc, attr) => {
                            acc[attr.name] = attr.value.slice(0, 80);
                            return acc;
                        }, {})
                    });
                });

                // ===== 3. СПЕЦИАЛЬНЫЙ ПОИСК ДЛЯ KREA =====
                const kreaSpecific = {
                    upload: [],
                    prompt: [],
                    generate: [],
                    download: [],
                    model: []
                };

                elementsData.forEach(el => {
                    const text = (el.text || '').toLowerCase();
                    const className = (el.className || '').toLowerCase();
                    const attrs = JSON.stringify(el.attributes).toLowerCase();

                    if (text.includes('upload') || className.includes('upload') || attrs.includes('file')) {
                        kreaSpecific.upload.push(el);
                    }
                    if (text.includes('prompt') || className.includes('prompt') || el.tag === 'TEXTAREA') {
                        kreaSpecific.prompt.push(el);
                    }
                    if (text.includes('generate') || text.includes('run') || text.includes('create')) {
                        kreaSpecific.generate.push(el);
                    }
                    if (text.includes('download') || text.includes('save') || text.includes('export')) {
                        kreaSpecific.download.push(el);
                    }
                    if (text.includes('model') || className.includes('model') || el.tag === 'SELECT') {
                        kreaSpecific.model.push(el);
                    }
                });

                // ===== 4. СКРЫТЫЕ ЭЛЕМЕНТЫ =====
                const hidden = [];
                document.querySelectorAll('*').forEach(el => {
                    const styles = window.getComputedStyle(el);
                    if ((styles.display === 'none' || styles.visibility === 'hidden' || styles.opacity === '0') &&
                        (el.id || el.className || el.hasAttribute('data-testid'))) {
                        hidden.push({
                            tag: el.tagName,
                            id: el.id || null,
                            className: el.className || null,
                            text: (el.textContent || '').trim().slice(0, 50),
                            display: styles.display,
                            visibility: styles.visibility
                        });
                    }
                });

                // ===== 5. API ЗАПРОСЫ =====
                const apiCalls = performance.getEntriesByType('resource')
                    .filter(e => e.initiatorType === 'fetch' || e.initiatorType === 'xmlhttprequest')
                    .map(e => ({
                        url: e.name,
                        duration: Math.round(e.duration),
                        size: e.transferSize || 0
                    }))
                    .slice(0, 15);

                return {
                    info: info,
                    elements: elementsData,
                    krea: kreaSpecific,
                    hidden: hidden.slice(0, 30),
                    api: apiCalls,
                    timestamp: new Date().toISOString()
                };
            })();
        """, return_by_value=True)

        # 3. Сохраняем JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"krea_explore_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(research_data, f, indent=2, ensure_ascii=False)

        # 4. Формируем отчет
        report = f"""📊 **Исследование Krea.ai/edit**

📌 **Общее:**
• Элементов на странице: {research_data['info']['totalElements']}
• Найдено интерактивных: {len(research_data['elements'])}
• Скрытых элементов: {len(research_data['hidden'])}

🎯 **Найдено для Krea:**
• Upload: {len(research_data['krea']['upload'])}
• Prompt: {len(research_data['krea']['prompt'])}
• Generate: {len(research_data['krea']['generate'])}
• Download: {len(research_data['krea']['download'])}
• Model: {len(research_data['krea']['model'])}

📝 **Ключевые селекторы:**

"""
        # Добавляем селекторы для каждого типа
        for category, items in research_data['krea'].items():
            if items:
                report += f"**{category.upper()}**:\n"
                for item in items[:3]:
                    selector = f"#{item['id']}" if item['id'] else f".{item['className'].split()[0]}" if item['className'] else item['tag']
                    report += f"  • `{selector}` — {item['text'][:40]}\n"
                report += "\n"

        report += f"""
💾 **Полные данные:** `{filename}`

📋 **Скрытые элементы** (могут появляться после действий):
"""
        for h in research_data['hidden'][:5]:
            report += f"  • {h['tag']} {h['id'] or h['className'] or ''}\n"

        # 5. Отправляем отчет
        await status_msg.delete()
        
        # Разбиваем отчет, если он слишком длинный
        if len(report) > 4096:
            for i in range(0, len(report), 4000):
                await update.message.reply_text(report[i:i+4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(report, parse_mode='Markdown')

        # 6. Отправляем JSON файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption="📄 Полный дамп DOM"
            )

        # 7. Очистка (опционально)
        # os.remove(filename)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ТЕСТ СЕЛЕКТОРОВ ДЛЯ KREA ====================

async def test_krea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирует основные селекторы на странице"""
    user_id = update.effective_user.id

    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /explore_krea")
        return

    _, tab = user_browsers[user_id]

    # Селекторы для теста (обновляйте после исследования)
    selectors = [
        "input[type='file']",
        "textarea",
        "button:contains('Upload')",
        "button:contains('Generate')",
        "a[download]",
        "[data-testid='upload-button']",
        "[role='listbox']",
        "[contenteditable='true']"
    ]

    await update.message.reply_text("🧪 Тестирую селекторы...")
    results = {}

    for selector in selectors:
        try:
            el = await tab.find_element(selector, timeout=2)
            if el:
                visible = await el.is_displayed()
                results[selector] = {
                    'found': True,
                    'visible': visible,
                    'tag': await el.get_attribute('tagName')
                }
            else:
                results[selector] = {'found': False}
        except:
            results[selector] = {'found': False}

    # Отчет
    report = "📋 **Результаты теста:**\n\n"
    for selector, result in results.items():
        if result['found']:
            status = "✅ видим" if result['visible'] else "✅ скрыт"
            report += f"• `{selector}` — {status}\n"
        else:
            report += f"• `{selector}` — ❌ не найден\n"

    await update.message.reply_text(report, parse_mode='Markdown')

# ==================== ОСТАЛЬНЫЕ KREA КОМАНДЫ ====================

async def krea_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загружает изображение в Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📤 Укажи путь к файлу:\n"
            "`/krea_upload /path/to/photo.jpg`",
            parse_mode='Markdown'
        )
        return
    
    _, tab = user_browsers[user_id]
    image_path = context.args[0]
    
    try:
        await update.message.reply_text("📤 Загружаю изображение...")
        
        # Ищем кнопку загрузки
        upload_btn = await tab.find_element(
            '//*[contains(text(), "Upload image") or contains(@class, "upload")]',
            by='xpath',
            timeout=5
        )
        
        if upload_btn:
            await upload_btn.click()
            await asyncio.sleep(1)
        
        # Ищем input[type="file"]
        file_input = await tab.find_element('input[type="file"]', timeout=3)
        if file_input:
            await file_input.send_keys(image_path)
            await asyncio.sleep(3)
            await update.message.reply_text("✅ Изображение загружено!")
        else:
            await update.message.reply_text("❌ Не найден input для загрузки")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def krea_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вводит промт в Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 Введи промт:\n"
            "`/krea_prompt Remove background, professional photo`",
            parse_mode='Markdown'
        )
        return
    
    _, tab = user_browsers[user_id]
    prompt = ' '.join(context.args)
    
    try:
        await update.message.reply_text(f"📝 Ввожу промт: {prompt[:50]}...")
        
        # Ищем поле ввода промта
        prompt_input = await tab.find_element(
            'textarea[placeholder*="prompt"], textarea[placeholder*="describe"], [contenteditable="true"]',
            timeout=5
        )
        
        if prompt_input:
            await prompt_input.clear()
            await prompt_input.send_keys(prompt)
            await update.message.reply_text("✅ Промт введен!")
        else:
            await update.message.reply_text("❌ Не найдено поле для промта")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def krea_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбирает модель в Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("🤖 Ищу доступные модели...")
        
        # Получаем список моделей
        models = await tab.execute_script("""
            const modelElements = document.querySelectorAll(
                '[role="listbox"] [role="option"], .model-selector li, [class*="model"] button'
            );
            return Array.from(modelElements).map(el => el.textContent.trim()).filter(Boolean);
        """, return_by_value=True)
        
        if models:
            # Показываем кнопки для выбора модели
            keyboard = []
            for model in models[:6]:
                keyboard.append([InlineKeyboardButton(
                    f"🤖 {model}", 
                    callback_data=f"krea_select_model_{model}"
                )])
            
            await update.message.reply_text(
                f"🤖 **Доступные модели:**\n\nВыбери модель:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Модели не найдены")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def krea_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает генерацию в Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("🚀 Запускаю генерацию...")
        
        # Ищем кнопку Generate
        generate_btn = await tab.find_element(
            'button:contains("Generate"), button:contains("Run"), [data-action="generate"]',
            timeout=5
        )
        
        if generate_btn:
            await generate_btn.click()
            await update.message.reply_text("⏳ Генерация запущена, жду результат...")
            
            # Ждем результат (до 60 секунд)
            for _ in range(60):
                await asyncio.sleep(1)
                
                # Проверяем появление результата
                result = await tab.find_element(
                    'img[class*="result"], img[class*="generated"], .result-container img',
                    timeout=1
                )
                
                if result:
                    await update.message.reply_text("✅ Результат готов!")
                    break
            else:
                await update.message.reply_text("⏰ Таймаут ожидания результата")
        else:
            await update.message.reply_text("❌ Не найдена кнопка Generate")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def krea_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачивает результат из Krea.ai"""
    user_id = update.effective_user.id
    
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала выполни /krea_login")
        return
    
    _, tab = user_browsers[user_id]
    
    try:
        await update.message.reply_text("📥 Скачиваю результат...")
        
        # Ищем кнопку Download
        download_btn = await tab.find_element(
            'a[download], button[class*="download"], [data-testid="download"]',
            timeout=5
        )
        
        if download_btn:
            # Получаем ссылку
            href = await download_btn.get_attribute('href')
            if href:
                await update.message.reply_text(f"📥 Ссылка на скачивание: {href}")
            else:
                await download_btn.click()
                await update.message.reply_text("✅ Клик по Download выполнен")
        else:
            # Ищем изображение результата
            result_img = await tab.find_element(
                'img[class*="result"], img[class*="generated"]',
                timeout=3
            )
            
            if result_img:
                src = await result_img.get_attribute('src')
                if src:
                    await update.message.reply_text(f"📥 Результат: {src}")
                else:
                    await update.message.reply_text("❌ Не удалось получить изображение")
            else:
                await update.message.reply_text("❌ Результат не найден")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК КНОПОК ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    # ===== КНОПКИ ДЛЯ X.COM =====
    if action in ["do_login", "do_eval", "do_savepage", "close_browser", 
                  "cursor_up", "cursor_down", "cursor_left", "cursor_right",
                  "diag_up_left", "diag_up_right", "diag_down_left", "diag_down_right",
                  "cursor_center", "step_30", "step_60", "step_100",
                  "scroll_up", "scroll_down", "scroll_top", "scroll_bottom",
                  "mouse_click", "take_screenshot", "extract_tweets", "refresh_screen"]:
        
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
        
        if action == "close_browser":
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
                menu_text = get_x_menu_text()
                full_caption = f"📸 Скриншот\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
                await query.edit_message_media(
                    media=InputMediaPhoto(media=img_data, caption=full_caption),
                    reply_markup=get_x_keyboard()
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
                menu_text = get_x_menu_text()
                full_caption = f"🔄 Обновлено\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
                await query.edit_message_media(
                    media=InputMediaPhoto(media=img_data, caption=full_caption),
                    reply_markup=get_x_keyboard()
                )
                return
            else:
                await query.edit_message_text("❌ Неизвестная команда")
                return
                
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
            return
        
        img_data, x, y = await get_screenshot_with_cursor(user_id)
        menu_text = get_x_menu_text()
        full_caption = f"{captions}\n\n{menu_text}\n\n📍 Курсор: ({x}, {y}) | Шаг: {cursor.step}px"
        
        await query.edit_message_media(
            media=InputMediaPhoto(media=img_data, caption=full_caption),
            reply_markup=get_x_keyboard()
        )
        return

    # ===== КНОПКИ ДЛЯ KREA.AI =====
    if action.startswith("krea_"):
        if action == "krea_upload":
            await query.message.reply_text("📤 Отправь /krea_upload /path/to/image.jpg")
        elif action == "krea_prompt":
            await query.message.reply_text("📝 Отправь /krea_prompt твой промт")
        elif action == "krea_model":
            await krea_model(update, context)
        elif action == "krea_generate":
            await krea_generate(update, context)
        elif action == "krea_download":
            await krea_download(update, context)
        elif action == "krea_explore":
            await explore_krea(update, context)
        elif action == "krea_test":
            await test_krea(update, context)
        elif action == "krea_screenshot" or action == "krea_refresh":
            await krea_menu(update, context)
        elif action == "krea_close":
            if user_id in user_browsers:
                browser, _ = user_browsers[user_id]
                await browser.close()
                del user_browsers[user_id]
                await query.edit_message_text("✅ Браузер закрыт")
                await start(update, context)
            return
        elif action.startswith("krea_select_model_"):
            model_name = action.replace("krea_select_model_", "")
            _, tab = user_browsers[user_id]
            
            try:
                await tab.execute_script("""
                    const modelName = arguments[0];
                    const elements = document.querySelectorAll(
                        '[role="option"], [role="listbox"] li, .model-selector button'
                    );
                    
                    elements.forEach(el => {
                        if (el.textContent.trim().includes(modelName)) {
                            el.click();
                        }
                    });
                """, model_name)
                await query.edit_message_text(f"✅ Выбрана модель: {model_name}")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
        return

    # ===== ПЕРЕКЛЮЧЕНИЕ МЕЖДУ РЕЖИМАМИ =====
    if action == "switch_to_x":
        user_modes[user_id] = 'x'
        await query.message.delete()
        await send_or_update_menu(update, user_id)
        return

# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================

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

# ==================== ЗАПУСК ====================

def main():
    app = Application.builder().token(TOKEN).build()
    
    # X.com команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("x_menu", x_menu))
    app.add_handler(CommandHandler("savepage", savepage_command))
    app.add_handler(CommandHandler("pageinfo", pageinfo_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    
    # Krea.ai команды
    app.add_handler(CommandHandler("krea_login", krea_login))
    app.add_handler(CommandHandler("krea_menu", krea_menu))
    app.add_handler(CommandHandler("explore_krea", explore_krea))
    app.add_handler(CommandHandler("test_krea", test_krea))
    app.add_handler(CommandHandler("krea_upload", krea_upload))
    app.add_handler(CommandHandler("krea_prompt", krea_prompt))
    app.add_handler(CommandHandler("krea_model", krea_model))
    app.add_handler(CommandHandler("krea_generate", krea_generate))
    app.add_handler(CommandHandler("krea_download", krea_download))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    print("Доступные команды:")
    print("  X.com: /start, /login, /savepage, /pageinfo, /analyze")
    print("  Krea.ai: /krea_login, /explore_krea, /test_krea, /krea_upload, /krea_prompt, /krea_model, /krea_generate, /krea_download")
    
    app.run_polling()

if __name__ == "__main__":
    main()