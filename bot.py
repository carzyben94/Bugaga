# bot.py
import os
import sys
import time
import logging
import json
import re
import asyncio
import traceback
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# НАСТРОЙКА ЛОГОВ
# ============================================================

LOGS_DIR = '/app/logs'
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.FileHandler(os.path.join(LOGS_DIR, 'debug.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
debug_logger = logging.getLogger("debug")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, js,
    list_tabs, current_tab, close_tab, switch_tab
)
from browser_harness.admin import ensure_daemon

# ============================================================
# КУКИ (WebSocket)
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    
    async def set_cookies_async():
        """Устанавливает куки через WebSocket CDP"""
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                debug_logger.error("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            debug_logger.info("🔗 Подключаюсь к WebSocket для установки кук...")
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({
                    "id": 1, 
                    "method": "Network.setCookies", 
                    "params": {"cookies": COOKIES}
                }))
                response = json.loads(await ws.recv())
                if "error" in response:
                    debug_logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                debug_logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            debug_logger.error(f"❌ Ошибка установки кук: {e}")
            return False
    
    def set_cookies_global():
        """Синхронная обёртка для установки кук"""
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            debug_logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    debug_logger.warning("⚠️ cookies.py не найден, куки не будут установлены")
    COOKIES = []
    def set_cookies_global():
        debug_logger.warning("⚠️ set_cookies_global вызвана, но cookies.py не найден")
        return False

# ============================================================
# НАСТРОЙКИ
# ============================================================

MAX_TABS = 5
_browser_ok = False
_browser_check_time = 0

# Настройки Z.ai
ZAI_MODELS = {
    "glm-5.2": "GLM-5.2",
    "glm-5.1": "GLM-5.1", 
    "glm-4.5": "GLM-4.5",
    "deepseek-v3": "DeepSeek V3",
    "qwen-2.5": "Qwen 2.5",
    "llama-3.3": "Llama 3.3"
}
_current_model = "glm-5.2"
_search_enabled = False

# ============================================================
# ДЕКОРАТОР ДЛЯ ЛОГИРОВАНИЯ ОШИБОК
# ============================================================

def log_errors(func):
    """Декоратор для логирования всех ошибок в командах"""
    async def wrapper(update, context, *args, **kwargs):
        try:
            debug_logger.debug(f"🚀 Запуск команды: {func.__name__}")
            debug_logger.debug(f"   Пользователь: {update.effective_user.username if update.effective_user else 'unknown'}")
            debug_logger.debug(f"   Чат ID: {update.effective_chat.id if update.effective_chat else 'unknown'}")
            
            result = await func(update, context, *args, **kwargs)
            
            debug_logger.debug(f"✅ Команда {func.__name__} завершена успешно")
            return result
            
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            debug_logger.error(f"❌ ОШИБКА в {func.__name__}: {error_msg}")
            debug_logger.error(f"📋 ТРЕЙС:\n{error_trace}")
            
            try:
                if "cdp_disconnected" in error_msg:
                    await update.message.reply_text(
                        "⚠️ Браузер отключился.\n"
                        "Попробуйте ещё раз через 5 секунд."
                    )
                elif "timed out" in error_msg.lower():
                    await update.message.reply_text(
                        "⏰ Слишком долгий ответ.\n"
                        "Попробуйте упростить запрос или сменить модель."
                    )
                elif "timeout" in error_msg.lower():
                    await update.message.reply_text(
                        "⏰ Слишком долгая загрузка.\n"
                        "Попробуйте ещё раз."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Ошибка: {error_msg[:200]}\n"
                        f"Проверьте логи: /log"
                    )
            except:
                pass
            
            return None
            
    return wrapper

# ============================================================
# ФУНКЦИИ
# ============================================================

def ensure_browser_ready():
    """Проверяет браузер с кешированием (раз в 30 секунд)"""
    global _browser_ok, _browser_check_time
    
    now = time.time()
    if now - _browser_check_time < 30:
        debug_logger.debug(f"🔍 Браузер (кеш): {_browser_ok}")
        return _browser_ok
    
    debug_logger.debug("🔍 Проверка браузера...")
    
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if pages:
            debug_logger.debug("✅ Браузер работает")
            _browser_ok = True
        else:
            debug_logger.warning("⚠️ Браузер не отвечает (пустой ответ), перезапускаю...")
            ensure_daemon()
            time.sleep(3)
            set_cookies_global()
            debug_logger.info("✅ Браузер перезапущен")
            _browser_ok = True
            
    except httpx.ConnectError as e:
        debug_logger.error(f"❌ Не удаётся подключиться к браузеру: {e}")
        debug_logger.info("🔄 Перезапускаю браузер...")
        ensure_daemon()
        time.sleep(3)
        set_cookies_global()
        debug_logger.info("✅ Браузер перезапущен")
        _browser_ok = True
        
    except httpx.TimeoutException as e:
        debug_logger.error(f"❌ Таймаут подключения к браузеру: {e}")
        debug_logger.info("🔄 Перезапускаю браузер...")
        ensure_daemon()
        time.sleep(3)
        set_cookies_global()
        debug_logger.info("✅ Браузер перезапущен")
        _browser_ok = True
        
    except Exception as e:
        debug_logger.error(f"❌ Неизвестная ошибка при проверке браузера: {e}")
        debug_logger.info("🔄 Перезапускаю браузер...")
        ensure_daemon()
        time.sleep(3)
        set_cookies_global()
        debug_logger.info("✅ Браузер перезапущен")
        _browser_ok = True
    
    _browser_check_time = now
    return _browser_ok

def cleanup_tabs():
    """Закрывает лишние вкладки, оставляя максимум MAX_TABS"""
    debug_logger.debug(f"🧹 Очистка вкладок (макс: {MAX_TABS})...")
    
    try:
        tabs = list_tabs()
        if not tabs:
            debug_logger.debug("📭 Нет вкладок")
            return
        
        debug_logger.debug(f"📑 Текущих вкладок: {len(tabs)}")
        current = current_tab()
        
        if len(tabs) > MAX_TABS:
            to_close = tabs[:(len(tabs) - MAX_TABS)]
            debug_logger.info(f"🗑️ Закрываю лишние вкладки: {len(to_close)} шт.")
            for tab in to_close:
                if tab != current:
                    try:
                        close_tab(tab)
                        debug_logger.debug(f"   Закрыта: {tab}")
                    except Exception as e:
                        debug_logger.warning(f"   Не удалось закрыть {tab}: {e}")
            
    except Exception as e:
        debug_logger.error(f"❌ Ошибка очистки вкладок: {e}")

def ensure_tab():
    """Создаёт новую вкладку, если нужно"""
    debug_logger.debug("📂 Создание новой вкладки...")
    
    try:
        try:
            current = current_tab()
            debug_logger.debug(f"   Текущая вкладка: {current}")
        except Exception as e:
            debug_logger.warning(f"   Нет активной вкладки: {e}")
            current = None
        
        tabs = list_tabs()
        debug_logger.debug(f"   Всего вкладок: {len(tabs)}")
        
        if len(tabs) >= MAX_TABS:
            old_tab = tabs[0]
            debug_logger.info(f"🗑️ Достигнут лимит ({MAX_TABS}), закрываю старую: {old_tab}")
            if old_tab != current:
                try:
                    close_tab(old_tab)
                except:
                    pass
            else:
                if len(tabs) > 1:
                    try:
                        close_tab(tabs[1])
                    except:
                        pass
        
        new_tab()
        debug_logger.info("✅ Новая вкладка создана")
        time.sleep(0.5)
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка создания вкладки: {e}")
        traceback.print_exc()
        try:
            new_tab()
            time.sleep(0.5)
            debug_logger.info("✅ Вкладка создана принудительно")
        except Exception as e2:
            debug_logger.error(f"❌ Не удалось создать вкладку: {e2}")

# ============================================================
# КОМАНДЫ
# ============================================================

@log_errors
async def start(update, context):
    debug_logger.debug("📝 /start вызван")
    await update.message.reply_text(
        "🌐 **Браузер бот**\n\n"
        "📌 **Основные команды:**\n"
        "/dom <url> — парсинг DOM\n"
        "/kyiv — погода в Киеве\n\n"
        "🤖 **Z.ai команды:**\n"
        "/zai <запрос> — спросить Z.ai\n"
        "/zai_model — показать доступные модели\n"
        "/zai_model <модель> — сменить модель\n"
        "/zai_search — включить/выключить поиск\n\n"
        "📑 **Вкладки:**\n"
        "/tabs — список вкладок\n"
        "/tab_new — открыть вкладку\n"
        "/tab_close <номер> — закрыть вкладку\n"
        "/tab_switch <номер> — переключить вкладку\n\n"
        "📥 **Логи:**\n"
        "/log — скачать логи\n\n"
        f"📌 Максимум вкладок: {MAX_TABS}",
        parse_mode='Markdown'
    )

@log_errors
async def log(update, context):
    debug_logger.debug("📝 /log вызван")
    try:
        log_files = ['bot.log', 'debug.log']
        for filename in log_files:
            log_file = os.path.join(LOGS_DIR, filename)
            if os.path.exists(log_file):
                with open(log_file, 'rb') as f:
                    await update.message.reply_document(document=f, filename=filename)
        
        await update.message.reply_text("📋 Логи отправлены")
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка отправки логов: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def dom(update, context):
    debug_logger.debug("📝 /dom вызван")
    
    try:
        ensure_browser_ready()
        cleanup_tabs()
        
        if not context.args:
            debug_logger.debug("   Нет аргументов")
            await update.message.reply_text(
                "❌ Укажите URL\n"
                "Пример: /dom https://example.com"
            )
            return

        url = context.args[0].strip()
        debug_logger.debug(f"   URL: {url}")
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            debug_logger.debug(f"   Добавлен https: {url}")

        status_msg = await update.message.reply_text(f"🌐 Открываю {url}...")
        debug_logger.debug("   Статус сообщение отправлено")

        try:
            ensure_tab()
            debug_logger.debug("   Вкладка создана")
            
            debug_logger.debug(f"   Переход на {url}")
            goto_url(url)
            debug_logger.debug("   goto_url выполнен")
            
            debug_logger.debug("   Ожидание загрузки...")
            wait_for_load(timeout=60)
            debug_logger.debug("   Страница загружена")
            
            await status_msg.edit_text("✅ Страница загружена, парсинг...")
            debug_logger.debug("   Статус обновлён")
            
        except Exception as e:
            error_msg = str(e)
            debug_logger.error(f"❌ Ошибка загрузки: {error_msg}")
            debug_logger.error(traceback.format_exc())
            
            if "cdp_disconnected" in error_msg:
                await status_msg.edit_text("⚠️ Браузер отключился, перезапускаю...")
                debug_logger.info("🔄 Перезапуск браузера...")
                ensure_daemon()
                time.sleep(3)
                set_cookies_global()
                debug_logger.info("   Браузер перезапущен")
                
                try:
                    debug_logger.debug("   Повторная попытка...")
                    ensure_tab()
                    goto_url(url)
                    wait_for_load(timeout=60)
                    await status_msg.edit_text("✅ Страница загружена, парсинг...")
                    debug_logger.info("   Повторная попытка успешна")
                except Exception as e2:
                    debug_logger.error(f"❌ Повторная попытка не удалась: {e2}")
                    debug_logger.error(traceback.format_exc())
                    await status_msg.edit_text(f"❌ Ошибка: {str(e2)[:200]}")
                    return
            else:
                await status_msg.edit_text(f"❌ Ошибка загрузки: {error_msg[:200]}")
                return

        debug_logger.debug("📊 Выполнение JavaScript...")
        js_code = """
        const elements = { buttons: [], inputs: [], links: [], forms: [], selects: [], textareas: [], divs: [], spans: [], lis: [], others: [] };
        const selectors = ['button', 'input:not([type="hidden"])', 'a[href]', 'form', 'select', 'textarea', '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]', '[contenteditable="true"]'];
        const all = new Set(document.querySelectorAll(selectors.join(',')));
        document.querySelectorAll('[onclick], [data-testid], [data-test], [data-cy], [data-qa]').forEach(el => all.add(el));
        
        for (const el of all) {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim() || '',
                value: el.value || '',
                placeholder: el.placeholder || '',
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                className: el.className || '',
                href: el.href || '',
                src: el.src || '',
                alt: el.alt || '',
                title: el.title || '',
                disabled: el.disabled || false,
                readonly: el.readOnly || false,
                required: el.required || false,
                checked: el.checked || false,
                selected: el.selected || false,
                visible: el.offsetParent !== null,
                attributes: {},
                dataAttributes: {}
            };
            for (const attr of el.attributes) {
                info.attributes[attr.name] = attr.value;
                if (attr.name.startsWith('data-')) info.dataAttributes[attr.name] = attr.value;
            }
            const tag = info.tag;
            if (tag === 'button' || (el.hasAttribute('role') && el.getAttribute('role') === 'button')) {
                elements.buttons.push(info);
            } else if (tag === 'input') {
                elements.inputs.push(info);
            } else if (tag === 'a') {
                elements.links.push(info);
            } else if (tag === 'form') {
                elements.forms.push(info);
            } else if (tag === 'select') {
                elements.selects.push(info);
            } else if (tag === 'textarea') {
                elements.textareas.push(info);
            } else if (tag === 'div') {
                elements.divs.push(info);
            } else if (tag === 'span') {
                elements.spans.push(info);
            } else if (tag === 'li') {
                elements.lis.push(info);
            } else {
                elements.others.push(info);
            }
        }
        return JSON.stringify({ page: { url: window.location.href, title: document.title, timestamp: Date.now() }, elements: elements }, null, 2);
        """

        debug_logger.debug("   Выполнение JS...")
        result = js(js_code)
        debug_logger.debug(f"   JS выполнен, результат: {len(result) if result else 0} символов")

        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные DOM")
            return

        try:
            dom_data = json.loads(result)
            debug_logger.debug(f"   JSON распарсен, элементов: {sum(len(v) for v in dom_data.get('elements', {}).values())}")
        except Exception as e:
            debug_logger.error(f"❌ Ошибка парсинга JSON: {e}")
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return

        timestamp = int(time.time())
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        filename = f"dom_{domain}_{timestamp}.json"
        file_path = os.path.join(LOGS_DIR, filename)

        debug_logger.debug(f"   Сохранение в {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(dom_data, f, ensure_ascii=False, indent=2)
        debug_logger.debug("   Файл сохранён")

        with open(file_path, 'rb') as f:
            await status_msg.edit_text("📄 Отправляю JSON...")
            debug_logger.debug("   Отправка документа...")
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 DOM страницы\nURL: {dom_data.get('page', {}).get('url', 'unknown')}"
            )
            debug_logger.debug("   Документ отправлен")

        elements = dom_data.get('elements', {})
        stats = "📊 Статистика DOM:\n\n"
        total = 0
        for key, value in elements.items():
            if value:
                count = len(value)
                total += count
                stats += f"• {key}: {count}\n"
        stats += f"\nВсего: {total}"

        await update.message.reply_text(stats)
        debug_logger.debug("   Статистика отправлена")

        try:
            os.remove(file_path)
            debug_logger.debug("   Временный файл удалён")
        except:
            pass

        debug_logger.info(f"✅ /dom завершён успешно для {url}")

    except Exception as e:
        debug_logger.error(f"❌ Критическая ошибка в /dom: {e}")
        debug_logger.error(traceback.format_exc())
        raise

@log_errors
async def kyiv(update, context):
    debug_logger.debug("📝 /kyiv вызван")
    
    try:
        ensure_browser_ready()
        cleanup_tabs()
        
        status_msg = await update.message.reply_text("🌤️ Открываю погоду в Киеве...")
        debug_logger.debug("   Статус сообщение отправлено")

        try:
            ensure_tab()
            debug_logger.debug("   Вкладка создана")
            
            debug_logger.debug("   Переход на sinoptik.ua...")
            goto_url("https://sinoptik.ua/pohoda/kyiv")
            debug_logger.debug("   goto_url выполнен")
            
            debug_logger.debug("   Ожидание загрузки...")
            wait_for_load(timeout=60)
            debug_logger.debug("   Страница загружена")
            
            await status_msg.edit_text("📊 Парсинг погоды...")
            
        except Exception as e:
            error_msg = str(e)
            debug_logger.error(f"❌ Ошибка загрузки: {error_msg}")
            debug_logger.error(traceback.format_exc())
            
            if "cdp_disconnected" in error_msg:
                await status_msg.edit_text("⚠️ Браузер отключился, перезапускаю...")
                debug_logger.info("🔄 Перезапуск браузера...")
                ensure_daemon()
                time.sleep(3)
                set_cookies_global()
                debug_logger.info("   Браузер перезапущен")
                
                try:
                    debug_logger.debug("   Повторная попытка...")
                    ensure_tab()
                    goto_url("https://sinoptik.ua/pohoda/kyiv")
                    wait_for_load(timeout=60)
                    await status_msg.edit_text("📊 Парсинг погоды...")
                    debug_logger.info("   Повторная попытка успешна")
                except Exception as e2:
                    debug_logger.error(f"❌ Повторная попытка не удалась: {e2}")
                    debug_logger.error(traceback.format_exc())
                    await status_msg.edit_text(f"❌ Ошибка: {str(e2)[:200]}")
                    return
            else:
                await status_msg.edit_text(f"❌ Ошибка загрузки: {error_msg[:200]}")
                return

        debug_logger.debug("📊 Выполнение JavaScript...")
        js_code = """
        const days = [];
        const links = document.querySelectorAll('a.tkK415TH');
        for (const link of links) {
            const text = link.textContent?.trim();
            if (text) {
                days.push(text);
            }
        }
        return JSON.stringify(days);
        """

        result = js(js_code)
        debug_logger.debug(f"   JS выполнен, результат: {len(result) if result else 0} символов")

        if not result:
            await status_msg.edit_text("❌ Не удалось получить погоду")
            return

        try:
            days = json.loads(result)
            debug_logger.debug(f"   Парсинг завершён, дней: {len(days)}")
        except Exception as e:
            debug_logger.error(f"❌ Ошибка парсинга JSON: {e}")
            await status_msg.edit_text("❌ Ошибка парсинга")
            return

        if not days:
            await status_msg.edit_text("📭 Данные о погоде не найдены")
            return

        response = "🌤️ **Погода в Киеве**\n\n"

        days_uk = {
            "вівторок": "Вівторок",
            "середа": "Середа",
            "четвер": "Четвер",
            "пʼятниця": "П'ятниця",
            "субота": "Субота",
            "неділя": "Неділя",
            "понеділок": "Понеділок"
        }

        for day in days[:7]:
            match = re.search(r'([а-яіїєґ\']+)(\d+[а-я]+)мін\.([+-]?\d+°)макс\.([+-]?\d+°)', day)
            if match:
                day_raw = match.group(1)
                date = match.group(2)
                min_temp = match.group(3)
                max_temp = match.group(4)

                day_name = days_uk.get(day_raw, day_raw.capitalize())
                date_formatted = re.sub(r'(\d+)([а-я]+)', r'\1 \2', date)

                response += f"**{day_name}** {date_formatted}: {min_temp} / {max_temp}\n"

        debug_logger.debug("   Вкладка оставлена открытой")

        await status_msg.edit_text(response, parse_mode='Markdown')
        debug_logger.info("✅ /kyiv завершён успешно")

    except Exception as e:
        debug_logger.error(f"❌ Критическая ошибка в /kyiv: {e}")
        debug_logger.error(traceback.format_exc())
        raise

@log_errors
async def zai(update, context):
    """Отправляет запрос к Z.ai с текущей моделью"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Напишите запрос для Z.ai\n"
                "Пример: /zai Привет, как дела?\n\n"
                f"📌 Текущая модель: `{_current_model}`\n"
                f"🔍 Поиск в сети: {'✅ Включен' if _search_enabled else '❌ Выключен'}\n\n"
                "📌 Команды:\n"
                "/zai_model <модель> — сменить модель\n"
                "/zai_search — включить/выключить поиск",
                parse_mode='Markdown'
            )
            return

        query = " ".join(context.args)
        debug_logger.debug(f"📝 /zai запрос: {query[:100]}...")

        ensure_browser_ready()
        cleanup_tabs()

        status_msg = await update.message.reply_text(f"🤖 Отправляю запрос к Z.ai...")
        debug_logger.debug(f"   Модель: {_current_model}, Поиск: {_search_enabled}")

        try:
            ensure_tab()
            
            # Проверяем, открыта ли уже страница Z.ai
            try:
                test_url = js("return window.location.href;")
                debug_logger.debug(f"   Текущий URL: {test_url}")
                if "chat.z.ai" not in str(test_url):
                    debug_logger.info("   Переход на chat.z.ai...")
                    goto_url("https://chat.z.ai/")
                    wait_for_load(timeout=60)
            except:
                debug_logger.info("   Переход на chat.z.ai...")
                goto_url("https://chat.z.ai/")
                wait_for_load(timeout=60)
                
            debug_logger.debug("✅ Страница Z.ai загружена")
            
            # Дополнительная пауза для полной загрузки страницы
            await asyncio.sleep(3)

            await status_msg.edit_text("✍️ Ввожу запрос...")

            # Экранируем кавычки в запросе
            query_escaped = query[:500].replace("'", "\\'").replace('"', '\\"')
            
            # === JS КОД С ТАЙМАУТАМИ ===
            js_code = f"""
            (async function() {{
                const query = '{query_escaped}';
                const model = '{_current_model}';
                const searchEnabled = {str(_search_enabled).lower()};
                
                // Функция для ожидания элемента
                function waitForElement(selector, timeout = 10000) {{
                    return new Promise((resolve) => {{
                        if (document.querySelector(selector)) {{
                            resolve(document.querySelector(selector));
                            return;
                        }}
                        const observer = new MutationObserver(() => {{
                            const el = document.querySelector(selector);
                            if (el) {{
                                observer.disconnect();
                                resolve(el);
                            }}
                        }});
                        observer.observe(document.body, {{ childList: true, subtree: true }});
                        setTimeout(() => {{
                            observer.disconnect();
                            resolve(null);
                        }}, timeout);
                    }});
                }}
                
                // Функция для ожидания кнопки
                function waitForButton(selector, timeout = 10000) {{
                    return new Promise((resolve) => {{
                        const btn = document.querySelector(selector);
                        if (btn && !btn.disabled) {{
                            resolve(btn);
                            return;
                        }}
                        const observer = new MutationObserver(() => {{
                            const btn = document.querySelector(selector);
                            if (btn && !btn.disabled) {{
                                observer.disconnect();
                                resolve(btn);
                            }}
                        }});
                        observer.observe(document.body, {{ attributes: true, childList: true, subtree: true }});
                        setTimeout(() => {{
                            observer.disconnect();
                            resolve(null);
                        }}, timeout);
                    }});
                }}
                
                try {{
                    // 1. Смена модели
                    if (model) {{
                        const modelSelector = document.querySelector('#model-selector-glm-5_2-button');
                        if (modelSelector) {{
                            modelSelector.click();
                            await new Promise(r => setTimeout(r, 1000));
                            
                            const modelItems = document.querySelectorAll('[role="menuitemradio"]');
                            for (const item of modelItems) {{
                                const text = item.textContent?.trim() || '';
                                if (text.toLowerCase().includes(model.toLowerCase()) || 
                                    text.includes(model)) {{
                                    item.click();
                                    await new Promise(r => setTimeout(r, 1000));
                                    break;
                                }}
                            }}
                        }}
                    }}
                    
                    // 2. Включаем/выключаем поиск
                    if (searchEnabled !== undefined) {{
                        const searchToggle = document.querySelector('[aria-label*="search"], [aria-label*="Search"], button[data-search]');
                        if (searchToggle) {{
                            const isActive = searchToggle.getAttribute('data-active') === 'true';
                            if (isActive !== searchEnabled) {{
                                searchToggle.click();
                                await new Promise(r => setTimeout(r, 1000));
                            }}
                        }}
                    }}
                    
                    // 3. Ждём поле ввода и вводим запрос
                    const input = await waitForElement('#chat-input', 15000);
                    if (!input) return '❌ Поле ввода не найдено';
                    
                    input.value = '';
                    input.focus();
                    
                    // Вводим текст посимвольно с задержкой
                    for (let i = 0; i < query.length; i++) {{
                        input.value += query[i];
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        await new Promise(r => setTimeout(r, 3));
                    }}
                    
                    // 4. Ждём кнопку отправки
                    const sendBtn = await waitForButton('#send-message-button', 15000);
                    if (!sendBtn) return '❌ Кнопка отправки не найдена';
                    
                    sendBtn.click();
                    
                    // 5. Ждём ответ (увеличенный таймаут до 120 секунд)
                    await new Promise(resolve => {{
                        let lastText = '';
                        let attempts = 0;
                        const maxAttempts = 120; // 120 секунд
                        
                        const checkResponse = () => {{
                            attempts++;
                            const messages = document.querySelectorAll('[data-message-role="assistant"]');
                            if (messages.length > 0) {{
                                const lastMsg = messages[messages.length - 1];
                                const text = lastMsg.textContent?.trim() || '';
                                if (text && text.length > 10 && text !== lastText) {{
                                    lastText = text;
                                    if (text.length > 100 || attempts > 30) {{
                                        resolve();
                                        return;
                                    }}
                                }}
                            }}
                            if (attempts >= maxAttempts) {{
                                resolve();
                            }} else {{
                                setTimeout(checkResponse, 1000);
                            }}
                        }};
                        checkResponse();
                    }});
                    
                    // 6. Получаем ответ
                    const messages = document.querySelectorAll('[data-message-role="assistant"]');
                    if (messages.length === 0) return '⏰ Ответ не получен';
                    
                    const lastMsg = messages[messages.length - 1];
                    const text = lastMsg.textContent?.trim() || 'Пустой ответ';
                    
                    return text;
                    
                }} catch(e) {{
                    return '❌ Ошибка: ' + e.message;
                }}
            }})();
            """

            debug_logger.debug("📤 Отправка запроса...")
            
            # Увеличиваем таймаут выполнения JS до 180 секунд
            result = js(js_code, timeout=180)
            debug_logger.debug(f"📥 Получен ответ: {len(result) if result else 0} символов")

            if not result:
                await status_msg.edit_text("❌ Не удалось получить ответ от Z.ai")
                return

            if result.startswith("❌"):
                await status_msg.edit_text(result)
                return

            if len(result) > 4000:
                result = result[:3900] + "\n\n... (ответ обрезан)"

            header = f"🤖 **Z.ai ответ**\n"
            header += f"📌 Модель: `{_current_model}`\n"
            header += f"🔍 Поиск: {'✅ Включен' if _search_enabled else '❌ Выключен'}\n\n"
            
            await status_msg.edit_text(header + result, parse_mode='Markdown')

        except Exception as e:
            error_msg = str(e)
            debug_logger.error(f"❌ Ошибка в /zai: {error_msg}")
            
            if "timed out" in error_msg:
                await status_msg.edit_text(
                    "⏰ AI долго думает... Попробуйте:\n"
                    "1. Упростить запрос\n"
                    "2. Сменить модель (/zai_model deepseek-v3)\n"
                    "3. Попробовать ещё раз через 10 секунд"
                )
            else:
                await status_msg.edit_text(f"❌ Ошибка: {error_msg[:200]}")

    except Exception as e:
        debug_logger.error(f"❌ Критическая ошибка в /zai: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def zai_model(update, context):
    """Сменить модель Z.ai"""
    global _current_model
    
    try:
        if not context.args:
            models_list = "\n".join([f"  • `{k}` — {v}" for k, v in ZAI_MODELS.items()])
            await update.message.reply_text(
                f"📌 **Доступные модели:**\n\n{models_list}\n\n"
                f"Текущая: `{_current_model}`\n\n"
                f"Пример: `/zai_model glm-5.1`\n"
                f"Пример: `/zai_model deepseek-v3`",
                parse_mode='Markdown'
            )
            return

        model = context.args[0].strip().lower()
        
        if model not in ZAI_MODELS:
            found = None
            for key in ZAI_MODELS:
                if model in key or key in model:
                    found = key
                    break
            
            if found:
                model = found
            else:
                await update.message.reply_text(
                    f"❌ Модель `{model}` не найдена\n\n"
                    f"Доступные модели:\n" + "\n".join([f"  • `{k}` — {v}" for k, v in ZAI_MODELS.items()]),
                    parse_mode='Markdown'
                )
                return
        
        _current_model = model
        await update.message.reply_text(
            f"✅ Модель изменена на: `{ZAI_MODELS[model]}`\n"
            f"Теперь все запросы будут использовать эту модель.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /zai_model: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def zai_search(update, context):
    """Включить/выключить поиск в сети"""
    global _search_enabled
    
    try:
        _search_enabled = not _search_enabled
        status = "✅ Включен" if _search_enabled else "❌ Выключен"
        
        await update.message.reply_text(
            f"🔍 Поиск в сети: {status}\n\n"
            f"Теперь все запросы будут {'с поиском в интернете' if _search_enabled else 'без поиска в интернете'}.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /zai_search: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def tabs(update, context):
    debug_logger.debug("📝 /tabs вызван")
    
    try:
        ensure_browser_ready()
        
        try:
            tab_list = list_tabs()
            debug_logger.debug(f"   Вкладок: {len(tab_list)}")
        except RuntimeError as e:
            if "cdp_disconnected" in str(e):
                debug_logger.warning("⚠️ CDP отключился, перезапускаю браузер...")
                ensure_daemon()
                time.sleep(3)
                set_cookies_global()
                ensure_browser_ready()
                tab_list = list_tabs()
                debug_logger.debug(f"   Вкладок после перезапуска: {len(tab_list)}")
            else:
                raise
        
        if not tab_list:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return

        try:
            current = current_tab()
        except RuntimeError as e:
            if "cdp_disconnected" in str(e):
                debug_logger.warning("⚠️ CDP отключился при получении текущей вкладки")
                ensure_daemon()
                time.sleep(3)
                set_cookies_global()
                ensure_browser_ready()
                current = current_tab()
            else:
                raise
        
        response = f"📑 Список вкладок ({len(tab_list)}/{MAX_TABS}):\n\n"
        for i, tab in enumerate(tab_list, 1):
            if tab == current:
                response += f"✅ {i}. {tab} (текущая)\n"
            else:
                response += f"🔲 {i}. {tab}\n"

        response += "\n/tab_new - открыть новую\n/tab_close <номер> - закрыть\n/tab_switch <номер> - переключиться"
        await update.message.reply_text(response)
        debug_logger.info("✅ /tabs завершён")
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /tabs: {e}")
        debug_logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def tab_new(update, context):
    debug_logger.debug("📝 /tab_new вызван")
    
    try:
        ensure_browser_ready()
        cleanup_tabs()
        ensure_tab()
        
        tabs_count = len(list_tabs())
        await update.message.reply_text(f"✅ Новая вкладка открыта (всего: {tabs_count}/{MAX_TABS})")
        debug_logger.info(f"✅ /tab_new завершён, вкладок: {tabs_count}")
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /tab_new: {e}")
        debug_logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def tab_close(update, context):
    debug_logger.debug("📝 /tab_close вызван")
    
    try:
        ensure_browser_ready()
        
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_close 1")
            return

        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return

        tabs_list = list_tabs()
        debug_logger.debug(f"   Вкладок: {len(tabs_list)}, запрошен: {tab_num + 1}")
        
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return

        tab_id = tabs_list[tab_num]
        current = current_tab()

        if tab_id == current and len(tabs_list) > 1:
            await update.message.reply_text("❌ Нельзя закрыть текущую вкладку")
            return

        close_tab(tab_id)
        await update.message.reply_text(f"✅ Вкладка {tab_num + 1} закрыта")
        debug_logger.info(f"✅ /tab_close завершён, закрыта вкладка {tab_num + 1}")
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /tab_close: {e}")
        debug_logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

@log_errors
async def tab_switch(update, context):
    debug_logger.debug("📝 /tab_switch вызван")
    
    try:
        ensure_browser_ready()
        
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_switch 2")
            return

        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return

        tabs_list = list_tabs()
        debug_logger.debug(f"   Вкладок: {len(tabs_list)}, запрошен: {tab_num + 1}")
        
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return

        switch_tab(tabs_list[tab_num])
        await update.message.reply_text(f"✅ Переключился на вкладку {tab_num + 1}")
        debug_logger.info(f"✅ /tab_switch завершён, переключён на {tab_num + 1}")
        
    except Exception as e:
        debug_logger.error(f"❌ Ошибка в /tab_switch: {e}")
        debug_logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    debug_logger.info("=" * 60)
    debug_logger.info("🚀 ЗАПУСК БОТА")
    debug_logger.info(f"   Время: {datetime.now()}")
    debug_logger.info("=" * 60)
    
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_TOKEN:
        debug_logger.error("❌ TELEGRAM_BOT_TOKEN не задан!")
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

    debug_logger.info("📡 Запуск браузера...")
    os.environ["BU_CDP_URL"] = "http://localhost:9222"
    ensure_daemon()
    debug_logger.info("✅ Браузер готов")
    
    debug_logger.info("🍪 Установка кук...")
    set_cookies_global()

    debug_logger.info("📡 Создание приложения...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom))
    app.add_handler(CommandHandler("kyiv", kyiv))
    
    # Z.ai команды
    app.add_handler(CommandHandler("zai", zai))
    app.add_handler(CommandHandler("zai_model", zai_model))
    app.add_handler(CommandHandler("zai_search", zai_search))
    
    # Управление вкладками
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    
    # Логи
    app.add_handler(CommandHandler("log", log))

    debug_logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()