# bot.py - Полный бот с агентом-исследователем
import os
import sys
import subprocess
import json
import logging
import traceback
import asyncio
import math
import random
import time
from datetime import datetime
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass, field
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import Page, async_playwright
from playwright_stealth import stealth_async

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

# ========== КЛАСС ТРЕКЕРА ПРОГРЕССА ==========
class ProgressTracker:
    """Отслеживание прогресса и зависаний"""
    
    def __init__(self, update, msg):
        self.update = update
        self.msg = msg
        self.start_time = time.time()
        self.last_update = time.time()
        self.steps = []
        self.current_step = 0
        self.total_steps = 0
        self.is_stuck = False
        self.stuck_warning_sent = False
        self.progress_bars = []
        
    def set_total_steps(self, total: int):
        self.total_steps = total
        self.progress_bars = ['░'] * 20
        
    async def update(self, step_name: str):
        self.current_step += 1
        self.steps.append({
            'name': step_name,
            'time': time.time(),
            'timestamp': datetime.now().isoformat()
        })
        self.last_update = time.time()
        
        progress = min(1.0, self.current_step / self.total_steps if self.total_steps > 0 else 0)
        filled = int(progress * 20)
        self.progress_bars = ['█'] * filled + ['░'] * (20 - filled)
        
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        status = "🟢"
        if self.is_stuck:
            status = "🔴 ЗАВИС!"
        elif time.time() - self.last_update > 10:
            status = "🟡 Медленно..."
        
        progress_text = f"""
==================================================
⏳ ПРОГРЕСС: {self.current_step}/{self.total_steps}
[{''.join(self.progress_bars)}] {int(progress * 100)}%

{status} ТЕКУЩИЙ ШАГ: {step_name}
🕐 ВРЕМЯ: {minutes}м {seconds}с
📊 ШАГОВ: {len(self.steps)}
==================================================
"""
        
        try:
            await self.msg.edit_text(progress_text)
        except:
            pass
            
    async def check_stuck(self):
        if time.time() - self.last_update > 15:
            self.is_stuck = True
            if not self.stuck_warning_sent:
                self.stuck_warning_sent = True
                await self.update.message.reply_text("⚠️ Агент возможно завис! Перезапускаю...")
                try:
                    return True
                except:
                    pass
        else:
            self.is_stuck = False
            self.stuck_warning_sent = False
        return False
    
    def get_report(self) -> str:
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        report = f"""
📊 ОТЧЕТ О ПРОГРЕССЕ
{'='*40}
✅ Шагов выполнено: {self.current_step}
📋 Всего шагов: {self.total_steps}
🕐 Время: {minutes}м {seconds}с
{'='*40}
"""
        for step in self.steps[-10:]:
            report += f"  • {step['name']}\n"
        
        return report

