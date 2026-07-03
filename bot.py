import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
import random
import time
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
LOG_FILE = f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

logger.info("=" * 60)
logger.info(f"🚀 ЗАПУСК БОТА {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logger.info("=" * 60)

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
    logger.warning("⚠️ Chromium не найден!")
    return False

check_chromium()

# ========== ПРОВЕРКА PYDOLL ==========
PYDOLL_AVAILABLE = False
PYDOLL_VERSION = None

try:
    import pydoll
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions
    PYDOLL_AVAILABLE = True
    PYDOLL_VERSION = getattr(pydoll, '__version__', 'unknown')
    logger.info(f"✅ Pydoll загружен (версия: {PYDOLL_VERSION})")
except ImportError as e:
    logger.warning(f"⚠️ Pydoll не найден: {e}")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки Pydoll: {e}")

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

logger.info(f"🍪 Загружено {len(COOKIES)} кук")

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
        return True
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)
        return False

async def human_scroll(page, amount=300):
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
        return True
    except Exception as e:
        logger.warning(f"Human scroll error: {e}")
        await page.execute_script(f'window.scrollBy(0, {amount})')
        return False

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

# ========== БЕЗОПАСНОЕ ВЫПОЛНЕНИЕ JS ==========

async def safe_execute_js(script, timeout=10, default_return=None):
    """
    Безопасное выполнение JS с обработкой всех ошибок
    Всегда возвращает простой Python объект (dict, list, str, int, None)
    """
    logger.debug(f"  📜 Выполнение JS (таймаут: {timeout}с)")
    
    page = await get_browser()
    if page is None:
        logger.error("  ❌ Страница не получена")
        return default_return
    
    try:
        # Пробуем выполнить с таймаутом
        result = await asyncio.wait_for(
            page.execute_script(script),
            timeout=timeout
        )
        
        # Проверяем и преобразуем результат в безопасный формат
        return safe_convert_result(result)
        
    except asyncio.TimeoutError:
        logger.warning(f"  ⏱️ Таймаут {timeout}с")
        return default_return
    except TypeError as e:
        if 'unhashable type' in str(e):
            logger.warning(f"  ⚠️ Ошибка хеширования: {e}")
            # Пробуем через return_by_value если доступно
            try:
                if hasattr(page, 'execute_script') and hasattr(page.execute_script, 'return_by_value'):
                    result = await asyncio.wait_for(
                        page.execute_script(script, return_by_value=True),
                        timeout=timeout
                    )
                    return safe_convert_result(result)
            except:
                pass
            return default_return
        else:
            logger.error(f"  ❌ TypeError: {e}")
            return default_return
    except Exception as e:
        logger.error(f"  ❌ Ошибка JS: {str(e)[:100]}")
        return default_return

def safe_convert_result(data):
    """Рекурсивно преобразует данные в безопасный формат (хешируемые типы)"""
    if data is None:
        return None
    elif isinstance(data, (str, int, float, bool)):
        return data
    elif isinstance(data, list):
        return [safe_convert_result(item) for item in data]
    elif isinstance(data, dict):
        # Преобразуем ключи в строки
        return {str(key): safe_convert_result(value) for key, value in data.items()}
    elif isinstance(data, tuple):
        return tuple(safe_convert_result(item) for item in data)
    elif hasattr(data, '__dict__'):
        # Для объектов с __dict__ преобразуем в dict
        try:
            return {str(k): safe_convert_result(v) for k, v in data.__dict__.items()}
        except:
            return str(data)
    else:
        # Все остальное преобразуем в строку
        try:
            return str(data)
        except:
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

# ========== 5 ФУНКЦИЙ SHADOW DOM ==========

