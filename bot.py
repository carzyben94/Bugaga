# x_model_builder.py - Строит полную модель X.com
import os
import sys
import subprocess
import json
import asyncio
import logging
import traceback
import re
from datetime import datetime
from typing import List, Dict, Any, Set
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Куки X.com
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
]

browser_data = None
browser_lock = False
site_model = {}

# ========== УСТАНОВКА БРАУЗЕРА ==========
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
                '--disable-gpu'
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        for cookie in COOKIES:
            try:
                await context.add_cookies([cookie])
            except:
                pass
        
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
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== ПОСТРОИТЕЛЬ МОДЕЛИ САЙТА ==========
class SiteModelBuilder:
    def __init__(self, page):
        self.page = page
        self.model = {
            'pages': {},
            'components': {},
            'selectors': {},
            'testids': {},
            'attributes': {},
            'classes': {},
            'roles': {},
            'structure': {},
            'fields': {},
            'buttons': {},
            'links': {},
            'forms': {},
            'tweets': [],
            'navigation': {},
            'headers': {},
            'footers': {},
            'sidebars': {},
            'modals': {},
            'dropdowns': {},
            'inputs': {},
            'texts': {},
            'images': {},
            'videos': {},
            'metadata': {},
            'api_endpoints': [],
            'javascript': [],
            'css': [],
            'timestamp': datetime.now().isoformat()
        }
        self.visited_urls = set()
        
    async def build_full_model(self):
        """Строит полную модель сайта"""
        logger.info("🏗️ Начинаю построение полной модели X.com...")
        
        # 1. Базовая страница
        await self.analyze_page('https://x.com', 'home')
        
        # 2. Все разделы
        sections = [
            ('https://x.com/explore', 'explore'),
            ('https://x.com/notifications', 'notifications'),
            ('https://x.com/messages', 'messages'),
            ('https://x.com/settings', 'settings'),
            ('https://x.com/i/trends', 'trends'),
        ]
        
        for url, name in sections:
            await self.analyze_page(url, name)
        
        # 3. Глубокий анализ структуры
        await self.analyze_structure()
        
        # 4. Сбор всех компонентов
        await self.collect_all_components()
        
        # 5. Анализ DOM
        await self.analyze_dom()
        
        # 6. Сбор API вызовов
        await self.capture_api_calls()
        
        logger.info("✅ Модель сайта построена!")
        return self.model
    
    async def analyze_page(self, url: str, page_name: str):
        """Анализирует отдельную страницу"""
        try:
            logger.info(f"📄 Анализирую страницу: {page_name}")
            
            await self.page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            
            # Ждем загрузки
            await self.page.wait_for_load_state('networkidle', timeout=5000)
            
            # Собираем все данные со страницы
            page_data = await self.extract_page_data(page_name)
            self.model['pages'][page_name] = page_data
            
            # Добавляем URL
            self.visited_urls.add(url)
            
            # Скроллим для загрузки контента
            for _ in range(3):
                await self.page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(1)
            
            # Собираем дополнительный контент
            await self.extract_additional_content(page_name)
            
        except Exception as e:
            logger.error(f"Ошибка анализа {page_name}: {e}")
            self.model['pages'][page_name] = {'error': str(e)}
    
    async def extract_page_data(self, page_name: str) -> Dict:
        """Извлекает все данные со страницы"""
        return await self.page.evaluate(f'''
            () => {{
                const data = {{
                    url: window.location.href,
                    title: document.title,
                    html: document.documentElement.outerHTML.slice(0, 50000),
                    meta: {{}},
                    headers: [],
                    paragraphs: [],
                    links: [],
                    images: [],
                    videos: [],
                    forms: [],
                    inputs: [],
                    buttons: [],
                    dropdowns: [],
                    modals: [],
                    testids: [],
                    attributes: {{}},
                    classes: new Set(),
                    roles: new Set(),
                    textContent: document.body?.textContent?.slice(0, 10000) || '',
                    scripts: [],
                    styles: []
                }};
                
                // Meta теги
                document.querySelectorAll('meta').forEach(el => {{
                    const name = el.getAttribute('name') || el.getAttribute('property') || '';
                    const content = el.getAttribute('content') || '';
                    if (name && content) data.meta[name] = content;
                }});
                
                // Заголовки
                document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => {{
                    const text = el.textContent?.trim() || '';
                    if (text) data.headers.push({{
                        tag: el.tagName,
                        text: text.slice(0, 200),
                        level: el.tagName.replace('H', ''),
                        testid: el.getAttribute('data-testid') || ''
                    }});
                }});
                
                // Параграфы
                document.querySelectorAll('p').forEach(el => {{
                    const text = el.textContent?.trim() || '';
                    if (text && text.length > 10) data.paragraphs.push(text.slice(0, 500));
                }});
                
                // Ссылки
                document.querySelectorAll('a[href]').forEach(el => {{
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {{
                        data.links.push({{
                            href: href.slice(0, 200),
                            text: el.textContent?.trim()?.slice(0, 100) || '',
                            title: el.getAttribute('title') || '',
                            aria: el.getAttribute('aria-label') || '',
                            testid: el.getAttribute('data-testid') || '',
                            role: el.getAttribute('role') || ''
                        }});
                    }}
                }});
                
                // Изображения
                document.querySelectorAll('img').forEach(el => {{
                    const src = el.getAttribute('src');
                    if (src) {{
                        data.images.push({{
                            src: src.slice(0, 200),
                            alt: el.getAttribute('alt') || '',
                            title: el.getAttribute('title') || '',
                            testid: el.getAttribute('data-testid') || ''
                        }});
                    }}
                }});
                
                // Формы
                document.querySelectorAll('form').forEach(el => {{
                    const form = {{
                        action: el.getAttribute('action') || '',
                        method: el.getAttribute('method') || 'get',
                        id: el.id || '',
                        testid: el.getAttribute('data-testid') || '',
                        inputs: []
                    }};
                    el.querySelectorAll('input, textarea, select, button').forEach(input => {{
                        form.inputs.push({{
                            type: input.getAttribute('type') || input.tagName.toLowerCase(),
                            name: input.getAttribute('name') || '',
                            id: input.id || '',
                            placeholder: input.getAttribute('placeholder') || '',
                            value: input.value || '',
                            testid: input.getAttribute('data-testid') || '',
                            required: input.hasAttribute('required'),
                            disabled: input.hasAttribute('disabled'),
                            readonly: input.hasAttribute('readonly')
                        }});
                    }});
                    data.forms.push(form);
                }});
                
                // Кнопки
                document.querySelectorAll('button, [role="button"]').forEach(el => {{
                    data.buttons.push({{
                        text: el.textContent?.trim()?.slice(0, 50) || '',
                        testid: el.getAttribute('data-testid') || '',
                        aria: el.getAttribute('aria-label') || '',
                        role: el.getAttribute('role') || '',
                        type: el.getAttribute('type') || 'button',
                        disabled: el.hasAttribute('disabled'),
                        class: el.className?.slice(0, 100) || ''
                    }});
                }});
                
                // Все data-testid
                document.querySelectorAll('[data-testid]').forEach(el => {{
                    const testid = el.getAttribute('data-testid');
                    if (testid && !data.testids.includes(testid)) {{
                        data.testids.push(testid);
                    }}
                }});
                
                // Все атрибуты
                document.querySelectorAll('*').forEach(el => {{
                    for (const attr of el.attributes) {{
                        if (!data.attributes[attr.name]) data.attributes[attr.name] = new Set();
                        data.attributes[attr.name].add(attr.value?.slice(0, 100) || '');
                    }}
                    if (el.className) {{
                        el.className.split(' ').forEach(c => {{
                            if (c) data.classes.add(c.slice(0, 50));
                        }});
                    }}
                    const role = el.getAttribute('role');
                    if (role) data.roles.add(role);
                }});
                
                // Преобразуем Set в массивы
                data.classes = Array.from(data.classes);
                data.roles = Array.from(data.roles);
                const attrs = {{}};
                for (const [key, values] of Object.entries(data.attributes)) {{
                    attrs[key] = Array.from(values).slice(0, 20);
                }}
                data.attributes = attrs;
                
                return data;
            }}
        ''')
    
    async def extract_additional_content(self, page_name: str):
        """Извлекает дополнительный контент (посты, тренды)"""
        try:
            # Посты
            if page_name in ['home', 'explore']:
                tweets = await self.page.evaluate('''
                    () => {
                        const result = [];
                        document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                            const text = el.textContent?.trim() || '';
                            if (text.length > 20) {
                                const authorEl = el.querySelector('[data-testid="User-Name"]');
                                const timeEl = el.querySelector('time');
                                const likeEl = el.querySelector('[data-testid="like"]');
                                const retweetEl = el.querySelector('[data-testid="retweet"]');
                                const replyEl = el.querySelector('[data-testid="reply"]');
                                const viewsEl = el.querySelector('[data-testid="views"]');
                                
                                result.push({
                                    text: text.slice(0, 300),
                                    author: authorEl?.textContent?.trim() || 'Unknown',
                                    time: timeEl?.getAttribute('datetime') || '',
                                    likes: likeEl?.textContent?.trim() || '0',
                                    retweets: retweetEl?.textContent?.trim() || '0',
                                    replies: replyEl?.textContent?.trim() || '0',
                                    views: viewsEl?.textContent?.trim() || '0',
                                    testid: el.getAttribute('data-testid') || ''
                                });
                            }
                        });
                        return result;
                    }
                ''')
                self.model['tweets'].extend(tweets)
                logger.info(f"🐦 Собрано постов: {len(tweets)}")
            
            # Тренды
            if page_name == 'explore':
                trends = await self.page.evaluate('''
                    () => {
                        const result = [];
                        document.querySelectorAll('[data-testid="trend"]').forEach(el => {
                            const text = el.textContent?.trim() || '';
                            if (text) result.push(text.slice(0, 100));
                        });
                        return result;
                    }
                ''')
                self.model['metadata']['trends'] = trends
                logger.info(f"📈 Найдено трендов: {len(trends)}")
                
        except Exception as e:
            logger.error(f"Ошибка извлечения контента: {e}")
    
    async def analyze_structure(self):
        """Анализирует структуру сайта"""
        structure = await self.page.evaluate('''
            () => {
                const result = {
                    hasHeader: !!document.querySelector('header'),
                    hasFooter: !!document.querySelector('footer'),
                    hasNav: !!document.querySelector('nav'),
                    hasMain: !!document.querySelector('main'),
                    hasSidebar: !!document.querySelector('aside'),
                    hasArticle: !!document.querySelector('article'),
                    hasSection: !!document.querySelector('section'),
                    hasDialog: !!document.querySelector('dialog'),
                    hasModal: !!document.querySelector('[role="dialog"]'),
                    hasMenu: !!document.querySelector('[role="menu"]'),
                    hasTablist: !!document.querySelector('[role="tablist"]'),
                    hasToolbar: !!document.querySelector('[role="toolbar"]'),
                    mainContent: '',
                    sidebarContent: '',
                    headerContent: '',
                    footerContent: ''
                };
                
                const main = document.querySelector('main');
                if (main) result.mainContent = main.textContent?.slice(0, 500) || '';
                
                const sidebar = document.querySelector('aside');
                if (sidebar) result.sidebarContent = sidebar.textContent?.slice(0, 200) || '';
                
                const header = document.querySelector('header');
                if (header) result.headerContent = header.textContent?.slice(0, 200) || '';
                
                const footer = document.querySelector('footer');
                if (footer) result.footerContent = footer.textContent?.slice(0, 200) || '';
                
                // Структура заголовков
                result.headings = {};
                document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => {
                    const level = el.tagName;
                    if (!result.headings[level]) result.headings[level] = 0;
                    result.headings[level]++;
                });
                
                return result;
            }
        ''')
        self.model['structure'] = structure
    
    async def collect_all_components(self):
        """Собирает все компоненты сайта"""
        components = await self.page.evaluate('''
            () => {
                const result = {
                    buttons: {},
                    inputs: {},
                    dropdowns: [],
                    modals: [],
                    tabs: [],
                    menus: [],
                    lists: [],
                    cards: [],
                    avatars: [],
                    badges: [],
                    progress: [],
                    notifications: [],
                    searchFields: [],
                    navigation: {}
                };
                
                // Навигация
                const navItems = document.querySelectorAll('[data-testid*="AppTabBar"]');
                navItems.forEach(el => {
                    const testid = el.getAttribute('data-testid');
                    if (testid) {
                        result.navigation[testid] = {
                            text: el.textContent?.trim() || '',
                            present: true,
                            testid: testid
                        };
                    }
                });
                
                // Кнопки с testid
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const testid = el.getAttribute('data-testid');
                    if (testid && testid.includes('button')) {
                        result.buttons[testid] = {
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            testid: testid,
                            tag: el.tagName
                        };
                    }
                    
                    // Поля ввода
                    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                        const type = el.getAttribute('type') || 'text';
                        result.inputs[testid || el.id || 'unknown'] = {
                            type: type,
                            placeholder: el.getAttribute('placeholder') || '',
                            testid: testid || '',
                            name: el.getAttribute('name') || ''
                        };
                    }
                    
                    // Поиск
                    if (testid === 'Search' || testid?.includes('search')) {
                        result.searchFields.push({
                            testid: testid,
                            placeholder: el.getAttribute('placeholder') || '',
                            type: el.tagName
                        });
                    }
                });
                
                // Списки
                document.querySelectorAll('ul, ol').forEach(el => {
                    const items = el.querySelectorAll('li').length;
                    if (items > 0) {
                        result.lists.push({
                            items: items,
                            testid: el.getAttribute('data-testid') || '',
                            role: el.getAttribute('role') || ''
                        });
                    }
                });
                
                // Карточки
                document.querySelectorAll('[data-testid*="card"], article').forEach(el => {
                    const testid = el.getAttribute('data-testid') || '';
                    result.cards.push({
                        testid: testid,
                        text: el.textContent?.slice(0, 100) || '',
                        hasImage: !!el.querySelector('img')
                    });
                });
                
                return result;
            }
        ''')
        
        self.model['components'] = components
        logger.info(f"🧩 Собрано компонентов: {len(components)}")
    
    async def analyze_dom(self):
        """Глубокий анализ DOM структуры"""
        dom = await self.page.evaluate('''
            () => {
                const result = {
                    totalElements: document.querySelectorAll('*').length,
                    uniqueTags: new Set(),
                    elementCounts: {},
                    depth: 0,
                    attributes: {},
                    textNodes: 0
                };
                
                // Считаем элементы по тегам
                document.querySelectorAll('*').forEach(el => {
                    const tag = el.tagName.toLowerCase();
                    if (!result.elementCounts[tag]) result.elementCounts[tag] = 0;
                    result.elementCounts[tag]++;
                    result.uniqueTags.add(tag);
                    
                    // Собираем частоту атрибутов
                    for (const attr of el.attributes) {
                        if (!result.attributes[attr.name]) result.attributes[attr.name] = 0;
                        result.attributes[attr.name]++;
                    }
                });
                
                // Максимальная глубина
                function getMaxDepth(node, depth = 0) {
                    let max = depth;
                    for (const child of node.children) {
                        max = Math.max(max, getMaxDepth(child, depth + 1));
                    }
                    return max;
                }
                result.depth = getMaxDepth(document.body);
                
                result.uniqueTags = Array.from(result.uniqueTags);
                
                // Сортируем по популярности
                const sorted = Object.entries(result.elementCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 20);
                result.elementCounts = Object.fromEntries(sorted);
                
                return result;
            }
        ''')
        self.model['metadata']['dom'] = dom
        logger.info(f"📊 DOM: {dom['totalElements']} элементов, глубина {dom['depth']}")
    
    async def capture_api_calls(self):
        """Перехватывает API вызовы"""
        api_calls = []
        
        # Перехватываем запросы
        self.page.on('request', lambda request: api_calls.append({
            'url': request.url,
            'method': request.method,
            'headers': dict(request.headers),
            'resourceType': request.resource_type
        }))
        
        # Ждем немного для сбора
        await asyncio.sleep(3)
        
        # Фильтруем API вызовы X.com
        api_calls = [call for call in api_calls if 'x.com' in call['url'] and 
                    (call['resourceType'] in ['xhr', 'fetch'] or 
                     'api' in call['url'] or 'graphql' in call['url'])]
        
        self.model['api_endpoints'] = api_calls[:20]  # Топ 20
        logger.info(f"🌐 Перехвачено API вызовов: {len(api_calls)}")
    
    async def save_model(self, filename: str):
        """Сохраняет модель в файл"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.model, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Модель сохранена: {filename}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏗️ **X.com Complete Model Builder**\n\n"
        "Строит полную модель сайта X.com:\n"
        "• Все страницы и разделы\n"
        "• Все элементы DOM\n"
        "• Все testid и компоненты\n"
        "• Структура и навигация\n"
        "• API вызовы\n"
        "• Полная карта сайта\n\n"
        "📌 Команды:\n"
        "/build - построить полную модель\n"
        "/model - показать модель\n"
        "/components - все компоненты\n"
        "/testids - все testid\n"
        "/structure - структура сайта\n"
        "/export - экспортировать JSON\n"
        "/xlogin - войти в X.com"
    )

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await msg.edit_text("✅ Вход выполнен!")
        await update.message.reply_photo(photo=screenshot, caption="📸 X.com")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def build_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Строит полную модель сайта"""
    msg = await update.message.reply_text(
        "🏗️ **Начинаю построение полной модели X.com...**\n\n"
        "📄 Анализирую страницы:\n"
        "• Главная\n"
        "• Обзор\n"
        "• Уведомления\n"
        "• Сообщения\n"
        "• Настройки\n"
        "• Тренды\n\n"
        "⏳ Это займет 2-3 минуты..."
    )
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Идем на X.com
        await page.goto('https://x.com', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Строим модель
        builder = SiteModelBuilder(page)
        model = await builder.build_full_model()
        
        # Сохраняем глобально
        global site_model
        site_model = model
        
        # Отчет
        report = f"📊 **МОДЕЛЬ ПОСТРОЕНА!**\n\n"
        report += f"📄 Страниц: {len(model['pages'])}\n"
        report += f"🔘 Кнопок: {len(model['components'].get('buttons', {}))}\n"
        report += f"🏷️ TestID: {len(model.get('testids', {}))}\n"
        report += f"📝 Форм: {len(model['pages'].get('home', {}).get('forms', []))}\n"
        report += f"🔗 Ссылок: {len(model['pages'].get('home', {}).get('links', []))}\n"
        report += f"🐦 Постов: {len(model.get('tweets', []))}\n"
        report += f"🌐 API вызовов: {len(model.get('api_endpoints', []))}\n"
        report += f"📊 DOM элементов: {model.get('metadata', {}).get('dom', {}).get('totalElements', 0)}\n\n"
        
        report += f"**Структура:**\n"
        structure = model.get('structure', {})
        report += f"• Header: {'✅' if structure.get('hasHeader') else '❌'}\n"
        report += f"• Footer: {'✅' if structure.get('hasFooter') else '❌'}\n"
        report += f"• Main: {'✅' if structure.get('hasMain') else '❌'}\n"
        report += f"• Sidebar: {'✅' if structure.get('hasSidebar') else '❌'}\n"
        
        await msg.edit_text(report)
        
        # Сохраняем модель
        filename = f"x_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await builder.save_model(filename)
        
        # Отправляем файл
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption="📄 Полная модель X.com"
        )
        os.remove(filename)
        
        # Скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 Текущая страница")
        
        logger.info(f"✅ Модель построена для user {update.effective_user.id}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Build error: {traceback.format_exc()}")

