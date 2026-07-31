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
# BROWSER HARNESS (с увеличенным буфером)
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
    
    def _get_ws_url(self):
        try:
            resp = httpx.get(f"{self.cdp_url}/json/list", timeout=5)
            pages = resp.json()
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
        return None
    
    async def _send_cdp(self, method, params=None):
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
            await ws.send(json.dumps(message))
            response = await ws.recv()
            return json.loads(response)
    
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
    
    async def wait_for_load(self, timeout=15):
        await asyncio.sleep(timeout)

browser = BrowserHarness(CDP_URL)

# ============================================================
# DOM ПАРСЕР (ГЛУБОКИЙ)
# ============================================================

def get_dom_parser_js():
    """JavaScript для глубокого парсинга DOM"""
    return """
(function() {
    function walk(node, arr) {
        if (!node || node.nodeType !== 1) return;
        
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
            rc: (function() {
                var r = el.getBoundingClientRect();
                return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
            })(),
            dt: (function() {
                var d = {};
                for (var i = 0; i < el.attributes.length; i++) {
                    var a = el.attributes[i];
                    if (a.name.indexOf('data-') === 0) d[a.name] = a.value;
                }
                return Object.keys(d).length ? d : null;
            })(),
            ar: (function() {
                var a = {};
                var keys = ['label','describedby','hidden','expanded','selected','checked','disabled'];
                for (var i = 0; i < keys.length; i++) {
                    var v = el.getAttribute('aria-' + keys[i]);
                    if (v) a[keys[i]] = v;
                }
                return Object.keys(a).length ? a : null;
            })(),
            rf: (function() {
                var fiberKey = null;
                var keys = Object.keys(el);
                for (var i = 0; i < keys.length; i++) {
                    if (keys[i].indexOf('__reactFiber') === 0 || keys[i].indexOf('__reactInternalInstance') === 0) {
                        fiberKey = keys[i];
                        break;
                    }
                }
                if (!fiberKey) return null;
                var f = el[fiberKey];
                var p = {};
                while (f) {
                    if (f.memoizedProps) {
                        var mp = f.memoizedProps;
                        for (var k in mp) p[k] = mp[k];
                    }
                    f = f.return;
                }
                var clean = {};
                for (var k in p) {
                    if (k.indexOf('_') !== 0 && k !== 'children' && typeof p[k] !== 'function' && typeof p[k] !== 'object') {
                        clean[k] = p[k];
                    }
                }
                return Object.keys(clean).length ? clean : null;
            })(),
            cs: (function() {
                var s = {};
                var props = ['display','visibility','opacity','position','width','height','color','backgroundColor','fontSize','zIndex','cursor'];
                var cs = window.getComputedStyle(el);
                for (var i = 0; i < props.length; i++) {
                    s[props[i]] = cs[props[i]];
                }
                return s;
            })(),
            ev: (function() {
                var e = [];
                var evs = ['onclick','onchange','oninput','onsubmit','onfocus','onblur','onkeydown','onscroll'];
                for (var i = 0; i < evs.length; i++) {
                    if (el[evs[i]]) e.push(evs[i]);
                }
                return e.length ? e : null;
            })(),
            sh: el.shadowRoot ? {mode: el.shadowRoot.mode, kids: el.shadowRoot.children.length} : null
        };
        
        arr.push(data);
        
        if (el.shadowRoot) {
            var shadowKids = el.shadowRoot.children;
            for (var i = 0; i < shadowKids.length; i++) {
                walk(shadowKids[i], arr);
            }
        }
        
        if ((el.tagName === 'IFRAME' || el.tagName === 'FRAME') && el.contentDocument) {
            walk(el.contentDocument.documentElement, arr);
        }
        
        var kids = el.children;
        for (var i = 0; i < kids.length; i++) {
            walk(kids[i], arr);
        }
    }
    
    var elements = [];
    walk(document.documentElement, elements);
    
    var grouped = {};
    for (var i = 0; i < elements.length; i++) {
        var el = elements[i];
        var tag = el.t;
        if (!grouped[tag]) grouped[tag] = [];
        grouped[tag].push(el);
    }
    
    var stats = {total: elements.length, tags: Object.keys(grouped).length, byTag: {}};
    for (var tag in grouped) stats.byTag[tag] = grouped[tag].length;
    
    return JSON.stringify({
        page: {
            url: window.location.href,
            domain: window.location.hostname,
            title: document.title,
            desc: (document.querySelector('meta[name="description"]') || {}).content || ''
        },
        stats: stats,
        elements: grouped
    });
})();
"""

# ============================================================
# ACCESSIBILITY TREE ПАРСЕР
# ============================================================

