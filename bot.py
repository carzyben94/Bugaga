# bot.py - Полный бот с джойстиком, AI управлением, поиском постов и переводом ON/OFF
import os
import sys
import subprocess
import json
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
from playwright.async_api import Page, async_playwright
from playwright_stealth import stealth_async
import requests  # Для перевода

# ========== НАСТРОЙКА ПЕРЕВОДА ==========
translate_enabled = True  # По умолчанию перевод ВКЛЮЧЕН

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

# ========== ФУНКЦИЯ ПЕРЕВОДА ==========
async def translate_text(text: str, target_lang: str = 'ru') -> str:
    """Переводит текст через бесплатный API"""
    if not translate_enabled or not text or len(text) < 5:
        return text
    
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': 'auto',
            'tl': target_lang,
            'dt': 't',
            'q': text[:500]
        }
        response = requests.get(url, params=params, timeout=3)
        if response.status_code == 200:
            data = response.json()
            translated = ''.join([part[0] for part in data[0] if part[0]])
            if translated:
                return translated
    except Exception as e:
        logger.warning(f"Translation error: {e}")
    return text

# ========== КЛАСС ДЖОЙСТИКА ==========
@dataclass
class JoystickState:
    x: float = 0.0
    y: float = 0.0
    speed: float = 1.0
    smoothness: float = 0.3

class JoystickController:
    """Управление мышью как джойстиком для AI-агентов"""
    
    def __init__(self, page: Page):
        self.page = page
        self.state = JoystickState()
        self.current_pos = (0, 0)
        self.is_moving = False
        self.move_task = None
        self.viewport_width = 1920
        self.viewport_height = 1080
        
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
    
    async def move_joystick(self, x: float, y: float, duration: float = 0.5, speed_mult: float = 1.0) -> Tuple[int, int]:
        max_move = 200 * speed_mult
        dx = x * max_move
        dy = y * max_move
        
        cx, cy = self.current_pos
        target_x = max(0, min(self.viewport_width, cx + dx))
        target_y = max(0, min(self.viewport_height, cy + dy))
        
        steps = max(1, int(duration * 60))
        
        for i in range(steps):
            progress = (i + 1) / steps
            eased = self._ease_in_out(progress)
            
            cur_x = cx + (target_x - cx) * eased
            cur_y = cy + (target_y - cy) * eased
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
        
        return self.current_pos
    
    async def move_to_element(self, selector: str, offset_x: int = 0, offset_y: int = 0, duration: float = 0.5) -> bool:
        try:
            element = await self.page.query_selector(selector)
            if not element:
                return False
            
            box = await element.bounding_box()
            if not box:
                return False
            
            target_x = box['x'] + box['width'] // 2 + offset_x
            target_y = box['y'] + box['height'] // 2 + offset_y
            
            cx, cy = self.current_pos
            steps = max(1, int(duration * 60))
            
            for i in range(steps):
                progress = (i + 1) / steps
                eased = self._ease_in_out(progress)
                
                cur_x = cx + (target_x - cx) * eased
                cur_y = cy + (target_y - cy) * eased
                
                await self.page.mouse.move(cur_x, cur_y)
                self.current_pos = (cur_x, cur_y)
                
                if i < steps - 1:
                    await asyncio.sleep(duration / steps)
            
            return True
            
        except Exception as e:
            logger.error(f"Move to element error: {e}")
            return False
    
    async def click(self, button: str = 'left', double: bool = False, delay: float = 0.1) -> None:
        await asyncio.sleep(delay)
        
        if double:
            await self.page.mouse.dblclick(*self.current_pos)
        else:
            if button == 'left':
                await self.page.mouse.click(*self.current_pos)
            elif button == 'right':
                await self.page.mouse.click(*self.current_pos, button='right')
            elif button == 'middle':
                await self.page.mouse.click(*self.current_pos, button='middle')
    
    async def drag(self, target_x: float, target_y: float, duration: float = 0.5) -> None:
        cx, cy = self.current_pos
        
        await self.page.mouse.down()
        
        steps = max(1, int(duration * 60))
        for i in range(steps):
            progress = (i + 1) / steps
            eased = self._ease_in_out(progress)
            
            cur_x = cx + (target_x - cx) * eased
            cur_y = cy + (target_y - cy) * eased
            
            await self.page.mouse.move(cur_x, cur_y)
            self.current_pos = (cur_x, cur_y)
            
            if i < steps - 1:
                await asyncio.sleep(duration / steps)
        
        await self.page.mouse.up()
    
    async def scroll(self, delta_x: int = 0, delta_y: int = 0) -> None:
        await self.page.mouse.wheel(delta_x, delta_y)
    
    async def human_like_move(self, target_x: int, target_y: int, speed: float = 1.0) -> None:
        cx, cy = self.current_pos
        
        distance = math.sqrt((target_x - cx)**2 + (target_y - cy)**2)
        duration = min(2.0, distance / (800 * speed)) + random.uniform(0.1, 0.3)
        
        steps = max(1, int(duration * 60))
        
        for i in range(steps):
            progress = (i + 1) / steps
            
            human_progress = self._human_curve(progress)
            
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
    
    async def explore_screen(self) -> List[Dict[str, Any]]:
        try:
            elements = await self.page.evaluate('''
                () => {
                    const result = [];
                    const selectors = [
                        'button', 
                        'a[href]', 
                        'input', 
                        'textarea',
                        'select',
                        '[role="button"]',
                        '[role="link"]',
                        '[role="checkbox"]',
                        '[role="radio"]',
                        '[role="tab"]',
                        '[role="menuitem"]',
                        '[role="option"]',
                        '[contenteditable="true"]',
                        '[data-testid]'
                    ];
                    
                    document.querySelectorAll(selectors.join(',')).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                            const text = el.textContent?.trim() || '';
                            const ariaLabel = el.getAttribute('aria-label') || '';
                            const placeholder = el.getAttribute('placeholder') || '';
                            const value = el.value || '';
                            
                            result.push({
                                tag: el.tagName.toLowerCase(),
                                type: el.type || '',
                                text: text.slice(0, 100),
                                ariaLabel: ariaLabel.slice(0, 100),
                                placeholder: placeholder.slice(0, 50),
                                value: value.slice(0, 50),
                                testid: el.getAttribute('data-testid') || '',
                                id: el.id || '',
                                className: el.className || '',
                                x: rect.x + rect.width / 2,
                                y: rect.y + rect.height / 2,
                                width: rect.width,
                                height: rect.height,
                                visible: rect.width > 0 && rect.height > 0,
                                disabled: el.disabled || false,
                                readonly: el.readOnly || false
                            });
                        }
                    });
                    return result;
                }
            ''')
            return elements
        except Exception as e:
            logger.error(f"Explore screen error: {e}")
            return []
    
    async def find_and_click(self, description: str) -> bool:
        elements = await self.explore_screen()
        
        if not elements:
            return False
        
        best_match = None
        best_score = 0
        
        keywords = description.lower().split()
        
        for el in elements:
            score = 0
            text_lower = el['text'].lower()
            aria_lower = el['ariaLabel'].lower()
            testid_lower = el['testid'].lower()
            placeholder_lower = el['placeholder'].lower()
            
            for keyword in keywords:
                if keyword in text_lower:
                    score += 3
                if keyword in aria_lower:
                    score += 2
                if keyword in testid_lower:
                    score += 2
                if keyword in placeholder_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = el
        
        if best_match and best_score > 0:
            await self.human_like_move(best_match['x'], best_match['y'])
            await asyncio.sleep(0.2)
            await self.click()
            return True
        
        if elements:
            el = elements[0]
            await self.human_like_move(el['x'], el['y'])
            await asyncio.sleep(0.2)
            await self.click()
            return True
        
        return False
    
    async def continuous_move(self, duration: float = 5.0):
        self.is_moving = True
        start_time = asyncio.get_event_loop().time()
        
        while self.is_moving and (asyncio.get_event_loop().time() - start_time) < duration:
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(50, 200)
            
            cx, cy = self.current_pos
            target_x = max(0, min(self.viewport_width, cx + math.cos(angle) * distance))
            target_y = max(0, min(self.viewport_height, cy + math.sin(angle) * distance))
            
            await self.human_like_move(target_x, target_y, speed=0.7)
            
            if random.random() < 0.1:
                await self.click()
            
            await asyncio.sleep(random.uniform(0.5, 2.0))
        
        self.is_moving = False
    
    def stop_continuous_move(self):
        self.is_moving = False
    
    async def move_with_pattern(self, pattern: str, **kwargs):
        cx, cy = self.current_pos
        duration = kwargs.get('duration', 3.0)
        size = kwargs.get('size', 100)
        steps = max(1, int(duration * 60))
        
        if pattern == 'circle':
            for i in range(steps):
                angle = (i / steps) * 2 * math.pi
                x = cx + math.cos(angle) * size
                y = cy + math.sin(angle) * size
                x = max(0, min(self.viewport_width, x))
                y = max(0, min(self.viewport_height, y))
                await self.page.mouse.move(x, y)
                self.current_pos = (x, y)
                await asyncio.sleep(duration / steps)
                
        elif pattern == 'square':
            points = [
                (cx - size, cy - size),
                (cx + size, cy - size),
                (cx + size, cy + size),
                (cx - size, cy + size),
                (cx - size, cy - size)
            ]
            per_side = max(1, steps // 4)
            for side in range(4):
                start = points[side]
                end = points[side + 1]
                for i in range(per_side):
                    t = i / per_side
                    x = start[0] + (end[0] - start[0]) * t
                    y = start[1] + (end[1] - start[1]) * t
                    x = max(0, min(self.viewport_width, x))
                    y = max(0, min(self.viewport_height, y))
                    await self.page.mouse.move(x, y)
                    self.current_pos = (x, y)
                    await asyncio.sleep(duration / steps)
                    
        elif pattern == 'spiral':
            for i in range(steps):
                t = i / steps
                angle = t * 4 * math.pi
                r = t * size
                x = cx + math.cos(angle) * r
                y = cy + math.sin(angle) * r
                x = max(0, min(self.viewport_width, x))
                y = max(0, min(self.viewport_height, y))
                await self.page.mouse.move(x, y)
                self.current_pos = (x, y)
                await asyncio.sleep(duration / steps)
                
        elif pattern == 'random':
            for _ in range(min(steps, 20)):
                x = random.randint(0, self.viewport_width)
                y = random.randint(0, self.viewport_height)
                await self.human_like_move(x, y)
                await asyncio.sleep(random.uniform(0.3, 1.0))
    
    @staticmethod
    def _ease_in_out(t: float) -> float:
        return t * t * (3.0 - 2.0 * t)
    
    @staticmethod
    def _human_curve(t: float) -> float:
        return 1 - math.pow(1 - t, 2.5)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def log_error(error_msg, traceback_str=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'time': timestamp,
        'error': error_msg,
        'traceback': traceback_str
    }
    error_logs.append(log_entry)
    if len(error_logs) > MAX_LOGS:
        error_logs.pop(0)
    logger.error(f"{error_msg}\n{traceback_str}" if traceback_str else error_msg)

def install_playwright_browser():
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    if os.path.exists(browser_path):
        print("✅ Браузер уже установлен")
        return True
    print("⏳ Устанавливаю браузер Chromium...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
        print("✅ Браузер успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки браузера: {e}")
        return False

install_playwright_browser()

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
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--disable-gpu',
                '--disable-software-rasterizer'
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
        )
        page = await context.new_page()
        await stealth_async(page)
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = {
                runtime: {}
            };
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 4
            });
        """)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page
        }
        
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data, browser_lock
    
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== КОМАНДЫ ПЕРЕВОДА ==========
async def translate_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включает автоматический перевод постов"""
    global translate_enabled
    translate_enabled = True
    await update.message.reply_text("✅ **Перевод ВКЛЮЧЕН**\n\nТеперь все посты будут автоматически переводиться на русский язык.")

