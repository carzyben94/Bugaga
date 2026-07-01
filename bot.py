# bot.py - X.com бот с Phantomwright
import os
import sys
import subprocess
import logging
import traceback
import asyncio
import math
import random
from datetime import datetime
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== ПРОВЕРКА И УСТАНОВКА PHANTOMWRIGHT ==========
try:
    from phantomwright_driver.async_api import Page, async_playwright
    PHANTOMWRIGHT_AVAILABLE = True
    print("✅ Phantomwright загружен")
except ImportError:
    PHANTOMWRIGHT_AVAILABLE = False
    print("⚠️ Phantomwright не найден, использую Playwright")
    from playwright.async_api import Page, async_playwright

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# ========== КУКИ X.COM ==========
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "gt", "value": "2071329406237220892", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": ".I7b6GGmlN4fNcwOMuw9lT0dsT0ARfcIVwJt0bKVn1A-1782678389.549309-1.0.1.1-ZyWyQlXJpxNQRq6_2VYG2dr8Gz2iv_dZ2DrW2mnM.xR8yrtzsdhU310hzPoDkIQZYC6QGWKef5dCUOQQKZdp5_AmnVQS5zZ1p67ydtzPrydFxyV6zl740zd69v0Xs3JC", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"}
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
browser_data = None
error_logs = []
MAX_LOGS = 50
browser_lock = False

# ========== УСТАНОВКА БРАУЗЕРА ==========
def get_chromium_path() -> Optional[str]:
    """Находит путь к Chromium"""
    base_dir = PLAYWRIGHT_DIR
    
    if not os.path.exists(base_dir):
        return None
    
    for item in os.listdir(base_dir):
        if item.startswith("chromium-") and "headless" not in item:
            chrome_path = os.path.join(base_dir, item, "chrome-linux", "chrome")
            if os.path.exists(chrome_path):
                return chrome_path
    
    return None

def install_browser():
    """Устанавливает браузер"""
    # Проверяем, установлен ли уже
    if get_chromium_path():
        print("✅ Браузер уже установлен")
        return True
    
    print("⏳ Устанавливаю браузер...")
    
    # Пробуем через Phantomwright
    if PHANTOMWRIGHT_AVAILABLE:
        try:
            subprocess.run(
                [sys.executable, "-m", "phantomwright_driver", "install", "chromium"],
                check=True,
                capture_output=True
            )
            print("✅ Браузер установлен через Phantomwright")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка Phantomwright: {e}")
    
    # Fallback на Playwright
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps"],
            check=True,
            capture_output=True
        )
        print("✅ Браузер установлен через Playwright")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки: {e}")
        return False

# Устанавливаем браузер при запуске
install_browser()

# ========== ДЖОЙСТИК ==========
@dataclass
class JoystickState:
    x: float = 0.0
    y: float = 0.0
    speed: float = 1.0
    smoothness: float = 0.3

