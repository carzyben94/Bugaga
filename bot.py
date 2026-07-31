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
        
        # Увеличиваем буфер до 10 МБ
        async with websockets.connect(
            self.ws_url,
            max_size=10_000_000,  # 10 MB на приём
            write_limit=10_000_000  # 10 MB на отправку
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
        
        // Shadow DOM
        if (el.shadowRoot) {
            var shadowKids = el.shadowRoot.children;
            for (var i = 0; i < shadowKids.length; i++) {
                walk(shadowKids[i], arr);
            }
        }
        
        // iframe
        if ((el.tagName === 'IFRAME' || el.tagName === 'FRAME') && el.contentDocument) {
            walk(el.contentDocument.documentElement, arr);
        }
        
        // Дети
        var kids = el.children;
        for (var i = 0; i < kids.length; i++) {
            walk(kids[i], arr);
        }
    }
    
    var elements = [];
    walk(document.documentElement, elements);
    
    // Группировка
    var grouped = {};
    for (var i = 0; i < elements.length; i++) {
        var el = elements[i];
        var tag = el.t;
        if (!grouped[tag]) grouped[tag] = [];
        grouped[tag].push(el);
    }
    
    // Статистика
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

async def parse_dom(url):
    """Глубокий парсинг DOM страницы"""
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
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
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: не загружены"
    
    await update.message.reply_text(
        f"🌐 **DOM Parser Bot**\n\n"
        f"{cookies_status}\n\n"
        f"Глубокий парсинг DOM:\n"
        f"• React Fiber / Props\n"
        f"• Shadow DOM\n"
        f"• Все атрибуты и стили\n"
        f"• Позиции элементов\n\n"
        f"Использование:\n"
        f"/dom <url> — парсинг DOM страницы",
        parse_mode='Markdown'
    )

async def dom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /dom https://example.com")
        return
    
    url = context.args[0].strip()
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        dom_data, error = await parse_dom(url)
        
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
            f"📦 Всего элементов: {stats.get('total', 0)}\n"
            f"🏷️ Уникальных тегов: {stats.get('tags', 0)}\n\n"
            f"**Топ тегов:**\n"
        )
        
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