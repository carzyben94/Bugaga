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

# ========== НАСТРОЙКА ГЛУБОКОГО ЛОГГИРОВАНИЯ ==========
LOG_FILE = f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Настройка логгера с записью в файл
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

# Отключаем шумные логгеры
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
    logger.debug("🔍 Проверка Chromium...")
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
current_operation = None
operation_start_time = None

# ========== ФУНКЦИЯ ДЛЯ ОТСЛЕЖИВАНИЯ ПРОЦЕССА ==========

def log_operation_start(operation_name):
    """Логирует начало операции"""
    global current_operation, operation_start_time
    current_operation = operation_name
    operation_start_time = time.time()
    logger.info(f"▶️ НАЧАЛО: {operation_name}")

def log_operation_end(operation_name, status="SUCCESS", details=None):
    """Логирует окончание операции"""
    global current_operation, operation_start_time
    elapsed = time.time() - operation_start_time if operation_start_time else 0
    logger.info(f"⏹️ КОНЕЦ: {operation_name} | Статус: {status} | Время: {elapsed:.2f}с")
    if details:
        logger.info(f"📋 Детали: {details}")
    current_operation = None
    operation_start_time = None

def log_step(step_name, data=None):
    """Логирует шаг внутри операции"""
    logger.info(f"  🔹 {step_name}")
    if data:
        logger.debug(f"    📊 {json.dumps(data, ensure_ascii=False)[:200]}")

def log_error(error, context=None):
    """Логирует ошибку с полным стеком"""
    logger.error(f"❌ ОШИБКА: {error}")
    if context:
        logger.error(f"  📍 Контекст: {context}")
    logger.error(f"  📚 Стек:\n{traceback.format_exc()}")

# ========== БРАУЗЕРНАЯ ЛОГИКА ==========

def random_delay(min_sec=0.5, max_sec=2.0):
    return random.uniform(min_sec, max_sec)

async def human_goto(page, url):
    log_step(f"Переход на {url[:50]}...")
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
        log_step(f"✅ Переход выполнен")
        return True
    except Exception as e:
        log_error(e, f"human_goto({url})")
        await page.go_to(url)
        return False

async def human_scroll(page, amount=300):
    log_step(f"Скролл на {amount}px...")
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
        return True
    except Exception as e:
        log_error(e, f"human_scroll({amount})")
        await page.execute_script(f'window.scrollBy(0, {amount})')
        return False

async def get_pydoll_browser():
    global pydoll_browser, pydoll_tab
    log_operation_start("get_pydoll_browser")
    
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            log_step("✅ Существующий браузер работает")
            log_operation_end("get_pydoll_browser", "SUCCESS", "использован существующий")
            return pydoll_tab
        except Exception as e:
            log_warning(f"Браузер не отвечает: {e}")
            await close_pydoll_browser()
    
    if not PYDOLL_AVAILABLE:
        log_error("Pydoll не установлен")
        log_operation_end("get_pydoll_browser", "FAILED", "Pydoll не установлен")
        return None
    
    if not CHROMIUM_INSTALLED:
        log_error("Chromium не найден")
        log_operation_end("get_pydoll_browser", "FAILED", "Chromium не найден")
        return None
    
    try:
        log_step("Создание опций Chromium...")
        options = ChromiumOptions()
        options.binary_location = CHROMIUM_PATH
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        log_step("✅ Опции созданы")
        
        log_step("Запуск браузера...")
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        log_step("✅ Браузер запущен")
        
        log_step("Переход на X.com...")
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        log_step("✅ Переход выполнен")
        
        log_operation_end("get_pydoll_browser", "SUCCESS", "браузер готов")
        return pydoll_tab
    except Exception as e:
        log_error(e, "get_pydoll_browser")
        log_operation_end("get_pydoll_browser", "FAILED", str(e))
        return None

async def close_pydoll_browser():
    global pydoll_browser, pydoll_tab
    log_operation_start("close_pydoll_browser")
    if pydoll_browser:
        try:
            await pydoll_browser.close()
            log_step("✅ Браузер закрыт")
        except Exception as e:
            log_error(e, "close_pydoll_browser")
        pydoll_browser = None
        pydoll_tab = None
    log_operation_end("close_pydoll_browser", "SUCCESS")

async def get_browser():
    return await get_pydoll_browser()

