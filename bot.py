# bot.py - X.com бот с Goose и Agnes AI
import os
import sys
import subprocess
import logging
import asyncio
import json
import requests
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Awaitable
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== ПРОВЕРКА PHANTOMWRIGHT ==========
try:
    from phantomwright_driver.async_api import async_playwright
    PHANTOMWRIGHT_AVAILABLE = True
    print("✅ Phantomwright загружен")
except ImportError:
    PHANTOMWRIGHT_AVAILABLE = False
    print("⚠️ Phantomwright не найден, использую Playwright")
    from playwright.async_api import async_playwright

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

# ========== НАСТРОЙКА AGNES AI ==========
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

def call_agnes(prompt: str, tools: list = None) -> str:
    """Вызывает Agnes-2.0-Flash через OpenAI-совместимый API"""
    if not AGNES_API_KEY:
        return "⚠️ AGNES_API_KEY не задан! Добавь переменную на Railway."

    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": "Ты — AI-агент, управляющий браузером. Отвечай кратко, только результат. Используй эмодзи."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200,
        "tools": tools or [],
        "parallel_tool_calls": True
    }

    try:
        response = requests.post(
            f"{AGNES_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            return result
        else:
            return f"❌ Ошибка Agnes: {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def format_goose_response(text: str) -> str:
    """Форматирует ответ Goose"""
    if not text:
        return "✅ Готово"
    
    lines = text.split('\n')
    cleaned = []
    
    for line in lines:
        if any(x in line for x in [
            'shell', 'command:', 'timeout_secs', 'node -e', 
            'require', 'Module', 'Error:', 'npm install',
            'playwright', 'chromium', 'launch', 'headless',
            'browser.newPage', 'page.goto', 'browser.close',
            'URL:', 'Title:', '---', '```', '─', '│', '▸',
            'const', 'await', 'async', 'function', 'console.log',
            'stdout', 'stderr', 'exit code', 'Command exited'
        ]):
            continue
        if not line.strip():
            continue
        cleaned.append(line.strip())
    
    if not cleaned:
        if 'google' in text.lower():
            return "✅ Google открыт"
        elif 'x.com' in text.lower() or 'twitter' in text.lower():
            return "✅ X.com открыт"
        elif 'error' in text.lower() or 'ошибк' in text.lower():
            return "❌ Ошибка"
        elif 'screenshot' in text.lower() or 'скриншот' in text.lower():
            return "📸 Скриншот сделан"
        else:
            return "✅ Готово"
    
    result = ' '.join(cleaned[:3])
    if len(result) > 200:
        result = result[:200] + '...'
    
    if not any(x in result for x in ['✅', '❌', '📸', '🔗', '📊', '⏳', '🚀', '🔍', '📝', '🖱️']):
        if 'error' in result.lower() or 'ошибк' in result.lower():
            result = "❌ " + result
        elif 'google' in result.lower():
            result = "✅ " + result
        elif 'x.com' in result.lower():
            result = "✅ " + result
        elif 'скриншот' in result.lower():
            result = "📸 " + result
        else:
            result = "✅ " + result
    
    return result

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
browser_lock = False
browser_ws_url = None
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}
active_joysticks = {}

# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ==========
async def check_goose_installed() -> tuple:
    try:
        process = await asyncio.create_subprocess_exec(
            "goose", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            version = stdout.decode().strip() or stderr.decode().strip()
            return True, version
        return False, None
    except FileNotFoundError:
        return False, None

# ========== GOOSE МЕНЕДЖЕР ==========
class GooseManager:
    def __init__(self):
        self.process = None
        self.initialized = False
        self.init_error = None
        
    async def initialize(self):
        if self.initialized:
            return True
            
        try:
            logger.info("🔄 Проверяю Goose...")
            check = await asyncio.create_subprocess_exec(
                "goose", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await check.communicate()
            
            if check.returncode != 0:
                self.init_error = "goose не найден"
                return False
            
            config_dir = os.path.expanduser("~/.config/goose")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.yaml")
            
            config_content = f"""
provider:
  type: openai
  base_url: https://apihub.agnes-ai.com/v1
  api_key: {AGNES_API_KEY or ""}
  model: agnes-2.0-flash
"""
            with open(config_path, "w") as f:
                f.write(config_content)
            logger.info("✅ Конфиг Goose создан")
            
            if not os.path.exists(config_path):
                self.init_error = "Не удалось создать конфиг"
                return False
                
            self.initialized = True
            logger.info("✅ Goose готов к работе")
            return True
                
        except FileNotFoundError:
            self.init_error = "goose не найден в PATH"
            return False
        except Exception as e:
            self.init_error = str(e)[:200]
            logger.error(f"Ошибка: {e}")
            return False
    
    async def execute_command(self, command: str, progress_callback=None) -> str:
        """Выполняет команду через goose run с куками"""
        if not self.initialized:
            success = await self.initialize()
            if not success:
                return f"❌ Не удалось инициализировать Goose: {self.init_error or 'Неизвестная ошибка'}"
        
        if progress_callback:
            await progress_callback("📋 Формирую команду...")
        
        browser_ctx = ""
        if browser_data:
            try:
                page = browser_data['page']
                url = page.url
                browser_ctx = f"Текущая страница: {url}\n"
                if progress_callback:
                    await progress_callback(f"🌐 Текущая страница: {url[:60]}...")
            except:
                pass
        
        full_command = f"{browser_ctx}Выполни в браузере: {command}"
        
        if progress_callback:
            await progress_callback(f"🤖 Отправляю команду: {command[:50]}...")
        
        try:
            env = os.environ.copy()
            env["GOOSE_TELEMETRY_ENABLED"] = "false"
            env["GOOSE_PROVIDER"] = "openai"
            env["OPENAI_BASE_URL"] = "https://apihub.agnes-ai.com/v1"
            env["OPENAI_API_KEY"] = AGNES_API_KEY or ""
            env["GOOSE_MODEL"] = "agnes-2.0-flash"
            
            if progress_callback:
                await progress_callback("🔄 Запускаю Goose...")
            
            cookies_str = "; ".join([f"{c['name']}={c['value']}" for c in COOKIES])
            extension_cmd = f"npx -y @playwright/mcp@latest --cookies '{cookies_str}'"
            
            if progress_callback:
                await progress_callback(f"🔧 Расширение: {extension_cmd[:60]}...")
            
            process = await asyncio.create_subprocess_exec(
                "goose", "run",
                "--with-extension", extension_cmd,
                "-t", full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            if progress_callback:
                await progress_callback("⏳ Выполняю команду...")
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode == 0:
                result = stdout.decode() if stdout else stderr.decode()
                if progress_callback:
                    await progress_callback("✅ Готово!")
                return result if result else "✅ Готово"
            else:
                error = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"Goose ошибка: {error}")
                return f"❌ Ошибка: {error[:200]}"
                
        except asyncio.TimeoutError:
            return "❌ Таймаут (120 сек)"
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return f"❌ Ошибка: {str(e)[:200]}"
    
    async def close(self):
        self.initialized = False
        logger.info("Goose остановлен")

goose_manager = GooseManager()

# ========== УСТАНОВКА БРАУЗЕРА ==========
def get_chromium_path() -> Optional[str]:
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
    if get_chromium_path():
        print("✅ Браузер уже установлен")
        return True
    
    print("⏳ Устанавливаю браузер...")
    
    if PHANTOMWRIGHT_AVAILABLE:
        try:
            subprocess.run([sys.executable, "-m", "phantomwright_driver", "install", "chromium"], check=True)
            print("✅ Браузер установлен через Phantomwright")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка Phantomwright: {e}")
    
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
        print("✅ Браузер установлен через Playwright")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки: {e}")
        return False

install_browser()

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    global browser_data, browser_lock, browser_ws_url
    
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
            browser_ws_url = None
    
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        
        chromium_path = get_chromium_path()
        if not chromium_path:
            install_browser()
            chromium_path = get_chromium_path()
        
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
                '--remote-debugging-port=9222',
            ]
        }
        if chromium_path:
            launch_args['executable_path'] = chromium_path
        
        browser = await p.chromium.launch(**launch_args)
        
        try:
            if hasattr(browser, 'ws_endpoint'):
                browser_ws_url = browser.ws_endpoint
                logger.info(f"🔗 WebSocket URL: {browser_ws_url}")
            elif hasattr(browser, '_connection') and browser._connection:
                browser_ws_url = browser._connection.websocket.url
                logger.info(f"🔗 WebSocket URL: {browser_ws_url}")
            else:
                browser_ws_url = None
                logger.warning("⚠️ Не удалось получить WebSocket URL")
        except Exception as e:
            browser_ws_url = None
            logger.warning(f"⚠️ Ошибка получения WebSocket URL: {e}")
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
            }
        )
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} }, app: { isInstalled: false } };
            Object.defineProperty(document, 'hidden', { get: () => false });
            Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        """)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page,
            'started_at': datetime.now()
        }
        
        logger.info("✅ Браузер запущен")
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data, login_status, browser_ws_url
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None
        browser_ws_url = None
        login_status = {
            'is_logged_in': False,
            'username': None,
            'last_check': None,
            'cookies_valid': False
        }

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐦 X.com Bot с Goose + Agnes AI\n\n"
        "Основные команды:\n"
        "/login — авторизация в X.com\n"
        "/joystick — открыть джойстик управления\n"
        "/screen — скриншот\n"
        "/status — статус браузера\n"
        "/goose <команда> — управление браузером через ИИ\n"
        "/close — закрыть браузер\n\n"
        "Управление Goose:\n"
        "/goose_config — настройка Goose\n"
        "/goose_restart — перезапустить Goose\n\n"
        "Скиллы:\n"
        "/skills_status — статус скиллов\n"
        "/skills_install — установить Playwright CLI\n\n"
        f"Мозг: {'Agnes AI ✅' if AGNES_API_KEY else 'Agnes AI ❌'}"
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
        
        try:
            await page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
        except:
            await page.wait_for_timeout(5000)
        
        await page.wait_for_timeout(3000)
        
        auth_status = await page.evaluate('''
            () => {
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]');
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasHomeLink = !!document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasLoginForm = !!document.querySelector('[data-testid="loginForm"]');
                const hasPrimaryColumn = !!document.querySelector('[data-testid="primaryColumn"]');
                
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    acc[key] = val;
                    return acc;
                }, {});
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                return {
                    hasTweetBtn,
                    hasProfileLink,
                    hasHomeLink,
                    hasSideNav,
                    hasLoginForm,
                    hasPrimaryColumn,
                    hasAuthToken: !!cookies.auth_token,
                    hasCt0: !!cookies.ct0,
                    username: username,
                    isLoggedIn: hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav
                };
            }
        ''')
        
        global login_status
        login_status['is_logged_in'] = auth_status['isLoggedIn']
        login_status['username'] = auth_status.get('username')
        login_status['last_check'] = datetime.now()
        login_status['cookies_valid'] = auth_status['hasAuthToken'] and auth_status['hasCt0']
        
        status_msg = f"✅ X.com\n\n"
        status_msg += f"🍪 auth_token: {'✅' if auth_status['hasAuthToken'] else '❌'}\n"
        status_msg += f"🍪 ct0: {'✅' if auth_status['hasCt0'] else '❌'}\n\n"
        
        if auth_status['isLoggedIn']:
            status_msg += "✅ ВЫ АВТОРИЗОВАНЫ!\n"
            if auth_status.get('username'):
                status_msg += f"👤 @{auth_status['username']}\n"
            if auth_status['hasTweetBtn']:
                status_msg += "   • Кнопка Tweet: ✅\n"
            if auth_status['hasProfileLink']:
                status_msg += "   • Профиль: ✅\n"
            if auth_status['hasHomeLink']:
                status_msg += "   • Домой: ✅\n"
        elif auth_status['hasLoginForm']:
            status_msg += "❌ НЕ АВТОРИЗОВАН (форма входа)\n"
        else:
            status_msg += "⚠️ НЕ ОПРЕДЕЛЕНО\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 X.com - {'✅ Авторизован' if auth_status['isLoggedIn'] else '❌ Не авторизован'}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        if page.url == "about:blank" or not page.url:
            await page.goto('https://x.com', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
        
        screenshot_bytes = await page.screenshot(type='jpeg', quality=80)
        await msg.delete()
        
        url = page.url
        title = await page.title()
        
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"📸 Скриншот\n🔗 {url[:50]}\n📌 {title[:40] if title else 'Без заголовка'}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        browser_ok = False
        browser_info = {}
        
        if browser_data:
            try:
                page = browser_data['page']
                await page.evaluate('1')
                browser_ok = True
                
                url = page.url
                title = await page.title()
                started_at = browser_data.get('started_at')
                uptime = (datetime.now() - started_at).total_seconds() if started_at else 0
                
                auth_check = await page.evaluate('''
                    () => {
                        const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]');
                        const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                        const hasHomeLink = !!document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                        const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                        const hasLoginForm = !!document.querySelector('[data-testid="loginForm"]');
                        
                        const cookies = document.cookie.split(';').reduce((acc, c) => {
                            const [key, val] = c.trim().split('='');
                            acc[key] = val;
                            return acc;
                        }, {});
                        
                        let username = null;
                        const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                        if (profileLink) {
                            const href = profileLink.getAttribute('href');
                            if (href) {
                                const match = href.match(/^\\/([^\\/]+)/);
                                if (match) username = match[1];
                            }
                        }
                        
                        return {
                            hasTweetBtn,
                            hasProfileLink,
                            hasHomeLink,
                            hasSideNav,
                            hasLoginForm,
                            hasAuthToken: !!cookies.auth_token,
                            hasCt0: !!cookies.ct0,
                            username: username,
                            isLoggedIn: hasTweetBtn || hasProfileLink || hasHomeLink || hasSideNav
                        };
                    }
                ''')
                
                browser_info = {
                    'url': url,
                    'title': title[:60] if title else 'Нет',
                    'uptime': uptime,
                    'auth': auth_check
                }
                
                login_status['is_logged_in'] = auth_check['isLoggedIn']
                login_status['username'] = auth_check.get('username')
                login_status['last_check'] = datetime.now()
                login_status['cookies_valid'] = auth_check['hasAuthToken'] and auth_check['hasCt0']
                
            except Exception as e:
                browser_ok = False
                browser_info['error'] = str(e)[:50]
        else:
            browser_info = {'error': 'Браузер не запущен'}
        
        status_msg = "📊 СТАТУС БОТА\n\n"
        
        if browser_ok:
            status_msg += "🌐 Браузер: ✅ Запущен\n"
            if browser_info.get('uptime'):
                hours = int(browser_info['uptime'] // 3600)
                minutes = int((browser_info['uptime'] % 3600) // 60)
                status_msg += f"⏱️ Аптайм: {hours}ч {minutes}м\n"
            if browser_ws_url:
                status_msg += f"🔗 WebSocket: ✅ {browser_ws_url[:50]}...\n"
            else:
                status_msg += "🔗 WebSocket: ❌ Не сохранён\n"
        else:
            status_msg += "🌐 Браузер: ❌ Не запущен\n"
        
        if browser_ok and browser_info.get('url'):
            status_msg += f"🔗 URL: {browser_info['url'][:60]}\n"
            status_msg += f"📌 Заголовок: {browser_info.get('title', 'Нет')}\n"
        
        status_msg += "\n🔐 АВТОРИЗАЦИЯ:\n"
        
        if browser_ok and browser_info.get('auth'):
            auth = browser_info['auth']
            
            status_msg += f"🍪 auth_token: {'✅' if auth.get('hasAuthToken') else '❌'}\n"
            status_msg += f"🍪 ct0: {'✅' if auth.get('hasCt0') else '❌'}\n"
            
            if auth.get('isLoggedIn'):
                status_msg += "\n✅ ВЫ АВТОРИЗОВАНЫ\n"
                if auth.get('username'):
                    status_msg += f"👤 @{auth['username']}\n"
                if auth.get('hasTweetBtn'):
                    status_msg += "   • Кнопка Tweet: ✅\n"
                if auth.get('hasProfileLink'):
                    status_msg += "   • Профиль: ✅\n"
                if auth.get('hasHomeLink'):
                    status_msg += "   • Домой: ✅\n"
            elif auth.get('hasLoginForm'):
                status_msg += "\n❌ НЕ АВТОРИЗОВАН (форма входа)\n"
            else:
                status_msg += "\n⚠️ НЕ ОПРЕДЕЛЕНО\n"
        else:
            status_msg += "❌ Нет данных (выполните /login)\n"
        
        installed, version = await check_goose_installed()
        status_msg += f"\n🤖 Goose CLI: {'✅ ' + version if installed else '❌ Не установлен'}\n"
        status_msg += f"🤖 Goose готов: {'✅' if goose_manager.initialized else '❌ Не инициализирован'}\n"
        if goose_manager.init_error:
            status_msg += f"⚠️ Ошибка: {goose_manager.init_error[:100]}\n"
        
        status_msg += f"🧠 Agnes AI: {'✅ Ключ задан' if AGNES_API_KEY else '❌ Ключ не задан'}\n"
        status_msg += f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        status_msg += f"📦 Драйвер: {'Phantomwright' if PHANTOMWRIGHT_AVAILABLE else 'Playwright'}\n"
        status_msg += f"🍪 Куки загружены: {len(COOKIES)} шт."
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ДЖОЙСТИК ==========
async def joystick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает джойстик для управления браузером через Goose"""
    user_id = update.effective_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("⬆️ Вверх", callback_data=f"joy_{user_id}_up"),
            InlineKeyboardButton("⬇️ Вниз", callback_data=f"joy_{user_id}_down"),
        ],
        [
            InlineKeyboardButton("⬅️ Влево", callback_data=f"joy_{user_id}_left"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"joy_{user_id}_refresh"),
            InlineKeyboardButton("➡️ Вправо", callback_data=f"joy_{user_id}_right"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"joy_{user_id}_back"),
            InlineKeyboardButton("🖱️ Клик", callback_data=f"joy_{user_id}_click"),
            InlineKeyboardButton("📸 Скриншот", callback_data=f"joy_{user_id}_screenshot"),
        ],
        [
            InlineKeyboardButton("🔝 В начало", callback_data=f"joy_{user_id}_top"),
            InlineKeyboardButton("🔽 В конец", callback_data=f"joy_{user_id}_bottom"),
            InlineKeyboardButton("📄 Текст", callback_data=f"joy_{user_id}_text"),
        ],
        [
            InlineKeyboardButton("🤖 Спросить Goose", callback_data=f"joy_{user_id}_ask"),
            InlineKeyboardButton("❌ Закрыть", callback_data=f"joy_{user_id}_close"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(
        "🎮 **Джойстик управления браузером**\n\n"
        "Нажимай кнопки — Goose управляет браузером!\n"
        "🤖 Goose — твой ИИ-помощник.\n\n"
        "💡 Нажми 'Спросить Goose' и напиши что хочешь сделать.\n"
        "📍 Сначала выполни /login для авторизации.",
        reply_markup=reply_markup
    )
    active_joysticks[user_id] = msg.message_id

async def joystick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок джойстика"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if not data.startswith(f"joy_{user_id}_"):
        return
    
    action = data.replace(f"joy_{user_id}_", "")
    
    if action == "close":
        await query.edit_message_text("🎮 Джойстик закрыт")
        if user_id in active_joysticks:
            del active_joysticks[user_id]
        return
    
    command_map = {
        "up": "прокрути страницу вверх",
        "down": "прокрути страницу вниз",
        "left": "прокрути страницу влево",
        "right": "прокрути страницу вправо",
        "refresh": "обнови страницу",
        "back": "вернись на предыдущую страницу",
        "click": "кликни по центру страницы",
        "screenshot": "сделай скриншот",
        "top": "прокрути в начало страницы",
        "bottom": "прокрути в конец страницы",
        "text": "покажи текст текущей страницы",
        "ask": "Спросить Goose"
    }
    
    if action == "ask":
        await query.edit_message_text(
            "🤖 **Спроси Goose**\n\n"
            "Напиши что хочешь сделать в браузере.\n"
            "Примеры:\n"
            "• найди новости про ИИ\n"
            "• открой профиль\n"
            "• напиши твит: Привет!\n"
            "• прокрути вниз 3 раза"
        )
        context.user_data['waiting_for_goose'] = True
        return
    
    command_text = command_map.get(action, "")
    if not command_text:
        await query.edit_message_text("❌ Неизвестная команда")
        return
    
    await query.edit_message_text(f"🔄 **Goose выполняет:** {command_text}\n\n⏳ Пожалуйста, подождите...")
    
    try:
        if not browser_data:
            await get_browser()
            await asyncio.sleep(1)
        
        if not goose_manager.initialized:
            await goose_manager.initialize()
            await asyncio.sleep(1)
        
        result = await goose_manager.execute_command(command_text)
        formatted_result = format_goose_response(result)
        
        if "скрин" in command_text.lower():
            try:
                if browser_data:
                    page = browser_data['page']
                    screenshot_bytes = await page.screenshot(type='jpeg', quality=80)
                    url = page.url
                    title = await page.title()
                    
                    await query.delete_message()
                    await update.effective_chat.send_photo(
                        photo=screenshot_bytes,
                        caption=f"📸 Скриншот\n🔗 {url[:50]}\n📌 {title[:40] if title else 'Без заголовка'}"
                    )
                    await show_joystick(update, context)
                    return
            except Exception as e:
                logger.error(f"Ошибка скриншота: {e}")
        
        await query.edit_message_text(f"✅ **Goose:** {formatted_result}")
        await asyncio.sleep(2)
        await show_joystick(update, context)
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка:\n\n`{str(e)[:200]}`")
        await asyncio.sleep(2)
        await show_joystick(update, context)

async def show_joystick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает джойстик снова"""
    user_id = update.effective_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("⬆️ Вверх", callback_data=f"joy_{user_id}_up"),
            InlineKeyboardButton("⬇️ Вниз", callback_data=f"joy_{user_id}_down"),
        ],
        [
            InlineKeyboardButton("⬅️ Влево", callback_data=f"joy_{user_id}_left"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"joy_{user_id}_refresh"),
            InlineKeyboardButton("➡️ Вправо", callback_data=f"joy_{user_id}_right"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"joy_{user_id}_back"),
            InlineKeyboardButton("🖱️ Клик", callback_data=f"joy_{user_id}_click"),
            InlineKeyboardButton("📸 Скриншот", callback_data=f"joy_{user_id}_screenshot"),
        ],
        [
            InlineKeyboardButton("🔝 В начало", callback_data=f"joy_{user_id}_top"),
            InlineKeyboardButton("🔽 В конец", callback_data=f"joy_{user_id}_bottom"),
            InlineKeyboardButton("📄 Текст", callback_data=f"joy_{user_id}_text"),
        ],
        [
            InlineKeyboardButton("🤖 Спросить Goose", callback_data=f"joy_{user_id}_ask"),
            InlineKeyboardButton("❌ Закрыть", callback_data=f"joy_{user_id}_close"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if user_id in active_joysticks:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=active_joysticks[user_id],
                text="🎮 **Джойстик управления браузером**\n\n"
                     "🤖 Goose — твой ИИ-помощник.\n"
                     "Нажимай кнопки или спроси Goose!",
                reply_markup=reply_markup
            )
        except:
            pass

async def handle_goose_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые команды для Goose"""
    if not context.user_data.get('waiting_for_goose'):
        return
    
    user_id = update.effective_user.id
    command_text = update.message.text
    
    context.user_data['waiting_for_goose'] = False
    
    msg = await update.message.reply_text(f"🔄 **Goose выполняет:** {command_text}\n\n⏳ Пожалуйста, подождите...")
    
    try:
        if not browser_data:
            await get_browser()
            await asyncio.sleep(1)
        
        if not goose_manager.initialized:
            await goose_manager.initialize()
            await asyncio.sleep(1)
        
        result = await goose_manager.execute_command(command_text)
        formatted_result = format_goose_response(result)
        
        if "скрин" in command_text.lower() or "screenshot" in command_text.lower():
            try:
                if browser_data:
                    page = browser_data['page']
                    screenshot_bytes = await page.screenshot(type='jpeg', quality=80)
                    url = page.url
                    title = await page.title()
                    
                    await msg.delete()
                    await update.effective_chat.send_photo(
                        photo=screenshot_bytes,
                        caption=f"📸 Скриншот\n🔗 {url[:50]}\n📌 {title[:40] if title else 'Без заголовка'}"
                    )
                    await show_joystick(update, context)
                    return
            except Exception as e:
                logger.error(f"Ошибка скриншота: {e}")
        
        await msg.edit_text(f"✅ **Goose:** {formatted_result}")
        await asyncio.sleep(2)
        await show_joystick(update, context)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка:\n\n`{str(e)[:200]}`")
        await asyncio.sleep(2)
        await show_joystick(update, context)

# ========== УПРАВЛЕНИЕ GOOSE ==========
async def goose_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Читаю конфиг Goose...")
    try:
        config_path = os.path.expanduser("~/.config/goose/config.yaml")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                content = f.read()
            await msg.edit_text(f"📄 Конфиг Goose:\n\n```yaml\n{content[:3000]}\n```")
        else:
            await msg.edit_text("❌ Конфиг не найден. Выполните /goose_restart")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def goose_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Перезапускаю Goose...")
    try:
        await goose_manager.close()
        goose_manager.initialized = False
        success = await goose_manager.initialize()
        if success:
            await msg.edit_text("✅ Goose перезапущен!")
        else:
            await msg.edit_text(f"❌ Ошибка: {goose_manager.init_error}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== СКИЛЛЫ ==========
async def skills_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Проверяю статус...")
    try:
        skills_dir = os.path.expanduser("~/.agents/skills/")
        skills_list = []
        if os.path.exists(skills_dir):
            for item in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, item)
                if os.path.isdir(skill_path):
                    skill_file = os.path.join(skill_path, "SKILL.md")
                    if os.path.exists(skill_file):
                        skills_list.append(item)
        
        status_msg = f"📦 СТАТУС СКИЛЛОВ\n\n📁 Папка: {skills_dir}\n📦 Скиллов: {len(skills_list)}\n\n"
        if skills_list:
            for skill in skills_list:
                status_msg += f"  ✅ {skill}\n"
        else:
            status_msg += "❌ Скиллы не установлены\n\n📌 /skills_install — Playwright CLI"
        await msg.edit_text(status_msg)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills_install(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Устанавливаю скилл Playwright CLI...")
    try:
        skills_dir = os.path.expanduser("~/.agents/skills/playwright-cli")
        os.makedirs(skills_dir, exist_ok=True)
        
        skill_content = """---
name: playwright-cli
description: Управление браузером через Playwright CLI.
---

# Playwright CLI Skill

## Команды
- npx playwright open <url> — открыть страницу
- npx playwright click <selector> — кликнуть
- npx playwright fill <selector> <text> — заполнить поле
- npx playwright screenshot — скриншот
"""
        skill_file = os.path.join(skills_dir, "SKILL.md")
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(skill_content)
        
        await msg.edit_text(f"✅ Скилл установлен!\n📁 {skills_dir}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def goose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_text = " ".join(context.args) if context.args else None
    
    if not command_text:
        await update.message.reply_text(
            "🤖 Goose AI Agent\n\n"
            "Используйте: /goose <команда>\n\n"
            "Примеры:\n"
            "• /goose открой x.com\n"
            "• /goose сделай скриншот\n"
            "• /goose найди кнопку Tweet\n\n"
            "Мозг: Agnes AI"
        )
        return
    
    msg = await update.message.reply_text("🔄 Начинаю работу...")
    
    async def update_status(text):
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            await msg.edit_text(f"🔄 Логи ({timestamp}):\n\n`{text}`")
        except Exception:
            try:
                await update.message.reply_text(f"📋 {text}")
            except:
                pass
    
    try:
        await update_status("🌐 Проверяю браузер...")
        await get_browser()
        
        if not goose_manager.initialized:
            await update_status("🔄 Инициализирую Goose...")
            success = await goose_manager.initialize()
            if not success:
                error_msg = goose_manager.init_error or "Неизвестная ошибка"
                await msg.edit_text(f"❌ Ошибка:\n\n`{error_msg[:200]}`")
                return
        
        await update_status("🚀 Выполняю...")
        result = await goose_manager.execute_command(command_text, progress_callback=update_status)
        
        formatted_result = format_goose_response(result)
        
        if "скрин" in command_text.lower() or "screenshot" in command_text.lower():
            try:
                if browser_data:
                    page = browser_data['page']
                    screenshot_bytes = await page.screenshot(type='jpeg', quality=80)
                    url = page.url
                    title = await page.title()
                    
                    await msg.delete()
                    await update.message.reply_photo(
                        photo=screenshot_bytes,
                        caption=f"📸 Скриншот\n🔗 {url[:50]}\n📌 {title[:40] if title else 'Без заголовка'}"
                    )
                    return
            except Exception as e:
                logger.error(f"Ошибка скриншота: {e}")
        
        if len(formatted_result) > 4000:
            parts = [formatted_result[i:i+4000] for i in range(0, len(formatted_result), 4000)]
            await msg.edit_text(f"✅ Результат:\n\n{parts[0]}")
            for part in parts[1:]:
                await update.message.reply_text(f"📄 Продолжение:\n\n{part}")
        else:
            await msg.edit_text(f"✅ {formatted_result}")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка:\n\n`{str(e)[:200]}`")

async def diagnose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Провожу диагностику...")
    try:
        diag = "🔍 ДИАГНОСТИКА\n\n"
        diag += f"🐍 Python: {sys.version.split()[0]}\n"
        installed, version = await check_goose_installed()
        diag += f"📦 Goose: {'✅ ' + version if installed else '❌'}\n"
        try:
            import playwright
            diag += "🎭 Playwright: ✅\n"
        except ImportError:
            diag += "🎭 Playwright: ❌\n"
        diag += f"🌐 Браузер: {'✅' if browser_data else '❌'}\n"
        diag += f"🔗 WebSocket: {'✅' if browser_ws_url else '❌'}\n"
        diag += f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
        diag += f"🤖 Goose: {'✅' if goose_manager.initialized else '❌'}\n"
        diag += f"🧠 Agnes: {'✅' if AGNES_API_KEY else '❌'}\n"
        await msg.edit_text(diag)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("goose", goose_command))
    
    # Джойстик
    app.add_handler(CommandHandler("joystick", joystick))
    app.add_handler(CallbackQueryHandler(joystick_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goose_text))
    
    # Управление
    app.add_handler(CommandHandler("goose_config", goose_config))
    app.add_handler(CommandHandler("goose_restart", goose_restart))
    app.add_handler(CommandHandler("skills_status", skills_status))
    app.add_handler(CommandHandler("skills_install", skills_install))
    app.add_handler(CommandHandler("diagnose", diagnose))
    
    import atexit
    @atexit.register
    def cleanup():
        asyncio.create_task(goose_manager.close())
    
    print("🐦 X.com Bot с Goose + Agnes AI запущен!")
    print("📌 Команды: /start, /login, /screen, /status, /goose, /close")
    print("🎮 Джойстик: /joystick")
    if AGNES_API_KEY:
        print("🧠 Agnes AI: ✅")
    else:
        print("⚠️ AGNES_API_KEY не задан!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()