async def shadow_v1(page):
    """Вариант 1: Простой поиск shadowRoot"""
    logger.info("  🔍 V1: Простой поиск shadowRoot")
    try:
        js = """
            (function() {
                try {
                    var result = [];
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        if (el.shadowRoot) {
                            result.push({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || null,
                                class: el.className || null,
                                children: el.shadowRoot.children.length
                            });
                        }
                    }
                    return result;
                } catch(e) {
                    return {error: e.message};
                }
            })()
        """
        result = await safe_execute_js(js, timeout=5.0, default_return=[])
        
        if result and isinstance(result, dict) and 'error' in result:
            logger.warning(f"  ⚠️ V1: JS ошибка - {result['error']}")
            return []
        
        count = len(result) if result else 0
        logger.info(f"  ✅ V1: Найдено {count} элементов")
        return result if result else []
        
    except Exception as e:
        logger.error(f"  ❌ V1: {str(e)[:100]}")
        return []

async def shadow_v2(page):
    """Вариант 2: Поиск конкретных элементов"""
    logger.info("  🔍 V2: Поиск конкретных элементов")
    try:
        js = """
            (function() {
                try {
                    var result = [];
                    var selectors = ['grok-drawer', 'video-player', 'emoji-picker'];
                    for (var s = 0; s < selectors.length; s++) {
                        var sel = selectors[s];
                        try {
                            var el = document.querySelector(sel);
                            if (el && el.shadowRoot) {
                                var children = [];
                                var childNodes = el.shadowRoot.children;
                                for (var c = 0; c < childNodes.length; c++) {
                                    var child = childNodes[c];
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
                        } catch(e) {
                            // Пропускаем ошибки для отдельных селекторов
                        }
                    }
                    return result;
                } catch(e) {
                    return {error: e.message};
                }
            })()
        """
        result = await safe_execute_js(js, timeout=5.0, default_return=[])
        
        if result and isinstance(result, dict) and 'error' in result:
            logger.warning(f"  ⚠️ V2: JS ошибка - {result['error']}")
            return []
        
        count = len(result) if result else 0
        logger.info(f"  ✅ V2: Найдено {count} элементов")
        return result if result else []
        
    except Exception as e:
        logger.error(f"  ❌ V2: {str(e)[:100]}")
        return []

async def shadow_v3(page):
    """Вариант 3: Рекурсивный обход"""
    logger.info("  🔍 V3: Рекурсивный обход")
    try:
        js = """
            (function() {
                try {
                    function traverse(el, path) {
                        var data = {
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            class: el.className || null,
                            path: path,
                            hasShadow: !!el.shadowRoot,
                            children: []
                        };
                        
                        if (el.shadowRoot) {
                            var shadowChildren = el.shadowRoot.children;
                            for (var i = 0; i < shadowChildren.length; i++) {
                                try {
                                    data.children.push(traverse(shadowChildren[i], path + ' > shadow'));
                                } catch(e) {
                                    data.children.push({error: e.message});
                                }
                            }
                        }
                        
                        var domChildren = el.children;
                        for (var j = 0; j < domChildren.length; j++) {
                            var child = domChildren[j];
                            if (!child.shadowRoot) {
                                try {
                                    data.children.push(traverse(child, path + ' > ' + el.tagName));
                                } catch(e) {
                                    data.children.push({error: e.message});
                                }
                            }
                        }
                        
                        return data;
                    }
                    
                    return traverse(document.body, 'body');
                } catch(e) {
                    return {error: e.message};
                }
            })()
        """
        result = await safe_execute_js(js, timeout=10.0, default_return={})
        
        if result and isinstance(result, dict) and 'error' in result:
            logger.warning(f"  ⚠️ V3: JS ошибка - {result['error']}")
            return {}
        
        logger.info(f"  ✅ V3: Обход завершен")
        return result if result else {}
        
    except Exception as e:
        logger.error(f"  ❌ V3: {str(e)[:100]}")
        return {}