async def translate_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выключает автоматический перевод постов"""
    global translate_enabled
    translate_enabled = False
    await update.message.reply_text("❌ **Перевод ВЫКЛЮЧЕН**\n\nПосты будут показываться в оригинале.")

async def translate_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус перевода"""
    status = "✅ ВКЛЮЧЕН" if translate_enabled else "❌ ВЫКЛЮЧЕН"
    await update.message.reply_text(
        f"🔤 **Статус перевода:** {status}\n\n"
        f"📌 Команды:\n"
        f"/translate_on - включить перевод\n"
        f"/translate_off - выключить перевод"
    )

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с браузером Playwright + Джойстик\n\n"
        "📌 Основные команды:\n"
        "/go <url> - открыть сайт\n"
        "/xlogin - вход в X.com\n"
        "/explore - исследовать интерфейс X.com\n"
        "/findbuttons - найти все кнопки\n"
        "/click <testid> - клик по data-testid\n"
        "/screen - скриншот\n"
        "/status - состояние браузера\n"
        "/stats - статистика\n"
        "/check - проверка авторизации\n"
        "/logs - показать логи\n"
        "/close - закрыть браузер\n\n"
        "🎮 Команды джойстика:\n"
        "/joystick - тест джойстика\n"
        "/joystick_ai <задача> - AI поиск и клик\n"
        "/find <запрос> - найти элементы\n\n"
        "🐦 Команды для постов:\n"
        "/user <ник> - перейти к пользователю\n"
        "/tweet <номер> - показать пост\n"
        "/last - последний пост\n"
        "/tweets - все посты\n"
        "/like_tweet <номер> - лайкнуть пост\n"
        "/find_tweet <текст> - найти пост по тексту\n\n"
        "🔍 Поиск постов:\n"
        "/search <запрос> - найти посты по ключевому слову\n"
        "/search_author @ник - найти посты автора\n"
        "/search_hashtag #хештег - найти посты по хештегу\n\n"
        "🔤 Перевод:\n"
        "/translate_on - включить перевод\n"
        "/translate_off - выключить перевод\n"
        "/translate_status - статус перевода"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await msg.edit_text(f"✅ Открыл: {url}")
    except Exception as e:
        error_msg = f"Ошибка в go: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        logger.info(f"User {update.effective_user.id} начал xlogin")
        
        await page.goto('about:blank')
        await page.wait_for_timeout(1000)
        
        try:
            await browser['context'].clear_cookies()
            logger.info("Старые куки очищены")
        except Exception as e:
            logger.warning(f"Ошибка очистки кук: {e}")
            await close_browser()
            browser = await get_browser()
            page = browser['page']
        
        cookie_errors = []
        cookie_success = []
        
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([cookie])
                cookie_success.append(cookie['name'])
            except Exception as e:
                error_msg = f"Ошибка установки куки {cookie['name']}: {str(e)}"
                cookie_errors.append(error_msg)
                logger.warning(error_msg)
        
        log_msg = f"✅ Установлено кук: {len(cookie_success)}\n"
        log_msg += f"❌ Ошибок: {len(cookie_errors)}\n"
        
        if cookie_errors:
            log_msg += f"\n⚠️ Ошибки установки:\n" + "\n".join(cookie_errors[:3])
            if len(cookie_errors) > 3:
                log_msg += f"\n... и еще {len(cookie_errors)-3}"
        
        log_msg += "\n\n🔄 Перехожу на x.com..."
        try:
            await page.goto('https://x.com', wait_until='commit', timeout=15000)
            logger.info("Страница начала загрузку")
            await page.wait_for_timeout(5000)
            
            try:
                await page.wait_for_selector('body', timeout=10000)
                logger.info("Body загружен")
            except:
                logger.warning("Body не загружен")
            
        except Exception as e:
            error_msg = f"Ошибка загрузки: {str(e)}"
            log_error(error_msg, traceback.format_exc())
            log_msg += f"\n❌ {error_msg}"
            
            try:
                await page.reload(wait_until='domcontentloaded', timeout=15000)
                log_msg += "\n🔄 Страница перезагружена"
                await page.wait_for_timeout(3000)
            except:
                pass
        
        try:
            current_url = page.url
            log_msg += f"\n📍 URL: {current_url[:80]}"
        except:
            log_msg += f"\n📍 URL: Недоступен"
        
        is_logged = False
        try:
            selectors = [
                ("primary_column", '[data-testid="primaryColumn"]'),
                ("tweet_button", '[data-testid="tweetButton"]'),
                ("profile_link", '[data-testid="AppTabBar_Profile_Link"]'),
                ("login_form", '[data-testid="loginForm"]'),
                ("toast_error", '[data-testid="toast"]'),
                ("challenge", '[data-testid="challenge"]')
            ]
            
            selector_results = []
            for name, selector in selectors:
                try:
                    exists = await page.query_selector(selector) is not None
                    selector_results.append(f"{name}: {'✅' if exists else '❌'}")
                    if name == "primary_column" and exists:
                        is_logged = True
                except Exception as e:
                    selector_results.append(f"{name}: ⚠️ ошибка")
            
            log_msg += "\n\n🔍 Элементы:\n" + "\n".join(selector_results)
            
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки элементов: {str(e)}"
        
        try:
            cookies_in_browser = await browser['context'].cookies()
            auth_token = next((c for c in cookies_in_browser if c.get('name') == 'auth_token'), None)
            log_msg += f"\n\n🍪 Кук: {len(cookies_in_browser)}"
            log_msg += f"\n🔑 auth_token: {'✅' if auth_token else '❌'}"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки кук: {str(e)}"
        
        try:
            title = await page.title()
            log_msg += f"\n\n📌 Заголовок: {title[:60] if title else 'Нет заголовка'}"
        except:
            log_msg += f"\n\n📌 Заголовок: Недоступен"
        
        screenshot = None
        try:
            screenshot = await page.screenshot(
                full_page=False,
                type='jpeg',
                quality=80
            )
            log_msg += f"\n\n📸 Скриншот сделан"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка скриншота: {str(e)}"
        
        await msg.edit_text(
            f"✅ Зашёл в X.com!\n\n{log_msg}"
        )
        
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Скриншот {datetime.now().strftime('%H:%M:%S')}"
            )
        
        logger.info(f"xlogin завершен, статус: {is_logged}")
        
    except Exception as e:
        error_msg = f"Критическая ошибка: {str(e)}"
        traceback_str = traceback.format_exc()
        log_error(error_msg, traceback_str)
        
        if "closed" in str(e).lower():
            await close_browser()
            await msg.edit_text("❌ Браузер закрыт. Попробуйте снова /xlogin")
        else:
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Исследую интерфейс X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        current_url = page.url
        if 'x.com' not in current_url:
            await msg.edit_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        explore_result = "🔍 ИССЛЕДОВАНИЕ ИНТЕРФЕЙСА X.COM\n\n"
        
        try:
            title = await page.title()
            explore_result += f"📌 Заголовок: {title[:60]}\n"
            explore_result += f"📍 URL: {current_url[:80]}\n\n"
        except:
            pass
        
        explore_result += "🔘 НАЙДЕННЫЕ КНОПКИ:\n"
        try:
            buttons = await page.evaluate('''
                () => {
                    const buttons = [];
                    document.querySelectorAll('button, [role="button"], [data-testid*="button"]').forEach(el => {
                        const text = el.textContent?.trim() || '';
                        const testId = el.getAttribute('data-testid') || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const type = el.getAttribute('type') || '';
                        const className = el.className || '';
                        buttons.push({
                            text: text.slice(0, 50),
                            testId: testId.slice(0, 50),
                            ariaLabel: ariaLabel.slice(0, 50),
                            type: type,
                            class: className.slice(0, 50)
                        });
                    });
                    return buttons;
                }
            ''')
            
            if buttons:
                button_groups = {}
                for btn in buttons:
                    key = btn['testId'] or btn['ariaLabel'] or btn['text'] or 'unknown'
                    if key not in button_groups:
                        button_groups[key] = 0
                    button_groups[key] += 1
                
                count = 0
                for key, value in list(button_groups.items())[:20]:
                    if key and key != 'unknown':
                        explore_result += f"  • {key}: {value} шт.\n"
                        count += 1
                
                if count == 0:
                    explore_result += "  ⚠️ Кнопки не найдены\n"
                else:
                    explore_result += f"\n  Всего уникальных кнопок: {len(button_groups)}\n"
            else:
                explore_result += "  ❌ Кнопки не найдены\n"
        except Exception as e:
            explore_result += f"  ⚠️ Ошибка поиска кнопок: {str(e)[:50]}\n"
        
        explore_result += "\n🏷️ DATA-TESTID ЭЛЕМЕНТЫ:\n"
        try:
            testids = await page.evaluate('''
                () => {
                    const elements = {};
                    document.querySelectorAll('[data-testid]').forEach(el => {
                        const id = el.getAttribute('data-testid');
                        if (id) {
                            elements[id] = (elements[id] || 0) + 1;
                        }
                    });
                    return elements;
                }
            ''')
            
            if testids:
                sorted_ids = sorted(testids.items(), key=lambda x: x[1], reverse=True)
                count = 0
                for testid, count_elem in sorted_ids[:30]:
                    explore_result += f"  • {testid}: {count_elem} шт.\n"
                    count += 1
                
                if count == 0:
                    explore_result += "  ⚠️ data-testid не найдены\n"
                else:
                    explore_result += f"\n  Всего data-testid: {len(testids)}\n"
            else:
                explore_result += "  ❌ data-testid не найдены\n"
        except Exception as e:
            explore_result += f"  ⚠️ Ошибка поиска data-testid: {str(e)[:50]}\n"
        
        explore_result += "\n📝 ФОРМЫ:\n"
        try:
            forms = await page.evaluate('''
                () => {
                    const forms = [];
                    document.querySelectorAll('form').forEach(el => {
                        const action = el.getAttribute('action') || '';
                        const method = el.getAttribute('method') || '';
                        const inputs = el.querySelectorAll('input, textarea, select').length;
                        forms.push({ action: action.slice(0, 50), method: method, inputs: inputs });
                    });
                    return forms;
                }
            ''')
            
            if forms:
                for i, form in enumerate(forms[:5], 1):
                    explore_result += f"  Форма {i}: action={form['action'] or 'не указан'}, method={form['method'] or 'get'}, полей={form['inputs']}\n"
            else:
                explore_result += "  ❌ Формы не найдены\n"
        except Exception as e:
            explore_result += f"  ⚠️ Ошибка поиска форм: {str(e)[:50]}\n"
        
        explore_result += "\n🔗 ССЫЛКИ:\n"
        try:
            links = await page.evaluate('''
                () => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(el => {
                        const href = el.getAttribute('href');
                        const text = el.textContent?.trim() || '';
                        if (href && !href.startsWith('javascript:')) {
                            links.push({
                                href: href.slice(0, 60),
                                text: text.slice(0, 40)
                            });
                        }
                    });
                    return links;
                }
            ''')
            
            if links:
                explore_result += f"  Всего ссылок: {len(links)}\n"
                for i, link in enumerate(links[:5], 1):
                    explore_result += f"  {i}. {link['text'] or 'без текста'} → {link['href']}\n"
            else:
                explore_result += "  ❌ Ссылки не найдены\n"
        except Exception as e:
            explore_result += f"  ⚠️ Ошибка поиска ссылок: {str(e)[:50]}\n"
        
        try:
            html_content = await page.content()
            html_filename = f"x_com_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            explore_result += f"\n💾 HTML сохранен: {html_filename} ({len(html_content)} символов)"
            
            await update.message.reply_document(
                document=open(html_filename, 'rb'),
                filename=html_filename,
                caption="📄 HTML страницы X.com"
            )
            os.remove(html_filename)
            
        except Exception as e:
            explore_result += f"\n⚠️ Ошибка сохранения HTML: {str(e)[:50]}"
        
        try:
            screenshot = await page.screenshot(
                full_page=False,
                type='jpeg',
                quality=80
            )
            
            await update.message.reply_photo(
                photo=screenshot,
                caption="📸 Скриншот X.com"
            )
        except Exception as e:
            explore_result += f"\n⚠️ Ошибка скриншота: {str(e)[:50]}"
        
        if len(explore_result) > 4000:
            with open('explore_result.txt', 'w') as f:
                f.write(explore_result)
            await update.message.reply_document(
                document=open('explore_result.txt', 'rb'),
                filename=f"explore_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            os.remove('explore_result.txt')
        else:
            await msg.edit_text(explore_result)
        
        logger.info(f"Explore завершен для user {update.effective_user.id}")
        
    except Exception as e:
        error_msg = f"Ошибка в explore: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def findbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Ищу кнопки...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        buttons = [el for el in elements if el['tag'] == 'button' or 'button' in el.get('role', '')]
        
        if buttons:
            result = "🔘 НАЙДЕННЫЕ КНОПКИ:\n\n"
            for i, btn in enumerate(buttons[:30], 1):
                result += f"{i}. {btn['text'][:50] or 'без текста'}\n"
                if btn['testid']:
                    result += f"   🏷️ {btn['testid']}\n"
                if btn['ariaLabel']:
                    result += f"   🏷️ aria-label: {btn['ariaLabel']}\n"
                result += f"   📍 ({int(btn['x'])}, {int(btn['y'])})\n\n"
            
            if len(buttons) > 30:
                result += f"... и еще {len(buttons) - 30} кнопок"
            else:
                result += f"Всего кнопок: {len(buttons)}"
            
            if len(result) > 4000:
                with open('buttons.txt', 'w') as f:
                    f.write(result)
                await update.message.reply_document(
                    document=open('buttons.txt', 'rb'),
                    filename=f"buttons_{datetime.now().strftime('%Y%m%d')}.txt"
                )
                os.remove('buttons.txt')
            else:
                await msg.edit_text(result)
        else:
            await msg.edit_text("❌ Кнопки не найдены")
            
    except Exception as e:
        error_msg = f"Ошибка в findbuttons: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def click_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи data-testid кнопки\n"
            "Пример: /click AppTabBar_Explore_Link\n\n"
            "📌 Доступные кнопки:\n"
            "• AppTabBar_Home_Link - Главная\n"
            "• AppTabBar_Explore_Link - Обзор\n"
            "• AppTabBar_Notifications_Link - Уведомления\n"
            "• AppTabBar_Profile_Link - Профиль\n"
            "• AppTabBar_DirectMessage_Link - Чат\n"
            "• SideNav_NewTweet_Button - Новый пост\n"
            "• tweetButton - Опубликовать\n"
            "• reply - Ответить\n"
            "• retweet - Репост\n"
            "• like - Нравится\n"
            "• bookmark - Закладка"
        )
        return
    
    testid = context.args[0]
    msg = await update.message.reply_text(f"⏳ Ищу кнопку {testid}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        selector = f'[data-testid="{testid}"]'
        success = await joystick.move_to_element(selector)
        
        if not success:
            await msg.edit_text(f"❌ Кнопка {testid} не найдена")
            return
        
        await joystick.click()
        await asyncio.sleep(1)
        
        screenshot = await page.screenshot(
            full_page=False,
            type='jpeg',
            quality=80
        )
        
        await msg.edit_text(f"✅ Нажал на {testid}")
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 После клика на {testid}"
        )
        
    except Exception as e:
        error_msg = f"Ошибка в click_button: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(
            full_page=False,
            type='jpeg',
            quality=80
        )
        
        await msg.delete()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот текущей страницы"
        )
    except Exception as e:
        error_msg = f"Ошибка в screen: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверка браузера...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        url = page.url
        title = await page.title()
        
        await msg.edit_text(
            f"✅ Браузер работает!\n"
            f"📌 Страница: {title[:40] if title else 'Нет заголовка'}\n"
            f"🔗 URL: {url[:50]}"
        )
    except Exception as e:
        error_msg = f"Ошибка в status: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    installed = os.path.exists(browser_path)
    
    is_open = "❌"
    url = "Нет"
    if browser_data:
        try:
            page = browser_data['page']
            url = page.url
            is_open = "✅"
        except:
            is_open = "❌ (закрыт)"
    
    await update.message.reply_text(
        f"📊 Статистика\n\n"
        f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"🌐 Браузер: {'✅' if installed else '❌'}\n"
        f"📂 Браузер открыт: {is_open}\n"
        f"🔗 Текущий URL: {url[:50]}\n"
        f"🍪 Куки: {len(COOKIES)} шт."
    )