async def show_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает модель"""
    global site_model
    if not site_model:
        await update.message.reply_text("❌ Модель не построена. Сначала /build")
        return
    
    model = site_model
    
    report = f"🏗️ **ПОЛНАЯ МОДЕЛЬ X.COM**\n\n"
    report += f"🕐 {model.get('timestamp', '')[:19]}\n\n"
    
    # Страницы
    report += f"**📄 СТРАНИЦЫ ({len(model.get('pages', {}))}):**\n"
    for page_name, data in model.get('pages', {}).items():
        if isinstance(data, dict) and 'error' not in data:
            title = data.get('title', '')[:30]
            report += f"• {page_name}: {title}\n"
    report += "\n"
    
    # Компоненты
    comps = model.get('components', {})
    report += f"**🧩 КОМПОНЕНТЫ:**\n"
    report += f"• Кнопок: {len(comps.get('buttons', {}))}\n"
    report += f"• Поля ввода: {len(comps.get('inputs', {}))}\n"
    report += f"• Карточек: {len(comps.get('cards', []))}\n"
    report += f"• Списков: {len(comps.get('lists', []))}\n"
    report += f"• Поисков: {len(comps.get('searchFields', []))}\n"
    report += "\n"
    
    # Навигация
    nav = comps.get('navigation', {})
    if nav:
        report += f"**🧭 НАВИГАЦИЯ:**\n"
        for testid, info in nav.items():
            report += f"• {testid}: {info.get('text', '')[:30]}\n"
        report += "\n"
    
    # API
    api = model.get('api_endpoints', [])
    if api:
        report += f"**🌐 API ({len(api)}):**\n"
        for call in api[:5]:
            report += f"• {call.get('method', 'GET')}: {call.get('url', '')[:50]}\n"
        if len(api) > 5:
            report += f"• ... и еще {len(api) - 5}\n"
    
    await update.message.reply_text(report)

async def show_components(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все компоненты"""
    global site_model
    if not site_model:
        await update.message.reply_text("❌ Модель не построена. Сначала /build")
        return
    
    comps = site_model.get('components', {})
    
    result = "🧩 **ВСЕ КОМПОНЕНТЫ**\n\n"
    
    # Кнопки
    buttons = comps.get('buttons', {})
    if buttons:
        result += f"**🔘 КНОПКИ ({len(buttons)}):**\n"
        for testid, info in list(buttons.items())[:10]:
            result += f"• `{testid}`: {info.get('text', '')[:30]}\n"
        if len(buttons) > 10:
            result += f"• ... и еще {len(buttons) - 10}\n"
        result += "\n"
    
    # Поля ввода
    inputs = comps.get('inputs', {})
    if inputs:
        result += f"**📝 ПОЛЯ ВВОДА ({len(inputs)}):**\n"
        for name, info in list(inputs.items())[:10]:
            result += f"• {name}: {info.get('type', '')} - {info.get('placeholder', '')}\n"
        if len(inputs) > 10:
            result += f"• ... и еще {len(inputs) - 10}\n"
        result += "\n"
    
    # Поиск
    search = comps.get('searchFields', [])
    if search:
        result += f"**🔍 ПОИСК ({len(search)}):**\n"
        for s in search[:5]:
            result += f"• {s.get('testid', '')}: {s.get('placeholder', '')}\n"
    
    await update.message.reply_text(result)

