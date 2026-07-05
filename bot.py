import os
import logging
import asyncio
import base64
import json
import re
from io import BytesIO
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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

class CursorManager:
    def __init__(self):
        self.x = 500
        self.y = 300

cursor_managers = {}

def get_cursor(user_id):
    if user_id not in cursor_managers:
        cursor_managers[user_id] = CursorManager()
    return cursor_managers[user_id]

def get_menu_text():
    return (
        "🤖 Бот для X.com\n\n"
        "🔐 /login — войти в X.com\n"
        "❌ /close — закрыть браузер\n"
        "⚡ /eval <js> — выполнить JS код\n"
        "📸 /screen — скриншот страницы\n"
        "📊 /extract <x> <y> — извлечь твит\n\n"
        "⬇️⬆️ Кнопки скролла внизу"
    )

def get_scroll_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Вверх", callback_data="scroll_up"),
            InlineKeyboardButton("⬇️ Вниз", callback_data="scroll_down"),
        ],
        [
            InlineKeyboardButton("⬆️⬆️ Вверх 500", callback_data="scroll_up_fast"),
            InlineKeyboardButton("⬇️⬇️ Вниз 500", callback_data="scroll_down_fast"),
        ],
        [
            InlineKeyboardButton("🔝 Наверх", callback_data="scroll_top"),
            InlineKeyboardButton("🔽 Вниз", callback_data="scroll_bottom"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="refresh_screen"),
        ],
    ])

async def get_screenshot_with_cursor(user_id):
    """Делает скриншот с курсором"""
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)

    try:
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        await tab.refresh()
        await asyncio.sleep(3)
        screenshot_base64 = await tab.take_screenshot(as_base64=True)

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
    """Отправляет или обновляет меню со скриншотом в одном сообщении"""
    
    # Если браузер не открыт — только меню
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

    # Делаем скриншот
    img_data, x, y = await get_screenshot_with_cursor(user_id)
    
    menu_text = get_menu_text()
    if caption:
        menu_text = f"{caption}\n\n{menu_text}"
    
    full_caption = f"{menu_text}\n\n📍 Курсор: ({x}, {y})"

    # Если уже есть сообщение — редактируем его
    if user_id in user_menu_messages:
        try:
            await update.effective_message.edit_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_scroll_keyboard()
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать: {e}")
    
    # Если нет сообщения — создаём новое
    msg = await update.message.reply_photo(
        photo=img_data,
        caption=full_caption,
        reply_markup=get_scroll_keyboard()
    )
    user_menu_messages[user_id] = msg.message_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_or_update_menu(update, update.effective_user.id)

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
        await send_or_update_menu(update, user_id, "✅ Вход выполнен!")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def close_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_browsers:
        browser, _ = user_browsers[user_id]
        await browser.close()
        del user_browsers[user_id]
        if user_id in user_menu_messages:
            del user_menu_messages[user_id]
        await update.message.reply_text("✅ Браузер закрыт")
        await send_or_update_menu(update, user_id)
    else:
        await update.message.reply_text("❌ Браузер не открыт")

async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала /login")
        return
    await send_or_update_menu(update, user_id, "📸 Скриншот обновлён")

async def eval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи JS код\nПример: /eval document.title")
        return

    user_id = update.effective_user.id
    js_code = ' '.join(context.args)

    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала /login")
        return

    _, tab = user_browsers[user_id]
    try:
        raw = await tab.execute_script(js_code, return_by_value=True)
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