async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        checks = {
            'primary_column': await page.query_selector('[data-testid="primaryColumn"]'),
            'tweet_button': await page.query_selector('[data-testid="tweetButton"]'),
            'profile_link': await page.query_selector('[data-testid="AppTabBar_Profile_Link"]'),
            'login_form': await page.query_selector('[data-testid="loginForm"]'),
            'challenge': await page.query_selector('[data-testid="challenge"]')
        }
        
        status_msg = "🔍 СТАТУС АВТОРИЗАЦИИ:\n\n"
        for name, element in checks.items():
            status_msg += f"{name}: {'✅' if element else '❌'}\n"
        
        cookies = await browser['context'].cookies()
        auth_token = next((c for c in cookies if c.get('name') == 'auth_token'), None)
        ct0 = next((c for c in cookies if c.get('name') == 'ct0'), None)
        
        status_msg += f"\n🍪 auth_token: {'✅' if auth_token else '❌'}"
        status_msg += f"\n🍪 ct0: {'✅' if ct0 else '❌'}"
        
        try:
            current_url = page.url
            status_msg += f"\n\n📍 URL: {current_url[:80]}"
        except:
            status_msg += f"\n\n📍 URL: Недоступен"
        
        try:
            title = await page.title()
            status_msg += f"\n📌 Заголовок: {title[:60] if title else 'Нет'}"
        except:
            status_msg += f"\n📌 Заголовок: Недоступен"
        
        status_msg += "\n\n"
        if checks['primary_column'] and checks['profile_link'] and checks['tweet_button']:
            status_msg += "✅ ПОЛНАЯ АВТОРИЗАЦИЯ!"
        elif checks['primary_column'] and checks['profile_link']:
            status_msg += "⚠️ ЧАСТИЧНАЯ АВТОРИЗАЦИЯ (не хватает кнопок)"
        elif checks['primary_column']:
            status_msg += "⚠️ ЧАСТИЧНАЯ АВТОРИЗАЦИЯ (только основная колонка)"
        elif checks['login_form']:
            status_msg += "❌ ТРЕБУЕТСЯ ВХОД"
        elif checks['challenge']:
            status_msg += "⚠️ ТРЕБУЕТСЯ ПРОВЕРКА (капча/Cloudflare)"
        else:
            status_msg += "❌ СТАТУС НЕ ОПРЕДЕЛЕН"
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        error_msg = f"Ошибка в check_auth: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю логи...")
    
    try:
        if error_logs:
            log_text = "📋 Последние ошибки:\n\n"
            for i, log in enumerate(error_logs[-10:], 1):
                log_text += f"{i}. 🕐 {log['time']}\n"
                log_text += f"   ❌ {log['error'][:100]}\n"
                if log.get('traceback'):
                    traceback_preview = log['traceback'].split('\n')[-3:]
                    log_text += f"   📍 {traceback_preview[0][:60]}\n"
                log_text += "\n"
        else:
            log_text = "✅ Ошибок нет"
        
        try:
            with open('bot.log', 'r') as f:
                lines = f.readlines()
                if lines:
                    log_text += "\n📄 Последние записи из файла:\n"
                    last_lines = lines[-5:]
                    log_text += "".join(last_lines)
        except:
            pass
        
        if len(log_text) > 4000:
            with open('logs_temp.txt', 'w') as f:
                f.write(log_text)
            await update.message.reply_document(
                document=open('logs_temp.txt', 'rb'),
                filename=f"logs_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            os.remove('logs_temp.txt')
        else:
            await msg.edit_text(log_text)
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при загрузке логов: {str(e)}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== КОМАНДЫ ДЖОЙСТИКА ==========
async def joystick_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🎮 Тестирую джойстик...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        await msg.edit_text("🔄 Круг...")
        await joystick.move_with_pattern('circle', duration=2.0, size=150)
        
        await msg.edit_text("🔄 Квадрат...")
        await joystick.move_with_pattern('square', duration=2.0, size=150)
        
        await msg.edit_text("🔄 Спираль...")
        await joystick.move_with_pattern('spiral', duration=2.0, size=100)
        
        elements = await joystick.explore_screen()
        
        result = "🎮 ДЖОЙСТИК ТЕСТ\n\n"
        result += f"Найдено элементов: {len(elements)}\n\n"
        
        for i, el in enumerate(elements[:5], 1):
            result += f"{i}. {el['tag']}: {el['text'][:30]}\n"
            result += f"   📍 ({int(el['x'])}, {int(el['y'])})\n"
            result += f"   📐 {int(el['width'])}×{int(el['height'])}\n"
            if el['testid']:
                result += f"   🏷️ testid: {el['testid']}\n"
            result += "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        error_msg = f"Ошибка в joystick_test: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def joystick_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи задачу для AI\n"
            "Пример: /joystick_ai найти кнопку Обзор\n"
            "Пример: /joystick_ai нажать на Войти"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🤖 AI ищет: {task}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        found = None
        best_score = 0
        
        for el in elements:
            score = 0
            text_lower = el['text'].lower()
            testid_lower = el['testid'].lower()
            aria_lower = el['ariaLabel'].lower()
            
            for word in task.lower().split():
                if word in text_lower:
                    score += 3
                if word in testid_lower:
                    score += 2
                if word in aria_lower:
                    score += 2
                for part in [text_lower, testid_lower, aria_lower]:
                    if word in part and len(word) > 2:
                        score += 1
            
            if score > best_score:
                best_score = score
                found = el
        
        if found and best_score > 0:
            await joystick.human_like_move(found['x'], found['y'])
            await asyncio.sleep(0.3)
            await joystick.click()
            
            await msg.edit_text(
                f"✅ AI нашел и нажал!\n\n"
                f"📌 Элемент: {found['tag']}\n"
                f"📝 Текст: {found['text'][:50]}\n"
                f"🏷️ testid: {found['testid'] or 'нет'}\n"
                f"📍 Координаты: ({int(found['x'])}, {int(found['y'])})\n"
                f"🎯 Точность: {best_score} баллов"
            )
        else:
            result = f"❌ AI не нашел подходящий элемент\n\n"
            result += f"Найдено элементов: {len(elements)}\n"
            result += f"Запрос: {task}\n\n"
            result += "📋 Доступные элементы:\n"
            
            for i, el in enumerate(elements[:10], 1):
                result += f"{i}. {el['tag']}: {el['text'][:30]}\n"
                if el['testid']:
                    result += f"   🏷️ {el['testid']}\n"
            
            if len(elements) > 10:
                result += f"\n... и еще {len(elements) - 10} элементов"
            
            await msg.edit_text(result)
            
    except Exception as e:
        error_msg = f"Ошибка в joystick_ai: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def find_elements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Что ищем?\n"
            "Пример: /find кнопка Войти\n"
            "Пример: /find testid tweetButton"
        )
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        found = []
        for el in elements:
            text = el['text'].lower()
            testid = el['testid'].lower()
            aria = el['ariaLabel'].lower()
            el_id = el['id'].lower()
            tag = el['tag'].lower()
            
            if (query.lower() in text or 
                query.lower() in testid or
                query.lower() in aria or
                query.lower() in el_id or
                query.lower() in tag):
                found.append(el)
        
        if found:
            result = f"✅ Найдено {len(found)} элементов:\n\n"
            for i, el in enumerate(found[:10], 1):
                result += f"{i}. {el['tag']}"
                if el['type']:
                    result += f" [{el['type']}]"
                result += f": {el['text'][:30]}\n"
                result += f"   📍 ({int(el['x'])}, {int(el['y'])})\n"
                if el['testid']:
                    result += f"   🏷️ testid: {el['testid']}\n"
                if el['id']:
                    result += f"   🔑 id: {el['id']}\n"
                result += "\n"
            
            if len(found) > 10:
                result += f"... и еще {len(found) - 10} элементов"
            
            if found:
                await joystick.human_like_move(found[0]['x'], found[0]['y'])
                result += "\n\n🖱️ Курсор наведен на первый элемент"
            
            await msg.edit_text(result)
        else:
            await msg.edit_text(
                f"❌ Ничего не найдено по запросу: {query}\n\n"
                f"Всего элементов на странице: {len(elements)}"
            )
            
    except Exception as e:
        error_msg = f"Ошибка в find_elements: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДЫ ДЛЯ ПОСТОВ ==========
