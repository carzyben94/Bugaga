import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
import random
from datetime import datetime
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ПРОВЕРКА CHROMIUM ==========
CHROMIUM_PATH = None
CHROMIUM_INSTALLED = False

def check_chromium():
    global CHROMIUM_PATH, CHROMIUM_INSTALLED
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    for path in chromium_paths:
        if os.path.exists(path):
            CHROMIUM_PATH = path
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден: {path}")
            return True
    return False

check_chromium()

# ========== ПРОВЕРКА PYDOLL ==========
PYDOLL_AVAILABLE = False

try:
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions
    PYDOLL_AVAILABLE = True
    logger.info("✅ Pydoll загружен")
except ImportError as e:
    logger.warning(f"⚠️ Pydoll не найден: {e}")

# ========== КУКИ X.COM ==========
COOKIES = [
    {"domain": ".x.com", "name": "__cuid", "path": "/", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "name": "__cuid", "path": "/", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"domain": ".x.com", "name": "lang", "path": "/", "value": "ru"},
    {"domain": ".x.com", "name": "dnt", "path": "/", "value": "1"},
    {"domain": ".x.com", "name": "guest_id", "path": "/", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "guest_id_marketing", "path": "/", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "guest_id_ads", "path": "/", "value": "v1%3A178267838599411411"},
    {"domain": ".x.com", "name": "personalization_id", "path": "/", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""},
    {"domain": ".x.com", "name": "twid", "path": "/", "value": "u%3D2067347503503052800"},
    {"domain": ".x.com", "name": "auth_token", "path": "/", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"domain": ".x.com", "name": "ct0", "path": "/", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"domain": ".x.com", "name": "__cf_bm", "path": "/", "value": "3PHty0MUYSrud60gKo41iFni0wDB5uFEa.TAyF3eWFQ-1783076730.4783854-1.0.1.1-tIYvV5IeAbbckRKhliuQ8DI9NYoY6JmPZJdARb6ixRKFjmT7KZAh51b0nLs.b7Luev2xSanCGZe_nfRDp8grfYUFb86myqghHqcGrGpymnU2..9obAQIOtsQQ7mUYWo0"}
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
pydoll_browser = None
pydoll_tab = None
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None
}

# ========== БРАУЗЕРНАЯ ЛОГИКА ==========

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

async def get_pydoll_browser():
    global pydoll_browser, pydoll_tab
    
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            return pydoll_tab
        except:
            await close_pydoll_browser()
    
    if not PYDOLL_AVAILABLE or not CHROMIUM_INSTALLED:
        return None
    
    try:
        options = ChromiumOptions()
        options.binary_location = CHROMIUM_PATH
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        return pydoll_tab
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Pydoll: {e}")
        return None

async def close_pydoll_browser():
    global pydoll_browser, pydoll_tab
    if pydoll_browser:
        try:
            await pydoll_browser.close()
        except:
            pass
        pydoll_browser = None
        pydoll_tab = None

async def get_browser():
    return await get_pydoll_browser()

async def execute_js(script):
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'execute_script'):
            result = await page.execute_script(script)
            return result
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка JS: {e}")
        return None

async def take_screenshot():
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'take_screenshot'):
            screenshot_base64 = await page.take_screenshot(as_base64=True)
            if screenshot_base64:
                return base64.b64decode(screenshot_base64)
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        return None

# ========== SHADOW DOM - МНОЖЕСТВО ВАРИАНТОВ ==========

async def shadow_v1(page):
    """Вариант 1: Простой поиск shadowRoot"""
    try:
        js = """
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        result.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            class: el.className || null,
                            children: el.shadowRoot.children.length
                        });
                    }
                });
                return result;
            }
        """
        return await page.execute_script(js)
    except Exception as e:
        logger.error(f"Shadow V1 error: {e}")
        return None

async def shadow_v2(page):
    """Вариант 2: С поиском конкретных элементов"""
    try:
        js = """
            () => {
                const result = [];
                const selectors = ['grok-drawer', 'video-player', 'emoji-picker'];
                selectors.forEach(sel => {
                    const el = document.querySelector(sel);
                    if (el && el.shadowRoot) {
                        const children = [];
                        for (let child of el.shadowRoot.children) {
                            children.push({
                                tag: child.tagName.toLowerCase(),
                                id: child.id || null,
                                text: child.textContent ? child.textContent.slice(0, 50) : null
                            });
                        }
                        result.push({
                            host: sel,
                            id: el.id || null,
                            children: children
                        });
                    }
                });
                return result;
            }
        """
        return await page.execute_script(js)
    except Exception as e:
        logger.error(f"Shadow V2 error: {e}")
        return None

