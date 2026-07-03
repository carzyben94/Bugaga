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

# ========== МНОЖЕСТВО СПОСОБОВ ВЫПОЛНЕНИЯ JS ==========

async def exec_method_1(page, script):
    """Метод 1: Прямой execute_script"""
    try:
        return await asyncio.wait_for(page.execute_script(script), timeout=5.0)
    except Exception as e:
        logger.warning(f"M1 error: {e}")
        return None

async def exec_method_2(page, script):
    """Метод 2: С try/catch внутри JS"""
    wrapped = f"try {{ return ({script}); }} catch(e) {{ return {{'error': e.message}}; }}"
    try:
        return await asyncio.wait_for(page.execute_script(wrapped), timeout=5.0)
    except Exception as e:
        logger.warning(f"M2 error: {e}")
        return None

async def exec_method_3(page, script):
    """Метод 3: JSON.stringify + JSON.parse"""
    wrapped = f"JSON.stringify((function() {{ try {{ return {script}; }} catch(e) {{ return {{'error': e.message}}; }} }})())"
    try:
        result = await asyncio.wait_for(page.execute_script(wrapped), timeout=5.0)
        if isinstance(result, str):
            return json.loads(result)
        return result
    except Exception as e:
        logger.warning(f"M3 error: {e}")
        return None

async def exec_method_4(page, script):
    """Метод 4: Через return_by_value (если есть)"""
    try:
        if hasattr(page.execute_script, 'return_by_value'):
            return await asyncio.wait_for(
                page.execute_script(script, return_by_value=True),
                timeout=5.0
            )
        return await asyncio.wait_for(page.execute_script(script), timeout=5.0)
    except Exception as e:
        logger.warning(f"M4 error: {e}")
        return None

async def exec_method_5(page, script):
    """Метод 5: eval + JSON.stringify"""
    wrapped = f"JSON.stringify(eval('({script})'))"
    try:
        result = await asyncio.wait_for(page.execute_script(wrapped), timeout=5.0)
        if isinstance(result, str):
            return json.loads(result)
        return result
    except Exception as e:
        logger.warning(f"M5 error: {e}")
        return None

async def exec_method_6(page, script):
    """Метод 6: function + return"""
    wrapped = f"(function() {{ try {{ return {script}; }} catch(e) {{ return {{error: e.message}}; }} }})()"
    try:
        return await asyncio.wait_for(page.execute_script(wrapped), timeout=5.0)
    except Exception as e:
        logger.warning(f"M6 error: {e}")
        return None

# ========== ПОИСК SHADOW DOM (ТОЛЬКО JS) ==========

async def find_shadow_simple(page):
    """Простой поиск shadowRoot"""
    script = """
        (function() {
            var result = [];
            var els = document.querySelectorAll('*');
            for (var i = 0; i < els.length; i++) {
                if (els[i].shadowRoot) {
                    result.push({
                        tag: els[i].tagName,
                        id: els[i].id || '',
                        children: els[i].shadowRoot.children.length
                    });
                }
            }
            return result;
        })()
    """
    return script

async def find_shadow_by_tags(page):
    """Поиск по конкретным тегам"""
    script = """
        (function() {
            var result = [];
            var tags = ['grok-drawer', 'video-player', 'emoji-picker'];
            for (var i = 0; i < tags.length; i++) {
                var el = document.querySelector(tags[i]);
                if (el && el.shadowRoot) {
                    result.push({
                        tag: tags[i],
                        id: el.id || '',
                        children: el.shadowRoot.children.length
                    });
                }
            }
            return result;
        })()
    """
    return script

async def find_shadow_deep(page):
    """Глубокий рекурсивный поиск"""
    script = """
        (function() {
            function find(el, depth) {
                if (depth > 5) return [];
                var result = [];
                if (el.shadowRoot) {
                    result.push({
                        tag: el.tagName,
                        id: el.id || '',
                        depth: depth,
                        children: el.shadowRoot.children.length
                    });
                }
                for (var i = 0; i < el.children.length; i++) {
                    result = result.concat(find(el.children[i], depth + 1));
                }
                return result;
            }
            return find(document.body, 0);
        })()
    """
    return script