async def show_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает структуру сайта"""
    global site_model
    if not site_model:
        await update.message.reply_text("❌ Модель не построена. Сначала /build")
        return
    
    structure = site_model.get('structure', {})
    dom = site_model.get('metadata', {}).get('dom', {})
    
    result = "📊 **СТРУКТУРА САЙТА**\n\n"
    
    result += f"**Основные элементы:**\n"
    result += f"• Header: {'✅' if structure.get('hasHeader') else '❌'}\n"
    result += f"• Footer: {'✅' if structure.get('hasFooter') else '❌'}\n"
    result += f"• Navigation: {'✅' if structure.get('hasNav') else '❌'}\n"
    result += f"• Main: {'✅' if structure.get('hasMain') else '❌'}\n"
    result += f"• Sidebar: {'✅' if structure.get('hasSidebar') else '❌'}\n"
    result += f"• Article: {'✅' if structure.get('hasArticle') else '❌'}\n"
    result += f"• Section: {'✅' if structure.get('hasSection') else '❌'}\n"
    result += f"• Modal: {'✅' if structure.get('hasModal') else '❌'}\n\n"
    
    result += f"**DOM Статистика:**\n"
    result += f"• Всего элементов: {dom.get('totalElements', 0)}\n"
    result += f"• Уникальных тегов: {len(dom.get('uniqueTags', []))}\n"
    result += f"• Макс. глубина: {dom.get('depth', 0)}\n\n"
    
    result += f"**Заголовки:**\n"
    headings = structure.get('headings', {})
    for level, count in headings.items():
        result += f"• {level}: {count} шт.\n"
    
    await update.message.reply_text(result)

async def export_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспортирует модель в JSON"""
    global site_model
    if not site_model:
        await update.message.reply_text("❌ Модель не построена. Сначала /build")
        return
    
    filename = f"x_model_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(site_model, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_document(
        document=open(filename, 'rb'),
        filename=filename,
        caption="📄 Полная модель X.com"
    )
    os.remove(filename)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    if browser_data:
        try:
            page = browser_data['page']
            await update.message.reply_text(f"✅ Браузер активен\n📍 {page.url[:60]}")
        except:
            await update.message.reply_text("⚠️ Браузер не отвечает")
    else:
        await update.message.reply_text("❌ Браузер закрыт")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await close_browser()
    await update.message.reply_text("✅ Браузер закрыт")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("build", build_model))
    app.add_handler(CommandHandler("model", show_model))
    app.add_handler(CommandHandler("components", show_components))
    app.add_handler(CommandHandler("structure", show_structure))
    app.add_handler(CommandHandler("export", export_model))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🏗️ X.com Model Builder запущен!")
    print("📌 Команды: /build - построить полную модель")
    app.run_polling()

if __name__ == "__main__":
    main()