async def go_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи ник пользователя\n"
            "Пример: /user elonmusk\n"
            "Пример: /user @elonmusk"
        )
        return
    
    username = context.args[0].replace('@', '')
    msg = await update.message.reply_text(f"👤 Перехожу к @{username}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        url = f"https://x.com/{username}"
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)
        
        await msg.edit_text(f"✅ Перешел к @{username}")
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"👤 Профиль @{username}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def get_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает пост по номеру с движением джойстика, скриншотом и переводом"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи номер поста\n"
            "Пример: /tweet 1 - последний\n"
            "Пример: /tweet 2 - второй сверху"
        )
        return
    
    try:
        num = int(context.args[0]) - 1
        if num < 0:
            num = 0
    except:
        await update.message.reply_text("❌ Укажи число: /tweet 1")
        return
    
    status_msg = await update.message.reply_text(f"🔍 Ищу пост #{num + 1}...")
    
    try:
        browser = await get_browser()
        if not browser:
            await status_msg.edit_text("❌ Браузер не открыт. Сначала /xlogin")
            return
            
        page = browser['page']
        
        current_url = page.url
        if 'x.com' not in current_url:
            await status_msg.edit_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        try:
            await page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        except:
            await status_msg.edit_text("❌ Посты не загрузились. Попробуй обновить страницу")
            return
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                
                tweets.forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    
                    if (rect.width > 0 && rect.height > 0) {
                        const authorEl = el.querySelector('[data-testid="User-Name"]');
                        const author = authorEl?.textContent?.trim() || 'Unknown';
                        
                        const likeEl = el.querySelector('[data-testid="like"]');
                        const retweetEl = el.querySelector('[data-testid="retweet"]');
                        const replyEl = el.querySelector('[data-testid="reply"]');
                        
                        const likes = likeEl?.textContent?.trim() || '0';
                        const retweets = retweetEl?.textContent?.trim() || '0';
                        const replies = replyEl?.textContent?.trim() || '0';
                        
                        const timeEl = el.querySelector('time');
                        const time = timeEl?.getAttribute('datetime') || '';
                        
                        result.push({
                            text: text,
                            author: author,
                            likes: likes,
                            retweets: retweets,
                            replies: replies,
                            time: time,
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            bottom: rect.bottom
                        });
                    }
                });
                return result;
            }
        ''')
        
        if not posts:
            await status_msg.edit_text("❌ Посты не найдены на странице")
            return
        
        if num >= len(posts):
            await status_msg.edit_text(f"❌ Пост #{num + 1} не найден. Всего постов: {len(posts)}")
            return
        
        posts_reversed = list(reversed(posts))
        post = posts_reversed[num]
        
        viewport = await page.viewport_size()
        if not viewport:
            viewport = {'width': 1280, 'height': 720}
        
        if post['top'] < 0 or post['bottom'] > viewport['height']:
            await status_msg.edit_text(f"📜 Скроллю к посту #{num + 1}...")
            
            await page.evaluate(f'''
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                if (tweets.length > {num}) {{
                    const index = tweets.length - {num + 1};
                    tweets[index].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            ''')
            await asyncio.sleep(1.5)
            
            coords = await page.evaluate(f'''
                () => {{
                    const tweets = document.querySelectorAll('[data-testid="tweet"]');
                    if (tweets.length > {num}) {{
                        const index = tweets.length - {num + 1};
                        const el = tweets[index];
                        const rect = el.getBoundingClientRect();
                        return {{
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            bottom: rect.bottom
                        }};
                    }}
                    return null;
                }}
            ''')
            
            if coords:
                post['x'] = coords['x']
                post['y'] = coords['y']
                post['width'] = coords['width']
                post['height'] = coords['height']
        
        # ===== ПОЛУЧАЕМ ТЕКСТ ПОСТА =====
        original_text = post['text']
        
        # ===== ПЕРЕВОД (если включен) =====
        translated_text = None
        if translate_enabled and len(original_text) > 10:
            try:
                translated_text = await translate_text(original_text)
                if translated_text == original_text:
                    translated_text = None
            except:
                pass
        
        # Форматируем время
        time_str = post['time']
        if time_str:
            try:
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                time_str = dt.strftime('%d %b %Y, %H:%M')
            except:
                time_str = post['time'][:10]
        
        # ===== ФОРМИРУЕМ ВЫВОД =====
        text_preview = original_text[:300]
        if len(original_text) > 300:
            text_preview += '...'
        
        result = f"📌 #{num + 1} @{post['author']}\n\n"
        result += f"📝 {text_preview}\n"
        
        # Добавляем перевод, если включен и есть
        if translate_enabled and translated_text:
            trans_preview = translated_text[:300]
            if len(translated_text) > 300:
                trans_preview += '...'
            result += f"\n🇷🇺 {trans_preview}\n"
        
        result += f"\n❤️ {post['likes']}  🔁 {post['retweets']}  💬 {post['replies']}\n"
        result += f"🕐 {time_str}"
        
        # ===== ДВИЖЕНИЕ ДЖОЙСТИКА =====
        await status_msg.edit_text(f"🖱️ Двигаюсь к посту #{num + 1}...")
        
        joystick = JoystickController(page)
        await joystick.init_position()
        await joystick.human_like_move(post['x'], post['y'])
        
        await asyncio.sleep(0.3)
        
        # ===== СКРИНШОТ =====
        await status_msg.edit_text(f"📸 Делаю скриншот поста #{num + 1}...")
        
        screenshot = None
        try:
            clip_x = max(0, post['x'] - post['width']/2 - 20)
            clip_y = max(0, post['y'] - post['height']/2 - 20)
            clip_width = min(post['width'] + 40, viewport['width'])
            clip_height = min(post['height'] + 40, viewport['height'])
            
            if (clip_x + clip_width <= viewport['width'] and 
                clip_y + clip_height <= viewport['height'] and
                clip_width > 20 and clip_height > 20):
                
                screenshot = await page.screenshot(
                    clip={
                        'x': clip_x,
                        'y': clip_y,
                        'width': clip_width,
                        'height': clip_height
                    },
                    type='jpeg',
                    quality=85
                )
            else:
                screenshot = await page.screenshot(type='jpeg', quality=80)
                
        except Exception as e:
            logger.warning(f"Screenshot error: {e}")
            try:
                screenshot = await page.screenshot(type='jpeg', quality=80)
            except:
                pass
        
        # Отправляем результат
        if len(result) > 4000:
            with open('tweet_result.txt', 'w', encoding='utf-8') as f:
                f.write(result)
            await status_msg.edit_text("📄 Пост слишком длинный, отправляю файлом:")
            await update.message.reply_document(
                document=open('tweet_result.txt', 'rb'),
                filename=f"tweet_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            )
            os.remove('tweet_result.txt')
        else:
            await status_msg.edit_text(result)
        
        if screenshot:
            caption = f"📸 Пост #{num + 1}"
            if translate_enabled and translated_text:
                caption += " (с переводом)"
            await update.message.reply_photo(
                photo=screenshot,
                caption=caption
            )
        else:
            await update.message.reply_text("⚠️ Не удалось сделать скриншот поста")
        
    except Exception as e:
        error_msg = f"Ошибка в get_tweet: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        except:
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def last_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последний пост"""
    try:
        browser = await get_browser()
        if not browser:
            await update.message.reply_text("❌ Браузер не открыт. Сначала /xlogin")
            return
            
        page = browser['page']
        current_url = page.url
        if 'x.com' not in current_url:
            await update.message.reply_text("❌ Сначала зайди на X.com через /xlogin")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Браузер не открыт. Сначала /xlogin\nОшибка: {str(e)[:100]}")
        return
    
    old_args = context.args
    context.args = ['1']
    try:
        await get_tweet(update, context)
    finally:
        context.args = old_args

async def list_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех постов"""
    msg = await update.message.reply_text("🔍 Ищу посты...")
    
    try:
        browser = await get_browser()
        if not browser:
            await msg.edit_text("❌ Браузер не открыт. Сначала /xlogin")
            return
            
        page = browser['page']
        
        await msg.edit_text("📜 Скроллю вниз для загрузки постов...")
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 800)')
            await asyncio.sleep(0.8)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                
                tweets.forEach((el, index) => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    
                    const authorEl = el.querySelector('[data-testid="User-Name"]');
                    let author = authorEl?.textContent?.trim() || 'Unknown';
                    author = author.replace(/·/g, '').trim();
                    
                    const isPinned = el.querySelector('[aria-label="Pinned tweet"]') !== null;
                    
                    const likeEl = el.querySelector('[data-testid="like"]');
                    const retweetEl = el.querySelector('[data-testid="retweet"]');
                    const replyEl = el.querySelector('[data-testid="reply"]');
                    
                    const likes = likeEl?.textContent?.trim() || '0';
                    const retweets = retweetEl?.textContent?.trim() || '0';
                    const replies = replyEl?.textContent?.trim() || '0';
                    
                    const timeEl = el.querySelector('time');
                    const time = timeEl?.getAttribute('datetime') || '';
                    
                    const textLines = text.split('\\n').filter(line => line.trim().length > 0);
                    const preview = textLines.slice(0, 2).join(' ').slice(0, 120);
                    
                    result.push({
                        index: index + 1,
                        author: author,
                        text: text,
                        preview: preview,
                        time: time,
                        likes: likes,
                        retweets: retweets,
                        replies: replies,
                        isPinned: isPinned,
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2
                    });
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        result = f"📋 **НАЙДЕНО {len(posts)} ПОСТОВ**\n\n"
        
        for i, post in enumerate(posts, 1):
            if post['isPinned']:
                result += f"📌 **#{i}** (Закреплено) "
            else:
                result += f"**#{i}** "
            
            result += f"@{post['author']}\n"
            
            text_preview = post['preview'][:120]
            if len(post['preview']) > 120:
                text_preview += '...'
            
            if text_preview:
                result += f"   {text_preview}\n"
            
            stats = []
            if post['likes'] != '0':
                stats.append(f"❤️ {post['likes']}")
            if post['retweets'] != '0':
                stats.append(f"🔄 {post['retweets']}")
            if post['replies'] != '0':
                stats.append(f"💬 {post['replies']}")
            
            if stats:
                result += f"   {'  '.join(stats)}\n"
            
            if post['time']:
                try:
                    dt = datetime.fromisoformat(post['time'].replace('Z', '+00:00'))
                    result += f"   🕐 {dt.strftime('%d %b %Y, %H:%M')}\n"
                except:
                    pass
            
            result += "\n"
            
            if len(result) > 3500:
                result += f"\n... и еще {len(posts) - i} постов\n"
                break
        
        if len(result) > 4000:
            with open('tweets_list.txt', 'w', encoding='utf-8') as f:
                f.write(result)
            await msg.edit_text("📄 Список постов слишком длинный, отправляю файлом:")
            await update.message.reply_document(
                document=open('tweets_list.txt', 'rb'),
                filename=f"tweets_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            )
            os.remove('tweets_list.txt')
        else:
            await msg.edit_text(result)
        
    except Exception as e:
        error_msg = f"Ошибка в list_tweets: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def like_tweet_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи номер поста: /like_tweet 1")
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
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        if num >= len(posts):
            await msg.edit_text(f"❌ Пост #{num + 1} не найден")
            return
        
        post = posts[len(posts) - 1 - num]
        like_btn = await post.query_selector('[data-testid="like"]')
        
        if not like_btn:
            await msg.edit_text("❌ Кнопка Like не найдена в этом посте")
            return
        
        await msg.edit_text(f"🖱️ Двигаюсь к кнопке Like...")
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        box = await like_btn.bounding_box()
        await joystick.human_like_move(
            box['x'] + box['width'] / 2,
            box['y'] + box['height'] / 2
        )
        
        await asyncio.sleep(0.2)
        await joystick.click()
        
        await msg.edit_text(f"❤️ Лайкнут пост #{num + 1}!")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def find_tweet_by_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Что ищем? /find_tweet текст")
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        posts = await page.evaluate(f'''
            () => {{
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {{
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    
                    if (text.toLowerCase().includes('{query.lower()}')) {{
                        result.push({{
                            text: text.slice(0, 300),
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2
                        }});
                    }}
                }});
                return result;
            }}
        ''')
        
        if posts:
            post = posts[0]
            
            await msg.edit_text(f"🖱️ Двигаюсь к найденному посту...")
            
            joystick = JoystickController(page)
            await joystick.init_position()
            await joystick.human_like_move(post['x'], post['y'])
            
            result = f"✅ Найден пост:\n\n"
            result += f"{post['text'][:300]}\n\n"
            result += f"📍 Координаты: ({int(post['x'])}, {int(post['y'])})"
            
            await msg.edit_text(result)
        else:
            await msg.edit_text(f"❌ Пост с текстом '{query}' не найден")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ПОИСК ПОСТОВ ==========

async def search_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет посты по ключевому слову с джойстиком и скриншотом"""
    if not context.args:
        await update.message.reply_text(
            "❌ Введи поисковый запрос\n"
            "Пример: /search Bitcoin\n"
            "Пример: /search AI news\n\n"
            "📌 Опции:\n"
            "/search_author @elonmusk - поиск по автору\n"
            "/search_hashtag #BTC - поиск по хештегу"
        )
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        if not browser:
            await msg.edit_text("❌ Браузер не открыт. Сначала /xlogin")
            return
            
        page = browser['page']
        current_url = page.url
        if 'x.com' not in current_url:
            await msg.edit_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        await msg.edit_text(f"🔍 Сканирую ленту на: {query}...")
        
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 600)')
            await asyncio.sleep(0.5)
        
        posts = await page.evaluate(f'''
            () => {{
                const query = '{query.lower()}';
                const result = [];
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                
                tweets.forEach((el, index) => {{
                    const text = el.textContent?.trim() || '';
                    const textLower = text.toLowerCase();
                    
                    if (textLower.includes(query)) {{
                        const rect = el.getBoundingClientRect();
                        
                        const authorEl = el.querySelector('[data-testid="User-Name"]');
                        let author = authorEl?.textContent?.trim() || 'Unknown';
                        author = author.replace(/·/g, '').trim();
                        
                        const likeEl = el.querySelector('[data-testid="like"]');
                        const retweetEl = el.querySelector('[data-testid="retweet"]');
                        const replyEl = el.querySelector('[data-testid="reply"]');
                        
                        const likes = likeEl?.textContent?.trim() || '0';
                        const retweets = retweetEl?.textContent?.trim() || '0';
                        const replies = replyEl?.textContent?.trim() || '0';
                        
                        const timeEl = el.querySelector('time');
                        const time = timeEl?.getAttribute('datetime') || '';
                        
                        const textLines = text.split('\\n').filter(line => line.trim().length > 0);
                        const preview = textLines.slice(0, 3).join(' ').slice(0, 200);
                        
                        result.push({{
                            index: index + 1,
                            author: author,
                            text: text,
                            preview: preview,
                            time: time,
                            likes: likes,
                            retweets: retweets,
                            replies: replies,
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            bottom: rect.bottom
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
        
        for i, post in enumerate(posts[:5], 1):
            result += f"**{i}.** @{post['author']}\n"
            
            text_preview = post['preview'][:200]
            if len(post['preview']) > 200:
                text_preview += '...'
            result += f"   {text_preview}\n"
            
            stats = []
            if post['likes'] != '0':
                stats.append(f"❤️ {post['likes']}")
            if post['retweets'] != '0':
                stats.append(f"🔄 {post['retweets']}")
            if post['replies'] != '0':
                stats.append(f"💬 {post['replies']}")
            if stats:
                result += f"   {'  '.join(stats)}\n"
            
            if post['time']:
                try:
                    dt = datetime.fromisoformat(post['time'].replace('Z', '+00:00'))
                    result += f"   🕐 {dt.strftime('%d %b %H:%M')}\n"
                except:
                    pass
            
            result += "\n"
        
        if len(posts) > 5:
            result += f"... и еще {len(posts) - 5} постов\n"
        
        first_post = posts[0]
        await msg.edit_text(f"🖱️ Двигаюсь к первому найденному посту...")
        
        joystick = JoystickController(page)
        await joystick.init_position()
        await joystick.human_like_move(first_post['x'], first_post['y'])
        
        viewport = await page.viewport_size()
        if not viewport:
            viewport = {'width': 1280, 'height': 720}
        
        screenshot = None
        try:
            clip_x = max(0, first_post['x'] - first_post['width']/2 - 20)
            clip_y = max(0, first_post['y'] - first_post['height']/2 - 20)
            clip_width = min(first_post['width'] + 40, viewport['width'])
            clip_height = min(first_post['height'] + 40, viewport['height'])
            
            if (clip_x + clip_width <= viewport['width'] and 
                clip_y + clip_height <= viewport['height'] and
                clip_width > 20 and clip_height > 20):
                screenshot = await page.screenshot(
                    clip={
                        'x': clip_x,
                        'y': clip_y,
                        'width': clip_width,
                        'height': clip_height
                    },
                    type='jpeg',
                    quality=85
                )
        except Exception as e:
            logger.warning(f"Screenshot error: {e}")
        
        if len(result) > 4000:
            with open('search_result.txt', 'w', encoding='utf-8') as f:
                f.write(result)
            await msg.edit_text(f"📄 Найдено {len(posts)} постов, отправляю файлом:")
            await update.message.reply_document(
                document=open('search_result.txt', 'rb'),
                filename=f"search_{query[:20]}_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            os.remove('search_result.txt')
        else:
            await msg.edit_text(result)
        
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Первый найденный пост по запросу: {query[:30]}"
            )
        
    except Exception as e:
        error_msg = f"Ошибка в search_tweets: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def search_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет посты от конкретного автора"""
    if not context.args:
        await update.message.reply_text("❌ Укажи автора: /search_author @elonmusk")
        return
    
    username = context.args[0].replace('@', '')
    msg = await update.message.reply_text(f"🔍 Ищу посты от @{username}...")
    
    try:
        browser = await get_browser()
        if not browser:
            await msg.edit_text("❌ Браузер не открыт")
            return
            
        page = browser['page']
        
        await page.goto(f"https://x.com/{username}", wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)
        
        await msg.edit_text(f"📜 Сканирую посты @{username}...")
        
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 600)')
            await asyncio.sleep(0.5)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    
                    const likeEl = el.querySelector('[data-testid="like"]');
                    const retweetEl = el.querySelector('[data-testid="retweet"]');
                    const replyEl = el.querySelector('[data-testid="reply"]');
                    
                    result.push({
                        text: text.slice(0, 300),
                        likes: likeEl?.textContent?.trim() || '0',
                        retweets: retweetEl?.textContent?.trim() || '0',
                        replies: replyEl?.textContent?.trim() || '0',
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2
                    });
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text(f"❌ Посты от @{username} не найдены")
            return
        
        joystick = JoystickController(page)
        await joystick.init_position()
        await joystick.human_like_move(posts[0]['x'], posts[0]['y'])
        
        result = f"📋 **ПОСТЫ ОТ @{username}**\n\n"
        for i, post in enumerate(posts[:5], 1):
            result += f"**{i}.** {post['text'][:150]}\n"
            result += f"   ❤️ {post['likes']}  🔄 {post['retweets']}  💬 {post['replies']}\n\n"
        
        if len(posts) > 5:
            result += f"... и еще {len(posts) - 5} постов"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def search_hashtag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет посты с хештегом"""
    if not context.args:
        await update.message.reply_text("❌ Укажи хештег: /search_hashtag #BTC")
        return
    
    hashtag = context.args[0]
    if not hashtag.startswith('#'):
        hashtag = '#' + hashtag
    
    msg = await update.message.reply_text(f"🔍 Ищу посты с {hashtag}...")
    
    try:
        browser = await get_browser()
        if not browser:
            await msg.edit_text("❌ Браузер не открыт")
            return
            
        page = browser['page']
        
        await page.goto(f"https://x.com/search?q={hashtag}&src=typed_query", wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)
        
        await msg.edit_text(f"📜 Сканирую посты с {hashtag}...")
        
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 600)')
            await asyncio.sleep(0.5)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    
                    const authorEl = el.querySelector('[data-testid="User-Name"]');
                    const author = authorEl?.textContent?.trim()?.replace(/·/g, '').trim() || 'Unknown';
                    
                    result.push({
                        text: text.slice(0, 300),
                        author: author,
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2
                    });
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text(f"❌ Посты с {hashtag} не найдены")
            return
        
        joystick = JoystickController(page)
        await joystick.init_position()
        await joystick.human_like_move(posts[0]['x'], posts[0]['y'])
        
        result = f"📋 **ПОСТЫ С {hashtag}**\n\n"
        for i, post in enumerate(posts[:5], 1):
            result += f"**{i}.** @{post['author']}\n"
            result += f"   {post['text'][:150]}\n\n"
        
        if len(posts) > 5:
            result += f"... и еще {len(posts) - 5} постов"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("explore", explore))
    app.add_handler(CommandHandler("findbuttons", findbuttons))
    app.add_handler(CommandHandler("click", click_button))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("check", check_auth))
    app.add_handler(CommandHandler("logs", show_logs))
    app.add_handler(CommandHandler("close", close))
    
    # Команды джойстика
    app.add_handler(CommandHandler("joystick", joystick_test))
    app.add_handler(CommandHandler("joystick_ai", joystick_ai))
    app.add_handler(CommandHandler("find", find_elements))
    
    # Команды для постов
    app.add_handler(CommandHandler("user", go_to_user))
    app.add_handler(CommandHandler("tweet", get_tweet))
    app.add_handler(CommandHandler("last", last_tweet))
    app.add_handler(CommandHandler("tweets", list_tweets))
    app.add_handler(CommandHandler("like_tweet", like_tweet_by_number))
    app.add_handler(CommandHandler("find_tweet", find_tweet_by_text))
    
    # 🔍 Команды поиска
    app.add_handler(CommandHandler("search", search_tweets))
    app.add_handler(CommandHandler("search_author", search_author))
    app.add_handler(CommandHandler("search_hashtag", search_hashtag))
    
    # 🔤 Команды перевода
    app.add_handler(CommandHandler("translate_on", translate_on))
    app.add_handler(CommandHandler("translate_off", translate_off))
    app.add_handler(CommandHandler("translate_status", translate_status))
    
    print("🤖 Бот с джойстиком запущен...")
    print("📌 Доступные команды:")
    print("   Основные: /start, /go, /xlogin, /explore, /findbuttons, /click, /screen, /status, /stats, /check, /logs, /close")
    print("   Джойстик: /joystick, /joystick_ai, /find")
    print("   Посты: /user, /tweet, /last, /tweets, /like_tweet, /find_tweet")
    print("   🔍 Поиск: /search, /search_author, /search_hashtag")
    print("   🔤 Перевод: /translate_on, /translate_off, /translate_status")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()