# ========== /SHADOW С ТЕСТИРОВАНИЕМ ВСЕХ МЕТОДОВ ==========

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shadow DOM - тестирование всех методов выполнения JS"""
    logger.info(f"📩 /shadow от {update.effective_user.username}")
    
    # Создаем лог-файл для этой команды
    log_filename = f"shadow_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    def write_log(msg):
        log_file.write(f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        log_file.flush()
    
    write_log("=" * 60)
    write_log(f"SHADOW DOM ТЕСТ - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    write_log("=" * 60)
    
    msg = await update.message.reply_text("🛡️ Тестирую Shadow DOM...\n⏳ Проверяю 6 методов выполнения JS")
    write_log("🛡️ Начало тестирования")
    
    try:
        page = await get_browser()
        if page is None:
            await msg.edit_text("❌ Браузер не запущен. Используйте /login")
            write_log("❌ Браузер не запущен")
            log_file.close()
            return
        
        # Все методы выполнения
        exec_methods = [
            ('M1', exec_method_1, 'Прямой execute_script'),
            ('M2', exec_method_2, 'try/catch в JS'),
            ('M3', exec_method_3, 'JSON.stringify + parse'),
            ('M4', exec_method_4, 'return_by_value'),
            ('M5', exec_method_5, 'eval + JSON.stringify'),
            ('M6', exec_method_6, 'function + return'),
        ]
        
        # Все скрипты для поиска shadow
        shadow_scripts = [
            ('S1', await find_shadow_simple(page), 'Простой поиск'),
            ('S2', await find_shadow_by_tags(page), 'Поиск по тегам'),
            ('S3', await find_shadow_deep(page), 'Глубокий рекурсивный'),
        ]
        
        results = {}
        working_methods = []
        found_elements = []
        
        # Тестируем каждую комбинацию
        total_tests = len(exec_methods) * len(shadow_scripts)
        current = 0
        
        for m_name, m_func, m_desc in exec_methods:
            for s_name, s_script, s_desc in shadow_scripts:
                current += 1
                key = f"{m_name}_{s_name}"
                
                status_text = f"🔄 [{current}/{total_tests}] {m_name}+{s_name}..."
                await msg.edit_text(f"🛡️ Тестирую Shadow DOM...\n{status_text}")
                write_log(f"🔄 Тест {current}/{total_tests}: {m_name}+{s_name}")
                
                start = time.time()
                try:
                    result = await m_func(page, s_script)
                    elapsed = time.time() - start
                    
                    # Проверяем результат
                    is_working = False
                    count = 0
                    
                    if isinstance(result, list):
                        count = len(result)
                        is_working = count > 0
                    elif isinstance(result, dict):
                        if 'error' not in result:
                            count = 1
                            is_working = True
                    elif result is not None:
                        count = 1
                        is_working = True
                    
                    results[key] = {
                        'method': m_name,
                        'script': s_name,
                        'working': is_working,
                        'count': count,
                        'time': elapsed,
                        'result': result
                    }
                    
                    if is_working:
                        working_methods.append(key)
                        if isinstance(result, list):
                            found_elements.extend(result[:3])
                        write_log(f"✅ {m_name}+{s_name}: РАБОТАЕТ ({count} элементов) за {elapsed:.2f}с")
                    else:
                        write_log(f"⚠️ {m_name}+{s_name}: не найдено за {elapsed:.2f}с")
                        
                except Exception as e:
                    results[key] = {
                        'method': m_name,
                        'script': s_name,
                        'working': False,
                        'error': str(e),
                        'time': time.time() - start
                    }
                    write_log(f"❌ {m_name}+{s_name}: ошибка - {str(e)[:100]}")
        
        # Формируем отчет
        write_log("\n" + "=" * 60)
        write_log("📊 ФОРМИРОВАНИЕ ОТЧЕТА")
        write_log("=" * 60)
        
        response = "🛡️ **SHADOW DOM - РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ**\n\n"
        response += f"📊 Всего тестов: {total_tests}\n"
        response += f"✅ Работающих методов: {len(working_methods)}\n"
        response += f"⏱️ Общее время: {sum(r.get('time', 0) for r in results.values()):.2f}с\n\n"
        
        # Показываем работающие методы
        if working_methods:
            response += "✅ **РАБОТАЮЩИЕ МЕТОДЫ:**\n"
            for key in working_methods[:5]:
                data = results[key]
                response += f"  • {key} - {data.get('count', 0)} элементов ({data.get('time', 0):.2f}с)\n"
                write_log(f"✅ {key} - {data.get('count', 0)} элементов")
            
            # Показываем найденные элементы
            if found_elements:
                response += "\n📋 **НАЙДЕННЫЕ ЭЛЕМЕНТЫ:**\n"
                for item in found_elements[:3]:
                    if isinstance(item, dict):
                        tag = item.get('tag', 'unknown')
                        response += f"  • {tag}"
                        if item.get('id'):
                            response += f" (id: {item['id']})"
                        if item.get('children'):
                            response += f" - детей: {item['children']}"
                        response += "\n"
                        write_log(f"  • {tag} - {item}")
        else:
            response += "❌ **НИ ОДИН МЕТОД НЕ СРАБОТАЛ**\n"
            response += "💡 Проверьте:\n"
            response += "1. Авторизованы ли вы (/login)\n"
            response += "2. На странице есть shadowRoot элементы\n"
            response += "3. Попробуйте обновить страницу\n"
            write_log("❌ Ни один метод не сработал")
        
        # Рекомендация
        if working_methods:
            best = working_methods[0]
            best_data = results[best]
            response += f"\n🏆 **Лучший метод: {best}**\n"
            response += f"📊 Найдено: {best_data.get('count', 0)} элементов\n"
            response += f"⏱️ Время: {best_data.get('time', 0):.2f}с\n"
            
            # Показываем пример кода
            response += "\n💡 **Используйте этот код:**\n"
            response += "```python\n"
            response += f"# Лучший метод: {best}\n"
            response += f"result = await {best.split('_')[0]}(page, script)\n"
            response += "```"
            write_log(f"🏆 Лучший метод: {best}")
        
        await msg.edit_text(response, parse_mode='Markdown')
        write_log("✅ Отчет сформирован")
        
        # Сохраняем полные результаты в JSON
        json_filename = f"shadow_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            # Очищаем результаты от больших данных
            clean_results = {}
            for k, v in results.items():
                clean_results[k] = {
                    'method': v.get('method'),
                    'script': v.get('script'),
                    'working': v.get('working'),
                    'count': v.get('count', 0),
                    'time': v.get('time', 0)
                }
                if 'error' in v:
                    clean_results[k]['error'] = v['error']
            
            json.dump({
                'results': clean_results,
                'working_methods': working_methods,
                'best': working_methods[0] if working_methods else None,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        # Отправляем логи в чат
        log_file.close()
        await update.message.reply_document(
            document=open(log_filename, 'rb'),
            caption="📋 Полный лог выполнения"
        )
        await update.message.reply_document(
            document=open(json_filename, 'rb'),
            caption="📄 Результаты тестирования (JSON)"
        )
        
        # Скриншот
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Текущая страница")
        
    except Exception as e:
        logger.error(f"❌ Ошибка shadow: {e}", exc_info=True)
        write_log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        write_log(traceback.format_exc())
        log_file.close()
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

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
        # Используем exec_method_3 как самый надежный
        result = await exec_method_3(page, js_code)
        return result if isinstance(result, dict) else {'isLoggedIn': False}
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
        
        script = f"""
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
        
        tweets_data = await exec_method_3(page, script)
        
        if not tweets_data or not isinstance(tweets_data, list):
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
    print("  /shadow - Shadow DOM (тест 6 методов)")
    print("  /screen - Скриншот")
    print("  /status - Статус")
    print("  /close - Закрыть браузер")
    print("  /setcookies - Обновить куки")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()