def get_accessibility_tree_js():
    """JavaScript для получения Accessibility Tree"""
    return """
(function() {
    function getAccessibilityNode(element) {
        if (!element) return null;
        
        var role = element.getAttribute('role') || 
                   element.tagName.toLowerCase();
        
        var aria = {};
        for (var attr of element.attributes) {
            if (attr.name.startsWith('aria-')) {
                aria[attr.name] = attr.value;
            }
        }
        
        var label = element.getAttribute('aria-label') || 
                   element.getAttribute('aria-labelledby') ||
                   element.getAttribute('label') ||
                   element.title ||
                   '';
        
        var description = element.getAttribute('aria-description') ||
                        element.getAttribute('aria-describedby') ||
                        '';
        
        var state = {
            disabled: element.hasAttribute('disabled') || element.hasAttribute('aria-disabled'),
            hidden: element.hasAttribute('hidden') || element.getAttribute('aria-hidden') === 'true',
            expanded: element.getAttribute('aria-expanded') === 'true',
            selected: element.hasAttribute('aria-selected') && element.getAttribute('aria-selected') !== 'false',
            checked: element.hasAttribute('aria-checked') && element.getAttribute('aria-checked') !== 'false',
            pressed: element.getAttribute('aria-pressed') === 'true',
            busy: element.getAttribute('aria-busy') === 'true',
            invalid: element.getAttribute('aria-invalid') === 'true',
            required: element.hasAttribute('required') || element.getAttribute('aria-required') === 'true'
        };
        
        var level = element.getAttribute('aria-level') || 
                   (element.tagName.match(/^H([1-6])$/i) ? RegExp.$1 : null);
        
        var focusable = element.tabIndex >= 0 || 
                       ['input','button','select','textarea','a'].includes(element.tagName.toLowerCase());
        
        var hiddenForScreenReader = element.getAttribute('aria-hidden') === 'true' ||
                                    element.style.display === 'none' ||
                                    element.style.visibility === 'hidden';
        
        var textContent = element.textContent.trim().slice(0, 200);
        var alt = element.getAttribute('alt') || '';
        var title = element.title || '';
        var controlType = element.getAttribute('type') || 
                         element.getAttribute('role') || 
                         element.tagName.toLowerCase();
        var value = element.value || element.getAttribute('value') || '';
        var placeholder = element.placeholder || '';
        
        return {
            role: role,
            label: label,
            description: description,
            aria: aria,
            state: state,
            level: level,
            focusable: focusable,
            hiddenForScreenReader: hiddenForScreenReader,
            textContent: textContent,
            alt: alt,
            title: title,
            controlType: controlType,
            value: value,
            placeholder: placeholder,
            name: element.name || '',
            id: element.id || '',
            className: element.className || '',
            accessibilityScore: calculateAccessibilityScore(element)
        };
    }
    
    function calculateAccessibilityScore(element) {
        var score = 100;
        var tag = element.tagName.toLowerCase();
        
        if (tag === 'img' && !element.alt) score -= 20;
        
        if (tag === 'input' && !element.id && !element.getAttribute('aria-label') && !element.title) {
            score -= 25;
        }
        
        if (['button','a','input','select','textarea'].includes(tag)) {
            if (!element.getAttribute('aria-label') && 
                !element.title && 
                !element.textContent.trim()) {
                score -= 15;
            }
        }
        
        if (tag === 'a' && !element.textContent.trim() && !element.title && !element.getAttribute('aria-label')) {
            score -= 20;
        }
        
        if (tag.match(/^h[1-6]$/i) && !element.textContent.trim()) {
            score -= 10;
        }
        
        return Math.max(0, score);
    }
    
    function walkAccessibilityTree(node, depth) {
        if (!node || depth > 20) return null;
        
        var result = getAccessibilityNode(node);
        var children = [];
        
        for (var child of node.children) {
            var childResult = walkAccessibilityTree(child, depth + 1);
            if (childResult) {
                children.push(childResult);
            }
        }
        
        if (node.shadowRoot) {
            for (var child of node.shadowRoot.children) {
                var childResult = walkAccessibilityTree(child, depth + 1);
                if (childResult) {
                    children.push(childResult);
                }
            }
        }
        
        if ((node.tagName === 'IFRAME' || node.tagName === 'FRAME') && node.contentDocument) {
            var childResult = walkAccessibilityTree(node.contentDocument.documentElement, depth + 1);
            if (childResult) {
                children.push(childResult);
            }
        }
        
        result.children = children.length ? children : null;
        result.issues = getAccessibilityIssues(node);
        
        return result;
    }
    
    function getAccessibilityIssues(element) {
        var issues = [];
        var tag = element.tagName.toLowerCase();
        var text = element.textContent || '';
        
        if (tag === 'input' && !element.id && !element.getAttribute('aria-label') && 
            !element.title && !element.placeholder) {
            issues.push('Поле ввода без метки');
        }
        
        if (tag === 'img' && !element.alt && !element.getAttribute('role') === 'presentation') {
            issues.push('Изображение без alt текста');
        }
        
        if (tag === 'button' && !text.trim() && !element.getAttribute('aria-label')) {
            issues.push('Кнопка без текста');
        }
        
        if (tag === 'a' && !text.trim() && !element.getAttribute('aria-label')) {
            issues.push('Ссылка без текста');
        }
        
        if (tag.match(/^h[1-6]$/i) && !text.trim()) {
            issues.push('Пустой заголовок');
        }
        
        if (element.getAttribute('aria-hidden') === 'true' && 
            ['button','a','input','select','textarea'].includes(tag)) {
            issues.push('Интерактивный элемент скрыт для скринридера');
        }
        
        return issues.length ? issues : null;
    }
    
    var tree = {
        document: {
            role: 'document',
            title: document.title,
            url: window.location.href,
            domain: window.location.hostname,
            language: document.documentElement.lang || 'unknown'
        },
        accessibilityTree: walkAccessibilityTree(document.body, 0),
        summary: {
            totalElements: document.querySelectorAll('*').length,
            accessibleElements: document.querySelectorAll('[role], [aria-label], [title], button, a, input, select, textarea').length,
            issues: [],
            score: 0
        }
    };
    
    var allIssues = [];
    document.querySelectorAll('*').forEach(function(el) {
        var issues = getAccessibilityIssues(el);
        if (issues) {
            allIssues = allIssues.concat(issues);
        }
    });
    
    tree.summary.issues = [...new Set(allIssues)];
    tree.summary.score = Math.max(0, 100 - allIssues.length * 5);
    
    return JSON.stringify(tree);
})();
"""

