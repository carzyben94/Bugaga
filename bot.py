# bot.py
import os
import sys
import stat
import time
import logging
import base64
import re
import asyncio
import io
import json
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image

warnings.filterwarnings("ignore")

agent_workspace = "/app/browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)

helpers_file = os.path.join(agent_workspace, "agent_helpers.py")
os.makedirs(agent_workspace, exist_ok=True)
if not os.path.exists(helpers_file):
    with open(helpers_file, "w") as f:
        f.write('"""Agent-editable browser helpers."""\n')
os.chmod(agent_workspace, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
os.chmod(helpers_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

os.environ["BH_DOMAIN_SKILLS"] = "1"
os.environ["BH_AGENT_WORKSPACE"] = "/app/browser-harness/agent-workspace"

LOGS_DIR = '/app/logs'
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)
logger.info(f"✅ agent_workspace: {agent_workspace}")
logger.info(f"✅ helpers_file: {helpers_file}")
logger.info(f"✅ screenshots_dir: {SCREENSHOTS_DIR}")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
)
from browser_harness.admin import ensure_daemon

# ============================================================
# КУКИ (WebSocket)
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    import json
    
    async def set_cookies_async():
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            logger.info("🔗 Подключаюсь к WebSocket...")
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Network.setCookies", "params": {"cookies": COOKIES}}))
                response = json.loads(await ws.recv())
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def set_cookies_global():
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    logger.warning("⚠️ websockets не установлен")
    COOKIES = []
    def set_cookies_global():
        return False

# ============================================================
# НАСТРОЙКА РАЗМЕРА ОКНА (WebSocket)
# ============================================================

async def set_viewport_async():
    try:
        import httpx
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            logger.warning("⚠️ Нет активных вкладок для установки размера")
            return False
        ws_url = pages[0]["webSocketDebuggerUrl"]
        logger.info("🔗 Подключаюсь к WebSocket для установки размера...")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": 1280,
                    "height": 720,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                    "screenWidth": 1280,
                    "screenHeight": 720,
                    "positionX": 0,
                    "positionY": 0
                }
            }))
            response = json.loads(await ws.recv())
            if "error" in response:
                logger.warning(f"⚠️ CDP ошибка: {response['error']}")
                return False
            logger.info("✅ Размер окна установлен: 1280x720")
            return True
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

def set_viewport_global():
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

set_cookies_global()
set_viewport_global()

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    """Отправить файл навыка в GitHub по правильному пути."""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан, навык не будет отправлен в GitHub")
        return False

    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = f"browser-harness/agent-workspace/domain-skills/{host}/{filename}"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    # Проверяем, существует ли уже файл (чтобы получить его SHA для обновления)
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        else:
            sha = None
    except Exception:
        sha = None

    data = {
        "message": f"Добавлен/обновлён навык {filename} для {host}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Навык отправлен в GitHub: {file_path}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в GitHub: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке в GitHub: {e}")
        return False

# ============================================================
# DOM ПАРСЕР
# ============================================================