async def execute_js(script, timeout=10):
    """Выполнение JS с таймаутом"""
    log_step(f"Выполнение JS (таймаут: {timeout}с)...")
    page = await get_browser()
    if page is None:
        log_error("Страница не получена")
        return None
    
    try:
        result = await asyncio.wait_for(
            page.execute_script(script),
            timeout=timeout
        )
        log_step("✅ JS выполнен")
        return result
    except asyncio.TimeoutError:
        log_error(f"Таймаут {timeout}с при выполнении JS")
        return None
    except Exception as e:
        log_error(e, "execute_js")
        return None

async def take_screenshot():
    log_step("Создание скриншота...")
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'take_screenshot'):
            screenshot_base64 = await page.take_screenshot(as_base64=True)
            if screenshot_base64:
                log_step("✅ Скриншот создан")
                return base64.b64decode(screenshot_base64)
        return None
    except Exception as e:
        log_error(e, "take_screenshot")
        return None

# ========== SHADOW DOM - ВСЕ ВАРИАНТЫ С ЛОГАМИ ==========

async def shadow_v1(page):
    """Вариант 1: Простой поиск shadowRoot"""
    log_operation_start("shadow_v1")
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
        result = await asyncio.wait_for(page.execute_script(js), timeout=5.0)
        count = len(result) if result else 0
        log_step(f"✅ Найдено {count} элементов")
        log_operation_end("shadow_v1", "SUCCESS", f"найдено {count}")
        return result
    except asyncio.TimeoutError:
        log_error("Таймаут 5с в shadow_v1")
        log_operation_end("shadow_v1", "TIMEOUT")
        return None
    except Exception as e:
        log_error(e, "shadow_v1")
        log_operation_end("shadow_v1", "FAILED", str(e))
        return None

async def shadow_v2(page):
    """Вариант 2: С поиском конкретных элементов"""
    log_operation_start("shadow_v2")
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
        result = await asyncio.wait_for(page.execute_script(js), timeout=5.0)
        count = len(result) if result else 0
        log_step(f"✅ Найдено {count} элементов")
        log_operation_end("shadow_v2", "SUCCESS", f"найдено {count}")
        return result
    except asyncio.TimeoutError:
        log_error("Таймаут 5с в shadow_v2")
        log_operation_end("shadow_v2", "TIMEOUT")
        return None
    except Exception as e:
        log_error(e, "shadow_v2")
        log_operation_end("shadow_v2", "FAILED", str(e))
        return None

async def shadow_v3(page):
    """Вариант 3: Рекурсивный обход"""
    log_operation_start("shadow_v3")
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
        result = await asyncio.wait_for(page.execute_script(js), timeout=10.0)
        log_step(f"✅ Обход завершен")
        log_operation_end("shadow_v3", "SUCCESS")
        return result
    except asyncio.TimeoutError:
        log_error("Таймаут 10с в shadow_v3")
        log_operation_end("shadow_v3", "TIMEOUT")
        return None
    except Exception as e:
        log_error(e, "shadow_v3")
        log_operation_end("shadow_v3", "FAILED", str(e))
        return None

async def shadow_v4(page):
    """Вариант 4: Только хосты с shadowRoot"""
    log_operation_start("shadow_v4")
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
        result = await asyncio.wait_for(page.execute_script(js), timeout=5.0)
        count = len(result) if result else 0
        log_step(f"✅ Найдено {count} хостов")
        log_operation_end("shadow_v4", "SUCCESS", f"найдено {count}")
        return result
    except asyncio.TimeoutError:
        log_error("Таймаут 5с в shadow_v4")
        log_operation_end("shadow_v4", "TIMEOUT")
        return None
    except Exception as e:
        log_error(e, "shadow_v4")
        log_operation_end("shadow_v4", "FAILED", str(e))
        return None

async def shadow_v5(page):
    """Вариант 5: Через find + get_shadow_root (Pydoll метод)"""
    log_operation_start("shadow_v5")
    try:
        hosts = []
        selectors = ['grok-drawer', '[data-testid="GrokDrawer"]', 'video-player']
        
        for sel in selectors:
            log_step(f"Поиск селектора: {sel}")
            try:
                el = await asyncio.wait_for(page.find(sel, timeout=3000), timeout=5.0)
                if el and hasattr(el, 'get_shadow_root'):
                    log_step(f"✅ Найден {sel}, получаем shadowRoot")
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
                        log_step(f"✅ Добавлен {sel} с {len(children)} детьми")
            except asyncio.TimeoutError:
                log_step(f"⏱️ Таймаут при поиске {sel}")
            except Exception as e:
                log_step(f"⚠️ Ошибка при поиске {sel}: {e}")
                continue
        
        log_operation_end("shadow_v5", "SUCCESS", f"найдено {len(hosts)}")
        return hosts
    except Exception as e:
        log_error(e, "shadow_v5")
        log_operation_end("shadow_v5", "FAILED", str(e))
        return None

