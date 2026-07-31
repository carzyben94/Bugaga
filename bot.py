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
            "returnByValue": True  # ← ИСПРАВЛЕНО
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=15):
        """Подождать загрузки страницы"""
        await asyncio.sleep(timeout)

# Глобальный экземпляр
browser = BrowserHarness(CDP_URL)

# ============================================================
# DOM ПАРСЕР (ГЛУБОКИЙ)
# ============================================================

def get_deep_dom_parser_js():
    """JavaScript для глубокого парсинга DOM (все элементы, все атрибуты, React, Shadow DOM)"""
    return """
    (function() {
        // Рекурсивный обход ВСЕХ элементов, включая Shadow DOM
        function getAllElements(root) {
            const elements = [];
            
            function traverse(node) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    elements.push(node);
                    
                    // Проверяем Shadow DOM
                    if (node.shadowRoot) {
                        node.shadowRoot.childNodes.forEach(child => {
                            if (child.nodeType === Node.ELEMENT_NODE) {
                                elements.push(child);
                                traverse(child);
                            }
                        });
                    }
                    
                    // Проверяем iframe
                    if (node.tagName === 'IFRAME' || node.tagName === 'FRAME') {
                        try {
                            const iframeDoc = node.contentDocument || node.contentWindow.document;
                            if (iframeDoc && iframeDoc.documentElement) {
                                traverse(iframeDoc.documentElement);
                            }
                        } catch(e) {}
                    }
                    
                    // Обходим дочерние элементы
                    for (const child of node.children) {
                        traverse(child);
                    }
                }
            }
            
            traverse(root);
            return elements;
        }
        
        function extractReactFiber(el) {
            const key = Object.keys(el).find(k => 
                k.startsWith('__reactFiber') || 
                k.startsWith('__reactInternalInstance')
            );
            return key ? el[key] : null;
        }
        
        function extractReactProps(el) {
            const fiber = extractReactFiber(el);
            if (!fiber) return null;
            
            const props = {};
            let node = fiber;
            
            while (node) {
                if (node.memoizedProps) {
                    Object.assign(props, node.memoizedProps);
                }
                if (node.pendingProps) {
                    Object.assign(props, node.pendingProps);
                }
                node = node.return;
            }
            
            // Убираем служебные React-свойства
            const cleanProps = {};
            for (const [key, value] of Object.entries(props)) {
                if (!key.startsWith('_') && 
                    !key.startsWith('$$') &&
                    key !== 'children' &&
                    typeof value !== 'function' &&
                    typeof value !== 'object') {
                    cleanProps[key] = value;
                }
            }
            
            return Object.keys(cleanProps).length > 0 ? cleanProps : null;
        }
        
        function buildXPath(el) {
            if (el.id) return '//*[@id="' + el.id + '"]';
            
            const parts = [];
            let current = el;
            
            while (current && current.nodeType === Node.ELEMENT_NODE) {
                let index = 1;
                let sibling = current.previousElementSibling;
                
                while (sibling) {
                    if (sibling.tagName === current.tagName) index++;
                    sibling = sibling.previousElementSibling;
                }
                
                const tagPart = current.tagName.toLowerCase();
                const indexPart = index > 1 ? '[' + index + ']' : '';
                parts.unshift(tagPart + indexPart);
                
                current = current.parentElement;
            }
            
            return '/' + parts.join('/');
        }
        
        function buildCSSSelector(el) {
            if (el.id) return '#' + CSS.escape(el.id);
            
            const parts = [];
            let current = el;
            let depth = 0;
            
            while (current && current !== document.documentElement && depth < 5) {
                let selector = current.tagName.toLowerCase();
                
                if (current.id) {
                    parts.unshift('#' + CSS.escape(current.id));
                    break;
                }
                
                if (current.className && typeof current.className === 'string') {
                    const classes = current.className.trim().split(/\\s+/).filter(function(c) { return c; });
                    if (classes.length > 0) {
                        selector += '.' + classes.map(function(c) { return CSS.escape(c); }).join('.');
                    }
                }
                
                const parent = current.parentElement;
                if (parent) {
                    const sameTagSiblings = Array.from(parent.children).filter(function(s) {
                        return s.tagName === current.tagName;
                    });
                    
                    if (sameTagSiblings.length > 1) {
                        const index = sameTagSiblings.indexOf(current) + 1;
                        selector += ':nth-of-type(' + index + ')';
                    }
                }
                
                parts.unshift(selector);
                current = parent;
                depth++;
            }
            
            return parts.join(' > ');
        }
        
        function getAttributes(el) {
            const attrs = {};
            for (const attr of el.attributes) {
                attrs[attr.name] = attr.value;
            }
            return attrs;
        }
        
        function getComputedStyles(el) {
            const styles = {};
            const computed = window.getComputedStyle(el);
            const importantProps = [
                'display', 'visibility', 'opacity', 'position',
                'width', 'height', 'top', 'left', 'right', 'bottom',
                'color', 'backgroundColor', 'fontSize', 'fontWeight',
                'border', 'borderRadius', 'padding', 'margin',
                'zIndex', 'cursor', 'pointerEvents'
            ];
            
            for (const prop of importantProps) {
                styles[prop] = computed[prop];
            }
            
            return styles;
        }
        
        function getEventListeners(el) {
            const events = [];
            const possibleEvents = [
                'onclick', 'ondblclick', 'onmousedown', 'onmouseup',
                'onchange', 'oninput', 'onsubmit', 'onfocus', 'onblur',
                'onkeydown', 'onkeyup', 'onkeypress',
                'ontouchstart', 'ontouchend', 'ontouchmove',
                'onload', 'onerror', 'onscroll'
            ];
            
            for (const event of possibleEvents) {
                if (el[event]) {
                    events.push(event);
                }
            }
            
            return events;
        }
        
        function getElementData(el) {
            const tag = el.tagName.toLowerCase();
            
            return {
                tag: tag,
                role: el.getAttribute('role') || null,
                type: el.getAttribute('type') || null,
                
                // Идентификаторы
                id: el.id || null,
                name: el.getAttribute('name') || null,
                className: typeof el.className === 'string' ? el.className : '',
                testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || 
                        el.getAttribute('data-cy') || el.getAttribute('data-qa') || null,
                
                // Контент
                text: (el.textContent || '').trim().slice(0, 500),
                innerHTML: el.innerHTML ? el.innerHTML.slice(0, 1000) : '',
                placeholder: el.getAttribute('placeholder') || null,
                value: el.value !== undefined ? el.value : null,
                href: el.getAttribute('href') || null,
                src: el.getAttribute('src') || null,
                alt: el.getAttribute('alt') || null,
                title: el.getAttribute('title') || null,
                
                // Состояние
                disabled: el.disabled || false,
                readOnly: el.readOnly || false,
                required: el.required || false,
                checked: el.checked || false,
                selected: el.selected || false,
                
                // Видимость и позиция
                visible: !!(el.offsetParent || el.getClientRects().length > 0),
                rect: (function() {
                    const r = el.getBoundingClientRect();
                    return {
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        width: Math.round(r.width),
                        height: Math.round(r.height)
                    };
                })(),
                
                // Навигация
                xpath: buildXPath(el),
                cssSelector: buildCSSSelector(el),
                
                // Атрибуты (все)
                attributes: getAttributes(el),
                
                // ARIA
                aria: {
                    label: el.getAttribute('aria-label') || null,
                    describedby: el.getAttribute('aria-describedby') || null,
                    hidden: el.getAttribute('aria-hidden') || null,
                    expanded: el.getAttribute('aria-expanded') || null,
                    selected: el.getAttribute('aria-selected') || null,
                    checked: el.getAttribute('aria-checked') || null,
                    disabled: el.getAttribute('aria-disabled') || null,
                    required: el.getAttribute('aria-required') || null,
                    live: el.getAttribute('aria-live') || null,
                    atomic: el.getAttribute('aria-atomic') || null,
                },
                
                // Data атрибуты
                dataAttributes: (function() {
                    const data = {};
                    for (const attr of el.attributes) {
                        if (attr.name.startsWith('data-')) {
                            data[attr.name] = attr.value;
                        }
                    }
                    return Object.keys(data).length > 0 ? data : null;
                })(),
                
                // React
                reactProps: extractReactProps(el),
                
                // Стили
                computedStyles: getComputedStyles(el),
                
                // События
                eventListeners: getEventListeners(el),
                
                // Shadow DOM
                shadowRoot: el.shadowRoot ? {
                    mode: el.shadowRoot.mode,
                    childCount: el.shadowRoot.children.length
                } : null,
                
                // Дочерние элементы
                childElementCount: el.children.length,
                childTags: Array.from(el.children).slice(0, 20).map(function(c) { return c.tagName.toLowerCase(); }),
                
                // Родитель
                parentTag: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                
                // Форма
                form: el.form ? {
                    id: el.form.id || null,
                    name: el.form.getAttribute('name') || null,
                    action: el.form.action || null,
                    method: el.form.method || null,
                } : null,
            };
        }
        
        // Собираем ВСЕ элементы
        const allElements = getAllElements(document.documentElement);
        const elementsData = [];
        
        for (let i = 0; i < allElements.length; i++) {
            elementsData.push(getElementData(allElements[i]));
        }
        
        // Группируем по тегам
        const grouped = {};
        for (let i = 0; i < elementsData.length; i++) {
            const el = elementsData[i];
            const tag = el.tag;
            if (!grouped[tag]) grouped[tag] = [];
            grouped[tag].push(el);
        }
        
        // Информация о странице
        const pageInfo = {
            url: window.location.href,
            domain: window.location.hostname,
            pathname: window.location.pathname,
            title: document.title,
            description: (document.querySelector('meta[name="description"]') || {}).content || null,
            keywords: (document.querySelector('meta[name="keywords"]') || {}).content || null,
            charset: document.characterSet,
            lang: document.documentElement.lang || null,
            timestamp: Date.now(),
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight,
            },
            scripts: Array.from(document.scripts).map(function(s) { return s.src; }).filter(Boolean),
            stylesheets: Array.from(document.styleSheets).map(function(s) { return s.href || ''; }).filter(function(h) { return h; }),
            meta: (function() {
                const meta = {};
                document.querySelectorAll('meta').forEach(function(m) {
                    const name = m.getAttribute('name') || m.getAttribute('property');
                    const content = m.getAttribute('content');
                    if (name && content) meta[name] = content;
                });
                return meta;
            })(),
        };
        
        // Статистика
        const stats = {
            totalElements: elementsData.length,
            uniqueTags: Object.keys(grouped).length,
            byTag: (function() {
                const counts = {};
                for (const tag of Object.keys(grouped)) {
                    counts[tag] = grouped[tag].length;
                }
                return counts;
            })(),
            withReact: elementsData.filter(function(el) { return el.reactProps; }).length,
            withShadowDOM: elementsData.filter(function(el) { return el.shadowRoot; }).length,
            visible: elementsData.filter(function(el) { return el.visible; }).length,
            interactive: elementsData.filter(function(el) { 
                return ['input', 'button', 'select', 'textarea', 'a'].includes(el.tag);
            }).length,
        };
        
        return JSON.stringify({
            page: pageInfo,
            stats: stats,
            elements: grouped,
        });
    })();
    """