async def shadow_v3(page):
    """Вариант 3: Рекурсивный обход"""
    try:
        js = """
            () => {
                function traverse(el, path) {
                    const data = {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        class: el.className || null,
                        path: path,
                        hasShadow: !!el.shadowRoot,
                        children: []
                    };
                    
                    if (el.shadowRoot) {
                        for (let child of el.shadowRoot.children) {
                            data.children.push(traverse(child, path + ' > shadow'));
                        }
                    }
                    
                    for (let child of el.children) {
                        if (!child.shadowRoot) {
                            data.children.push(traverse(child, path + ' > ' + el.tagName));
                        }
                    }
                    
                    return data;
                }
                
                return traverse(document.body, 'body');
            }
        """
        return await page.execute_script(js)
    except Exception as e:
        logger.error(f"Shadow V3 error: {e}")
        return None

async def shadow_v4(page):
    """Вариант 4: Только хосты с shadowRoot"""
    try:
        js = """
            () => {
                const hosts = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        const info = {
                            tag: el.tagName,
                            id: el.id || null,
                            class: el.className || null,
                            childCount: el.shadowRoot.children.length
                        };
                        
                        // Пробуем найти интерактивные элементы внутри
                        const buttons = el.shadowRoot.querySelectorAll('button');
                        const inputs = el.shadowRoot.querySelectorAll('input, textarea');
                        
                        info.buttons = buttons.length;
                        info.inputs = inputs.length;
                        
                        hosts.push(info);
                    }
                });
                return hosts;
            }
        """
        return await page.execute_script(js)
    except Exception as e:
        logger.error(f"Shadow V4 error: {e}")
        return None

async def shadow_v5(page):
    """Вариант 5: Через find + get_shadow_root (Pydoll метод)"""
    try:
        # Пробуем найти через Pydoll
        hosts = []
        selectors = ['grok-drawer', '[data-testid="GrokDrawer"]', 'video-player']
        
        for sel in selectors:
            try:
                el = await page.find(sel, timeout=2000)
                if el and hasattr(el, 'get_shadow_root'):
                    shadow = await el.get_shadow_root()
                    if shadow:
                        children = []
                        # Пробуем получить детей
                        try:
                            inner = await shadow.find_all('*')
                            for child in inner[:5]:
                                text = await child.text() if hasattr(child, 'text') else None
                                children.append({
                                    'tag': await child.tag_name() if hasattr(child, 'tag_name') else 'unknown',
                                    'text': text[:50] if text else None
                                })
                        except:
                            pass
                        hosts.append({
                            'selector': sel,
                            'children': children
                        })
            except:
                pass
        
        return hosts
    except Exception as e:
        logger.error(f"Shadow V5 error: {e}")
        return None