async def extract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_browsers:
        await update.message.reply_text("❌ Сначала /login")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ /extract x y")
        return

    try:
        x, y = int(context.args[0]), int(context.args[1])
        _, tab = user_browsers[user_id]

        result = await tab.execute_script(f"""
            (function() {{
                const el = document.elementFromPoint({x}, {y});
                if (!el) return null;
                const tweet = el.closest('article[data-testid="tweet"]');
                if (!tweet) return {{ error: 'Не найден твит' }};
                const textEl = tweet.querySelector('[data-testid="tweetText"]');
                const authorEl = tweet.querySelector('[data-testid="User-Name"]');
                const likeEl = tweet.querySelector('[data-testid="like"]');
                const retweetEl = tweet.querySelector('[data-testid="retweet"]');
                const replyEl = tweet.querySelector('[data-testid="reply"]');
                const rect = tweet.getBoundingClientRect();
                let author = '';
                if (authorEl) {{
                    const spans = authorEl.querySelectorAll('span');
                    author = spans.length > 0 ? spans[0].textContent.trim() : '';
                }}
                return {{
                    text: textEl ? textEl.textContent.trim() : '',
                    author: author,
                    likes: likeEl ? likeEl.textContent.trim() : '0',
                    retweets: retweetEl ? retweetEl.textContent.trim() : '0',
                    replies: replyEl ? replyEl.textContent.trim() : '0',
                    coords: {{ x: Math.round(rect.left + rect.width/2), y: Math.round(rect.top + rect.height/2) }}
                }};
            }})()
        """, return_by_value=True)

        if not result:
            await update.message.reply_text("❌ Не удалось извлечь данные")
            return

        if result.get('error'):
            await update.message.reply_text(f"❌ {result['error']}")
            return

        reply = f"📊 **Твит под курсором:**\n\n"
        reply += f"👤 **Автор:** {result.get('author', 'Неизвестно')}\n"
        text = result.get('text', '')
        if text:
            reply += f"📝 **Текст:** {text[:200]}\n"
        else:
            reply += "📝 **Текст:** (пусто)\n"
        reply += f"❤️ **Лайки:** {result.get('likes', '0')}\n"
        reply += f"🔁 **Ретвиты:** {result.get('retweets', '0')}\n"
        reply += f"💬 **Ответы:** {result.get('replies', '0')}\n"
        coords = result.get('coords', {})
        if coords:
            reply += f"\n📍 **Координаты:** ({coords.get('x', '?')}, {coords.get('y', '?')})"

        await update.message.reply_text(reply, parse_mode='Markdown')
        await send_or_update_menu(update, user_id, "📊 Твит извлечён")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ==================== ОБРАБОТЧИК КНОПОК ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    if user_id not in user_browsers:
        await query.edit_message_text("❌ Сначала /login")
        return
    
    _, tab = user_browsers[user_id]
    cursor = get_cursor(user_id)
    
    try:
        # Выполняем скролл
        if action == "scroll_up":
            await tab.execute_script("window.scrollBy(0, -300)")
        elif action == "scroll_down":
            await tab.execute_script("window.scrollBy(0, 300)")
        elif action == "scroll_up_fast":
            await tab.execute_script("window.scrollBy(0, -500)")
        elif action == "scroll_down_fast":
            await tab.execute_script("window.scrollBy(0, 500)")
        elif action == "scroll_top":
            await tab.execute_script("window.scrollTo(0, 0)")
        elif action == "scroll_bottom":
            await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        elif action == "refresh_screen":
            # Просто обновляем скриншот
            img_data, x, y = await get_screenshot_with_cursor(user_id)
            menu_text = get_menu_text()
            full_caption = f"🔄 Обновлено\n\n{menu_text}\n\n📍 Курсор: ({x}, {y})"
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_data, caption=full_caption),
                reply_markup=get_scroll_keyboard()
            )
            return
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка скролла: {str(e)[:100]}")
        return
    
    # Обновляем скриншот после скролла
    img_data, x, y = await get_screenshot_with_cursor(user_id)
    
    # Определяем caption в зависимости от действия
    captions = {
        "scroll_up": "⬆️ Скролл вверх на 300px",
        "scroll_down": "⬇️ Скролл вниз на 300px",
        "scroll_up_fast": "⬆️⬆️ Скролл вверх на 500px",
        "scroll_down_fast": "⬇️⬇️ Скролл вниз на 500px",
        "scroll_top": "🔝 Наверх страницы",
        "scroll_bottom": "🔽 Вниз страницы",
    }
    
    caption_text = captions.get(action, "🔄 Обновлено")
    menu_text = get_menu_text()
    full_caption = f"{caption_text}\n\n{menu_text}\n\n📍 Курсор: ({x}, {y})"
    
    await query.edit_message_media(
        media=InputMediaPhoto(media=img_data, caption=full_caption),
        reply_markup=get_scroll_keyboard()
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("close", close_browser))
    app.add_handler(CommandHandler("eval", eval_command))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("extract", extract_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()