async def shadow_v4(page):
    """Вариант 4: Хосты с shadowRoot"""
    logger.info("  🔍 V4: Хосты с shadowRoot")
    try:
        js = """
            (function() {
                try {
                    var hosts = [];
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        if (el.shadowRoot) {
                            try {
                                var info = {
                                    tag: el.tagName,
                                    id: el.id || null,
                                    class: el.className || null,
                                    childCount: el.shadowRoot.children.length
                                };
                                
                                try {
                                    var buttons = el.shadowRoot.querySelectorAll('button');
                                    var inputs = el.shadowRoot.querySelectorAll('input, textarea');
                                    info.buttons = buttons.length;
                                    info.inputs = inputs.length;
                                } catch(e) {
                                    info.buttons = 0;
                                    info.inputs = 0;
                                }
                                
                                hosts.push(info);
                            } catch(e) {
                                // Пропускаем ошибки для отдельных элементов
                            }
                        }
                    }
                    return hosts;
                } catch(e) {
                    return {error: e.message};
                }
            })()
        """
        result = await safe_execute_js(js, timeout=5.0, default_return=[])
        
        if result and isinstance(result, dict) and 'error' in result:
            logger.warning(f"  ⚠️ V4: JS ошибка - {result['error']}")
            return []
        
        count = len(result) if result else 0
        logger.info(f"  ✅ V4: Найдено {count} хостов")
        return result if result else []
        
    except Exception as e:
        logger.error(f"  ❌ V4: {str(e)[:100]}")
        return []

async def shadow_v5(page):
    """Вариант 5: Через Pydoll find + get_shadow_root"""
    logger.info("  🔍 V5: Pydoll find + get_shadow_root")
    try:
        hosts = []
        selectors = ['grok-drawer', '[data-testid="GrokDrawer"]', 'video-player']
        
        for sel in selectors:
            try:
                el = await asyncio.wait_for(page.find(sel, timeout=3000), timeout=5.0)
                if el and hasattr(el, 'get_shadow_root'):
                    shadow = await asyncio.wait_for(el.get_shadow_root(), timeout=5.0)
                    if shadow:
                        children = []
                        try:
                            inner = await asyncio.wait_for(shadow.find_all('*', timeout=3000), timeout=5.0)
                            for child in inner[:3]:
                                try:
                                    text = await child.text() if hasattr(child, 'text') else None
                                    tag = await child.tag_name() if hasattr(child, 'tag_name') else 'unknown'
                                    children.append({
                                        'tag': tag,
                                        'text': text[:50] if text else None
                                    })
                                except:
                                    pass
                        except:
                            pass
                        hosts.append({
                            'selector': sel,
                            'children': children
                        })
                        logger.info(f"  ✅ V5: Найден {sel} с {len(children)} детьми")
            except asyncio.TimeoutError:
                logger.warning(f"  ⏱️ V5: Таймаут при поиске {sel}")
            except Exception as e:
                logger.warning(f"  ⚠️ V5: Ошибка при поиске {sel}: {str(e)[:50]}")
                continue
        
        logger.info(f"  ✅ V5: Найдено {len(hosts)} элементов")
        return hosts
        
    except Exception as e:
        logger.error(f"  ❌ V5: {str(e)[:100]}")
        return []

