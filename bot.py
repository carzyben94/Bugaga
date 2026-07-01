# bot.py - X.com бот с Goose
import os
import sys
import subprocess
import logging
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None,
    'cookies_valid': False
}

# ========== GOOSE МЕНЕДЖЕР ==========
class GooseManager:
    def __init__(self):
        self.process = None
        self.initialized = False
        self.request_id = 0
        self.init_error = None
        
    async def initialize(self):
        """Запускает Goose как MCP-сервер"""
        if self.initialized:
            return True
            
        try:
            logger.info("🔄 Запускаю Goose MCP сервер...")
            
            # Проверяем, установлен ли goose через pip
            try:
                import goose
                logger.info("✅ Goose найден как Python-модуль")
            except ImportError:
                logger.warning("⚠️ Goose не найден как Python-модуль, пробую установить...")
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", "goose-ai"], check=True)
                    logger.info("✅ Goose установлен через pip")
                except Exception as e:
                    logger.error(f"❌ Не удалось установить Goose: {e}")
                    self.init_error = f"Не удалось установить Goose: {e}"
                    return False
            
            # Пробуем запустить goose через разные способы
            commands = [
                [sys.executable, "-m", "goose", "mcp", "serve"],
                ["goose", "mcp", "serve"],
            ]
            
            for cmd in commands:
                try:
                    self.process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    logger.info(f"✅ Goose запущен через: {' '.join(cmd)}")
                    break
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.warning(f"Ошибка при попытке запуска {' '.join(cmd)}: {e}")
                    continue
            else:
                self.init_error = "Не найдена команда goose"
                return False
            
            # Даем время на запуск
            await asyncio.sleep(2)
            
            # Проверяем, жив ли процесс
            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"❌ Goose завершился при запуске: {error_msg}")
                self.init_error = error_msg
                return False
            
            # Отправляем initialize
            init_cmd = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "capabilities": {},
                    "clientInfo": {"name": "telegram-bot", "version": "1.0.0"}
                },
                "id": self._next_id()
            }
            
            response = await self._send_command(init_cmd)
            if response and "result" in response:
                self.initialized = True
                logger.info("✅ Goose MCP сервер инициализирован")
                return True
            else:
                logger.error(f"❌ Ошибка инициализации Goose: {response}")
                self.init_error = str(response)
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Goose: {e}")
            self.init_error = str(e)
            return False
    
    def _next_id(self):
        self.request_id += 1
        return self.request_id
    
    async def _send_command(self, command: Dict) -> Optional[Dict]:
        """Отправляет JSON-RPC команду в Goose"""
        if not self.process:
            logger.error("Goose процесс не запущен")
            return None
        
        if self.process.returncode is not None:
            logger.error(f"Goose процесс завершился с кодом {self.process.returncode}")
            try:
                stderr = await self.process.stderr.read()
                logger.error(f"stderr: {stderr.decode() if stderr else 'Нет'}")
            except:
                pass
            return None
        
        try:
            cmd_str = json.dumps(command) + "\n"
            logger.debug(f"Отправка команды: {cmd_str[:100]}...")
            
            self.process.stdin.write(cmd_str.encode())
            await self.process.stdin.drain()
            
            try:
                response_line = await asyncio.wait_for(
                    self.process.stdout.readline(), 
                    timeout=30.0
                )
                if response_line:
                    return json.loads(response_line.decode())
                else:
                    logger.warning("Пустой ответ от Goose")
                    return None
            except asyncio.TimeoutError:
                logger.warning("Таймаут при чтении ответа Goose (30 сек)")
                return None
            
        except BrokenPipeError:
            logger.error("BrokenPipeError: Goose процесс закрыл stdin")
            return None
        except Exception as e:
            logger.error(f"Ошибка отправки команды в Goose: {e}")
            return None
    
    async def execute_command(self, command: str) -> str:
        """Выполняет команду через Goose с Playwright"""
        if not self.initialized:
            success = await self.initialize()
            if not success:
                error_msg = self.init_error or "Неизвестная ошибка"
                return f"❌ Не удалось запустить Goose: {error_msg[:200]}"
        
        if self.process and self.process.returncode is not None:
            try:
                stderr = await self.process.stderr.read()
                error_msg = stderr.decode() if stderr else "процесс завершился"
                return f"❌ Goose завершился. Ошибка: {error_msg[:200]}"
            except:
                return "❌ Goose завершился. Попробуйте позже."
        
        browser_ctx = ""
        if browser_data:
            try:
                page = browser_data['page']
                url = page.url
                browser_ctx = f"Текущая страница: {url}\n"
            except:
                pass
        
        full_command = f"{browser_ctx}Выполни в браузере: {command}"
        
        methods = ["execute_natural_language", "execute_browser_command", "execute"]
        last_error = None
        
        for method in methods:
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": method,
                    "arguments": {"command": full_command}
                },
                "id": self._next_id()
            }
            
            response = await self._send_command(request)
            
            if response is None:
                continue
                
            if "result" in response:
                content = response["result"].get("content", [])
                if content and len(content) > 0:
                    text = content[0].get("text", "✅ Команда выполнена")
                    if text.startswith("✅ **Результат:**\n\n"):
                        text = text[18:]
                    return text
                return "✅ Команда выполнена"
            elif "error" in response:
                last_error = response['error'].get('message', 'Неизвестная ошибка')
                if "not found" in last_error.lower():
                    continue
                return f"❌ Ошибка Goose: {last_error}"
        
        if last_error:
            return f"❌ Не удалось выполнить команду. Последняя ошибка: {last_error}"
        else:
            return "❌ Не удалось выполнить команду (нет ответа от Goose). Проверьте логи."
    
    async def close(self):
        """Закрывает Goose"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.initialized = False
            logger.info("Goose остановлен")

# Создаём экземпляр Goose
goose = GooseManager()

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
    global browser_data, login_status
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None
        login_status = {
            'is_logged_in': False,
            'username': None,
            'last_check': None,
            'cookies_valid': False
        }

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐦 **X.com Bot с Goose AI**\n\n"
        "📌 **Основные команды:**\n"
        "/login — авторизация в X.com\n"
        "/screen — скриншот\n"
        "/status — статус браузера и авторизации\n"
        "/goose <команда> — управление браузером через ИИ\n"
        "/close — закрыть браузер\n\n"
        "🔧 **Утилиты:**\n"
        "/install_goose — установить Goose\n"
        "/test_goose — проверить Goose\n"
        "/diagnose — полная диагностика\n"
        "/restart_goose — перезапустить Goose\n\n"
        "🤖 **Примеры /goose:**\n"
        "• `открой x.com и найди новости про ИИ`\n"
        "• `сделай скриншот главной страницы`\n"
        "• `найди кнопку Tweet и нажми на неё`"
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
            status_msg += "✅ **ВЫ АВТОРИЗОВАНЫ!**\n"
            if auth_status.get('username'):
                status_msg += f"👤 @{auth_status['username']}\n"
            if auth_status['hasTweetBtn']:
                status_msg += "   • Кнопка Tweet: ✅\n"
            if auth_status['hasProfileLink']:
                status_msg += "   • Профиль: ✅\n"
            if auth_status['hasHomeLink']:
                status_msg += "   • Домой: ✅\n"
        elif auth_status['hasLoginForm']:
            status_msg += "❌ **НЕ АВТОРИЗОВАН** (форма входа)\n"
        else:
            status_msg += "⚠️ **НЕ ОПРЕДЕЛЕНО**\n"
        
        await msg.edit_text(status_msg)
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 X.com - {'✅ Авторизован' if auth_status['isLoggedIn'] else '❌ Не авторизован'}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.delete()
        
        url = page.url
        title = await page.title()
        
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 {title[:40] if title else 'X.com'}\n🔗 {url[:50]}"
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
        
        status_msg = "📊 **СТАТУС БОТА**\n\n"
        
        if browser_ok:
            status_msg += "🌐 **Браузер:** ✅ Запущен\n"
            if browser_info.get('uptime'):
                hours = int(browser_info['uptime'] // 3600)
                minutes = int((browser_info['uptime'] % 3600) // 60)
                status_msg += f"⏱️ Аптайм: {hours}ч {minutes}м\n"
        else:
            status_msg += "🌐 **Браузер:** ❌ Не запущен\n"
        
        if browser_ok and browser_info.get('url'):
            status_msg += f"🔗 URL: {browser_info['url'][:60]}\n"
            status_msg += f"📌 Заголовок: {browser_info.get('title', 'Нет')}\n"
        
        status_msg += "\n🔐 **АВТОРИЗАЦИЯ:**\n"
        
        if browser_ok and browser_info.get('auth'):
            auth = browser_info['auth']
            
            status_msg += f"🍪 auth_token: {'✅' if auth.get('hasAuthToken') else '❌'}\n"
            status_msg += f"🍪 ct0: {'✅' if auth.get('hasCt0') else '❌'}\n"
            
            if auth.get('isLoggedIn'):
                status_msg += "\n✅ **ВЫ АВТОРИЗОВАНЫ**\n"
                if auth.get('username'):
                    status_msg += f"👤 @{auth['username']}\n"
                if auth.get('hasTweetBtn'):
                    status_msg += "   • Кнопка Tweet: ✅\n"
                if auth.get('hasProfileLink'):
                    status_msg += "   • Профиль: ✅\n"
                if auth.get('hasHomeLink'):
                    status_msg += "   • Домой: ✅\n"
            elif auth.get('hasLoginForm'):
                status_msg += "\n❌ **НЕ АВТОРИЗОВАН** (форма входа)\n"
            else:
                status_msg += "\n⚠️ **НЕ ОПРЕДЕЛЕНО**\n"
        else:
            status_msg += "❌ Нет данных (выполните /login)\n"
        
        status_msg += f"\n🤖 **Goose:** {'✅ Запущен' if goose.initialized else '❌ Не запущен'}\n"
        if goose.init_error:
            status_msg += f"⚠️ Ошибка: {goose.init_error[:100]}\n"
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

# ========== КОМАНДА GOOSE ==========
async def goose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет команду через Goose AI"""
    command_text = " ".join(context.args) if context.args else None
    
    if not command_text:
        await update.message.reply_text(
            "🤖 **Goose AI Agent**\n\n"
            "Используйте: `/goose <команда>`\n\n"
            "📌 **Примеры:**\n"
            "• `/goose открой x.com и найди новости про ИИ`\n"
            "• `/goose сделай скриншот главной страницы`\n"
            "• `/goose найди кнопку Войти и нажми`\n"
            "• `/goose прокрути страницу вниз`\n\n"
            "💡 Goose использует ваш браузер и все куки!"
        )
        return
    
    msg = await update.message.reply_text("🤔 Анализирую команду...")
    
    try:
        await get_browser()
        
        if not goose.initialized:
            await msg.edit_text("🔄 Запускаю Goose...")
            success = await goose.initialize()
            if not success:
                error_msg = goose.init_error or "Неизвестная ошибка"
                await msg.edit_text(f"❌ Не удалось запустить Goose: {error_msg[:200]}")
                return
        
        await msg.edit_text("🎯 Выполняю...")
        result = await goose.execute_command(command_text)
        
        if len(result) > 4000:
            parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
            await msg.edit_text(f"✅ **Результат:**\n\n{parts[0]}")
            for part in parts[1:]:
                await update.message.reply_text(part)
        else:
            await msg.edit_text(f"✅ **Результат:**\n\n{result}")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== НОВЫЕ КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ GOOSE ==========

