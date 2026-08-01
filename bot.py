# bot.py
import os
import json
import asyncio
import logging
import httpx
import warnings
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Optional, Dict, Any, List

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
logging.getLogger("websockets").setLevel(logging.CRITICAL)

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
# BROWSER HARNESS С ПОДДЕРЖКОЙ SHADOW DOM И HTTP ПЕРЕХВАТА
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.http_requests = []
        self.http_responses = []
        self._request_id_map = {}
        
    def _get_ws_url(self):
        try:
            resp = httpx.get(f"{self.cdp_url}/json/list", timeout=5)
            pages = resp.json()
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
        return None
    
    async def _send_cdp(self, method, params=None, session_id=None):
        import websockets
        
        if not self.ws_url:
            self.ws_url = self._get_ws_url()
            if not self.ws_url:
                raise Exception("Нет активных вкладок")
        
        async with websockets.connect(
            self.ws_url,
            max_size=10_000_000,
            write_limit=10_000_000
        ) as ws:
            message = {
                "id": 1,
                "method": method,
                "params": params or {}
            }
            if session_id:
                message["sessionId"] = session_id
                
            await ws.send(json.dumps(message))
            response = await ws.recv()
            return json.loads(response)
    
    async def enable_network_monitoring(self):
        """Включаем мониторинг сетевых запросов"""
        # Включаем Network домен
        await self._send_cdp("Network.enable", {})
        
        # Подписываемся на события
        # requestWillBeSent
        # responseReceived
        # loadingFinished
        
    async def get_http_requests(self, filter_url=None):
        """Получить все HTTP запросы"""
        if filter_url:
            return [req for req in self.http_requests if filter_url in req.get('url', '')]
        return self.http_requests
    
    async def get_http_responses(self, filter_url=None):
        """Получить все HTTP ответы"""
        if filter_url:
            return [res for res in self.http_responses if filter_url in res.get('url', '')]
        return self.http_responses
    
    async def clear_http_logs(self):
        """Очистить логи HTTP"""
        self.http_requests = []
        self.http_responses = []
        self._request_id_map = {}
    
    async def set_cookies(self, cookies):
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
        result = await self._send_cdp("Page.navigate", {"url": url})
        return result.get("result", {})
    
    async def evaluate(self, expression):
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=30):
        """Ожидание загрузки страницы"""
        start = time.time()
        while time.time() - start < timeout:
            body_check = await self.evaluate("document.body ? document.body.children.length : 0")
            if body_check and body_check > 0:
                await asyncio.sleep(3)
                visible_check = await self.evaluate("""
                    (function() {
                        var els = document.querySelectorAll('*');
                        var count = 0;
                        for (var el of els) {
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && el.textContent.trim()) {
                                count++;
                                if (count > 10) break;
                            }
                        }
                        return count;
                    })();
                """)
                if visible_check and visible_check > 5:
                    logger.info(f"✅ Страница загружена (найдено {visible_check} видимых элементов)")
                    return
            await asyncio.sleep(1)
        logger.warning("⚠️ Таймаут ожидания загрузки страницы")

browser = BrowserHarness(CDP_URL)

# ============================================================
# SHADOW DOM ПАРСЕР
# ============================================================