# ========== КЛАСС АГЕНТА-ИССЛЕДОВАТЕЛЯ ==========
class SuperResearcherAgent:
    """Агент-исследователь, который обходит ВСЁ на сайте"""
    
    def __init__(self, page: Page, progress_tracker: ProgressTracker):
        self.page = page
        self.progress = progress_tracker
        self.visited_urls = set()
        self.visited_elements = set()
        self.full_map = {
            'pages': [],
            'elements': [],
            'interactions': [],
            'flows': [],
            'states': [],
            'screenshots': []
        }
        self.is_running = True
        self.last_activity = time.time()
        
    async def explore_everywhere(self):
        await self.progress.update("🚀 Запуск исследования...")
        
        await self.progress.update("📄 Анализ текущей страницы...")
        await self._explore_current_page()
        
        await self.progress.update("🗺️ Поиск всех страниц...")
        await self._discover_all_pages()
        
        total_pages = len(self.full_map['pages'])
        self.progress.set_total_steps(20 + total_pages * 5)
        
        for i, page_info in enumerate(self.full_map['pages'][:10]):
            if not self.is_running:
                break
            await self.progress.update(f"🌐 Посещение страницы {i+1}/{min(10, len(self.full_map['pages']))}: {page_info.get('text', 'Без названия')[:30]}")
            await self._visit_page(page_info)
            if await self.progress.check_stuck():
                await self._reset_agent()
        
        await self.progress.update("🖱️ Взаимодействие с элементами...")
        await self._interact_with_everything()
        
        await self.progress.update("📸 Сбор состояний...")
        await self._capture_all_states()
        
        await self.progress.update("🗺️ Построение карты сайта...")
        site_map = await self._build_site_map()
        
        await self.progress.update("✅ Исследование завершено!")
        return site_map
    
    async def _discover_all_pages(self):
        nav_links = await self.page.evaluate('''
            () => {
                const links = [];
                const selectors = [
                    'nav a', '[role="navigation"] a', '[data-testid*="nav"] a',
                    '[data-testid*="tab"]', '[data-testid*="menu"] a',
                    'header a', 'footer a', 'a[href*="/"]'
                ];
                
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        const href = el.getAttribute('href');
                        if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                            links.push({
                                text: el.textContent?.trim()?.slice(0, 50) || '',
                                href: href,
                                testid: el.getAttribute('data-testid') || ''
                            });
                        }
                    });
                });
                return links;
            }
        ''')
        
        for link in nav_links:
            if link['href'] not in self.visited_urls:
                self.full_map['pages'].append(link)
        
        await self.progress.update(f"🗺️ Найдено страниц: {len(self.full_map['pages'])}")
    
    async def _visit_page(self, page_info):
        url = page_info['href']
        if url in self.visited_urls:
            return
            
        try:
            self.last_activity = time.time()
            await self.page.goto(url, wait_until='domcontentloaded', timeout=10000)
            self.visited_urls.add(url)
            await self._explore_current_page()
            await self._take_screenshot(f'page_{len(self.visited_urls)}')
            await self.page.go_back()
            await asyncio.sleep(1)
            self.last_activity = time.time()
        except Exception as e:
            await self.progress.update(f"⚠️ Ошибка: {str(e)[:50]}")
    
    async def _explore_current_page(self):
        elements = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    if (rect.top > window.innerHeight) return;
                    
                    result.push({
                        tag: el.tagName.toLowerCase(),
                        text: el.textContent?.trim()?.slice(0, 200) || '',
                        testid: el.getAttribute('data-testid') || '',
                        id: el.id || '',
                        class: el.className || '',
                        role: el.getAttribute('role') || '',
                        type: el.getAttribute('type') || '',
                        href: el.getAttribute('href') || '',
                        placeholder: el.getAttribute('placeholder') || '',
                        aria_label: el.getAttribute('aria-label') || '',
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    });
                });
                return result;
            }
        ''')
        
        for el in elements:
            if el['testid'] not in self.visited_elements:
                self.visited_elements.add(el['testid'] or el['id'] or el['tag'])
                self.full_map['elements'].append(el)
        
        await self._find_interactive_elements()
        self.last_activity = time.time()
    
    async def _find_interactive_elements(self):
        interactive = await self.page.evaluate('''
            () => {
                const elements = [];
                const selectors = [
                    'button', '[role="button"]', '[data-testid*="button"]',
                    'a[href]', 'input:not([type="hidden"])', 'select', 'textarea',
                    '[role="tab"]', '[role="menuitem"]', '[role="checkbox"]',
                    '[role="radio"]', '[role="switch"]', '[role="link"]'
                ];
                
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            const text = el.textContent?.trim()?.slice(0, 50) || '';
                            const dangerous = ['logout', 'delete', 'remove', 'exit', 'signout'];
                            if (dangerous.some(word => text.toLowerCase().includes(word))) return;
                            
                            elements.push({
                                tag: el.tagName.toLowerCase(),
                                text: text,
                                testid: el.getAttribute('data-testid') || '',
                                id: el.id || '',
                                role: el.getAttribute('role') || '',
                                type: el.getAttribute('type') || '',
                                href: el.getAttribute('href') || '',
                                placeholder: el.getAttribute('placeholder') || '',
                                aria_label: el.getAttribute('aria-label') || '',
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2)
                            });
                        }
                    });
                });
                return elements;
            }
        ''')
        
        self.full_map['interactive'] = interactive
    
    async def _interact_with_everything(self):
        interactive = self.full_map.get('interactive', [])
        total = min(20, len(interactive))
        
        for i, el in enumerate(interactive[:total]):
            if not self.is_running:
                break
            await self.progress.update(f"🖱️ Тест {i+1}/{total}: {el.get('text', 'Без текста')[:30]}")
            
            try:
                await self._human_like_move(el['x'], el['y'])
                await asyncio.sleep(random.uniform(0.3, 0.6))
                
                before_url = self.page.url
                await self.page.mouse.click(el['x'], el['y'])
                await asyncio.sleep(random.uniform(0.5, 1.5))
                after_url = self.page.url
                
                self.full_map['interactions'].append({
                    'element': el,
                    'before_url': before_url,
                    'after_url': after_url,
                    'changed': before_url != after_url,
                    'timestamp': datetime.now().isoformat()
                })
                
                if i % 3 == 0:
                    await self._take_screenshot(f'interaction_{i}')
                
                if before_url != after_url:
                    await self._explore_current_page()
                    await self.page.go_back()
                    await asyncio.sleep(1)
                
                if await self.progress.check_stuck():
                    await self._reset_agent()
            except Exception as e:
                await self.progress.update(f"⚠️ Ошибка: {str(e)[:50]}")
                continue
            
            self.last_activity = time.time()
    
    async def _capture_all_states(self):
        states = {'default': await self._get_page_state()}
        
        for scroll_pos in [0, 300, 600]:
            await self.page.evaluate(f'window.scrollTo(0, {scroll_pos})')
            await asyncio.sleep(0.3)
            states[f'scroll_{scroll_pos}'] = await self._get_page_state()
        
        self.full_map['states'] = states
    
    async def _get_page_state(self) -> Dict:
        return await self.page.evaluate('''
            () => {
                return {
                    url: window.location.href,
                    title: document.title,
                    scrollY: window.scrollY,
                    visibleCount: document.querySelectorAll('*').length,
                    interactiveCount: document.querySelectorAll('button, a, input, select, textarea').length
                };
            }
        ''')
    
    async def _take_screenshot(self, name: str):
        try:
            filename = f"screenshot_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self.page.screenshot(path=filename, full_page=True)
            self.full_map['screenshots'].append(filename)
        except:
            pass
    
    async def _human_like_move(self, x: float, y: float):
        try:
            current = await self.page.mouse.position()
            cx, cy = current['x'], current['y']
            
            distance = ((x - cx)**2 + (y - cy)**2)**0.5
            duration = min(0.8, distance / 1500) + random.uniform(0.1, 0.2)
            steps = max(10, int(duration * 30))
            
            for i in range(steps):
                progress = (i + 1) / steps
                human_curve = 1 - (1 - progress)**2.5
                noise_x = random.uniform(-2, 2) * (1 - progress)
                noise_y = random.uniform(-2, 2) * (1 - progress)
                
                cur_x = cx + (x - cx) * human_curve + noise_x
                cur_y = cy + (y - cy) * human_curve + noise_y
                
                await self.page.mouse.move(cur_x, cur_y)
                await asyncio.sleep(duration / steps)
        except:
            pass
    
    async def _reset_agent(self):
        await self.progress.update("🔄 Сброс агента...")
        try:
            await self.page.reload()
            await asyncio.sleep(2)
            await self.progress.update("✅ Агент перезапущен")
        except:
            await self.progress.update("⚠️ Не удалось перезагрузить страницу")
    
    async def _build_site_map(self) -> Dict:
        return {
            'timestamp': datetime.now().isoformat(),
            'url': self.page.url,
            'total_pages': len(self.visited_urls),
            'total_elements': len(self.full_map['elements']),
            'total_interactions': len(self.full_map['interactions']),
            'pages': list(self.visited_urls),
            'elements_by_type': self._group_elements_by_type(),
            'interactive_elements': self.full_map.get('interactive', []),
            'interactions': self.full_map['interactions'],
            'states': self.full_map.get('states', {}),
            'flows': self._analyze_flows(),
            'screenshots': self.full_map['screenshots'],
            'progress_report': self.progress.get_report()
        }
    
    def _group_elements_by_type(self) -> Dict:
        groups = {}
        for el in self.full_map['elements']:
            tag = el.get('tag', 'unknown')
            if tag not in groups:
                groups[tag] = []
            groups[tag].append(el)
        return groups
    
    def _analyze_flows(self) -> List[Dict]:
        flows = []
        for interaction in self.full_map['interactions']:
            if interaction.get('changed'):
                flows.append({
                    'from': interaction.get('before_url', ''),
                    'to': interaction.get('after_url', ''),
                    'via': interaction.get('element', {}).get('text', 'unknown')
                })
        return flows
    
    def save_map(self, filename: str = None):
        if not filename:
            filename = f"site_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.full_map, f, indent=2, ensure_ascii=False, default=str)
        
        return filename

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

# ========== КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с агентом-исследователем\n\n"
        "📌 Основные команды:\n"
        "/xlogin - вход в X.com\n"
        "/explore - ЗАПУСТИТЬ ИССЛЕДОВАНИЕ 🚀\n"
        "/tweets - все посты\n"
        "/tweet <номер> - конкретный пост\n"
        "/last - последний пост\n"
        "/screen - скриншот\n"
        "/status - состояние браузера\n"
        "/close - закрыть браузер"
    )

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('about:blank')
        await page.wait_for_timeout(1000)
        
        try:
            await browser['context'].clear_cookies()
        except:
            pass
        
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([cookie])
            except:
                pass
        
        await page.goto('https://x.com', wait_until='commit', timeout=15000)
        await page.wait_for_timeout(3000)
        
        await msg.edit_text("✅ Зашёл в X.com!")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def explore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает агента-исследователя"""
    msg = await update.message.reply_text(
        "🗺️ **ЗАПУСК ИССЛЕДОВАНИЯ**\n\n"
        "Агент обойдет:\n"
        "• Все страницы\n"
        "• Все кнопки\n"
        "• Все элементы\n"
        "• Соберет состояния\n\n"
        "⏳ Прогресс будет обновляться..."
    )
    
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
        
        # Создаем трекер и агента
        tracker = ProgressTracker(update, msg)
        agent = SuperResearcherAgent(page, tracker)
        
        # Запускаем исследование
        site_map = await agent.explore_everywhere()
        
        # Сохраняем карту
        map_file = agent.save_map()
        
        # Отправляем итоги
        await update.message.reply_text(f"""
✅ **ИССЛЕДОВАНИЕ ЗАВЕРШЕНО!**

📊 ИТОГИ:
   • Страниц: {len(agent.visited_urls)}
   • Элементов: {len(agent.full_map['elements'])}
   • Взаимодействий: {len(agent.full_map['interactions'])}
   • Скриншотов: {len(agent.full_map['screenshots'])}

📁 Файл: {map_file}
""")
        
        # Отправляем карту
        await update.message.reply_document(
            document=open(map_file, 'rb'),
            filename=os.path.basename(map_file),
            caption="🗺️ Полная карта сайта"
        )
        
        # Отправляем скриншоты (первые 3)
        for screenshot in agent.full_map['screenshots'][:3]:
            try:
                with open(screenshot, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"📸 {os.path.basename(screenshot)}"
                    )
            except:
                pass
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Ищу посты...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 800)')
            await asyncio.sleep(0.8)
        
        posts = await page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    const rect = el.getBoundingClientRect();
                    const authorEl = el.querySelector('[data-testid="User-Name"]');
                    const author = authorEl?.textContent?.trim() || '';
                    
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            text: text.slice(0, 80),
                            author: author.slice(0, 50),
                            y: rect.y
                        });
                    }
                });
                return result;
            }
        ''')
        
        if not posts:
            await msg.edit_text("❌ Посты не найдены")
            return
        
        posts_sorted = sorted(posts, key=lambda x: x['y'])
        
        result = f"📋 НАЙДЕНО {len(posts_sorted)} ПОСТОВ:\n\n"
        for i, post in enumerate(posts_sorted[:15], 1):
            result += f"{i}. {post['text'][:80]}\n"
            if post['author']:
                result += f"   👤 {post['author']}\n"
            result += "\n"
        
        if len(posts_sorted) > 15:
            result += f"... и еще {len(posts_sorted) - 15} постов"
        
        await msg.edit_text(result)
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи номер поста: /tweet 1")
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
                    
                    const likes = likeEl?.textContent?.trim() || '0';
                    const retweets = retweetEl?.textContent?.trim() || '0';
                    const replies = replyEl?.textContent?.trim() || '0';
                    
                    const timeEl = el.querySelector('time');
                    const time = timeEl?.getAttribute('datetime') || '';
                    
                    if (rect.width > 0 && rect.height > 0) {
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
            await msg.edit_text("❌ Посты не найдены")
            return
        
        if num >= len(posts):
            await msg.edit_text(f"❌ Пост #{num + 1} не найден. Всего: {len(posts)}")
            return
        
        posts_reversed = list(reversed(posts))
        post = posts_reversed[num]
        
        text_preview = post['text'][:120]
        if len(post['text']) > 120:
            text_preview += '...'
        
        time_str = post['time']
        if time_str:
            try:
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                time_str = dt.strftime('%d %b %Y, %H:%M')
            except:
                time_str = post['time'][:10]
        
        result = f"""📌 #{num + 1} @{post['author']}

{text_preview}

❤️ {post['likes']}  🔁 {post['retweets']}  💬 {post['replies']}
🕐 {time_str}"""
        
        await msg.edit_text(result)
        
        # Скриншот поста
        try:
            viewport = await page.viewport_size()
            if not viewport:
                viewport = {'width': 1280, 'height': 720}
            
            clip_x = max(0, post['x'] - post['width']/2 - 20)
            clip_y = max(0, post['y'] - post['height']/2 - 20)
            clip_width = min(post['width'] + 40, viewport['width'])
            clip_height = min(post['height'] + 40, viewport['height'])
            
            if clip_width > 20 and clip_height > 20:
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
                await update.message.reply_photo(
                    photo=screenshot,
                    caption=f"📸 Пост #{num + 1}"
                )
        except:
            pass
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def last_tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ['1']
    await tweet_command(update, context)

async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("explore", explore_command))  # 👈 КОМАНДА ДЛЯ ЗАПУСКА
    app.add_handler(CommandHandler("tweets", tweets_command))
    app.add_handler(CommandHandler("tweet", tweet_command))
    app.add_handler(CommandHandler("last", last_tweet))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("close", close_command))
    
    print("🤖 Бот с агентом-исследователем запущен...")
    print("📌 Команды:")
    print("   /xlogin - вход в X.com")
    print("   /explore - ЗАПУСТИТЬ ИССЛЕДОВАНИЕ 🚀")
    print("   /tweets - все посты")
    print("   /tweet <номер> - конкретный пост")
    print("   /last - последний пост")
    print("   /screen - скриншот")
    print("   /status - состояние браузера")
    print("   /close - закрыть браузер")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()