async def install_goose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает Goose через pip"""
    msg = await update.message.reply_text("🔄 Устанавливаю Goose...")
    
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "goose-ai",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            await msg.edit_text("✅ **Goose успешно установлен!**\n\n"
                               "Теперь выполните `/test_goose` для проверки.")
            logger.info("Goose установлен через pip")
        else:
            error = stderr.decode() if stderr else "Неизвестная ошибка"
            await msg.edit_text(f"❌ **Ошибка установки Goose:**\n```\n{error[:500]}\n```")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def test_goose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирует Goose"""
    msg = await update.message.reply_text("🔄 Тестирую Goose...")
    
    try:
        try:
            import goose
            version = goose.__version__ if hasattr(goose, '__version__') else 'неизвестно'
            await msg.edit_text(f"✅ Goose найден как Python-модуль (версия: {version})")
        except ImportError:
            await msg.edit_text("⚠️ Goose не найден как Python-модуль. Установите через /install_goose")
            return
        
        try:
            process = await asyncio.create_subprocess_exec(
                "goose", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                version_output = stdout.decode().strip() or stderr.decode().strip()
                await msg.edit_text(f"✅ Goose CLI доступен: {version_output}")
            else:
                await msg.edit_text("⚠️ Goose CLI не найден, но модуль Python установлен.")
        except FileNotFoundError:
            await msg.edit_text("⚠️ Goose CLI не найден, но модуль Python установлен.")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка теста: {str(e)[:200]}")

async def diagnose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная диагностика"""
    msg = await update.message.reply_text("🔄 Провожу диагностику...")
    
    try:
        diag = "🔍 **ДИАГНОСТИКА БОТА**\n\n"
        diag += f"🐍 Python: {sys.version.split()[0]}\n"
        
        try:
            import goose
            diag += f"📦 Goose: ✅ установлен (версия: {goose.__version__ if hasattr(goose, '__version__') else 'неизвестно'})\n"
        except ImportError:
            diag += "📦 Goose: ❌ не установлен\n"
        
        try:
            import playwright
            diag += f"🎭 Playwright: ✅ установлен\n"
        except ImportError:
            diag += "🎭 Playwright: ❌ не установлен\n"
        
        diag += f"👻 Phantomwright: {'✅ доступен' if PHANTOMWRIGHT_AVAILABLE else '❌ не доступен'}\n"
        
        if browser_data:
            diag += "🌐 Браузер: ✅ запущен\n"
        else:
            diag += "🌐 Браузер: ❌ не запущен\n"
        
        if login_status['is_logged_in']:
            diag += f"🔐 X.com: ✅ авторизован (@{login_status['username']})\n"
        else:
            diag += "🔐 X.com: ❌ не авторизован\n"
        
        diag += f"🤖 Goose MCP: {'✅ запущен' if goose.initialized else '❌ не запущен'}\n"
        if goose.init_error:
            diag += f"   Ошибка: {goose.init_error[:100]}\n"
        
        diag += f"\n🔑 TOKEN: {'✅' if TOKEN else '❌'}\n"
        
        await msg.edit_text(diag)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка диагностики: {str(e)[:200]}")

async def restart_goose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапускает Goose"""
    msg = await update.message.reply_text("🔄 Перезапускаю Goose...")
    
    try:
        await goose.close()
        goose.initialized = False
        
        success = await goose.initialize()
        
        if success:
            await msg.edit_text("✅ **Goose перезапущен!**\n\n"
                               "Теперь можете использовать `/goose <команда>`")
        else:
            error_msg = goose.init_error or "Неизвестная ошибка"
            await msg.edit_text(f"❌ **Не удалось перезапустить Goose:**\n```\n{error_msg[:200]}\n```")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("goose", goose_command))
    app.add_handler(CommandHandler("install_goose", install_goose))
    app.add_handler(CommandHandler("test_goose", test_goose))
    app.add_handler(CommandHandler("diagnose", diagnose))
    app.add_handler(CommandHandler("restart_goose", restart_goose))
    
    import atexit
    @atexit.register
    def cleanup():
        asyncio.create_task(goose.close())
    
    print("🐦 X.com Bot с Goose запущен!")
    print("📌 Команды: /start, /login, /screen, /status, /goose, /close")
    print("🔧 Утилиты: /install_goose, /test_goose, /diagnose, /restart_goose")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()