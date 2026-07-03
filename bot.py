# bot.py - X.com бот с Pydoll (финальная версия)
import os
import logging
import asyncio
import json
import subprocess
import random
import base64
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден!")

# ========== МОДЕЛИ ==========
class Tweet(BaseModel):
    author: str
    text: str
    time: Optional[str] = None
    likes: str = "0"
    retweets: str = "0"
    
    @property
    def likes_int(self) -> int:
        try:
            return int(self.likes.replace(',', '').replace('K', '000'))
        except:
            return 0
    
    @property
    def retweets_int(self) -> int:
        try:
            return int(self.retweets.replace(',', '').replace('K', '000'))
        except:
            return 0

class ShadowHost(BaseModel):
    tag: str
    id: Optional[str] = ""
    class_name: Optional[str] = ""

class APIResponse(BaseModel):
    status: int
    ok: bool
    data: dict

# ========== ЭМУЛЯЦИЯ ЧЕЛОВЕКА ==========
def random_delay(min_sec=0.5, max_sec=2.0):
    return random.uniform(min_sec, max_sec)

async def human_goto(page, url):
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)

async def human_scroll(page, amount=300):
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
    except Exception as e:
        logger.warning(f"Human scroll error: {e}")
        await page.execute_script(f'window.scrollBy(0, {amount})')