# ============================================================
# ОСНОВНОЙ ПАРСЕР
# ============================================================

async def parse_dom(url, include_accessibility=True):
    """Глубокий парсинг DOM страницы с поддержкой Accessibility Tree"""
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        dom_js = get_dom_parser_js()
        dom_result = await browser.evaluate(dom_js)
        
        a11y_result = None
        if include_accessibility:
            a11y_js = get_accessibility_tree_js()
            a11y_result = await browser.evaluate(a11y_js)
        
        result = {
            "dom": json.loads(dom_result) if dom_result else None,
            "accessibility": json.loads(a11y_result) if a11y_result else None,
            "timestamp": asyncio.get_event_loop().time()
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
        f"🌐 **DOM Parser Bot**\n\n"
        f"{cookies_status}\n\n"
        f"Глубокий парсинг DOM:\n"
        f"• React Fiber / Props\n"
        f"• Shadow DOM\n"
        f"• Все атрибуты и стили\n"
        f"• Позиции элементов\n"
        f"• **Accessibility Tree** ♿\n\n"
        f"Использование:\n"
        f"/dom <url> — парсинг DOM\n"
        f"/dom <url> --a11y — парсинг DOM + Accessibility\n"
        f"/a11y <url> — только Accessibility Tree",
        parse_mode='Markdown'
    )

async def dom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /dom https://example.com")
        return
    
    url = context.args[0].strip()
    include_a11y = '--a11y' in context.args
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        result, error = await parse_dom(url, include_accessibility=include_a11y)
        
        if error:
            await status_msg.edit_text(f"❌ Ошибка: {error}")
            return
        
        if not result or not result.get('dom'):
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        domain = result['dom']['page']['domain'].replace('.', '_')
        filename = f"dom_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        stats = result['dom'].get('stats', {})
        a11y_score = result.get('accessibility', {}).get('summary', {}).get('score', 'N/A')
        
        caption = (
            f"📊 **DOM страницы**\n"
            f"🔗 {result['dom']['page']['url']}\n"
            f"📝 {result['dom']['page']['title'][:100]}\n"
            f"📦 Всего элементов: {stats.get('total', 0)}\n"
            f"🏷️ Уникальных тегов: {stats.get('tags', 0)}\n"
        )
        
        if include_a11y and a11y_score != 'N/A':
            caption += f"♿ Оценка доступности: {a11y_score}/100\n"
        
        caption += "\n**Топ тегов:**\n"
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

async def a11y_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения Accessibility Tree"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL\n"
            "Пример: /a11y https://example.com"
        )
        return
    
    url = context.args[0].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🔍 Анализирую доступность {url}...")
    
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        a11y_js = get_accessibility_tree_js()
        result = await browser.evaluate(a11y_js)
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить дерево доступности")
            return
        
        a11y_data = json.loads(result)
        
        summary = a11y_data.get('summary', {})
        score = summary.get('score', 0)
        issues_count = len(summary.get('issues', []))
        
        report = (
            f"♿ **Отчет по доступности**\n"
            f"🔗 {url}\n\n"
            f"📊 **Оценка:** {score}/100\n"
            f"📦 Всего элементов: {summary.get('totalElements', 0)}\n"
            f"♿ Доступных элементов: {summary.get('accessibleElements', 0)}\n"
            f"⚠️ Проблем: {issues_count}\n"
        )
        
        if issues_count > 0:
            report += "\n**Найденные проблемы:**\n"
            for issue in summary.get('issues', [])[:10]:
                report += f"• {issue}\n"
            if issues_count > 10:
                report += f"• ... и еще {issues_count - 10} проблем\n"
        
        domain = a11y_data['document'].get('domain', 'report').replace('.', '_')
        filename = f"a11y_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(a11y_data, f, ensure_ascii=False, indent=2)
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=report,
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка /a11y: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom_command))
    app.add_handler(CommandHandler("a11y", a11y_command))
    
    logger.info("🚀 Бот запущен с поддержкой Accessibility Tree!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()