async def parse_dom_deep(url):
    """Глубокий парсинг DOM страницы"""
    try:
        # Устанавливаем куки
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        # Переходим на URL
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        # Выполняем глубокий парсинг
        js_code = get_deep_dom_parser_js()
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
        f"Глубокий парсинг DOM с поддержкой:\n"
        f"• React Fiber / Props\n"
        f"• Shadow DOM\n"
        f"• XPath / CSS селекторы\n"
        f"• Все атрибуты и стили\n"
        f"• Позиции элементов\n\n"
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
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        dom_data, error = await parse_dom_deep(url)
        
        if error:
            await status_msg.edit_text(f"❌ Ошибка: {error}")
            return
        
        if not dom_data:
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        # Сохраняем JSON
        json_str = json.dumps(dom_data, ensure_ascii=False, indent=2)
        
        domain = dom_data['page']['domain'].replace('.', '_')
        filename = f"dom_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        # Статистика
        stats = dom_data.get('stats', {})
        
        caption = (
            f"📊 **DOM страницы**\n"
            f"🔗 {dom_data['page']['url']}\n"
            f"📝 {dom_data['page']['title'][:100]}\n"
            f"📦 Всего элементов: {stats.get('totalElements', 0)}\n"
            f"🏷️ Уникальных тегов: {stats.get('uniqueTags', 0)}\n"
            f"⚛️ React элементов: {stats.get('withReact', 0)}\n"
            f"🌑 Shadow DOM: {stats.get('withShadowDOM', 0)}\n"
            f"👁️ Видимых: {stats.get('visible', 0)}\n"
            f"🖱️ Интерактивных: {stats.get('interactive', 0)}\n\n"
            f"**Топ тегов:**\n"
        )
        
        # Топ-10 тегов
        by_tag = stats.get('byTag', {})
        top_tags = sorted(by_tag.items(), key=lambda x: x[1], reverse=True)[:10]
        for tag, count in top_tags:
            caption += f"• <{tag}>: {count}\n"
        
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

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom_command))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()