# ========== ПОЛНЫЕ КУКИ X.COM ==========
COOKIES = [
    {
        "name": "__cuid",
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "lang",
        "value": "ru",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "dnt",
        "value": "1",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id",
        "value": "v1%3A178267838599411411",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id_marketing",
        "value": "v1%3A178267838599411411",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "guest_id_ads",
        "value": "v1%3A178267838599411411",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "personalization_id",
        "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "twid",
        "value": "u%3D2067347503503052800",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "auth_token",
        "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "ct0",
        "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb",
        "domain": ".x.com",
        "path": "/"
    },
    {
        "name": "__cf_bm",
        "value": "8AS4KkJTPVEBxib6jMqZVT_KfZfetc9yFYZaTAjIero-1783072999.9943306-1.0.1.1-h.ZVKRVBwECbpuDlQc4BJwZxlvHQJAbIhjncRLnauthiJvlZYU0C0xGyfkYbQkkb4C5oZIoqS7sgU1uyById4wz_oQjkJ_cAMMWZTh67dXXCqpWyxQk3Zs76u9q3QrGL",
        "domain": ".x.com",
        "path": "/"
    }
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
pydoll_browser = None
pydoll_tab = None
login_status = {'is_logged_in': False, 'username': None}

# ========== ПОИСК CHROMIUM ==========
def find_chromium():
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/snap/bin/chromium',
        '/usr/lib/chromium-browser/chromium-browser',
    ]
    
    for path in chromium_paths:
        if os.path.exists(path):
            logger.info(f"✅ Chromium найден: {path}")
            return path
    
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            logger.info(f"✅ Chromium найден через which: {path}")
            return path
    except:
        pass
    
    try:
        result = subprocess.run(['which', 'chromium-browser'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            logger.info(f"✅ Chromium найден через which: {path}")
            return path
    except:
        pass
    
    logger.error("❌ Chromium не найден в системе!")
    return None

# ========== БРАУЗЕР ==========
async def get_browser():
    global pydoll_browser, pydoll_tab
    
    if pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            return pydoll_tab
        except:
            await close_browser()
    
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions
        
        chromium_path = find_chromium()
        if not chromium_path:
            raise Exception("Chromium не найден. Установи: apt-get install chromium")
        
        options = ChromiumOptions()
        options.binary_location = chromium_path
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1280,720')
        
        logger.info(f"🚀 Запуск браузера: {chromium_path}")
        
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        
        logger.info("✅ Браузер запущен!")
        
        await human_goto(pydoll_tab, 'https://x.com')
        
        for cookie in COOKIES:
            try:
                await pydoll_tab.set_cookie(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path']
                )
                logger.debug(f"🍪 Кука установлена: {cookie['name']}")
            except Exception as e:
                logger.warning(f"Cookie error {cookie['name']}: {e}")
        
        logger.info("✅ Браузер готов!")
        return pydoll_tab
        
    except Exception as e:
        logger.error(f"❌ Ошибка браузера: {e}", exc_info=True)
        return None

async def close_browser():
    global pydoll_browser, pydoll_tab
    if pydoll_browser:
        try:
            await pydoll_browser.close()
        except:
            pass
    pydoll_browser = None
    pydoll_tab = None

async def execute_js(script):
    page = await get_browser()
    if page is None:
        return None
    try:
        return await page.execute_script(script)
    except Exception as e:
        logger.error(f"JS error: {e}")
        return None

async def take_screenshot():
    page = await get_browser()
    if page is None:
        return None
    
    try:
        if hasattr(page, 'take_screenshot'):
            try:
                screenshot_base64 = await page.take_screenshot(as_base64=True)
                if screenshot_base64:
                    return base64.b64decode(screenshot_base64)
            except:
                temp_file = '/tmp/screenshot.png'
                await page.take_screenshot(path=temp_file)
                if os.path.exists(temp_file):
                    with open(temp_file, 'rb') as f:
                        return f.read()
        elif hasattr(page, 'screenshot'):
            return await page.screenshot()
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
    
    return None

# ========== УНИВЕРСАЛЬНЫЕ ФУНКЦИИ ОТПРАВКИ ==========
async def send_photo(update: Update, photo_bytes, caption=None):
    """Отправляет фото через update.message или update.callback_query"""
    try:
        if update.message:
            await update.message.reply_photo(photo=photo_bytes, caption=caption)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_photo(photo=photo_bytes, caption=caption)
        else:
            logger.error("❌ Нет способа отправить фото")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")

async def send_message(update: Update, text, parse_mode='Markdown'):
    """Отправляет текст через update.message или update.callback_query"""
    try:
        if update.message:
            await update.message.reply_text(text, parse_mode=parse_mode)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(text, parse_mode=parse_mode)
        else:
            logger.error("❌ Нет способа отправить сообщение")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

async def send_document(update: Update, file, caption=None):
    """Отправляет документ"""
    try:
        if update.message:
            await update.message.reply_document(document=file, caption=caption)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_document(document=file, caption=caption)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки документа: {e}")

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Логин", callback_data="login")],
        [InlineKeyboardButton("🛡️ Shadow DOM", callback_data="shadow")],
        [InlineKeyboardButton("🌐 API запрос", callback_data="api")],
        [InlineKeyboardButton("📊 Extract", callback_data="extract")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screen")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("❌ Закрыть браузер", callback_data="close")],
    ]
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n"
        f"🔐 Статус: {'✅ Авторизован' if login_status['is_logged_in'] else '❌ Не авторизован'}\n\n"
        f"Выбери действие:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "shadow":
        await shadow_dom(update, context)
    elif query.data == "api":
        await api_request(update, context)
    elif query.data == "extract":
        await extract_data(update, context)
    elif query.data == "screen":
        await screen(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "close":
        await close(update, context)

# ---------- ЛОГИН ----------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global login_status
    
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Авторизация...")
    else:
        msg = await update.message.reply_text("⏳ Авторизация...")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Не удалось запустить браузер")
            return
        
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(random_delay(2.0, 4.0))
        
        auth = await execute_js('''
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [k, v] = c.trim().split('=');
                    acc[k] = v;
                    return acc;
                }, {});
                
                const hasAuth = !!cookies.auth_token;
                const hasCt0 = !!cookies.ct0;
                
                const profile = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                let username = null;
                if (profile) {
                    const href = profile.getAttribute('href');
                    if (href) username = href.replace('/', '');
                }
                
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                
                const isLoggedIn = hasAuth || (hasProfileLink && !hasLoginLink);
                
                return {
                    hasAuthToken: hasAuth,
                    hasCt0: hasCt0,
                    username: username || 'неизвестно',
                    isLoggedIn: isLoggedIn
                };
            }
        ''')
        
        if auth is None:
            await msg.edit_text("❌ Не удалось проверить авторизацию")
            return
        
        login_status['is_logged_in'] = auth.get('isLoggedIn', False)
        login_status['username'] = auth.get('username')
        
        status_msg = f"✅ X.com\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth.get('hasAuthToken') else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth.get('hasCt0') else '❌'}\n\n"
        
        if auth.get('isLoggedIn'):
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth.get('username') and auth.get('username') != 'неизвестно':
                status_msg += f"👤 @{auth['username']}\n"
        else:
            status_msg += "❌ НЕ АВТОРИЗОВАН\n"
        
        await msg.edit_text(status_msg)
        
        await asyncio.sleep(random_delay(0.5, 1.0))
        screenshot = await take_screenshot()
        if screenshot:
            caption = f"📸 X.com - {'✅ Авторизован' if auth.get('isLoggedIn') else '❌ Не авторизован'}"
            if auth.get('isLoggedIn') and auth.get('username') and auth.get('username') != 'неизвестно':
                caption += f" @{auth['username']}"
            await send_photo(update, screenshot, caption)
        
        logger.info(f"✅ Логин выполнен: {login_status['username']}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в login: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- SHADOW DOM ----------
async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("🛡️ Поиск Shadow DOM...")
    else:
        msg = await update.message.reply_text("🛡️ Поиск Shadow DOM...")
    
    try:
        hosts_data = await execute_js('''
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        result.push({
                            tag: el.tagName,
                            id: el.id || '',
                            class_name: el.className || ''
                        });
                    }
                });
                return result;
            }
        ''')
        
        if not hosts_data or len(hosts_data) == 0:
            await msg.edit_text("🛡️ Shadow DOM элементы не найдены")
            return
        
        hosts = [ShadowHost(**h) for h in hosts_data]
        
        response = f"🛡️ **Найдено {len(hosts)} элементов с Shadow DOM**\n\n"
        for h in hosts[:5]:
            response += f"• `{h.tag}`"
            if h.id: response += f" id='{h.id}'"
            response += "\n"
        
        response += "\n💡 Используй в коде:\n"
        response += "```python\n"
        response += "host = await tab.find('selector')\n"
        response += "shadow = await host.get_shadow_root()\n"
        response += "inner = await shadow.query('.inner')\n"
        response += "```"
        
        await msg.edit_text(response, parse_mode='Markdown')
        
        await asyncio.sleep(random_delay(0.5, 1.0))
        img = await take_screenshot()
        if img:
            await send_photo(update, img, "📸 Текущая страница")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- API ----------
async def api_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text("🌐 Введите URL для API запроса:\n/api <url>")
        return
    
    if not context.args:
        await send_message(update, "🌐 Использование: /api <url>\nПример: /api https://x.com/i/api/1.1/onboarding/task.json")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text(f"🌐 Запрос к {url[:50]}...")
    
    try:
        result = await execute_js(f'''
            (async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        credentials: 'include',
                        headers: {{ 'Accept': 'application/json' }}
                    }});
                    const data = await r.json();
                    return {{ status: r.status, ok: r.ok, data: data }};
                }} catch(e) {{
                    return {{ error: e.message }};
                }}
            }})()
        ''')
        
        if result.get('error'):
            await msg.edit_text(f"❌ {result['error']}")
            return
        
        response_data = APIResponse(
            status=result.get('status', 0),
            ok=result.get('ok', False),
            data=result.get('data', {})
        )
        
        text = f"✅ **Статус:** {response_data.status}\n\n"
        if response_data.data:
            text += f"```json\n{json.dumps(response_data.data, indent=2, ensure_ascii=False)[:1000]}\n```"
        
        await msg.edit_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- EXTRACT ----------
async def extract_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📊 Извлечение данных...")
    else:
        msg = await update.message.reply_text("📊 Извлечение данных...")
    
    try:
        page = await get_browser()
        if page:
            await human_scroll(page, 300)
            await asyncio.sleep(random_delay(1.0, 2.0))
        
        raw_data = await execute_js('''
            () => {
                const items = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.querySelector('[data-testid="tweetText"]');
                    const user = el.querySelector('[data-testid="User-Name"]');
                    const time = el.querySelector('time');
                    const likes = el.querySelector('[data-testid="like"]');
                    const retweets = el.querySelector('[data-testid="retweet"]');
                    
                    items.push({
                        author: user ? user.textContent.trim() : '',
                        text: text ? text.textContent.trim() : '',
                        time: time ? time.getAttribute('datetime') : '',
                        likes: likes ? likes.textContent.trim() : '0',
                        retweets: retweets ? retweets.textContent.trim() : '0'
                    });
                });
                return items.slice(0, 10);
            }
        ''')
        
        if not raw_data or len(raw_data) == 0:
            await msg.edit_text("⚠️ Нет данных для извлечения.\n\nПопробуй:\n• Открыть страницу с твитами\n• Использовать /search или /tweets")
            return
        
        tweets = [Tweet(**item) for item in raw_data]
        
        response = f"📊 **Извлечено {len(tweets)} твитов**\n\n"
        for i, t in enumerate(tweets[:5], 1):
            response += f"**{i}.** {t.author}\n"
            response += f"   📝 {t.text[:100]}...\n"
            response += f"   ❤️ {t.likes_int} | 🔄 {t.retweets_int}\n\n"
        
        if len(tweets) > 5:
            response += f"... и еще {len(tweets) - 5} твитов\n\n"
        
        filename = f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([t.model_dump() for t in tweets], f, indent=2, ensure_ascii=False)
        
        await msg.edit_text(response)
        await send_document(update, open(filename, 'rb'), f"📄 {len(tweets)} твитов в JSON")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- СКРИНШОТ ----------
async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("📸 Делаю скриншот...")
    else:
        msg = await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        await asyncio.sleep(random_delay(0.5, 1.0))
        img = await take_screenshot()
        if img:
            await msg.delete()
            await send_photo(update, img, "📸 Скриншот")
        else:
            await msg.edit_text("❌ Не удалось сделать скриншот")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- СТАТУС ----------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Проверка...")
    else:
        msg = await update.message.reply_text("⏳ Проверка...")
    
    try:
        page = await get_browser()
        url = "Нет"
        if page:
            try:
                url = await execute_js('window.location.href') or "Неизвестно"
            except:
                pass
        
        await msg.edit_text(
            f"📊 **Статус**\n\n"
            f"🌐 Браузер: {'✅ Запущен' if page else '❌ Не запущен'}\n"
            f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
            f"👤 Пользователь: {login_status['username'] or 'Нет'}\n"
            f"🔗 URL: {url[:60]}\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ---------- ЗАКРЫТЬ ----------
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query'):
        msg = await update.callback_query.edit_message_text("⏳ Закрываю браузер...")
    else:
        msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("shadow", shadow_dom))
    app.add_handler(CommandHandler("api", api_request))
    app.add_handler(CommandHandler("extract", extract_data))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Бот запущен!")
    
    chromium_path = find_chromium()
    if chromium_path:
        print(f"✅ Chromium найден: {chromium_path}")
    else:
        print("❌ Chromium не найден! Установи: apt-get install chromium")
    
    print(f"🔐 Куки загружены: {len(COOKIES)} шт.")
    app.run_polling()

if __name__ == "__main__":
    main()