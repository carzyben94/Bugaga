# bot.py
import os
import json
import asyncio
import logging
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

warnings.filterwarnings("ignore")

# ============================================================
# НАСТРОЙКИ
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CDP_URL = os.getenv("CDP_URL", "http://localhost:9222")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

# ============================================================
# КУКИ
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"✅ Загружено {len(COOKIES)} кук")
except ImportError:
    COOKIES = []
    logger.warning("⚠️ cookies.py не найден, куки не будут установлены")

# ============================================================
# BROWSER HARNESS (минимальный)
# ============================================================

class BrowserHarness:
    """Минимальная обертка над Chrome DevTools Protocol"""
    
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
    
    def _get_ws_url(self):
        """Получить WebSocket URL активной вкладки"""
        try:
            resp = httpx.get(f"{self.cdp_url}/json/list", timeout=5)
            pages = resp.json()
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
        return None
    
    async def _send_cdp(self, method, params=None):
        """Отправить CDP команду через WebSocket"""
        import websockets
        
        if not self.ws_url:
            self.ws_url = self._get_ws_url()
            if not self.ws_url:
                raise Exception("Нет активных вкладок")
        
        async with websockets.connect(self.ws_url) as ws:
            message = {
                "id": 1,
                "method": method,
                "params": params or {}
            }
            await ws.send(json.dumps(message))
            response = await ws.recv()
            return json.loads(response)
    
    async def set_cookies(self, cookies):
        """Установить куки через CDP"""
        if not cookies:
            return
        
        try:
            result = await self._send_cdp("Network.setCookies", {"cookies": cookies})
            if "error" in result:
                logger.error(f"Ошибка установки кук: {result['error']}")
            else:
                logger.info(f"✅ Установлено {len(cookies)} кук")
        except Exception as e:
            logger.error(f"Ошибка установки кук: {e}")
    
    async def navigate(self, url):
        """Перейти на URL"""
        result = await self._send_cdp("Page.navigate", {"url": url})
        return result.get("result", {})
    
    async def evaluate(self, expression):
        """Выполнить JavaScript"""
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=15):
        """Подождать загрузки страницы"""
        await asyncio.sleep(timeout)

# Глобальный экземпляр
browser = BrowserHarness(CDP_URL)

# ============================================================
# DOM ПАРСЕР
# ============================================================