def get_shadow_dom_parser_js():
    """JavaScript для парсинга Shadow DOM"""
    return """
(function() {
    function walkShadowDOM(node, arr, path) {
        if (!node) return;
        
        // Проверяем, является ли элемент Shadow Host
        if (node.shadowRoot) {
            var shadowInfo = {
                type: 'shadow_root',
                host: node.tagName.toLowerCase(),
                hostId: node.id || '',
                hostClass: node.className || '',
                mode: node.shadowRoot.mode,
                children: []
            };
            
            // Обрабатываем детей внутри Shadow DOM
            var shadowChildren = node.shadowRoot.children;
            for (var i = 0; i < shadowChildren.length; i++) {
                var childData = walkShadowDOM(shadowChildren[i], null, path + ' > shadow');
                if (childData) {
                    shadowInfo.children.push(childData);
                }
            }
            
            // Добавляем shadow root в результаты
            if (arr !== null) {
                arr.push(shadowInfo);
            }
            return shadowInfo;
        }
        
        // Обычный элемент
        var data = {
            tag: node.tagName.toLowerCase(),
            id: node.id || '',
            className: node.className || '',
            text: (node.textContent || '').trim().slice(0, 200),
            path: path,
            children: []
        };
        
        // Проверяем, есть ли у элемента свой shadow root
        if (node.shadowRoot) {
            var shadowInfo = walkShadowDOM(node, null, path + ' > ' + data.tag);
            if (shadowInfo) {
                data.shadowRoot = shadowInfo;
            }
        }
        
        // Обрабатываем обычных детей
        var kids = node.children;
        for (var i = 0; i < kids.length; i++) {
            var childData = walkShadowDOM(kids[i], null, path + ' > ' + data.tag);
            if (childData) {
                data.children.push(childData);
            }
        }
        
        if (arr !== null) {
            arr.push(data);
        }
        return data;
    }
    
    var shadowElements = [];
    walkShadowDOM(document.documentElement, shadowElements, 'root');
    
    return JSON.stringify({
        page: {
            url: window.location.href,
            domain: window.location.hostname,
            title: document.title || ''
        },
        shadowElements: shadowElements,
        stats: {
            totalShadowRoots: document.querySelectorAll('*').filter(el => el.shadowRoot).length
        }
    });
})();
"""

# ============================================================
# УЛУЧШЕННЫЙ DOM ПАРСЕР С SHADOW DOM И IFrame
# ============================================================

def get_enhanced_dom_parser_js():
    """JavaScript для глубокого парсинга DOM с Shadow DOM"""
    return """
(function() {
    function walkEnhanced(node, arr, depth) {
        if (!node || node.nodeType !== 1 || depth > 30) return;
        
        var el = node;
        var data = {
            t: el.tagName.toLowerCase(),
            id: el.id || '',
            cl: (typeof el.className === 'string' ? el.className : ''),
            tx: (el.textContent || '').trim().slice(0, 300),
            v: el.value || '',
            ph: el.getAttribute('placeholder') || '',
            hr: el.getAttribute('href') || '',
            sr: el.getAttribute('src') || '',
            nm: el.getAttribute('name') || '',
            tp: el.getAttribute('type') || '',
            rl: el.getAttribute('role') || '',
            ds: !!el.disabled,
            vs: !!(el.offsetParent || el.getClientRects().length),
            hasShadowRoot: !!el.shadowRoot,
            shadowRootMode: el.shadowRoot ? el.shadowRoot.mode : null,
            children: [],
            shadowChildren: []
        };
        
        // Обычные дети
        var kids = el.children;
        for (var i = 0; i < kids.length; i++) {
            var childData = {};
            walkEnhanced(kids[i], [childData], depth + 1);
            if (Object.keys(childData).length) {
                data.children.push(childData);
            }
        }
        
        // Shadow DOM дети
        if (el.shadowRoot) {
            var shadowKids = el.shadowRoot.children;
            for (var i = 0; i < shadowKids.length; i++) {
                var shadowData = {};
                walkEnhanced(shadowKids[i], [shadowData], depth + 1);
                if (Object.keys(shadowData).length) {
                    data.shadowChildren.push(shadowData);
                }
            }
        }
        
        // iframe
        if ((el.tagName === 'IFRAME' || el.tagName === 'FRAME') && el.contentDocument) {
            var iframeData = {};
            walkEnhanced(el.contentDocument.documentElement, [iframeData], depth + 1);
            if (Object.keys(iframeData).length) {
                data.iframeContent = iframeData;
            }
        }
        
        arr.push(data);
    }
    
    var elements = [];
    walkEnhanced(document.documentElement, elements, 0);
    
    // Статистика
    var totalElements = 0;
    var shadowRoots = 0;
    
    function countElements(data) {
        if (!data) return;
        totalElements++;
        if (data.hasShadowRoot) shadowRoots++;
        if (data.children) {
            for (var child of data.children) countElements(child);
        }
        if (data.shadowChildren) {
            for (var child of data.shadowChildren) countElements(child);
        }
    }
    
    for (var el of elements) countElements(el);
    
    return JSON.stringify({
        page: {
            url: window.location.href,
            domain: window.location.hostname,
            title: document.title || '',
            desc: (document.querySelector('meta[name="description"]') || {}).content || ''
        },
        stats: {
            total: totalElements,
            shadowRoots: shadowRoots
        },
        elements: elements
    });
})();
"""