# ========== /SHADOW - ВСЕ ВАРИАНТЫ ==========

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shadow DOM - тестирование всех вариантов"""
    logger.info(f"📩 /shadow от {update.effective_user.username}")
    
    await send_message_safe(update, "🛡️ Тестирую Shadow DOM (5 вариантов)...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        results = {}
        
        # Вариант 1
        await send_message_safe(update, "🔄 Вариант 1: Простой поиск...")
        results['v1'] = await shadow_v1(page)
        
        # Вариант 2
        await send_message_safe(update, "🔄 Вариант 2: Конкретные элементы...")
        results['v2'] = await shadow_v2(page)
        
        # Вариант 3
        await send_message_safe(update, "🔄 Вариант 3: Рекурсивный обход...")
        results['v3'] = await shadow_v3(page)
        
        # Вариант 4
        await send_message_safe(update, "🔄 Вариант 4: Хосты с shadowRoot...")
        results['v4'] = await shadow_v4(page)
        
        # Вариант 5
        await send_message_safe(update, "🔄 Вариант 5: Pydoll find + get_shadow_root...")
        results['v5'] = await shadow_v5(page)
        
        # Формируем отчет
        response = f"🛡️ **SHADOW DOM - РЕЗУЛЬТАТЫ**\n\n"
        
        for key, data in results.items():
            if data and len(data) > 0:
                response += f"✅ **{key.upper()}** - Найдено: {len(data)} элементов\n"
                # Показываем первые 2 элемента
                for i, item in enumerate(data[:2]):
                    if isinstance(item, dict):
                        tag = item.get('tag', item.get('host', 'unknown'))
                        response += f"  └─ {i+1}. {tag}"
                        if item.get('id'):
                            response += f" (id: {item['id']})"
                        if item.get('childCount') or item.get('children'):
                            count = item.get('childCount', len(item.get('children', [])))
                            response += f" - детей: {count}"
                        response += "\n"
            else:
                response += f"❌ **{key.upper()}** - Ничего не найдено\n"
            response += "\n"
        
        # Определяем лучший вариант
        best = None
        max_count = 0
        for key, data in results.items():
            if data and len(data) > max_count:
                max_count = len(data)
                best = key
        
        if best:
            response += f"🏆 **Лучший вариант: {best.upper()}** ({max_count} элементов)\n"
            response += f"💡 Используйте этот вариант в коде."
        else:
            response += "❌ **Ни один вариант не сработал**\n"
            response += "💡 Попробуйте обновить страницу или зайти на X.com"
        
        # Сохраняем полные данные в JSON
        filename = f"shadow_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        await send_message_safe(update, response, parse_mode='Markdown')
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"📄 Полные результаты ({len(results)} вариантов)"
        )
        
        # Скриншот
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Текущая страница")
        
    except Exception as e:
        logger.error(f"❌ Ошибка shadow: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== /TEST - ТЕСТ ВСЕХ ФУНКЦИЙ ==========

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное тестирование всех функций"""
    logger.info(f"📩 /test от {update.effective_user.username}")
    
    await send_message_safe(update, "🧪 Запускаю полное тестирование...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        results = {
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # 1. Тест execute_js
        try:
            await send_message_safe(update, "🔄 Тест 1: execute_js...")
            result = await page.execute_script('return document.title;')
            results['tests']['execute_js'] = {'status': '✅', 'result': result}
        except Exception as e:
            results['tests']['execute_js'] = {'status': '❌', 'error': str(e)}
        
        # 2. Тест Shadow DOM (все варианты)
        await send_message_safe(update, "🔄 Тест 2: Shadow DOM...")
        results['tests']['shadow'] = {}
        
        try:
            data = await shadow_v1(page)
            results['tests']['shadow']['v1'] = {'status': '✅' if data else '⚠️', 'count': len(data) if data else 0}
        except Exception as e:
            results['tests']['shadow']['v1'] = {'status': '❌', 'error': str(e)}
        
        try:
            data = await shadow_v2(page)
            results['tests']['shadow']['v2'] = {'status': '✅' if data else '⚠️', 'count': len(data) if data else 0}
        except Exception as e:
            results['tests']['shadow']['v2'] = {'status': '❌', 'error': str(e)}
        
        try:
            data = await shadow_v3(page)
            results['tests']['shadow']['v3'] = {'status': '✅' if data else '⚠️', 'count': len(data) if data else 0}
        except Exception as e:
            results['tests']['shadow']['v3'] = {'status': '❌', 'error': str(e)}
        
        try:
            data = await shadow_v4(page)
            results['tests']['shadow']['v4'] = {'status': '✅' if data else '⚠️', 'count': len(data) if data else 0}
        except Exception as e:
            results['tests']['shadow']['v4'] = {'status': '❌', 'error': str(e)}
        
        try:
            data = await shadow_v5(page)
            results['tests']['shadow']['v5'] = {'status': '✅' if data else '⚠️', 'count': len(data) if data else 0}
        except Exception as e:
            results['tests']['shadow']['v5'] = {'status': '❌', 'error': str(e)}
        
        # 3. Тест скриншота
        await send_message_safe(update, "🔄 Тест 3: Скриншот...")
        try:
            screenshot = await take_screenshot()
            results['tests']['screenshot'] = {'status': '✅' if screenshot else '❌', 'size': len(screenshot) if screenshot else 0}
            if screenshot:
                await send_photo_safe(update, screenshot, "📸 Тестовый скриншот")
        except Exception as e:
            results['tests']['screenshot'] = {'status': '❌', 'error': str(e)}
        
        # 4. Тест кук
        await send_message_safe(update, "🔄 Тест 4: Куки...")
        try:
            cookies = await page.execute_script('return document.cookie;')
            results['tests']['cookies'] = {'status': '✅' if cookies else '⚠️', 'length': len(cookies) if cookies else 0}
        except Exception as e:
            results['tests']['cookies'] = {'status': '❌', 'error': str(e)}
        
        # 5. Тест URL
        await send_message_safe(update, "🔄 Тест 5: URL...")
        try:
            url = await page.execute_script('return window.location.href;')
            results['tests']['url'] = {'status': '✅', 'url': url}
        except Exception as e:
            results['tests']['url'] = {'status': '❌', 'error': str(e)}
        
        # 6. Тест элементов X.com
        await send_message_safe(update, "🔄 Тест 6: Элементы X.com...")
        try:
            js = """
                () => {
                    const elements = {
                        tweets: document.querySelectorAll('[data-testid="tweet"]').length,
                        profile: !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]'),
                        tweetBtn: !!document.querySelector('[data-testid="tweetButton"]'),
                        loginBtn: !!document.querySelector('[data-testid="loginButton"]')
                    };
                    return elements;
                }
            """
            x_elements = await page.execute_script(js)
            results['tests']['x_elements'] = {'status': '✅', 'data': x_elements}
        except Exception as e:
            results['tests']['x_elements'] = {'status': '❌', 'error': str(e)}
        
        # Итоговый отчет
        results['status'] = 'completed'
        
        total = len(results['tests'])
        success = sum(1 for t in results['tests'].values() if t.get('status') == '✅')
        warning = sum(1 for t in results['tests'].values() if t.get('status') == '⚠️')
        error = sum(1 for t in results['tests'].values() if t.get('status') == '❌')
        
        response = f"🧪 **РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ**\n\n"
        response += f"📊 Всего тестов: {total}\n"
        response += f"✅ Успешно: {success}\n"
        response += f"⚠️ Предупреждений: {warning}\n"
        response += f"❌ Ошибок: {error}\n\n"
        
        response += f"📋 **Детали:**\n"
        for name, data in results['tests'].items():
            status = data.get('status', '❌')
            if name == 'shadow':
                response += f"\n  🛡️ **Shadow DOM:**\n"
                for v, d in data.items():
                    if v != 'status':
                        response += f"    {v.upper()}: {d.get('status', '❌')}"
                        if d.get('count') is not None:
                            response += f" ({d['count']} элементов)"
                        response += "\n"
            else:
                response += f"  {name}: {status}"
                if data.get('result'):
                    response += f" → {data['result'][:50]}"
                elif data.get('url'):
                    response += f" → {data['url'][:50]}"
                elif data.get('data'):
                    response += f" → {json.dumps(data['data'])[:50]}"
                elif data.get('length'):
                    response += f" → {data['length']} байт"
                response += "\n"
        
        # Сохраняем JSON
        filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        await send_message_safe(update, response, parse_mode='Markdown')
        await update.message.reply_document(
            document=open(filename, 'rb'),
            caption=f"📄 Полные результаты тестирования"
        )
        
        # Определяем лучший Shadow вариант
        best_shadow = None
        best_count = 0
        if 'shadow' in results['tests']:
            for v, d in results['tests']['shadow'].items():
                if v != 'status' and d.get('count', 0) > best_count:
                    best_count = d['count']
                    best_shadow = v
        
        if best_shadow:
            await send_message_safe(update, 
                f"🏆 **Лучший Shadow DOM вариант: {best_shadow.upper()}** ({best_count} элементов)"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка test: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_photo_safe(update, photo, caption=""):
    try:
        if update.callback_query:
            await update.callback_query.message.reply_photo(photo=photo, caption=caption)
        elif update.message:
            await update.message.reply_photo(photo=photo, caption=caption)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")

async def send_message_safe(update, text, parse_mode=None, reply_markup=None):
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

async def set_cookies_combined(page):
    try:
        for cookie in COOKIES:
            await page.set_cookie(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain', '.x.com'),
                path=cookie.get('path', '/')
            )
        return True
    except:
        try:
            await page.execute_script('''
                document.cookie.split(";").forEach(function(c) {
                    document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
                });
            ''')
            for cookie in COOKIES:
                name = cookie['name']
                value = cookie['value'].replace("'", "\\'")
                domain = cookie.get('domain', '.x.com')
                path = cookie.get('path', '/')
                js_code = f"document.cookie = '{name}={value}; domain={domain}; path={path}';"
                await page.execute_script(js_code)
            return True
        except:
            return False

async def emulate_human_login_flow(page):
    try:
        await asyncio.sleep(random_delay(1, 3))
        await human_scroll(page, 200)
        await asyncio.sleep(random_delay(0.5, 1.5))
        await page.execute_script('window.scrollTo(0, 0);')
    except Exception as e:
        logger.warning(f"⚠️ Ошибка эмуляции: {e}")

async def check_login_status_detailed(page):
    try:
        js_code = """
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    if (key && val) acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasLoginBtn = !!document.querySelector('[data-testid="loginButton"]');
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const isOnLoginPage = window.location.href.includes('/login');
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                const hasUserElements = hasProfileLink || hasTweetBtn || hasSideNav;
                const hasLoginElements = hasLoginBtn || hasLoginLink;
                const isLoggedIn = hasAuthToken && hasUserElements && !hasLoginElements && !isOnLoginPage;
                
                return {
                    isLoggedIn: isLoggedIn,
                    username: username || null,
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    hasProfileLink: hasProfileLink,
                    hasTweetBtn: hasTweetBtn,
                    hasSideNav: hasSideNav,
                    hasLoginBtn: hasLoginBtn,
                    hasLoginLink: hasLoginLink,
                    isOnLoginPage: isOnLoginPage,
                    url: window.location.href
                };
            }
        """
        return await page.execute_script(js_code)
    except:
        return {'isLoggedIn': False}

# ========== КОМАНДА ЛОГИН ==========

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /login от {update.effective_user.username}")
    await send_message_safe(update, "🚀 Запускаю браузер...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Не удалось запустить браузер.")
            return
        
        await send_message_safe(update, "🌐 Захожу на X.com...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(2)
        
        await send_message_safe(update, "🍪 Устанавливаю куки...")
        await set_cookies_combined(page)
        
        await send_message_safe(update, "🚶 Эмулирую поведение...")
        await emulate_human_login_flow(page)
        
        await send_message_safe(update, "🔄 Обновляю страницу...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(3)
        
        await send_message_safe(update, "🔍 Проверяю авторизацию...")
        status_data = await check_login_status_detailed(page)
        
        global login_status
        login_status['is_logged_in'] = status_data.get('isLoggedIn', False)
        login_status['username'] = status_data.get('username')
        login_status['last_check'] = datetime.now()
        
        response = f"📊 **СТАТУС АВТОРИЗАЦИИ**\n\n"
        response += f"📍 URL: {status_data.get('url', 'unknown')}\n\n"
        response += f"🍪 auth_token: {'✅' if status_data.get('hasAuthToken') else '❌'}\n"
        response += f"🍪 ct0: {'✅' if status_data.get('hasCt0') else '❌'}\n\n"
        response += f"👤 Профиль: {'✅' if status_data.get('hasProfileLink') else '❌'}\n"
        response += f"📝 Твитнуть: {'✅' if status_data.get('hasTweetBtn') else '❌'}\n"
        response += f"⚙️ Меню: {'✅' if status_data.get('hasSideNav') else '❌'}\n\n"
        
        if status_data.get('isLoggedIn'):
            response += f"✅ **ВЫ АВТОРИЗОВАНЫ!**\n"
            if status_data.get('username'):
                response += f"👤 @{status_data['username']}\n"
            response += "\n💡 Бот готов к работе!"
        else:
            response += f"❌ **НЕ АВТОРИЗОВАН**\n\n"
            if status_data.get('isOnLoginPage'):
                response += "⚠️ Куки устарели. Обновите через /setcookies"
            elif not status_data.get('hasAuthToken'):
                response += "⚠️ auth_token отсутствует. Обновите куки"
            else:
                response += "⚠️ Попробуйте /login еще раз"
        
        await send_message_safe(update, response)
        
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(
                update,
                screenshot,
                f"📸 X.com - {'✅ Авторизован' if status_data.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка login: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Авторизация", callback_data="login")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screen")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("📝 Твиты", callback_data="tweets")],
        [InlineKeyboardButton("🛡️ Shadow DOM", callback_data="shadow")],
        [InlineKeyboardButton("🧪 Тест", callback_data="test")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        f"📌 **Нажмите кнопку:**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "screen":
        await screen(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "tweets":
        await query.edit_message_text(
            "📝 **Введите username для парсинга твитов:**\n\n"
            "Пример: `/tweets elonmusk 5`"
        )
    elif query.data == "shadow":
        await shadow(update, context)
    elif query.data == "test":
        await test(update, context)
    elif query.data == "close":
        await close(update, context)

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message_safe(update, "📸 Делаю скриншот...")
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Скриншот X.com")
        else:
            await send_message_safe(update, "❌ Не удалось сделать скриншот")
    except Exception as e:
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"📊 **СТАТУС БОТА**\n\n"
    status_text += f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username']:
        status_text += f"👤 @{login_status['username']}\n"
    status_text += f"🕐 {login_status['last_check'] or 'Никогда'}\n\n"
    status_text += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
    status_text += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
    status_text += f"🌐 Браузер: {'✅' if pydoll_browser else '❌'}\n"
    status_text += f"🍪 Кук: {len(COOKIES)}"
    await send_message_safe(update, status_text, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message_safe(update, "⏳ Закрываю браузер...")
    await close_pydoll_browser()
    await send_message_safe(update, "✅ Браузер закрыт!")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /tweets <username> [count]")
        return
    
    username = context.args[0].replace('@', '').strip()
    count = int(context.args[1]) if len(context.args) > 1 else 10
    
    await send_message_safe(update, f"📊 Парсю твиты @{username}...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен")
            return
        
        await human_goto(page, f"https://x.com/{username}")
        await asyncio.sleep(2)
        await human_scroll(page, 500)
        await asyncio.sleep(1)
        
        js_tweets = f"""
            () => {{
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach((tweet, index) => {{
                    if (index >= {count}) return;
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const timeEl = tweet.querySelector('time');
                    const isPinned = !!tweet.querySelector('[data-testid="pinIcon"]');
                    tweets.push({{
                        text: textEl ? textEl.innerText.trim() : '',
                        time: timeEl ? timeEl.getAttribute('datetime') : '',
                        is_pinned: isPinned
                    }});
                }});
                return tweets;
            }}
        """
        
        tweets_data = await page.execute_script(js_tweets)
        
        if not tweets_data:
            await send_message_safe(update, f"❌ Твиты @{username} не найдены")
            return
        
        response = f"📊 **ТВИТЫ @{username}**\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n📌 {len(tweets_data)}\n\n"
        for i, tweet in enumerate(tweets_data[:5], 1):
            if isinstance(tweet, dict):
                response += f"**{i}.** {tweet.get('text', '')[:200]}\n"
                if tweet.get('is_pinned'):
                    response += "📌 ЗАКРЕПЛЕН\n"
                response += "\n"
        
        await send_message_safe(update, response)
        
    except Exception as e:
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍪 **Обновление кук**\n\n"
        "Отправьте JSON:\n"
        "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\"}]`",
        parse_mode='Markdown'
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COOKIES
    if not context.user_data.get('waiting_for_cookies'):
        return
    
    try:
        data = json.loads(update.message.text)
        new_cookies = []
        if isinstance(data, list):
            for cookie in data:
                if 'name' in cookie and 'value' in cookie:
                    new_cookies.append({
                        "name": cookie['name'],
                        "value": cookie['value'],
                        "domain": cookie.get('domain', '.x.com'),
                        "path": cookie.get('path', '/')
                    })
        if new_cookies:
            COOKIES = new_cookies
            context.user_data['waiting_for_cookies'] = False
            await close_pydoll_browser()
            await update.message.reply_text(f"✅ Обновлено {len(COOKIES)} кук")
    except:
        pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("shadow", shadow))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n✅ Бот запущен!")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды:")
    print("  /start - Главное меню")
    print("  /login - Авторизация")
    print("  /tweets <username> - Твиты")
    print("  /shadow - Shadow DOM (5 вариантов)")
    print("  /test - Полное тестирование")
    print("  /screen - Скриншот")
    print("  /status - Статус")
    print("  /close - Закрыть браузер")
    print("  /setcookies - Обновить куки")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()