# ========== /SHADOW ==========

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shadow DOM - тестирование всех 5 вариантов"""
    logger.info(f"📩 /shadow от {update.effective_user.username}")
    
    await send_message_safe(update, "🛡️ Тестирую Shadow DOM (5 вариантов)...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        results = {}
        times = {}
        errors = {}
        
        variants = [
            ('V1', shadow_v1, 'Простой поиск'),
            ('V2', shadow_v2, 'Конкретные элементы'),
            ('V3', shadow_v3, 'Рекурсивный обход'),
            ('V4', shadow_v4, 'Хосты с shadowRoot'),
            ('V5', shadow_v5, 'Pydoll find')
        ]
        
        for name, func, desc in variants:
            await send_message_safe(update, f"🔄 {name}: {desc}...")
            start = time.time()
            try:
                result = await func(page)
                results[name] = result
                times[name] = time.time() - start
                count = len(result) if isinstance(result, (list, dict)) else 0
                logger.info(f"✅ {name}: {count} элементов за {times[name]:.2f}с")
            except Exception as e:
                errors[name] = str(e)
                results[name] = []
                times[name] = time.time() - start
                logger.error(f"❌ {name}: {str(e)}")
                await send_message_safe(update, f"⚠️ {name}: ошибка - {str(e)[:50]}")
        
        # Формируем отчет
        response = f"🛡️ **SHADOW DOM - РЕЗУЛЬТАТЫ**\n\n"
        response += f"⏱️ Общее время: {sum(times.values()):.2f}с\n\n"
        
        best = None
        max_count = 0
        
        for name in ['V1', 'V2', 'V3', 'V4', 'V5']:
            data = results.get(name, [])
            t = times.get(name, 0)
            
            if name in errors:
                response += f"❌ **{name}** - ОШИБКА: {errors[name][:50]} ({t:.2f}с)\n"
            elif data and len(data) > 0:
                count = len(data)
                response += f"✅ **{name}** - {count} элементов ({t:.2f}с)\n"
                if count > max_count:
                    max_count = count
                    best = name
                for i, item in enumerate(data[:2]):
                    if isinstance(item, dict):
                        tag = item.get('tag', item.get('host', 'unknown'))
                        response += f"  └─ {i+1}. {tag}"
                        if item.get('id'):
                            response += f" (id: {item['id']})"
                        if item.get('childCount') or item.get('children'):
                            count_children = item.get('childCount', len(item.get('children', [])))
                            response += f" - детей: {count_children}"
                        response += "\n"
            else:
                response += f"❌ **{name}** - Ничего не найдено ({t:.2f}с)\n"
            response += "\n"
        
        if best:
            response += f"🏆 **Лучший вариант: {best}** ({max_count} элементов)\n"
        else:
            response += "❌ **Ни один вариант не сработал**\n"
        
        await send_message_safe(update, response, parse_mode='Markdown')
        
        # Сохраняем данные
        json_filename = f"shadow_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump({
                'results': results,
                'times': times,
                'errors': errors,
                'best': best,
                'max_count': max_count,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        await update.message.reply_document(
            document=open(json_filename, 'rb'),
            caption=f"📄 Полные данные"
        )
        
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Текущая страница")
        
    except Exception as e:
        logger.error(f"❌ Ошибка shadow: {e}", exc_info=True)
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
            (function() {
                var cookies = {};
                var parts = document.cookie.split(';');
                for (var i = 0; i < parts.length; i++) {
                    var pair = parts[i].trim().split('=');
                    if (pair[0]) {
                        cookies[pair[0]] = pair[1] || '';
                    }
                }
                
                var hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                var hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                var hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                var hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                var hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                var hasLoginBtn = !!document.querySelector('[data-testid="loginButton"]');
                var hasLoginLink = !!document.querySelector('a[href="/login"]');
                var isOnLoginPage = window.location.href.indexOf('/login') !== -1;
                
                var username = null;
                var profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    var href = profileLink.getAttribute('href');
                    if (href) {
                        var match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                if (!username) {
                    var accountBtn = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                    if (accountBtn) {
                        var text = accountBtn.textContent || '';
                        var match = text.match(/@([a-zA-Z0-9_]+)/);
                        if (match) username = match[1];
                    }
                }
                
                var hasUserElements = hasProfileLink || hasTweetBtn || hasSideNav;
                var hasLoginElements = hasLoginBtn || hasLoginLink;
                var isLoggedIn = hasAuthToken && hasUserElements && !hasLoginElements && !isOnLoginPage;
                
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
            })()
        """
        return await safe_execute_js(js_code, timeout=10.0, default_return={'isLoggedIn': False})
    except Exception as e:
        logger.error(f"❌ Ошибка проверки статуса: {e}")
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
            (function() {{
                var tweets = [];
                var elements = document.querySelectorAll('[data-testid="tweet"]');
                for (var i = 0; i < elements.length && i < {count}; i++) {{
                    var tweet = elements[i];
                    var textEl = tweet.querySelector('[data-testid="tweetText"]');
                    var timeEl = tweet.querySelector('time');
                    var isPinned = !!tweet.querySelector('[data-testid="pinIcon"]');
                    tweets.push({{
                        text: textEl ? textEl.innerText.trim() : '',
                        time: timeEl ? timeEl.getAttribute('datetime') : '',
                        is_pinned: isPinned
                    }});
                }}
                return tweets;
            }})()
        """
        
        tweets_data = await safe_execute_js(js_tweets, timeout=10.0, default_return=[])
        
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
    print("  /screen - Скриншот")
    print("  /status - Статус")
    print("  /close - Закрыть браузер")
    print("  /setcookies - Обновить куки")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()