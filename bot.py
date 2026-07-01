# explorer.py - Агент-исследователь X.com
import os
import sys
import subprocess
import logging
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('explorer.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# ========== ПРОВЕРКА PHANTOMWRIGHT ==========
try:
    from phantomwright_driver.async_api import async_playwright
    PHANTOMWRIGHT_AVAILABLE = True
    print("✅ Phantomwright загружен")
except ImportError:
    PHANTOMWRIGHT_AVAILABLE = False
    print("⚠️ Phantomwright не найден, использую Playwright")
    from playwright.async_api import async_playwright

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
exploration_results = {
    'pages': {},
    'total_elements': 0,
    'clicked_elements': 0,
    'errors': [],
    'logs': []
}

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
            'headless': False,  # Включаем видимый режим для отладки
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,720',
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
        )
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} }, app: { isInstalled: false } };
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
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== АГЕНТ-ИССЛЕДОВАТЕЛЬ ==========
class XExplorer:
    def __init__(self, page):
        self.page = page
        self.results = {
            'elements': [],
            'clicked': [],
            'errors': [],
            'screenshots': [],
            'logs': []
        }
        self.log("🔍 Агент-исследователь запущен")
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.results['logs'].append(log_entry)
        logger.info(log_entry)
        return log_entry
    
    async def scan_page(self, url: str, name: str = "unknown"):
        """Сканирует страницу и находит все интерактивные элементы"""
        self.log(f"📄 Сканирую страницу: {url}")
        
        try:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await self.page.wait_for_timeout(3000)
            
            # Делаем скриншот до сканирования
            screenshot = await self.page.screenshot(type='jpeg', quality=70)
            self.results['screenshots'].append({
                'stage': 'before_scan',
                'data': screenshot
            })
            
            # Собираем все элементы
            elements = await self.page.evaluate('''
                () => {
                    const elements = [];
                    const selectors = [
                        'button',
                        'a[href]',
                        'input',
                        'textarea',
                        'select',
                        '[role="button"]',
                        '[role="link"]',
                        '[role="tab"]',
                        '[role="menuitem"]',
                        '[data-testid]',
                        '[aria-label]',
                        '[aria-haspopup="menu"]'
                    ];
                    
                    const allElements = document.querySelectorAll(selectors.join(','));
                    
                    for (const el of allElements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        if (el.offsetParent === null) continue;
                        
                        const data = {
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            text: (el.textContent || '').trim().slice(0, 100),
                            aria: el.getAttribute('aria-label') || '',
                            testid: el.getAttribute('data-testid') || '',
                            role: el.getAttribute('role') || '',
                            href: el.getAttribute('href') || '',
                            id: el.id || '',
                            class: el.className || '',
                            visible: true,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            disabled: el.disabled || false,
                            readonly: el.readOnly || false
                        };
                        
                        if (data.text || data.aria || data.testid || data.role) {
                            elements.push(data);
                        }
                    }
                    
                    return elements;
                }
            ''')
            
            self.log(f"🔍 Найдено {len(elements)} интерактивных элементов")
            self.results['elements'] = elements
            
            # Сохраняем в файл
            with open(f'scan_{name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'url': url,
                    'name': name,
                    'timestamp': datetime.now().isoformat(),
                    'total': len(elements),
                    'elements': elements
                }, f, ensure_ascii=False, indent=2)
            
            return elements
            
        except Exception as e:
            self.log(f"❌ Ошибка сканирования: {str(e)}")
            self.results['errors'].append(str(e))
            return []
    
    async def click_elements(self, elements: List[Dict], max_clicks: int = 20):
        """Кликает по найденным элементам и логирует результат"""
        self.log(f"🖱️ Начинаю кликать по {min(len(elements), max_clicks)} элементам...")
        
        clicked = 0
        for i, el_data in enumerate(elements[:max_clicks]):
            try:
                # Пропускаем опасные элементы
                if el_data.get('disabled') or el_data.get('readonly'):
                    continue
                
                # Пропускаем ссылки на внешние сайты
                href = el_data.get('href', '')
                if href and (href.startswith('http') and 'x.com' not in href):
                    continue
                
                # Пропускаем элементы с большим текстом (обычно это не кнопки)
                if len(el_data.get('text', '')) > 50 and not el_data.get('aria'):
                    continue
                
                self.log(f"🔄 Клик #{i+1}: {el_data.get('text', 'без текста')} [{el_data.get('testid', '')}]")
                
                # Находим элемент на странице
                selector = self._build_selector(el_data)
                if not selector:
                    continue
                
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        await element.click(timeout=2000)
                        await self.page.wait_for_timeout(500)
                        clicked += 1
                        self.results['clicked'].append({
                            'element': el_data,
                            'success': True,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # Делаем скриншот после клика
                        if clicked % 5 == 0:
                            screenshot = await self.page.screenshot(type='jpeg', quality=70)
                            self.results['screenshots'].append({
                                'stage': f'after_click_{clicked}',
                                'data': screenshot
                            })
                    else:
                        self.log(f"⚠️ Элемент не найден на странице")
                except Exception as e:
                    self.log(f"⚠️ Клик не удался: {str(e)[:100]}")
                    self.results['errors'].append({
                        'element': el_data,
                        'error': str(e)
                    })
                    
            except Exception as e:
                self.log(f"❌ Ошибка при клике: {str(e)}")
                self.results['errors'].append(str(e))
        
        self.log(f"✅ Успешно кликнуто: {clicked} элементов")
        return clicked
    
    def _build_selector(self, el_data: Dict) -> Optional[str]:
        """Строит CSS-селектор для элемента"""
        if el_data.get('testid'):
            return f'[data-testid="{el_data["testid"]}"]'
        if el_data.get('id'):
            return f'#{el_data["id"]}'
        if el_data.get('aria'):
            return f'[aria-label="{el_data["aria"]}"]'
        if el_data.get('text'):
            text = el_data['text'][:30].replace('"', '\\"')
            return f'*:has-text("{text}")'
        return None
    
    def get_report(self) -> str:
        """Формирует отчет"""
        report = "📊 **Отчет агента-исследователя**\n\n"
        report += f"🔍 Найдено элементов: {len(self.results['elements'])}\n"
        report += f"🖱️ Кликнуто: {len(self.results['clicked'])}\n"
        report += f"❌ Ошибок: {len(self.results['errors'])}\n"
        report += f"📸 Скриншотов: {len(self.results['screenshots'])}\n\n"
        
        report += "📋 **Логи:**\n"
        for log in self.results['logs'][-20:]:
            report += f"• {log}\n"
        
        report += "\n📌 **Найденные элементы (первые 10):**\n"
        for i, el in enumerate(self.results['elements'][:10]):
            text = el.get('text', '') or el.get('aria', '') or el.get('testid', '')
            report += f"  {i+1}. {el['tag']}"
            if text:
                report += f" - {text[:40]}"
            if el.get('testid'):
                report += f" [testid: {el['testid']}]"
            report += "\n"
        
        return report

# ========== КОМАНДЫ БОТА ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **X.com Агент-исследователь**\n\n"
        "🔍 **Команды:**\n"
        "/explore — запустить исследование\n"
        "/explore_home — исследовать главную\n"
        "/explore_explore — исследовать обзор\n"
        "/explore_notifications — исследовать уведомления\n"
        "/explore_all — исследовать все страницы\n"
        "/report — показать отчет\n"
        "/status — статус бота\n"
        "/close — закрыть браузер",
        parse_mode='Markdown'
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
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.edit_text("✅ Авторизация выполнена!")
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Вы на главной странице X.com"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Запускаю агента-исследователя...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        explorer = XExplorer(page)
        
        # Сканируем текущую страницу
        url = page.url
        await explorer.scan_page(url, "current")
        
        # Кликаем по элементам
        elements = explorer.results['elements']
        await explorer.click_elements(elements, max_clicks=15)
        
        # Формируем отчет
        report = explorer.get_report()
        await msg.edit_text(report, parse_mode='Markdown')
        
        # Отправляем скриншоты
        if explorer.results['screenshots']:
            for s in explorer.results['screenshots'][:3]:
                try:
                    await update.message.reply_photo(
                        photo=s['data'],
                        caption=f"📸 {s['stage']}"
                    )
                except:
                    pass
        
        # Сохраняем результаты
        global exploration_results
        exploration_results = explorer.results
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🏠 Исследую главную страницу...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        explorer = XExplorer(page)
        
        # Переходим на главную
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Сканируем
        elements = await explorer.scan_page('https://x.com/home', 'home')
        
        # Кликаем по элементам (кроме опасных)
        safe_elements = [e for e in elements if not e.get('href', '').startswith('http')]
        await explorer.click_elements(safe_elements, max_clicks=20)
        
        report = explorer.get_report()
        await msg.edit_text(report, parse_mode='Markdown')
        
        # Отправляем скриншоты
        if explorer.results['screenshots']:
            for s in explorer.results['screenshots'][:2]:
                try:
                    await update.message.reply_photo(
                        photo=s['data'],
                        caption=f"📸 {s['stage']}"
                    )
                except:
                    pass
        
        global exploration_results
        exploration_results = explorer.results
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore_explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📈 Исследую страницу обзора...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        explorer = XExplorer(page)
        
        await page.goto('https://x.com/explore', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        elements = await explorer.scan_page('https://x.com/explore', 'explore')
        safe_elements = [e for e in elements if not e.get('href', '').startswith('http')]
        await explorer.click_elements(safe_elements, max_clicks=15)
        
        report = explorer.get_report()
        await msg.edit_text(report, parse_mode='Markdown')
        
        if explorer.results['screenshots']:
            for s in explorer.results['screenshots'][:2]:
                try:
                    await update.message.reply_photo(
                        photo=s['data'],
                        caption=f"📸 {s['stage']}"
                    )
                except:
                    pass
        
        global exploration_results
        exploration_results = explorer.results
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔔 Исследую страницу уведомлений...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        explorer = XExplorer(page)
        
        await page.goto('https://x.com/notifications', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        elements = await explorer.scan_page('https://x.com/notifications', 'notifications')
        safe_elements = [e for e in elements if not e.get('href', '').startswith('http')]
        await explorer.click_elements(safe_elements, max_clicks=15)
        
        report = explorer.get_report()
        await msg.edit_text(report, parse_mode='Markdown')
        
        if explorer.results['screenshots']:
            for s in explorer.results['screenshots'][:2]:
                try:
                    await update.message.reply_photo(
                        photo=s['data'],
                        caption=f"📸 {s['stage']}"
                    )
                except:
                    pass
        
        global exploration_results
        exploration_results = explorer.results
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌐 Исследую все страницы... (это займет время)")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        pages = [
            ('https://x.com/home', 'home'),
            ('https://x.com/explore', 'explore'),
            ('https://x.com/notifications', 'notifications'),
        ]
        
        all_results = {}
        
        for url, name in pages:
            explorer = XExplorer(page)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            
            elements = await explorer.scan_page(url, name)
            safe_elements = [e for e in elements if not e.get('href', '').startswith('http')]
            await explorer.click_elements(safe_elements, max_clicks=10)
            
            all_results[name] = explorer.results
            
            # Отправляем промежуточный отчет
            await update.message.reply_text(
                f"✅ {name} исследована: {len(elements)} элементов, {len(explorer.results['clicked'])} кликов"
            )
        
        # Формируем сводный отчет
        total_elements = sum(len(r['elements']) for r in all_results.values())
        total_clicks = sum(len(r['clicked']) for r in all_results.values())
        total_errors = sum(len(r['errors']) for r in all_results.values())
        
        report = "📊 **Сводный отчет по всем страницам**\n\n"
        report += f"📄 Страниц: {len(pages)}\n"
        report += f"🔍 Всего элементов: {total_elements}\n"
        report += f"🖱️ Всего кликов: {total_clicks}\n"
        report += f"❌ Ошибок: {total_errors}\n\n"
        
        for name, results in all_results.items():
            report += f"**{name}:** {len(results['elements'])} элементов, {len(results['clicked'])} кликов\n"
        
        await msg.edit_text(report, parse_mode='Markdown')
        
        global exploration_results
        exploration_results = all_results
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global exploration_results
    
    if not exploration_results or not exploration_results.get('elements'):
        await update.message.reply_text("📭 Нет данных. Запустите исследование: /explore")
        return
    
    if isinstance(exploration_results, dict) and 'elements' in exploration_results:
        # Один результат
        report = "📊 **Отчет исследования**\n\n"
        report += f"🔍 Найдено: {len(exploration_results['elements'])}\n"
        report += f"🖱️ Кликнуто: {len(exploration_results.get('clicked', []))}\n"
        report += f"❌ Ошибок: {len(exploration_results.get('errors', []))}\n\n"
        
        report += "📋 **Последние логи:**\n"
        for log in exploration_results.get('logs', [])[-10:]:
            report += f"• {log}\n"
        
        await update.message.reply_text(report, parse_mode='Markdown')
    else:
        # Несколько результатов
        report = "📊 **Сводный отчет**\n\n"
        for name, results in exploration_results.items():
            if isinstance(results, dict):
                report += f"**{name}:** {len(results.get('elements', []))} элементов, {len(results.get('clicked', []))} кликов\n"
        await update.message.reply_text(report, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = "📊 **Статус агента**\n\n"
    
    if browser_data:
        status_msg += "🌐 Браузер: ✅ Запущен\n"
        try:
            url = browser_data['page'].url
            status_msg += f"🔗 Текущая страница: {url[:60]}\n"
        except:
            status_msg += "🔗 Страница: Неизвестно\n"
    else:
        status_msg += "🌐 Браузер: ❌ Не запущен\n"
    
    if exploration_results:
        if isinstance(exploration_results, dict) and 'elements' in exploration_results:
            status_msg += f"\n📊 Последнее исследование:\n"
            status_msg += f"   🔍 Элементов: {len(exploration_results['elements'])}\n"
            status_msg += f"   🖱️ Кликов: {len(exploration_results.get('clicked', []))}\n"
    
    await update.message.reply_text(status_msg, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("explore", explore))
    app.add_handler(CommandHandler("explore_home", explore_home))
    app.add_handler(CommandHandler("explore_explore", explore_explore))
    app.add_handler(CommandHandler("explore_notifications", explore_notifications))
    app.add_handler(CommandHandler("explore_all", explore_all))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🐦 X.com Агент-исследователь запущен!")
    print("📌 Команды:")
    print("   🔐 /login — авторизация")
    print("   🔍 /explore — исследовать текущую страницу")
    print("   🏠 /explore_home — исследовать главную")
    print("   📈 /explore_explore — исследовать обзор")
    print("   🔔 /explore_notifications — исследовать уведомления")
    print("   🌐 /explore_all — исследовать все страницы")
    print("   📊 /report — показать отчет")
    print("   📊 /status — статус")
    print("   ❌ /close — закрыть браузер")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()