# ============================================================
# HTTP ПЕРЕХВАТЧИК
# ============================================================

async def capture_http_requests(url, max_requests=50):
    """Перехват HTTP запросов на странице"""
    try:
        # Включаем Network
        await browser._send_cdp("Network.enable", {})
        
        # Создаем обработчики через evaluate
        capture_js = """
        (function() {
            var requests = [];
            var originalFetch = window.fetch;
            
            window.fetch = function(...args) {
                var request = {
                    url: args[0],
                    method: args[1]?.method || 'GET',
                    headers: args[1]?.headers || {},
                    body: args[1]?.body || null,
                    timestamp: Date.now()
                };
                requests.push(request);
                
                // Сохраняем в глобальную переменную для доступа извне
                window.__captured_requests = requests;
                
                return originalFetch.apply(this, args);
            };
            
            // Перехватываем XMLHttpRequest
            var originalXHROpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...args) {
                this._url = url;
                this._method = method;
                return originalXHROpen.apply(this, [method, url, ...args]);
            };
            
            var originalXHRSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
                var request = {
                    url: this._url,
                    method: this._method || 'GET',
                    body: body,
                    timestamp: Date.now()
                };
                window.__captured_requests = window.__captured_requests || [];
                window.__captured_requests.push(request);
                return originalXHRSend.apply(this, [body]);
            };
            
            return 'Network capture enabled';
        })();
        """
        
        await browser.evaluate(capture_js)
        
        # Ждем немного для сбора запросов
        await asyncio.sleep(3)
        
        # Получаем захваченные запросы
        result = await browser.evaluate("return window.__captured_requests || []")
        
        return result[:max_requests] if result else []
        
    except Exception as e:
        logger.error(f"Ошибка перехвата HTTP: {e}")
        return []

# ============================================================
# ОСНОВНОЙ ПАРСЕР
# ============================================================

async def parse_dom_enhanced(url, capture_http=False):
    """Улучшенный парсинг DOM с поддержкой Shadow DOM и HTTP"""
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(30)
        
        # Парсим DOM с Shadow DOM
        dom_js = get_enhanced_dom_parser_js()
        dom_result = await browser.evaluate(dom_js)
        
        # Парсим Shadow DOM отдельно
        shadow_js = get_shadow_dom_parser_js()
        shadow_result = await browser.evaluate(shadow_js)
        
        # Перехватываем HTTP запросы
        http_requests = []
        if capture_http:
            http_requests = await capture_http_requests(url)
        
        dom_data = json.loads(dom_result) if dom_result else None
        shadow_data = json.loads(shadow_result) if shadow_result else None
        
        # Если DOM пустой, пробуем еще раз
        if dom_data and dom_data.get('stats', {}).get('total', 0) == 0:
            logger.warning("⚠️ DOM пустой, пробуем еще раз...")
            await asyncio.sleep(5)
            dom_result = await browser.evaluate(dom_js)
            dom_data = json.loads(dom_result) if dom_result else None
        
        result = {
            "dom": dom_data,
            "shadowDom": shadow_data,
            "httpRequests": http_requests,
            "timestamp": time.time(),
            "url": url
        }
        
        return result, None
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return None, str(e)

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: не загружены"
    
    await update.message.reply_text(
        f"🌐 **Enhanced DOM Parser Bot**\n\n"
        f"{cookies_status}\n\n"
        f"**Расширенные возможности:**\n"
        f"• **Shadow DOM** парсинг 🌑\n"
        f"• **HTTP запросы** перехват 📡\n"
        f"• React Fiber / Props\n"
        f"• Все атрибуты и стили\n"
        f"• iframe и вложенные документы\n"
        f"• **Accessibility Tree** ♿\n\n"
        f"**Использование:**\n"
        f"/dom <url> — парсинг DOM + Shadow DOM\n"
        f"/dom <url> --http — парсинг + HTTP перехват\n"
        f"/dom <url> --a11y — парсинг + Accessibility\n"
        f"/dom <url> --all — все режимы\n"
        f"/http <url> — только HTTP запросы\n"
        f"/shadow <url> — только Shadow DOM\n"
        f"/a11y <url> — только Accessibility Tree",
        parse_mode='Markdown'
    )