def parse_dom():
    """Парсит DOM страницы и возвращает JSON со всеми интерактивными элементами"""
    try:
        # JavaScript для сбора всех элементов
        js_code = """
        function getElementInfo(el) {
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
                xpath: '',
                cssSelector: '',
                attributes: {},
                dataAttributes: {}
            };
            
            // XPath
            try {
                const xpath = document.evaluate(
                    './/' + info.tag + 
                    (info.id ? '[@id="' + info.id + '"]' : '') +
                    (info.name ? '[@name="' + info.name + '"]' : '') +
                    (info.className ? '[contains(@class, "' + info.className.split(' ')[0] + '")]' : ''),
                    document.documentElement,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                if (xpath.singleNodeValue) {
                    info.xpath = './/' + info.tag + 
                        (info.id ? '[@id="' + info.id + '"]' : '') +
                        (info.name ? '[@name="' + info.name + '"]' : '') +
                        (info.className ? '[contains(@class, "' + info.className.split(' ')[0] + '")]' : '');
                }
            } catch(e) {}
            
            // CSS Selector
            try {
                if (info.id) {
                    info.cssSelector = '#' + info.id;
                } else if (info.className) {
                    info.cssSelector = info.tag + '.' + info.className.split(' ').filter(c => c).join('.');
                } else if (info.name) {
                    info.cssSelector = info.tag + '[name="' + info.name + '"]';
                } else {
                    info.cssSelector = info.tag;
                }
            } catch(e) {}
            
            // Все атрибуты
            for (const attr of el.attributes) {
                const name = attr.name;
                const value = attr.value;
                info.attributes[name] = value;
                
                // Собираем data-* атрибуты отдельно
                if (name.startsWith('data-')) {
                    info.dataAttributes[name] = value;
                }
            }
            
            // ARIA атрибуты
            const ariaAttrs = ['aria-label', 'aria-describedby', 'aria-labelledby', 
                              'aria-hidden', 'aria-disabled', 'aria-required', 
                              'aria-checked', 'aria-selected', 'aria-expanded'];
            for (const attr of ariaAttrs) {
                if (el.hasAttribute(attr)) {
                    info.attributes[attr] = el.getAttribute(attr);
                }
            }
            
            // Специальные атрибуты для тестирования
            const testAttrs = ['data-testid', 'data-test', 'data-cy', 'data-qa', 
                              'data-test-id', 'testid', 'test-id'];
            for (const attr of testAttrs) {
                if (el.hasAttribute(attr)) {
                    info.attributes[attr] = el.getAttribute(attr);
                }
            }
            
            return info;
        }
        
        // Собираем элементы
        const elements = {
            buttons: [],
            inputs: [],
            links: [],
            forms: [],
            selects: [],
            textareas: [],
            divs: [],
            spans: [],
            lis: [],
            others: []
        };
        
        // Все интерактивные элементы
        const selectors = [
            'button',
            'input:not([type="hidden"])',
            'a[href]',
            'form',
            'select',
            'textarea',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[contenteditable="true"]'
        ];
        
        const allElements = document.querySelectorAll(selectors.join(','));
        const extraSet = new Set(allElements);
        
        // Дополнительные элементы с onclick или data-* атрибутами
        const extraElements = document.querySelectorAll('[onclick], [data-testid], [data-test], [data-cy], [data-qa]');
        for (const el of extraElements) {
            if (!extraSet.has(el)) {
                extraSet.add(el);
            }
        }
        
        const finalElements = Array.from(extraSet);
        
        for (const el of finalElements) {
            const info = getElementInfo(el);
            const tag = info.tag;
            
            if (tag === 'button' || el.hasAttribute('role') && el.getAttribute('role') === 'button') {
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
        
        // Информация о странице
        const pageInfo = {
            url: window.location.href,
            title: document.title,
            timestamp: Date.now()
        };
        
        return JSON.stringify({ page: pageInfo, elements: elements }, null, 2);
        """
        
        result = js(js_code)
        return result, None
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга DOM: {e}")
        return None, str(e)

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузер:\n"
        "/dom <url> — парсинг DOM страницы\n"
        "/tabs — список вкладок\n"
        "/tab_new — открыть новую вкладку\n"
        "/tab_close <номер> — закрыть вкладку\n"
        "/tab_switch <номер> — переключить вкладку\n"
        "/log — скачать логи"
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log', caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dom(update, context):
    """Парсит DOM указанной страницы"""
    try:
        # Проверяем аргументы
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите URL\n"
                "Пример: /dom https://example.com\n"
                "Пример: /dom x.com"
            )
            return
        
        url = context.args[0].strip()
        
        # Добавляем https:// если нет протокола
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        status_msg = await update.message.reply_text(f"🌐 Открываю {url}...")
        
        # Открываем страницу
        try:
            new_tab()
            goto_url(url)
            wait_for_load(timeout=30)
            await status_msg.edit_text(f"✅ Страница загружена, парсинг...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        # Парсим DOM
        result, error = parse_dom()
        
        if error:
            await status_msg.edit_text(f"❌ Ошибка парсинга: {error}")
            return
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные DOM")
            return
        
        # Парсим JSON для проверки
        try:
            dom_data = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        # Сохраняем JSON в файл
        timestamp = int(time.time())
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        filename = f"dom_{domain}_{timestamp}.json"
        file_path = os.path.join(LOGS_DIR, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(dom_data, f, ensure_ascii=False, indent=2)
        
        # Отправляем JSON как документ
        with open(file_path, 'rb') as f:
            await status_msg.edit_text("📄 Отправляю JSON...")
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 DOM страницы\nURL: {dom_data.get('page', {}).get('url', 'unknown')}\nЭлементов: {sum(len(v) for v in dom_data.get('elements', {}).values())}"
            )
        
        # Отправляем статистику
        elements = dom_data.get('elements', {})
        stats = "📊 **Статистика DOM:**\n\n"
        total = 0
        for key, value in elements.items():
            if value:
                count = len(value)
                total += count
                stats += f"• {key}: {count}\n"
        stats += f"\n**Всего: {total}**"
        
        await update.message.reply_text(stats, parse_mode='Markdown')
        
        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass
            
    except Exception as e:
        logger.error(f"❌ Ошибка в /dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def kalshi(update, context):
    """Парсит последние 5 постов Kalshi"""
    try:
        status_msg = await update.message.reply_text("🔍 Открываю Kalshi...")
        
        # Открываем страницу Kalshi
        try:
            # Закрываем все старые вкладки кроме текущей
            tabs = list_tabs()
            for tab in tabs:
                if tab != current_tab():
                    try:
                        close_tab(tab)
                    except:
                        pass
            
            # Создаем новую вкладку
            new_tab()
            
            # Небольшая пауза перед переходом
            await asyncio.sleep(1)
            
            goto_url("https://x.com/Kalshi")
            wait_for_load(timeout=30)
            
            # Ждем и скроллим для подгрузки постов
            await asyncio.sleep(3)
            
            # Много скроллов для подгрузки
            for _ in range(8):
                scroll(0, 600)
                await asyncio.sleep(1.5)
            
            await status_msg.edit_text("✅ Страница загружена, парсинг постов...")
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        # JavaScript для парсинга постов
        js_code = """
        const posts = [];
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        
        console.log('Найдено постов:', articles.length);
        
        for (const article of articles) {
            try {
                const textEl = article.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent.trim() : '';
                
                // Берем только имя без @ и времени
                const nameEl = article.querySelector('[data-testid="User-Name"]');
                let name = 'Kalshi';
                if (nameEl) {
                    const fullName = nameEl.textContent.trim();
                    // Берем только то, что до @
                    const nameParts = fullName.split('@');
                    name = nameParts[0].trim();
                }
                
                const replyEl = article.querySelector('[data-testid="reply"]');
                const replies = replyEl ? replyEl.textContent.trim() : '0';
                
                const retweetEl = article.querySelector('[data-testid="retweet"]');
                const retweets = retweetEl ? retweetEl.textContent.trim() : '0';
                
                const likeEl = article.querySelector('[data-testid="like"]');
                const likes = likeEl ? likeEl.textContent.trim() : '0';
                
                posts.push({
                    text: text,
                    name: name,
                    replies: replies,
                    retweets: retweets,
                    likes: likes
                });
            } catch(e) {}
        }
        
        return JSON.stringify(posts);
        """
        
        result = js(js_code)
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить посты")
            return
        
        try:
            posts = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        if not posts:
            await status_msg.edit_text("📭 Постов не найдено. Попробуйте позже.")
            return
        
        # Берем первые 5 постов
        posts = posts[:5]
        
        # Формируем ответ
        response = f"📊 **Kalshi — последние 5 постов**\n\n"
        
        for i, post in enumerate(posts, 1):
            response += f"**{i}.** {post.get('name', 'Kalshi')}\n"
            response += f"💬 {post.get('replies', '0')} | 🔄 {post.get('retweets', '0')} | ❤️ {post.get('likes', '0')}\n"
            response += f"📝 {post.get('text', '')[:300]}"
            if len(post.get('text', '')) > 300:
                response += "..."
            response += "\n\n"
        
        await status_msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /kalshi: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs(update, context):
    """Показать список всех вкладок"""
    try:
        tab_list = list_tabs()
        if not tab_list:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return
        
        current = current_tab()
        response = "📑 Список вкладок:\n\n"
        for i, tab in enumerate(tab_list, 1):
            if tab == current:
                response += f"✅ {i}. {tab} (текущая)\n"
            else:
                response += f"🔲 {i}. {tab}\n"
        
        response += "\nКоманды:\n"
        response += "/tab_new — открыть новую вкладку\n"
        response += "/tab_close <номер> — закрыть вкладку\n"
        response += "/tab_switch <номер> — переключиться на вкладку"
        
        # Обрезаем если слишком длинный
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_new(update, context):
    """Открыть новую вкладку"""
    try:
        new_tab()
        await update.message.reply_text("✅ Новая вкладка открыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_close(update, context):
    """Закрыть вкладку по номеру"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_close 1")
            return
        
        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return
        
        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return
        
        tab_id = tabs_list[tab_num]
        current = current_tab()
        
        if tab_id == current and len(tabs_list) > 1:
            await update.message.reply_text("❌ Нельзя закрыть текущую вкладку, если есть другие. Сначала переключитесь на другую.")
            return
        
        close_tab(tab_id)
        await update.message.reply_text(f"✅ Вкладка {tab_num + 1} закрыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_switch(update, context):
    """Переключиться на вкладку по номеру"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_switch 2")
            return
        
        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return
        
        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return
        
        tab_id = tabs_list[tab_num]
        switch_tab(tab_id)
        await update.message.reply_text(f"✅ Переключился на вкладку {tab_num + 1}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom))
    app.add_handler(CommandHandler("kalshi", kalshi))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    app.add_handler(CommandHandler("log", log))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()