# ========== /SHADOW - С ЛОГАМИ И ТАЙМАУТАМИ ==========

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shadow DOM - тестирование всех вариантов с глубокими логами"""
    logger.info(f"📩 /shadow от {update.effective_user.username}")
    log_operation_start("shadow_command")
    
    # Создаем файл логов для этой команды
    log_filename = f"shadow_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    def write_log(msg):
        log_file.write(f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        log_file.flush()
    
    write_log("=" * 60)
    write_log(f"SHADOW DOM ТЕСТ - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    write_log("=" * 60)
    
    await send_message_safe(update, "🛡️ Тестирую Shadow DOM (5 вариантов)...")
    write_log("🛡️ Начало тестирования Shadow DOM")
    
    try:
        page = await get_browser()
        if page is None:
            write_log("❌ Браузер не запущен")
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            log_file.close()
            return
        
        results = {}
        times = {}
        
        # Вариант 1
        await send_message_safe(update, "🔄 Вариант 1: Простой поиск...")
        write_log("🔄 Вариант 1: Простой поиск...")
        start = time.time()
        results['v1'] = await shadow_v1(page)
        times['v1'] = time.time() - start
        write_log(f"✅ V1 завершен за {times['v1']:.2f}с, найдено: {len(results['v1']) if results['v1'] else 0}")
        
        # Вариант 2
        await send_message_safe(update, "🔄 Вариант 2: Конкретные элементы...")
        write_log("🔄 Вариант 2: Конкретные элементы...")
        start = time.time()
        results['v2'] = await shadow_v2(page)
        times['v2'] = time.time() - start
        write_log(f"✅ V2 завершен за {times['v2']:.2f}с, найдено: {len(results['v2']) if results['v2'] else 0}")
        
        # Вариант 3
        await send_message_safe(update, "🔄 Вариант 3: Рекурсивный обход...")
        write_log("🔄 Вариант 3: Рекурсивный обход...")
        start = time.time()
        results['v3'] = await shadow_v3(page)
        times['v3'] = time.time() - start
        write_log(f"✅ V3 завершен за {times['v3']:.2f}с")
        
        # Вариант 4
        await send_message_safe(update, "🔄 Вариант 4: Хосты с shadowRoot...")
        write_log("🔄 Вариант 4: Хосты с shadowRoot...")
        start = time.time()
        results['v4'] = await shadow_v4(page)
        times['v4'] = time.time() - start
        write_log(f"✅ V4 завершен за {times['v4']:.2f}с, найдено: {len(results['v4']) if results['v4'] else 0}")
        
        # Вариант 5
        await send_message_safe(update, "🔄 Вариант 5: Pydoll find + get_shadow_root...")
        write_log("🔄 Вариант 5: Pydoll find + get_shadow_root...")
        start = time.time()
        results['v5'] = await shadow_v5(page)
        times['v5'] = time.time() - start
        write_log(f"✅ V5 завершен за {times['v5']:.2f}с, найдено: {len(results['v5']) if results['v5'] else 0}")
        
        # Формируем отчет
        write_log("\n" + "=" * 60)
        write_log("📊 ФОРМИРОВАНИЕ ОТЧЕТА")
        write_log("=" * 60)
        
        response = f"🛡️ **SHADOW DOM - РЕЗУЛЬТАТЫ**\n\n"
        response += f"⏱️ Общее время: {sum(times.values()):.2f}с\n\n"
        
        for key in ['v1', 'v2', 'v3', 'v4', 'v5']:
            data = results.get(key)
            t = times.get(key, 0)
            if data and len(data) > 0:
                response += f"✅ **{key.upper()}** - {len(data)} элементов ({t:.2f}с)\n"
                write_log(f"✅ {key.upper()} - {len(data)} элементов ({t:.2f}с)")
                for i, item in enumerate(data[:2]):
                    if isinstance(item, dict):
                        tag = item.get('tag', item.get('host', 'unknown'))
                        response += f"  └─ {i+1}. {tag}"
                        write_log(f"  └─ {i+1}. {tag}")
                        if item.get('id'):
                            response += f" (id: {item['id']})"
                            write_log(f"     id: {item['id']}")
                        if item.get('childCount') or item.get('children'):
                            count = item.get('childCount', len(item.get('children', [])))
                            response += f" - детей: {count}"
                            write_log(f"     детей: {count}")
                        response += "\n"
            else:
                response += f"❌ **{key.upper()}** - Ничего не найдено ({t:.2f}с)\n"
                write_log(f"❌ {key.upper()} - Ничего не найдено ({t:.2f}с)")
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
            write_log(f"🏆 Лучший вариант: {best.upper()} ({max_count} элементов)")
        else:
            response += "❌ **Ни один вариант не сработал**\n"
            write_log("❌ Ни один вариант не сработал")
        
        write_log("\n" + "=" * 60)
        write_log("✅ ОТЧЕТ СФОРМИРОВАН")
        write_log("=" * 60)
        
        # Сохраняем полные данные в JSON
        json_filename = f"shadow_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump({
                'results': results,
                'times': times,
                'best': best,
                'max_count': max_count,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        write_log(f"📄 Сохранен JSON: {json_filename}")
        
        await send_message_safe(update, response, parse_mode='Markdown')
        
        # Отправляем логи
        log_file.close()
        await update.message.reply_document(
            document=open(log_filename, 'rb'),
            caption=f"📋 Лог выполнения Shadow DOM"
        )
        await update.message.reply_document(
            document=open(json_filename, 'rb'),
            caption=f"📄 Полные данные ({len(results)} вариантов)"
        )
        
        # Скриншот
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Текущая страница")
        
        log_operation_end("shadow_command", "SUCCESS")
        
    except Exception as e:
        log_error(e, "shadow_command")
        log_file.write(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}\n")
        log_file.write(traceback.format_exc())
        log_file.close()
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")
        log_operation_end("shadow_command", "FAILED", str(e))

# ========== /TEST ==========

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное тестирование всех функций с логами"""
    logger.info(f"📩 /test от {update.effective_user.username}")
    log_operation_start("test_command")
    
    log_filename = f"test_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    def write_log(msg):
        log_file.write(f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        log_file.flush()
    
    write_log("=" * 60)
    write_log(f"ПОЛНОЕ ТЕСТИРОВАНИЕ - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    write_log("=" * 60)
    
    await send_message_safe(update, "🧪 Запускаю полное тестирование...")
    write_log("🧪 Начало полного тестирования")
    
    try:
        page = await get_browser()
        if page is None:
            write_log("❌ Браузер не запущен")
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            log_file.close()
            return
        
        results = {
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'times': {}
        }
        
        # 1. Тест execute_js
        await send_message_safe(update, "🔄 Тест 1: execute_js...")
        write_log("🔄 Тест 1: execute_js...")
        start = time.time()
        try:
            result = await execute_js('return document.title;', timeout=5.0)
            results['tests']['execute_js'] = {'status': '✅' if result else '❌', 'result': result}
            write_log(f"✅ execute_js: {result if result else 'None'}")
        except Exception as e:
            results['tests']['execute_js'] = {'status': '❌', 'error': str(e)}
            write_log(f"❌ execute_js: {e}")
        results['times']['execute_js'] = time.time() - start
        
        # 2. Тест Shadow DOM
        await send_message_safe(update, "🔄 Тест 2: Shadow DOM...")
        write_log("🔄 Тест 2: Shadow DOM...")
        results['tests']['shadow'] = {}
        
        for v in ['v1', 'v2', 'v3', 'v4', 'v5']:
            start = time.time()
            func = globals().get(f'shadow_{v}')
            if func:
                try:
                    data = await func(page)
                    count = len(data) if data else 0
                    results['tests']['shadow'][v] = {'status': '✅' if data else '⚠️', 'count': count}
                    write_log(f"  {v.upper()}: {'✅' if data else '⚠️'} ({count} элементов) за {time.time()-start:.2f}с")
                except Exception as e:
                    results['tests']['shadow'][v] = {'status': '❌', 'error': str(e)}
                    write_log(f"  {v.upper()}: ❌ {e}")
            results['times'][f'shadow_{v}'] = time.time() - start
        
        # 3. Тест скриншота
        await send_message_safe(update, "🔄 Тест 3: Скриншот...")
        write_log("🔄 Тест 3: Скриншот...")
        start = time.time()
        try:
            screenshot = await take_screenshot()
            results['tests']['screenshot'] = {'status': '✅' if screenshot else '❌', 'size': len(screenshot) if screenshot else 0}
            write_log(f"✅ Скриншот: {len(screenshot) if screenshot else 0} байт")
            if screenshot:
                await send_photo_safe(update, screenshot, "📸 Тестовый скриншот")
        except Exception as e:
            results['tests']['screenshot'] = {'status': '❌', 'error': str(e)}
            write_log(f"❌ Скриншот: {e}")
        results['times']['screenshot'] = time.time() - start
        
        # 4. Тест кук
        await send_message_safe(update, "🔄 Тест 4: Куки...")
        write_log("🔄 Тест 4: Куки...")
        start = time.time()
        try:
            cookies = await execute_js('return document.cookie;', timeout=5.0)
            results['tests']['cookies'] = {'status': '✅' if cookies else '⚠️', 'length': len(cookies) if cookies else 0}
            write_log(f"✅ Куки: {len(cookies) if cookies else 0} байт")
        except Exception as e:
            results['tests']['cookies'] = {'status': '❌', 'error': str(e)}
            write_log(f"❌ Куки: {e}")
        results['times']['cookies'] = time.time() - start
        
        # 5. Тест URL
        await send_message_safe(update, "🔄 Тест 5: URL...")
        write_log("🔄 Тест 5: URL...")
        start = time.time()
        try:
            url = await execute_js('return window.location.href;', timeout=5.0)
            results['tests']['url'] = {'status': '✅' if url else '❌', 'url': url}
            write_log(f"✅ URL: {url if url else 'None'}")
        except Exception as e:
            results['tests']['url'] = {'status': '❌', 'error': str(e)}
            write_log(f"❌ URL: {e}")
        results['times']['url'] = time.time() - start
        
        # 6. Тест элементов X.com
        await send_message_safe(update, "🔄 Тест 6: Элементы X.com...")
        write_log("🔄 Тест 6: Элементы X.com...")
        start = time.time()
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
            x_elements = await execute_js(js, timeout=5.0)
            results['tests']['x_elements'] = {'status': '✅' if x_elements else '❌', 'data': x_elements}
            write_log(f"✅ X.com элементы: {json.dumps(x_elements) if x_elements else 'None'}")
        except Exception as e:
            results['tests']['x_elements'] = {'status': '❌', 'error': str(e)}
            write_log(f"❌ X.com элементы: {e}")
        results['times']['x_elements'] = time.time() - start
        
        # Итоговый отчет
        results['status'] = 'completed'
        
        total = len(results['tests'])
        success = sum(1 for t in results['tests'].values() if t.get('status') == '✅')
        warning = sum(1 for t in results['tests'].values() if t.get('status') == '⚠️')
        error = sum(1 for t in results['tests'].values() if t.get('status') == '❌')
        
        write_log("\n" + "=" * 60)
        write_log("📊 ИТОГОВЫЙ ОТЧЕТ")
        write_log("=" * 60)
        write_log(f"Всего: {total}, ✅: {success}, ⚠️: {warning}, ❌: {error}")
        
        response = f"🧪 **РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ**\n\n"
        response += f"📊 Всего тестов: {total}\n"
        response += f"✅ Успешно: {success}\n"
        response += f"⚠️ Предупреждений: {warning}\n"
        response += f"❌ Ошибок: {error}\n"
        response += f"⏱️ Общее время: {sum(results['times'].values()):.2f}с\n\n"
        
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
                        write_log(f"  {v.upper()}: {d.get('status', '❌')} ({d.get('count', 0)})")
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
                write_log(f"  {name}: {status}")
        
        # Сохраняем JSON
        json_filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        write_log(f"📄 Сохранен JSON: {json_filename}")
        
        await send_message_safe(update, response, parse_mode='Markdown')
        
        # Отправляем логи
        log_file.close()
        await update.message.reply_document(
            document=open(log_filename, 'rb'),
            caption=f"📋 Полный лог тестирования"
        )
        await update.message.reply_document(
            document=open(json_filename, 'rb'),
            caption=f"📄 Результаты тестирования"
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
            write_log(f"🏆 Лучший Shadow DOM вариант: {best_shadow.upper()} ({best_count} элементов)")
        
        log_operation_end("test_command", "SUCCESS")
        
    except Exception as e:
        log_error(e, "test_command")
        log_file.write(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}\n")
        log_file.write(traceback.format_exc())
        log_file.close()
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")
        log_operation_end("test_command", "FAILED", str(e))

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_photo_safe(update, photo, caption=""):
    try:
        if update.callback_query:
            await update.callback_query.message.reply_photo(photo=photo, caption=caption)
        elif update.message:
            await update.message.reply_photo(photo=photo, caption=caption)
    except Exception as e:
        log_error(e, "send_photo_safe")

async def send_message_safe(update, text, parse_mode=None, reply_markup=None):
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        log_error(e, "send_message_safe")

async def set_cookies_combined(page):
    log_operation_start("set_cookies_combined")
    try:
        for cookie in COOKIES:
            await page.set_cookie(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain', '.x.com'),
                path=cookie.get('path', '/')
            )
        log_step(f"✅ Установлено {len(COOKIES)} кук через Pydoll")
        log_operation_end("set_cookies_combined", "SUCCESS")
        return True
    except Exception as e:
        log_error(e, "set_cookies_combined (Pydoll)")
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
            log_step(f"✅ Установлено {len(COOKIES)} кук через JS")
            log_operation_end("set_cookies_combined", "SUCCESS", "через JS")
            return True
        except Exception as e2:
            log_error(e2, "set_cookies_combined (JS)")
            log_operation_end("set_cookies_combined", "FAILED", str(e2))
            return False

async def emulate_human_login_flow(page):
    log_operation_start("emulate_human_login_flow")
    try:
        await asyncio.sleep(random_delay(1, 3))
        await human_scroll(page, 200)
        await asyncio.sleep(random_delay(0.5, 1.5))
        await page.execute_script('window.scrollTo(0, 0);')
        log_step("✅ Эмуляция завершена")
        log_operation_end("emulate_human_login_flow", "SUCCESS")
    except Exception as e:
        log_error(e, "emulate_human_login_flow")
        log_operation_end("emulate_human_login_flow", "FAILED", str(e))

async def check_login_status_detailed(page):
    log_operation_start("check_login_status_detailed")
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
        result = await execute_js(js_code, timeout=10.0)
        log_step(f"✅ Статус: {result.get('isLoggedIn') if result else 'unknown'}")
        log_operation_end("check_login_status_detailed", "SUCCESS")
        return result
    except Exception as e:
        log_error(e, "check_login_status_detailed")
        log_operation_end("check_login_status_detailed", "FAILED", str(e))
        return {'isLoggedIn': False}

# ========== КОМАНДА ЛОГИН ==========

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /login от {update.effective_user.username}")
    log_operation_start("login_command")
    
    await send_message_safe(update, "🚀 Запускаю браузер...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Не удалось запустить браузер.")
            log_operation_end("login_command", "FAILED", "браузер не запущен")
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
        
        log_operation_end("login_command", "SUCCESS")
        
    except Exception as e:
        log_error(e, "login_command")
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")
        log_operation_end("login_command", "FAILED", str(e))

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
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
        f"📋 Логи: {LOG_FILE}\n\n"
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
    logger.info(f"📩 /screen от {update.effective_user.username}")
    await send_message_safe(update, "📸 Делаю скриншот...")
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Скриншот X.com")
        else:
            await send_message_safe(update, "❌ Не удалось сделать скриншот")
    except Exception as e:
        log_error(e, "screen")
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"📊 **СТАТУС БОТА**\n\n"
    status_text += f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username']:
        status_text += f"👤 @{login_status['username']}\n"
    status_text += f"🕐 {login_status['last_check'] or 'Никогда'}\n\n"
    status_text += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
    status_text += f"📦 Версия: {PYDOLL_VERSION or 'unknown'}\n"
    status_text += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
    status_text += f"🌐 Браузер: {'✅' if pydoll_browser else '❌'}\n"
    status_text += f"🍪 Кук: {len(COOKIES)}\n\n"
    status_text += f"📋 Лог-файл: {LOG_FILE}\n"
    status_text += f"🔄 Текущая операция: {current_operation or 'нет'}"
    
    await send_message_safe(update, status_text, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /close от {update.effective_user.username}")
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
        
        tweets_data = await execute_js(js_tweets, timeout=10.0)
        
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
        log_error(e, "tweets")
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
    except Exception as e:
        log_error(e, "handle_cookies_input")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== ЗАПУСК ==========

def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 60)
    
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
    
    print("\n" + "=" * 60)
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 60)
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Версия: {PYDOLL_VERSION or 'unknown'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print(f"📋 Лог-файл: {LOG_FILE}")
    print("=" * 60)
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
    print("=" * 60)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()