async def dom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /dom https://example.com")
        return
    
    url = context.args[0].strip()
    capture_http = '--http' in context.args or '--all' in context.args
    include_a11y = '--a11y' in context.args or '--all' in context.args
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        result, error = await parse_dom_enhanced(url, capture_http=capture_http)
        
        if error:
            await status_msg.edit_text(f"❌ Ошибка: {error}")
            return
        
        if not result or not result.get('dom'):
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        dom_data = result['dom']
        shadow_data = result.get('shadowDom')
        http_requests = result.get('httpRequests', [])
        
        # Проверка на пустой результат
        if dom_data.get('stats', {}).get('total', 0) == 0:
            await status_msg.edit_text(
                "⚠️ Страница загружена, но DOM пуст.\n"
                "Это SPA (React/Vue/Angular).\n"
                "Попробуйте:\n"
                "• /dom <url> --http для перехвата запросов\n"
                "• /shadow <url> для Shadow DOM\n"
                "• /a11y <url> для Accessibility"
            )
            return
        
        domain = dom_data['page']['domain'].replace('.', '_')
        filename = f"enhanced_dom_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        stats = dom_data.get('stats', {})
        shadow_stats = shadow_data.get('stats', {}) if shadow_data else {}
        
        caption = (
            f"📊 **DOM страницы**\n"
            f"🔗 {dom_data['page']['url']}\n"
            f"📝 {dom_data['page']['title'][:100]}\n"
            f"📦 Всего элементов: {stats.get('total', 0)}\n"
            f"🌑 Shadow DOM: {stats.get('shadowRoots', 0)}\n"
            f"📡 HTTP запросов: {len(http_requests)}\n"
        )
        
        if http_requests and capture_http:
            caption += "\n**Последние HTTP запросы:**\n"
            for req in http_requests[:5]:
                method = req.get('method', 'GET')
                req_url = req.get('url', '')[:60]
                caption += f"• {method} {req_url}...\n"
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=caption,
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка команды /dom: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def shadow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для парсинга Shadow DOM"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /shadow https://example.com")
        return
    
    url = context.args[0].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌑 Ищу Shadow DOM на {url}...")
    
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(30)
        
        shadow_js = get_shadow_dom_parser_js()
        result = await browser.evaluate(shadow_js)
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить Shadow DOM")
            return
        
        shadow_data = json.loads(result)
        
        shadow_count = shadow_data.get('stats', {}).get('totalShadowRoots', 0)
        
        if shadow_count == 0:
            await status_msg.edit_text("ℹ️ На странице не найдено Shadow DOM элементов")
            return
        
        domain = shadow_data['page']['domain'].replace('.', '_')
        filename = f"shadow_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(shadow_data, f, ensure_ascii=False, indent=2)
        
        caption = (
            f"🌑 **Shadow DOM анализ**\n"
            f"🔗 {shadow_data['page']['url']}\n"
            f"📦 Найдено Shadow DOM: {shadow_count}\n"
        )
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=caption,
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка /shadow: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def http_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для перехвата HTTP запросов"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /http https://example.com")
        return
    
    url = context.args[0].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"📡 Перехватываю HTTP запросы на {url}...")
    
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        # Включаем перехват
        http_requests = await capture_http_requests(url, max_requests=100)
        
        if not http_requests:
            await status_msg.edit_text("ℹ️ Не удалось перехватить HTTP запросы")
            return
        
        domain = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
        filename = f"http_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(http_requests, f, ensure_ascii=False, indent=2)
        
        caption = (
            f"📡 **HTTP запросы**\n"
            f"🔗 {url}\n"
            f"📦 Всего запросов: {len(http_requests)}\n\n"
            f"**Примеры запросов:**\n"
        )
        
        for req in http_requests[:10]:
            method = req.get('method', 'GET')
            req_url = req.get('url', '')[:60]
            caption += f"• {method} {req_url}...\n"
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=caption,
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка /http: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom_command))
    app.add_handler(CommandHandler("shadow", shadow_command))
    app.add_handler(CommandHandler("http", http_command))
    
    logger.info("🚀 Бот запущен с поддержкой Shadow DOM и HTTP перехвата!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()