def get_dom_parser_js():
    """JavaScript код для парсинга DOM"""
    return """
    (function() {
        function getElementInfo(el) {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().slice(0, 200),
                id: el.id || '',
                className: (typeof el.className === 'string' ? el.className : '') || '',
                name: el.getAttribute('name') || '',
                type: el.getAttribute('type') || '',
                placeholder: el.getAttribute('placeholder') || '',
                href: el.getAttribute('href') || '',
                src: el.getAttribute('src') || '',
                value: el.value || '',
                disabled: el.disabled || false,
                visible: el.offsetParent !== null,
                xpath: '',
                cssSelector: '',
                dataAttributes: {},
                ariaAttributes: {},
                eventHandlers: []
            };
            
            // Data-* атрибуты
            for (const attr of el.attributes) {
                if (attr.name.startsWith('data-')) {
                    info.dataAttributes[attr.name] = attr.value;
                }
            }
            
            // ARIA атрибуты
            const ariaAttrs = ['aria-label', 'aria-describedby', 'aria-hidden', 'aria-expanded', 'aria-selected', 'aria-checked'];
            for (const attr of ariaAttrs) {
                const val = el.getAttribute(attr);
                if (val) info.ariaAttributes[attr] = val;
            }
            
            // Обработчики событий
            ['onclick', 'onsubmit', 'onchange', 'oninput', 'onfocus'].forEach(handler => {
                if (el[handler]) info.eventHandlers.push(handler);
            });
            
            // XPath (упрощенный)
            try {
                if (info.id) {
                    info.xpath = `//*[@id="${info.id}"]`;
                } else if (info.className) {
                    const cls = info.className.split(' ')[0];
                    info.xpath = `//${info.tag}[contains(@class, "${cls}")]`;
                } else {
                    info.xpath = `//${info.tag}`;
                }
            } catch(e) {}
            
            // CSS селектор
            if (info.id) {
                info.cssSelector = `#${info.id}`;
            } else if (info.className) {
                const cls = info.className.split(' ').filter(c => c).join('.');
                info.cssSelector = `${info.tag}.${cls}`;
            } else {
                info.cssSelector = info.tag;
            }
            
            return info;
        }
        
        // Собираем элементы
        const result = {
            page: {
                url: window.location.href,
                title: document.title,
                timestamp: Date.now()
            },
            elements: {
                inputs: [],
                buttons: [],
                links: [],
                selects: [],
                textareas: [],
                forms: [],
                images: [],
                headings: [],
                divs: [],
                spans: [],
                lis: [],
                others: []
            }
        };
        
        // Селекторы для сбора
        const selectorMap = {
            inputs: 'input:not([type="hidden"])',
            buttons: 'button, input[type="submit"], input[type="button"], [role="button"]',
            links: 'a[href]',
            selects: 'select',
            textareas: 'textarea',
            forms: 'form',
            images: 'img[src]',
            headings: 'h1, h2, h3, h4, h5, h6',
            divs: 'div[id], div[class]',
            spans: 'span[id], span[class]',
            lis: 'li[id], li[class]'
        };
        
        const processed = new Set();
        
        for (const [category, selector] of Object.entries(selectorMap)) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                if (!processed.has(el)) {
                    processed.add(el);
                    result.elements[category].push(getElementInfo(el));
                }
            }
        }
        
        // Собираем элементы с data-* атрибутами, которые могли пропустить
        document.querySelectorAll('[data-testid], [data-test], [data-cy], [data-qa]').forEach(el => {
            if (!processed.has(el)) {
                processed.add(el);
                result.elements.others.push(getElementInfo(el));
            }
        });
        
        // Статистика
        result.stats = {
            total: processed.size,
            byCategory: Object.fromEntries(
                Object.entries(result.elements).map(([k, v]) => [k, v.length])
            )
        };
        
        return JSON.stringify(result);
    })();
    """

async def parse_dom(url):
    """Парсит DOM страницы"""
    try:
        # Устанавливаем куки
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        # Переходим на URL
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        # Выполняем парсинг
        js_code = get_dom_parser_js()
        result = await browser.evaluate(js_code)
        
        if not result:
            return None, "Пустой результат"
        
        return json.loads(result), None
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return None, str(e)

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: не загружены"
    
    await update.message.reply_text(
        f"🌐 **DOM Parser Bot**\n\n"
        f"{cookies_status}\n\n"
        f"Использование:\n"
        f"/dom <url> — парсинг DOM страницы\n\n"
        f"Примеры:\n"
        f"/dom https://example.com\n"
        f"/dom x.com",
        parse_mode='Markdown'
    )

async def dom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dom"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL\n"
            "Пример: /dom https://example.com"
        )
        return
    
    url = context.args[0].strip()
    
    # Добавляем протокол если нужно
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        # Парсим
        dom_data, error = await parse_dom(url)
        
        if error:
            await status_msg.edit_text(f"❌ Ошибка: {error}")
            return
        
        if not dom_data:
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        # Отправляем JSON
        json_str = json.dumps(dom_data, ensure_ascii=False, indent=2)
        
        # Сохраняем во временный файл
        filename = f"dom_{dom_data['page']['url'].replace('https://', '').replace('http://', '').replace('/', '_')[:50]}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        # Отправляем файл
        stats = dom_data.get('stats', {})
        total = stats.get('total', 0)
        
        caption = (
            f"📊 **DOM страницы**\n"
            f"🔗 {dom_data['page']['url']}\n"
            f"📝 {dom_data['page']['title'][:100]}\n"
            f"📦 Всего элементов: {total}\n\n"
            f"**По категориям:**\n"
        )
        
        for category, count in stats.get('byCategory', {}).items():
            if count > 0:
                caption += f"• {category}: {count}\n"
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=caption,
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        
        # Удаляем временный файл
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка команды /dom: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom_command))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()