class JoystickController:
    def __init__(self, page: Page):
        self.page = page
        self.state = JoystickState()
        self.current_pos = (0, 0)
        self.viewport_width = 1280
        self.viewport_height = 720
        
    async def init_position(self) -> Tuple[int, int]:
        try:
            viewport = await self.page.viewport_size()
            if viewport:
                self.viewport_width = viewport['width']
                self.viewport_height = viewport['height']
                center_x = viewport['width'] // 2
                center_y = viewport['height'] // 2
                await self.page.mouse.move(center_x, center_y)
                self.current_pos = (center_x, center_y)
                return center_x, center_y
        except Exception as e:
            logger.error(f"Init position error: {e}")
        return 0, 0
    
    async def human_like_move(self, target_x: int, target_y: int, speed: float = 1.0) -> None:
        cx, cy = self.current_pos
        distance = math.sqrt((target_x - cx)**2 + (target_y - cy)**2)
        
        if distance < 10:
            await self.page.mouse.move(target_x, target_y)
            self.current_pos = (target_x, target_y)
            return
        
        duration = min(2.0, distance / (800 * speed)) + random.uniform(0.1, 0.3)
        steps = max(1, int(duration * 60))
        
        for i in range(steps):
            progress = (i + 1) / steps
            human_progress = 1 - math.pow(1 - progress, 2.5)
            noise_x = random.uniform(-5, 5) * (1 - progress)
            noise_y = random.uniform(-5, 5) * (1 - progress)
            
            cur_x = cx + (target_x - cx) * human_progress + noise_x
            cur_y = cy + (target_y - cy) * human_progress + noise_y
            cur_x = max(0, min(self.viewport_width, cur_x))
            cur_y = max(0, min(self.viewport_height, cur_y))
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
    
    async def click(self, button: str = 'left', delay: float = 0.1) -> None:
        await asyncio.sleep(delay)
        await self.page.mouse.click(*self.current_pos, button=button)
    
    async def scroll(self, delta_y: int = 0) -> None:
        await self.page.mouse.wheel(0, delta_y)

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    global browser_data, browser_lock
    
    if browser_data:
        try:
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        
        # Находим путь к браузеру
        chromium_path = get_chromium_path()
        if not chromium_path:
            # Пробуем установить
            install_browser()
            chromium_path = get_chromium_path()
        
        print(f"🔍 Использую браузер: {chromium_path}")
        
        # Запускаем браузер
        launch_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,720',
                '--headless=new',
            ]
        }
        
        if chromium_path:
            launch_args['executable_path'] = chromium_path
        
        browser = await p.chromium.launch(**launch_args)
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
        )
        page = await context.new_page()
        
        # Маскировка
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            
            window.chrome = {
                runtime: { connect: () => {}, sendMessage: () => {} },
                app: { isInstalled: false },
                webstore: {}
            };
            
            Object.defineProperty(document, 'hidden', { get: () => false });
            Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
            
            if (window.console) {
                console.log = function() {};
                console.debug = function() {};
                console.info = function() {};
                console.warn = function() {};
            }
        """)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page
        }
        
        logger.info("✅ Браузер запущен")
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐦 **X.com Bot**\n\n"
        "📌 **Команды:**\n"
        "/login — авторизация в X.com\n"
        "/tweet <номер> — показать пост\n"
        "/last — последний пост\n"
        "/tweets — список постов\n"
        "/like <номер> — лайкнуть пост\n"
        "/search <запрос> — поиск постов\n"
        "/user <ник> — перейти к пользователю\n"
        "/screen — скриншот\n"
        "/status — статус браузера\n"
        "/close — закрыть браузер"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await browser['context'].clear_cookies()
        await page.goto('about:blank')
        await page.wait_for_timeout(2000)
        
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([{
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': '.x.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False
                }])
            except Exception as e:
                logger.warning(f"Cookie error {cookie['name']}: {e}")
        
        await msg.edit_text("🔄 Загружаю X.com...")
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(5000)
        
        cookies = await browser['context'].cookies()
        auth_token = next((c for c in cookies if c.get('name') == 'auth_token'), None)
        ct0 = next((c for c in cookies if c.get('name') == 'ct0'), None)
        
        status_msg = f"✅ X.com\n\n🍪 auth_token: {'✅' if auth_token else '❌'}\n🍪 ct0: {'✅' if ct0 else '❌'}\n"
        
        tweet_btn = await page.query_selector('[data-testid="tweetButton"]')
        if tweet_btn:
            status_msg += "\n✅ **ВЫ АВТОРИЗОВАНЫ!**"
        else:
            status_msg += "\n❌ **НЕ АВТОРИЗОВАН**"
        
        await msg.edit_text(status_msg)
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 X.com")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def get_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи номер: /tweet 1")
        return
    
    try:
        num = int(context.args[0]) - 1
        if num < 0:
            num = 0
    except:
        await update.message.reply_text("❌ Укажи число")
        return
    
    msg = await update.message.reply_text(f"🔍 Ищу пост #{num + 1}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Ждем загрузки постов
        try:
            await page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        except:
            await msg.edit_text("❌ Посты не загрузились. Попробуй /login сначала")
            return
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    const authorEl = el.querySelector('[data-testid="User-Name"]');
                    const author = authorEl?.textContent?.trim() || 'Unknown';
                    const likeEl = el.querySelector('[data-testid="like"]');
                    const retweetEl = el.querySelector('[data-testid="retweet"]');
                    const replyEl = el.querySelector('[data-testid="reply"]');
                    const timeEl = el.querySelector('time');
                    
                    result.push({
                        text: text,
                        author: author,
                        likes: likeEl?.textContent?.trim() || '0',
                        retweets: retweetEl?.textContent?.trim() || '0',
                        replies: replyEl?.textContent?.trim() || '0',
                        time: timeEl?.getAttribute('datetime') || '',
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2,
                        width: rect.width,
                        height: rect.height
                    });
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        if num >= len(posts):
            await msg.edit_text(f"❌ Пост #{num + 1} не найден. Всего: {len(posts)}")
            return
        
        posts_reversed = list(reversed(posts))
        post = posts_reversed[num]
        
        # Двигаемся к посту
        joystick = JoystickController(page)
        await joystick.init_position()
        await joystick.human_like_move(post['x'], post['y'])
        
        result = f"📌 **#{num + 1}** @{post['author']}\n\n"
        result += f"{post['text'][:500]}\n\n"
        result += f"❤️ {post['likes']}  🔁 {post['retweets']}  💬 {post['replies']}\n"
        
        if post['time']:
            try:
                dt = datetime.fromisoformat(post['time'].replace('Z', '+00:00'))
                result += f"🕐 {dt.strftime('%d %b %Y, %H:%M')}"
            except:
                pass
        
        await msg.edit_text(result)
        
        # Скриншот поста
        viewport = await page.viewport_size()
        if viewport:
            clip = {
                'x': max(0, post['x'] - post['width']/2 - 20),
                'y': max(0, post['y'] - post['height']/2 - 20),
                'width': min(post['width'] + 40, viewport['width']),
                'height': min(post['height'] + 40, viewport['height'])
            }
            try:
                screenshot = await page.screenshot(clip=clip, type='jpeg', quality=85)
                await update.message.reply_photo(photo=screenshot, caption=f"📸 Пост #{num + 1}")
            except:
                pass
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def last_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ['1']
    await get_tweet(update, context)

async def list_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Ищу посты...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await msg.edit_text("📜 Скроллю вниз...")
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 800)')
            await asyncio.sleep(0.8)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach((el, i) => {
                    const text = el.textContent?.trim() || '';
                    const authorEl = el.querySelector('[data-testid="User-Name"]');
                    const author = authorEl?.textContent?.trim()?.replace(/·/g, '').trim() || 'Unknown';
                    const likeEl = el.querySelector('[data-testid="like"]');
                    const retweetEl = el.querySelector('[data-testid="retweet"]');
                    
                    result.push({
                        index: i + 1,
                        author: author,
                        preview: text.split('\\n').filter(l => l.trim()).join(' ').slice(0, 120),
                        likes: likeEl?.textContent?.trim() || '0',
                        retweets: retweetEl?.textContent?.trim() || '0'
                    });
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        result = f"📋 **НАЙДЕНО {len(posts)} ПОСТОВ**\n\n"
        for post in posts[:10]:
            result += f"**#{post['index']}** @{post['author']}\n   {post['preview']}\n   ❤️ {post['likes']}  🔁 {post['retweets']}\n\n"
        
        if len(posts) > 10:
            result += f"... и еще {len(posts) - 10} постов"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def like_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи номер: /like 1")
        return
    
    try:
        num = int(context.args[0]) - 1
    except:
        await update.message.reply_text("❌ Укажи число")
        return
    
    msg = await update.message.reply_text(f"❤️ Ищу пост #{num + 1}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        posts = await page.query_selector_all('[data-testid="tweet"]')
        if not posts or num >= len(posts):
            await msg.edit_text("❌ Пост не найден")
            return
        
        post = posts[len(posts) - 1 - num]
        like_btn = await post.query_selector('[data-testid="like"]')
        
        if not like_btn:
            await msg.edit_text("❌ Кнопка Like не найдена")
            return
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        box = await like_btn.bounding_box()
        await joystick.human_like_move(box['x'] + box['width']/2, box['y'] + box['height']/2)
        await joystick.click()
        
        await msg.edit_text(f"❤️ Лайкнут пост #{num + 1}!")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def search_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Что ищем? /search текст")
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Скроллим для загрузки
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 600)')
            await asyncio.sleep(0.5)
        
        posts = await page.evaluate(f'''
            () => {{
                const query = '{query.lower()}';
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach((el, i) => {{
                    const text = el.textContent?.trim() || '';
                    if (text.toLowerCase().includes(query)) {{
                        const authorEl = el.querySelector('[data-testid="User-Name"]');
                        const author = authorEl?.textContent?.trim()?.replace(/·/g, '').trim() || 'Unknown';
                        result.push({{
                            index: i + 1,
                            author: author,
                            preview: text.split('\\n').filter(l => l.trim()).join(' ').slice(0, 200)
                        }});
                    }}
                }});
                return result;
            }}
        ''')
        
        if not posts:
            await msg.edit_text(f"❌ Посты с '{query}' не найдены")
            return
        
        result = f"🔍 **НАЙДЕНО {len(posts)} ПОСТОВ** по запросу: '{query}'\n\n"
        for post in posts[:5]:
            result += f"**#{post['index']}** @{post['author']}\n   {post['preview']}\n\n"
        
        if len(posts) > 5:
            result += f"... и еще {len(posts) - 5} постов"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def go_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи ник: /user elonmusk")
        return
    
    username = context.args[0].replace('@', '')
    msg = await update.message.reply_text(f"👤 Перехожу к @{username}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto(f"https://x.com/{username}", wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)
        
        await msg.edit_text(f"✅ Перешел к @{username}")
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption=f"👤 @{username}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.delete()
        await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        browser = await get_browser()
        page = browser['page']
        url = page.url
        title = await page.title()
        
        await update.message.reply_text(
            f"✅ Браузер работает!\n"
            f"📌 {title[:40] if title else 'Нет заголовка'}\n"
            f"🔗 {url[:60]}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("tweet", get_tweet))
    app.add_handler(CommandHandler("last", last_tweet))
    app.add_handler(CommandHandler("tweets", list_tweets))
    app.add_handler(CommandHandler("like", like_tweet))
    app.add_handler(CommandHandler("search", search_tweets))
    app.add_handler(CommandHandler("user", go_to_user))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🐦 X.com Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()