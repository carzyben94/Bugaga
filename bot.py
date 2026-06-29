# x_deep_parser.py - Полный парсинг X.com
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
full_site_data = {}

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

# ========== ГЛУБОКИЙ ПАРСИНГ ==========
class DeepXParser:
    def __init__(self, page):
        self.page = page
        self.data = {
            'pages': {},
            'all_elements': [],
            'buttons': {},
            'testids': {},
            'inputs': {},
            'links': {},
            'forms': {},
            'images': {},
            'texts': [],
            'headers': [],
            'navigation': {},
            'tweets': [],
            'trends': [],
            'modals': [],
            'dropdowns': [],
            'menus': [],
            'tabs': [],
            'cards': [],
            'avatars': [],
            'badges': [],
            'notifications': [],
            'search_fields': [],
            'settings': [],
            'profile': {},
            'footer': {},
            'sidebar': {},
            'api_calls': [],
            'dom_structure': {},
            'attributes': {},
            'classes': {},
            'roles': {},
            'aria_labels': {},
            'placeholders': {},
            'values': {},
            'javascript': [],
            'css': [],
            'timestamp': datetime.now().isoformat()
        }
        self.visited_urls = set()
        self.all_testids = set()
        self.all_buttons = {}
        self.all_inputs = {}
        
    async def parse_full_site(self):
        """Полный парсинг всего сайта"""
        logger.info("🕷️ Начинаю ГЛУБОКИЙ парсинг X.com...")
        
        # Список всех страниц для парсинга
        pages = [
            ('https://x.com/home', 'home'),
            ('https://x.com/explore', 'explore'),
            ('https://x.com/notifications', 'notifications'),
            ('https://x.com/messages', 'messages'),
            ('https://x.com/settings', 'settings'),
            ('https://x.com/i/trends', 'trends'),
            ('https://x.com/i/communities', 'communities'),
            ('https://x.com/i/grok', 'grok'),
            ('https://x.com/account/verify', 'verify'),
        ]
        
        for url, name in pages:
            await self.parse_page(url, name)
            await asyncio.sleep(1)
        
        # Дополнительно скроллим главную для постов
        await self.scroll_for_tweets()
        
        # Собираем всё в единую структуру
        self.compile_all_data()
        
        logger.info(f"✅ Парсинг завершен!")
        return self.data
    
    async def parse_page(self, url: str, page_name: str):
        """Парсит одну страницу максимально глубоко"""
        try:
            logger.info(f"📄 Парсинг: {page_name} ({url})")
            
            await self.page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(3)
            
            # Ждем загрузки
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass
            
            # Полный сбор данных со страницы
            page_data = await self.extract_everything(page_name)
            self.data['pages'][page_name] = page_data
            
            # Добавляем URL
            self.visited_urls.add(url)
            
            # Делаем несколько скроллов
            for i in range(5):
                await self.page.evaluate('window.scrollBy(0, 1000)')
                await asyncio.sleep(1.5)
                
                # Собираем новые элементы после скролла
                more_data = await self.extract_scrolled_content(page_name)
                if more_data:
                    self.merge_page_data(page_name, more_data)
            
            logger.info(f"✅ {page_name} - собрано данных")
            
        except Exception as e:
            logger.error(f"Ошибка парсинга {page_name}: {e}")
            self.data['pages'][page_name] = {'error': str(e)}
    
    async def extract_everything(self, page_name: str) -> Dict:
        """Извлекает ВСЕ данные со страницы"""
        return await self.page.evaluate(f'''
            () => {{
                const data = {{
                    url: window.location.href,
                    title: document.title,
                    html: document.documentElement.outerHTML.slice(0, 100000),
                    
                    // ВСЕ элементы с их атрибутами
                    elements: [],
                    
                    // Кнопки (ВСЕ)
                    buttons: [],
                    button_testids: [],
                    
                    // TestID (ВСЕ)
                    testids: [],
                    testid_elements: {{}},
                    
                    // Поля ввода (ВСЕ)
                    inputs: [],
                    textareas: [],
                    selects: [],
                    
                    // Ссылки (ВСЕ)
                    links: [],
                    
                    // Формы (ВСЕ)
                    forms: [],
                    
                    // Изображения (ВСЕ)
                    images: [],
                    
                    // Заголовки (ВСЕ)
                    headers: [],
                    
                    // Текст (ВЕСЬ)
                    all_text: '',
                    
                    // Навигация
                    navigation: {{}},
                    
                    // Модалки
                    modals: [],
                    
                    // Выпадающие списки
                    dropdowns: [],
                    
                    // Меню
                    menus: [],
                    
                    // Вкладки
                    tabs: [],
                    
                    // Карточки
                    cards: [],
                    
                    // Атрибуты (ВСЕ)
                    attributes: {{}},
                    
                    // Классы (ВСЕ)
                    classes: new Set(),
                    
                    // Роли (ВСЕ)
                    roles: new Set(),
                    
                    // ARIA метки
                    aria_labels: [],
                    
                    // Placeholder
                    placeholders: [],
                    
                    // Значения полей
                    values: [],
                    
                    // Скрипты
                    scripts: [],
                    
                    // Стили
                    styles: [],
                    
                    // Количество элементов
                    element_counts: {{}},
                    
                    // Структура
                    structure: {{
                        depth: 0,
                        children: 0,
                        siblings: 0
                    }}
                }};
                
                // ===== СБОР ВСЕХ ЭЛЕМЕНТОВ =====
                document.querySelectorAll('*').forEach(el => {{
                    const tag = el.tagName.toLowerCase();
                    const rect = el.getBoundingClientRect();
                    const testid = el.getAttribute('data-testid') || '';
                    const id = el.id || '';
                    const className = el.className || '';
                    const role = el.getAttribute('role') || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    
                    // Собираем все элементы для детального анализа
                    data.elements.push({{
                        tag: tag,
                        testid: testid,
                        id: id,
                        class: className.slice(0, 200),
                        role: role,
                        ariaLabel: ariaLabel.slice(0, 100),
                        text: el.textContent?.trim()?.slice(0, 200) || '',
                        visible: rect.width > 0 && rect.height > 0,
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    }});
                    
                    // Счетчики по тегам
                    if (!data.element_counts[tag]) data.element_counts[tag] = 0;
                    data.element_counts[tag]++;
                    
                    // Классы
                    if (className) {{
                        className.split(' ').forEach(c => {{
                            if (c) data.classes.add(c.slice(0, 100));
                        }});
                    }}
                    
                    // Роли
                    if (role) data.roles.add(role);
                    
                    // Атрибуты
                    for (const attr of el.attributes) {{
                        if (!data.attributes[attr.name]) data.attributes[attr.name] = new Set();
                        data.attributes[attr.name].add(attr.value?.slice(0, 100) || '');
                    }}
                    
                    // TestID
                    if (testid) {{
                        if (!data.testids.includes(testid)) data.testids.push(testid);
                        if (!data.testid_elements[testid]) data.testid_elements[testid] = [];
                        data.testid_elements[testid].push({{
                            tag: tag,
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            aria: ariaLabel.slice(0, 50)
                        }});
                    }}
                    
                    // ARIA метки
                    if (ariaLabel) data.aria_labels.push(ariaLabel.slice(0, 100));
                    
                    // Placeholder
                    const placeholder = el.getAttribute('placeholder');
                    if (placeholder) data.placeholders.push(placeholder.slice(0, 100));
                    
                    // Значения
                    const value = el.getAttribute('value');
                    if (value) data.values.push(value.slice(0, 100));
                }});
                
                // ===== КНОПКИ =====
                document.querySelectorAll('button, [role="button"], [data-testid*="button"]').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    const text = el.textContent?.trim()?.slice(0, 50) || '';
                    const aria = el.getAttribute('aria-label') || '';
                    const type = el.getAttribute('type') || 'button';
                    
                    data.buttons.push({{
                        testid: testid,
                        text: text,
                        aria: aria.slice(0, 50),
                        type: type,
                        disabled: el.hasAttribute('disabled'),
                        class: el.className?.slice(0, 100) || '',
                        tag: el.tagName
                    }});
                    
                    if (testid) data.button_testids.push(testid);
                }});
                
                // ===== ПОЛЯ ВВОДА =====
                document.querySelectorAll('input, textarea, select').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    const name = el.getAttribute('name') || '';
                    const type = el.getAttribute('type') || el.tagName.toLowerCase();
                    const placeholder = el.getAttribute('placeholder') || '';
                    const value = el.value || '';
                    
                    if (el.tagName === 'INPUT') {{
                        data.inputs.push({{
                            testid: testid,
                            name: name,
                            type: type,
                            placeholder: placeholder.slice(0, 50),
                            value: value.slice(0, 50),
                            required: el.hasAttribute('required'),
                            disabled: el.hasAttribute('disabled')
                        }});
                    }} else if (el.tagName === 'TEXTAREA') {{
                        data.textareas.push({{
                            testid: testid,
                            name: name,
                            placeholder: placeholder.slice(0, 50),
                            value: value.slice(0, 50)
                        }});
                    }} else if (el.tagName === 'SELECT') {{
                        const options = [];
                        el.querySelectorAll('option').forEach(opt => {{
                            options.push(opt.textContent?.trim() || '');
                        }});
                        data.selects.push({{
                            testid: testid,
                            name: name,
                            options: options.slice(0, 20)
                        }});
                    }}
                }});
                
                // ===== ССЫЛКИ =====
                document.querySelectorAll('a[href]').forEach(el => {{
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {{
                        data.links.push({{
                            href: href.slice(0, 200),
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            title: el.getAttribute('title') || '',
                            aria: el.getAttribute('aria-label') || '',
                            testid: el.getAttribute('data-testid') || '',
                            rel: el.getAttribute('rel') || ''
                        }});
                    }}
                }});
                
                // ===== ФОРМЫ =====
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
                            testid: input.getAttribute('data-testid') || ''
                        }});
                    }});
                    data.forms.push(form);
                }});
                
                // ===== ИЗОБРАЖЕНИЯ =====
                document.querySelectorAll('img').forEach(el => {{
                    const src = el.getAttribute('src');
                    if (src) {{
                        data.images.push({{
                            src: src.slice(0, 200),
                            alt: el.getAttribute('alt') || '',
                            title: el.getAttribute('title') || '',
                            testid: el.getAttribute('data-testid') || '',
                            width: el.width,
                            height: el.height
                        }});
                    }}
                }});
                
                // ===== ЗАГОЛОВКИ =====
                document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => {{
                    data.headers.push({{
                        tag: el.tagName,
                        text: el.textContent?.trim()?.slice(0, 200) || '',
                        level: el.tagName.replace('H', ''),
                        testid: el.getAttribute('data-testid') || '',
                        id: el.id || ''
                    }});
                }});
                
                // ===== ВЕСЬ ТЕКСТ =====
                data.all_text = document.body?.textContent?.slice(0, 50000) || '';
                
                // ===== НАВИГАЦИЯ =====
                const navItems = [
                    'AppTabBar_Home_Link',
                    'AppTabBar_Explore_Link',
                    'AppTabBar_Notifications_Link',
                    'AppTabBar_Profile_Link',
                    'AppTabBar_DirectMessage_Link',
                    'AppTabBar_More_Menu',
                    'AppTabBar_Follow_Link'
                ];
                navItems.forEach(id => {{
                    const el = document.querySelector(`[data-testid="${{id}}"]`);
                    data.navigation[id] = {{
                        present: !!el,
                        text: el?.textContent?.trim() || '',
                        aria: el?.getAttribute('aria-label') || ''
                    }};
                }});
                
                // ===== МОДАЛКИ =====
                document.querySelectorAll('[role="dialog"], [data-testid*="modal"], [data-testid*="Modal"]').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    data.modals.push({{
                        testid: testid,
                        text: el.textContent?.trim()?.slice(0, 200) || '',
                        visible: el.getBoundingClientRect().width > 0
                    }});
                }});
                
                // ===== ВЫПАДАЮЩИЕ СПИСКИ =====
                document.querySelectorAll('[role="listbox"], [data-testid*="dropdown"], select').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    const items = [];
                    el.querySelectorAll('option, [role="option"]').forEach(opt => {{
                        items.push(opt.textContent?.trim() || '');
                    }});
                    data.dropdowns.push({{
                        testid: testid,
                        items: items.slice(0, 20)
                    }});
                }});
                
                // ===== МЕНЮ =====
                document.querySelectorAll('[role="menu"], [data-testid*="menu"]').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    const items = [];
                    el.querySelectorAll('[role="menuitem"]').forEach(item => {{
                        items.push(item.textContent?.trim() || '');
                    }});
                    data.menus.push({{
                        testid: testid,
                        items: items.slice(0, 20)
                    }});
                }});
                
                // ===== ВКЛАДКИ =====
                document.querySelectorAll('[role="tablist"]').forEach(el => {{
                    const tabs = [];
                    el.querySelectorAll('[role="tab"]').forEach(tab => {{
                        tabs.push(tab.textContent?.trim() || '');
                    }});
                    data.tabs.push({{
                        testid: el.getAttribute('data-testid') || '',
                        tabs: tabs.slice(0, 10)
                    }});
                }});
                
                // ===== КАРТОЧКИ =====
                document.querySelectorAll('[data-testid*="card"], article, [role="article"]').forEach(el => {{
                    const testid = el.getAttribute('data-testid') || '';
                    data.cards.push({{
                        testid: testid,
                        text: el.textContent?.trim()?.slice(0, 200) || '',
                        hasImage: !!el.querySelector('img'),
                        hasLink: !!el.querySelector('a')
                    }});
                }});
                
                // ===== ПОСТЫ =====
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {{
                    const text = el.textContent?.trim() || '';
                    if (text.length > 10) {{
                        const authorEl = el.querySelector('[data-testid="User-Name"]');
                        const timeEl = el.querySelector('time');
                        const likeEl = el.querySelector('[data-testid="like"]');
                        const retweetEl = el.querySelector('[data-testid="retweet"]');
                        const replyEl = el.querySelector('[data-testid="reply"]');
                        const viewsEl = el.querySelector('[data-testid="views"]');
                        
                        // Проверяем, закреплен ли пост
                        const isPinned = el.querySelector('[aria-label="Pinned tweet"]') !== null;
                        
                        data.tweets.push({{
                            text: text.slice(0, 500),
                            author: authorEl?.textContent?.trim() || 'Unknown',
                            time: timeEl?.getAttribute('datetime') || '',
                            likes: likeEl?.textContent?.trim() || '0',
                            retweets: retweetEl?.textContent?.trim() || '0',
                            replies: replyEl?.textContent?.trim() || '0',
                            views: viewsEl?.textContent?.trim() || '0',
                            isPinned: isPinned
                        }});
                    }}
                }});
                
                // ===== СКРИПТЫ =====
                document.querySelectorAll('script').forEach(el => {{
                    const src = el.getAttribute('src');
                    if (src) {{
                        data.scripts.push(src.slice(0, 200));
                    }}
                }});
                
                // ===== СТИЛИ =====
                document.querySelectorAll('link[rel="stylesheet"]').forEach(el => {{
                    const href = el.getAttribute('href');
                    if (href) {{
                        data.styles.push(href.slice(0, 200));
                    }}
                }});
                
                // ===== СТРУКТУРА =====
                function getDepth(el, depth = 0) {{
                    let max = depth;
                    for (const child of el.children) {{
                        max = Math.max(max, getDepth(child, depth + 1));
                    }}
                    return max;
                }}
                data.structure.depth = getDepth(document.body);
                data.structure.children = document.body.children.length;
                
                // Преобразуем Set в массивы
                data.classes = Array.from(data.classes);
                data.roles = Array.from(data.roles);
                const attrs = {{}};
                for (const [key, values] of Object.entries(data.attributes)) {{
                    attrs[key] = Array.from(values).slice(0, 20);
                }}
                data.attributes = attrs;
                
                // Уникальные значения
                data.aria_labels = [...new Set(data.aria_labels)];
                data.placeholders = [...new Set(data.placeholders)];
                data.values = [...new Set(data.values)];
                
                return data;
            }}
        ''')
    
    async def extract_scrolled_content(self, page_name: str) -> Dict:
        """Извлекает контент после скролла"""
        return await self.page.evaluate('''
            () => {
                const result = {
                    tweets: [],
                    buttons: [],
                    testids: [],
                    images: []
                };
                
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    if (text.length > 20) {
                        result.tweets.push({
                            text: text.slice(0, 200),
                            author: el.querySelector('[data-testid="User-Name"]')?.textContent?.trim() || 'Unknown'
                        });
                    }
                });
                
                document.querySelectorAll('button, [role="button"]').forEach(el => {
                    const testid = el.getAttribute('data-testid');
                    if (testid) {
                        result.buttons.push({
                            testid: testid,
                            text: el.textContent?.trim()?.slice(0, 30) || ''
                        });
                    }
                });
                
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const testid = el.getAttribute('data-testid');
                    if (testid && !result.testids.includes(testid)) {
                        result.testids.push(testid);
                    }
                });
                
                return result;
            }
        ''')
    
    def merge_page_data(self, page_name: str, new_data: Dict):
        """Объединяет данные после скролла"""
        if page_name in self.data['pages']:
            page = self.data['pages'][page_name]
            
            # Добавляем новые посты
            if 'tweets' in new_data:
                page['tweets'] = page.get('tweets', []) + new_data['tweets']
                # Уникальные посты
                seen = set()
                unique = []
                for t in page['tweets']:
                    key = t.get('text', '')[:50]
                    if key not in seen:
                        seen.add(key)
                        unique.append(t)
                page['tweets'] = unique
            
            # Добавляем новые кнопки
            if 'buttons' in new_data:
                page['buttons'] = page.get('buttons', []) + new_data['buttons']
            
            # Добавляем новые testid
            if 'testids' in new_data:
                page['testids'] = list(set(page.get('testids', []) + new_data['testids']))
    
    async def scroll_for_tweets(self):
        """Скроллит главную для сбора постов"""
        try:
            logger.info("📜 Скроллю главную для сбора постов...")
            
            await self.page.goto('https://x.com/home', wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            all_tweets = []
            for i in range(10):
                await self.page.evaluate('window.scrollBy(0, 1200)')
                await asyncio.sleep(1.5)
                
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
                                
                                result.push({
                                    text: text.slice(0, 300),
                                    author: authorEl?.textContent?.trim() || 'Unknown',
                                    time: timeEl?.getAttribute('datetime') || '',
                                    likes: likeEl?.textContent?.trim() || '0',
                                    retweets: retweetEl?.textContent?.trim() || '0'
                                });
                            }
                        });
                        return result;
                    }
                ''')
                
                all_tweets.extend(tweets)
                logger.info(f"📊 Собрано постов: {len(all_tweets)}")
                
                # Уникальные
                seen = set()
                unique = []
                for t in all_tweets:
                    key = t.get('text', '')[:50]
                    if key not in seen:
                        seen.add(key)
                        unique.append(t)
                all_tweets = unique
            
            self.data['tweets'] = all_tweets
            logger.info(f"✅ Всего постов: {len(all_tweets)}")
            
        except Exception as e:
            logger.error(f"Ошибка скролла: {e}")
    
    def compile_all_data(self):
        """Собирает все данные в единую структуру"""
        logger.info("📊 Компилирую все данные...")
        
        # Собираем все testid со всех страниц
        all_testids = set()
        all_buttons = {}
        all_inputs = {}
        all_links = {}
        all_forms = []
        all_headers = []
        
        for page_name, page_data in self.data['pages'].items():
            if isinstance(page_data, dict) and 'error' not in page_data:
                # TestID
                for testid in page_data.get('testids', []):
                    all_testids.add(testid)
                
                # Кнопки
                for btn in page_data.get('buttons', []):
                    testid = btn.get('testid', '')
                    if testid:
                        if testid not in all_buttons:
                            all_buttons[testid] = {
                                'texts': [],
                                'arias': [],
                                'pages': []
                            }
                        if btn.get('text'):
                            all_buttons[testid]['texts'].append(btn['text'])
                        if btn.get('aria'):
                            all_buttons[testid]['arias'].append(btn['aria'])
                        if page_name not in all_buttons[testid]['pages']:
                            all_buttons[testid]['pages'].append(page_name)
                
                # Поля ввода
                for inp in page_data.get('inputs', []):
                    testid = inp.get('testid', '') or inp.get('name', '')
                    if testid:
                        if testid not in all_inputs:
                            all_inputs[testid] = {
                                'type': inp.get('type', ''),
                                'placeholders': [],
                                'pages': []
                            }
                        if inp.get('placeholder'):
                            all_inputs[testid]['placeholders'].append(inp['placeholder'])
                        if page_name not in all_inputs[testid]['pages']:
                            all_inputs[testid]['pages'].append(page_name)
                
                # Ссылки
                for link in page_data.get('links', []):
                    href = link.get('href', '')
                    if href:
                        all_links[href] = {
                            'text': link.get('text', ''),
                            'pages': all_links.get(href, {}).get('pages', []) + [page_name]
                        }
                        all_links[href]['pages'] = list(set(all_links[href]['pages']))
                
                # Формы
                for form in page_data.get('forms', []):
                    all_forms.append(form)
                
                # Заголовки
                for h in page_data.get('headers', []):
                    all_headers.append(h)
        
        # Сохраняем в основную структуру
        self.data['all_testids'] = list(all_testids)
        self.data['all_buttons'] = all_buttons
        self.data['all_inputs'] = all_inputs
        self.data['all_links'] = all_links
        self.data['all_forms'] = all_forms
        self.data['all_headers'] = all_headers
        
        # Статистика
        self.data['statistics'] = {
            'total_pages': len(self.data['pages']),
            'total_testids': len(all_testids),
            'total_buttons': len(all_buttons),
            'total_inputs': len(all_inputs),
            'total_links': len(all_links),
            'total_forms': len(all_forms),
            'total_headers': len(all_headers),
            'total_tweets': len(self.data.get('tweets', [])),
            'total_trends': len(self.data.get('trends', []))
        }
        
        logger.info(f"📊 Статистика: {self.data['statistics']}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕷️ **X.com Deep Parser**\n\n"
        "Выкачивает ВСЁ с X.com:\n"
        "• Все страницы и разделы\n"
        "• Все кнопки и их testid\n"
        "• Все поля ввода\n"
        "• Все ссылки и формы\n"
        "• Все посты с лайками\n"
        "• Все атрибуты и классы\n"
        "• Полная структура DOM\n\n"
        "📌 Команды:\n"
        "/xlogin - войти в X.com\n"
        "/parse - начать глубокий парсинг\n"
        "/report - показать отчет\n"
        "/export - экспортировать JSON\n"
        "/testids - все testid\n"
        "/buttons - все кнопки\n"
        "/tweets - все посты"
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

async def deep_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глубокий парсинг всего сайта"""
    msg = await update.message.reply_text(
        "🕷️ **Начинаю ГЛУБОКИЙ парсинг X.com...**\n\n"
        "📄 Парсинг страниц:\n"
        "• Главная\n"
        "• Обзор\n"
        "• Уведомления\n"
        "• Сообщения\n"
        "• Настройки\n"
        "• Тренды\n"
        "• Сообщества\n"
        "• Grok\n\n"
        "⏳ Это займет 3-5 минут..."
    )
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Идем на X.com
        await page.goto('https://x.com', wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Парсим
        parser = DeepXParser(page)
        data = await parser.parse_full_site()
        
        # Сохраняем глобально
        global full_site_data
        full_site_data = data
        
        # Отчет
        stats = data.get('statistics', {})
        report = f"📊 **ПАРСИНГ ЗАВЕРШЕН!**\n\n"
        report += f"📄 Страниц: {stats.get('total_pages', 0)}\n"
        report += f"🏷️ TestID: {stats.get('total_testids', 0)}\n"
        report += f"🔘 Кнопок: {stats.get('total_buttons', 0)}\n"
        report += f"📝 Поля ввода: {stats.get('total_inputs', 0)}\n"
        report += f"🔗 Ссылок: {stats.get('total_links', 0)}\n"
        report += f"📋 Форм: {stats.get('total_forms', 0)}\n"
        report += f"📌 Заголовков: {stats.get('total_headers', 0)}\n"
        report += f"🐦 Постов: {stats.get('total_tweets', 0)}\n"
        report += f"📈 Трендов: {stats.get('total_trends', 0)}\n"
        
        await msg.edit_text(report)
        
        # Сохраняем файл
        filename = f"x_deep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption="📄 Полный парсинг X.com"
        )
        os.remove(filename)
        
        # Скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 Текущая страница")
        
        logger.info(f"✅ Парсинг завершен для user {update.effective_user.id}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Parse error: {traceback.format_exc()}")

async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global full_site_data
    if not full_site_data:
        await update.message.reply_text("❌ Нет данных. Сначала /parse")
        return
    
    stats = full_site_data.get('statistics', {})
    report = f"📊 **ПОЛНЫЙ ОТЧЕТ**\n\n"
    report += f"🕐 {full_site_data.get('timestamp', '')[:19]}\n\n"
    report += f"**СТАТИСТИКА:**\n"
    report += f"📄 Страниц: {stats.get('total_pages', 0)}\n"
    report += f"🏷️ TestID: {stats.get('total_testids', 0)}\n"
    report += f"🔘 Кнопок: {stats.get('total_buttons', 0)}\n"
    report += f"📝 Поля ввода: {stats.get('total_inputs', 0)}\n"
    report += f"🔗 Ссылок: {stats.get('total_links', 0)}\n"
    report += f"📋 Форм: {stats.get('total_forms', 0)}\n"
    report += f"📌 Заголовков: {stats.get('total_headers', 0)}\n"
    report += f"🐦 Постов: {stats.get('total_tweets', 0)}\n"
    
    await update.message.reply_text(report)

async def show_all_testids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global full_site_data
    if not full_site_data:
        await update.message.reply_text("❌ Нет данных. Сначала /parse")
        return
    
    testids = full_site_data.get('all_testids', [])
    if not testids:
        await update.message.reply_text("❌ TestID не найдены")
        return
    
    result = "🏷️ **ВСЕ TESTID**\n\n"
    for i, testid in enumerate(testids[:30], 1):
        # Показываем на каких страницах
        pages = []
        for page_name, page_data in full_site_data['pages'].items():
            if isinstance(page_data, dict) and testid in page_data.get('testids', []):
                pages.append(page_name)
        result += f"{i}. `{testid}`"
        if pages:
            result += f" [{', '.join(pages[:3])}]"
        result += "\n"
    
    if len(testids) > 30:
        result += f"\n... и еще {len(testids) - 30} testid"
    
    await update.message.reply_text(result)

async def show_all_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global full_site_data
    if not full_site_data:
        await update.message.reply_text("❌ Нет данных. Сначала /parse")
        return
    
    buttons = full_site_data.get('all_buttons', {})
    if not buttons:
        await update.message.reply_text("❌ Кнопки не найдены")
        return
    
    result = "🔘 **ВСЕ КНОПКИ**\n\n"
    for i, (testid, info) in enumerate(list(buttons.items())[:25], 1):
        result += f"{i}. `{testid}`\n"
        if info.get('texts'):
            result += f"   📝 {info['texts'][0][:40]}\n"
        if info.get('pages'):
            result += f"   📄 {', '.join(info['pages'][:3])}\n"
        result += "\n"
    
    if len(buttons) > 25:
        result += f"... и еще {len(buttons) - 25} кнопок"
    
    await update.message.reply_text(result)

async def show_tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global full_site_data
    if not full_site_data:
        await update.message.reply_text("❌ Нет данных. Сначала /parse")
        return
    
    tweets = full_site_data.get('tweets', [])
    if not tweets:
        await update.message.reply_text("❌ Посты не найдены")
        return
    
    result = "🐦 **ВСЕ ПОСТЫ**\n\n"
    for i, tweet in enumerate(tweets[:10], 1):
        result += f"{i}. @{tweet.get('author', 'Unknown')}\n"
        result += f"   {tweet.get('text', '')[:100]}...\n"
        result += f"   ❤️ {tweet.get('likes', '0')}  🔁 {tweet.get('retweets', '0')}\n\n"
    
    if len(tweets) > 10:
        result += f"... и еще {len(tweets) - 10} постов"
    
    await update.message.reply_text(result)

async def export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global full_site_data
    if not full_site_data:
        await update.message.reply_text("❌ Нет данных. Сначала /parse")
        return
    
    filename = f"x_full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(full_site_data, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_document(
        document=open(filename, 'rb'),
        filename=filename,
        caption="📄 Полный экспорт X.com"
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
    app.add_handler(CommandHandler("parse", deep_parse))
    app.add_handler(CommandHandler("report", show_report))
    app.add_handler(CommandHandler("testids", show_all_testids))
    app.add_handler(CommandHandler("buttons", show_all_buttons))
    app.add_handler(CommandHandler("tweets", show_tweets))
    app.add_handler(CommandHandler("export", export_json))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🕷️ X.com Deep Parser запущен!")
    print("📌 Команды: /xlogin → /parse → /report")
    app.run_polling()

if __name__ == "__main__":
    main()