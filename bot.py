# bot.py (исправленная версия с CDP перехватом)

import os
import json
import asyncio
import logging
import httpx
import warnings
import time
import websockets
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
# BROWSER HARNESS С CDP ПЕРЕХВАТОМ
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self._ws = None
        self._message_id = 0
        self._pending_requests = {}
        
    def _get_ws_url(self):
        try:
            resp = httpx.get(f"{self.cdp_url}/json/list", timeout=5)
            pages = resp.json()
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception as e:
            logger.error(f"Ошибка подключения к CDP: {e}")
        return None
    
    async def _connect(self):
        if not self.ws_url:
            self.ws_url = self._get_ws_url()
            if not self.ws_url:
                raise Exception("Нет активных вкладок")
        
        if not self._ws:
            self._ws = await websockets.connect(
                self.ws_url,
                max_size=10_000_000,
                write_limit=10_000_000
            )
        return self._ws
    
    async def _send_cdp(self, method, params=None):
        ws = await self._connect()
        self._message_id += 1
        message = {
            "id": self._message_id,
            "method": method,
            "params": params or {}
        }
        await ws.send(json.dumps(message))
        
        # Ждем ответ
        while True:
            response = await ws.recv()
            data = json.loads(response)
            if data.get("id") == self._message_id:
                return data
    
    async def enable_network(self):
        """Включаем Network домен для перехвата запросов"""
        # Включаем Network
        await self._send_cdp("Network.enable", {})
        
        # Подписываемся на события
        await self._send_cdp("Network.setRequestInterception", {
            "patterns": [{"urlPattern": "*"}]
        })
        
    async def get_network_requests(self, url_filter=None, timeout=10):
        """Получаем все сетевые запросы через CDP"""
        requests = []
        responses = []
        
        # Включаем Network
        await self.enable_network()
        
        # Начинаем перехват
        start_time = time.time()
        
        ws = await self._connect()
        
        # Собираем запросы
        while time.time() - start_time < timeout:
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(response)
                
                # Обрабатываем события
                if "method" in data:
                    method = data["method"]
                    params = data.get("params", {})
                    
                    if method == "Network.requestWillBeSent":
                        request = params.get("request", {})
                        url = request.get("url", "")
                        
                        if url_filter and url_filter not in url:
                            continue
                            
                        requests.append({
                            "url": url,
                            "method": request.get("method", "GET"),
                            "headers": request.get("headers", {}),
                            "postData": request.get("postData", ""),
                            "timestamp": time.time()
                        })
                        
                    elif method == "Network.responseReceived":
                        response_data = params.get("response", {})
                        url = response_data.get("url", "")
                        
                        if url_filter and url_filter not in url:
                            continue
                            
                        responses.append({
                            "url": url,
                            "status": response_data.get("status", 0),
                            "statusText": response_data.get("statusText", ""),
                            "headers": response_data.get("headers", {}),
                            "mimeType": response_data.get("mimeType", ""),
                            "timestamp": time.time()
                        })
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Ошибка чтения: {e}")
                break
        
        return {
            "requests": requests,
            "responses": responses,
            "total": len(requests)
        }
    
    async def set_cookies(self, cookies):
        if not cookies:
            return
        try:
            result = await self._send_cdp("Network.setCookies", {"cookies": cookies})
            if "error" in result:
                logger.error(f"Ошибка установки кук: {result['error']}")
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
        start = time.time()
        while time.time() - start < timeout:
            try:
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
                        logger.info(f"✅ Страница загружена")
                        return
            except:
                pass
            await asyncio.sleep(1)
        logger.warning("⚠️ Таймаут ожидания загрузки страницы")
    
    async def close(self):
        if self._ws:
            await self._ws.close()
            self._ws = None

browser = BrowserHarness(CDP_URL)

# ============================================================
# HTTP ПЕРЕХВАТ ЧЕРЕЗ CDP
# ============================================================

async def capture_http_cdp(url, filter_url=None, timeout=15):
    """Перехват HTTP запросов через CDP"""
    try:
        # Открываем страницу
        await browser.navigate(url)
        await browser.wait_for_load(5)
        
        # Включаем перехват
        network_data = await browser.get_network_requests(
            url_filter=filter_url,
            timeout=timeout
        )
        
        return network_data
        
    except Exception as e:
        logger.error(f"Ошибка перехвата HTTP: {e}")
        return {"requests": [], "responses": [], "total": 0}

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: не загружены"
    
    await update.message.reply_text(
        f"🌐 **Enhanced DOM Parser Bot**\n\n"
        f"{cookies_status}\n\n"
        f"**Расширенные возможности:**\n"
        f"• **HTTP запросы** перехват через CDP 📡\n"
        f"• **Shadow DOM** парсинг 🌑\n"
        f"• React Fiber / Props\n"
        f"• Все атрибуты и стили\n"
        f"• iframe и вложенные документы\n\n"
        f"**Использование:**\n"
        f"/dom <url> — парсинг DOM\n"
        f"/http <url> — HTTP запросы (CDP)\n"
        f"/http <url> filter:api — фильтр по URL\n"
        f"/shadow <url> — Shadow DOM\n"
        f"/a11y <url> — Accessibility",
        parse_mode='Markdown'
    )

async def http_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для перехвата HTTP запросов через CDP"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL\n"
            "Пример: /http https://chat.qwen.ai\n"
            "Фильтр: /http https://chat.qwen.ai filter:api"
        )
        return
    
    url = context.args[0].strip()
    filter_url = None
    
    # Проверяем фильтр
    for arg in context.args[1:]:
        if arg.startswith('filter:'):
            filter_url = arg.split('filter:')[1]
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"📡 Перехватываю HTTP запросы на {url}...")
    
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        # Перехватываем запросы
        network_data = await capture_http_cdp(url, filter_url=filter_url, timeout=20)
        
        requests = network_data.get('requests', [])
        responses = network_data.get('responses', [])
        
        if not requests:
            await status_msg.edit_text(
                f"ℹ️ Не найдено HTTP запросов\n\n"
                f"Причины:\n"
                f"• Сайт использует WebSocket (не HTTP)\n"
                f"• Запросы уходят до перехвата\n"
                f"• Требуется авторизация\n\n"
                f"Попробуйте:\n"
                f"• /http {url} filter:api\n"
                f"• Открыть сайт в браузере с DevTools"
            )
            return
        
        domain = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
        filename = f"http_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(network_data, f, ensure_ascii=False, indent=2)
        
        # Формируем отчет
        caption = (
            f"📡 **HTTP запросы (CDP)**\n"
            f"🔗 {url}\n"
            f"📦 Всего запросов: {len(requests)}\n"
            f"📨 Ответов: {len(responses)}\n\n"
        )
        
        if filter_url:
            caption += f"🔍 Фильтр: {filter_url}\n\n"
        
        # Показываем уникальные URL
        unique_urls = set()
        for req in requests[:20]:
            req_url = req.get('url', '')
            if req_url:
                # Обрезаем длинные URL
                if len(req_url) > 80:
                    req_url = req_url[:80] + '...'
                unique_urls.add(req_url)
        
        if unique_urls:
            caption += "**Найденные запросы:**\n"
            for req_url in list(unique_urls)[:10]:
                caption += f"• {req_url}\n"
        
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
    finally:
        await browser.close()

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
        await browser.wait_for_load(10)
        
        # JS для поиска Shadow DOM
        shadow_js = """
        (function() {
            function findShadowRoots(node, path) {
                var results = [];
                if (!node) return results;
                
                if (node.shadowRoot) {
                    results.push({
                        host: node.tagName.toLowerCase(),
                        id: node.id || '',
                        className: node.className || '',
                        mode: node.shadowRoot.mode,
                        path: path,
                        children: node.shadowRoot.children.length
                    });
                }
                
                var kids = node.children;
                for (var i = 0; i < kids.length; i++) {
                    var childResults = findShadowRoots(kids[i], path + ' > ' + node.tagName.toLowerCase());
                    results = results.concat(childResults);
                }
                
                return results;
            }
            
            var shadowRoots = findShadowRoots(document.documentElement, 'root');
            
            return JSON.stringify({
                url: window.location.href,
                domain: window.location.hostname,
                title: document.title || '',
                shadowRoots: shadowRoots,
                total: shadowRoots.length
            });
        })();
        """
        
        result = await browser.evaluate(shadow_js)
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить Shadow DOM")
            return
        
        shadow_data = json.loads(result)
        
        if shadow_data.get('total', 0) == 0:
            await status_msg.edit_text("ℹ️ На странице не найдено Shadow DOM элементов")
            return
        
        domain = shadow_data['domain'].replace('.', '_')
        filename = f"shadow_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(shadow_data, f, ensure_ascii=False, indent=2)
        
        caption = (
            f"🌑 **Shadow DOM анализ**\n"
            f"🔗 {shadow_data['url']}\n"
            f"📦 Найдено Shadow DOM: {shadow_data['total']}\n\n"
        )
        
        for sr in shadow_data['shadowRoots'][:5]:
            caption += f"• <{sr['host']}> mode: {sr['mode']}, детей: {sr['children']}\n"
        
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
    finally:
        await browser.close()

async def dom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Базовая команда DOM парсинга"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /dom https://example.com")
        return
    
    url = context.args[0].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(10)
        
        # Простой DOM парсинг
        dom_js = """
        (function() {
            var stats = {
                total: document.querySelectorAll('*').length,
                tags: {}
            };
            
            document.querySelectorAll('*').forEach(function(el) {
                var tag = el.tagName.toLowerCase();
                stats.tags[tag] = (stats.tags[tag] || 0) + 1;
            });
            
            return JSON.stringify({
                url: window.location.href,
                domain: window.location.hostname,
                title: document.title || '',
                stats: stats
            });
        })();
        """
        
        result = await browser.evaluate(dom_js)
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        dom_data = json.loads(result)
        
        if dom_data['stats']['total'] == 0:
            await status_msg.edit_text(
                "⚠️ DOM пуст. Это SPA.\n"
                "Попробуйте:\n"
                "• /http <url> для перехвата запросов\n"
                "• /shadow <url> для Shadow DOM"
            )
            return
        
        domain = dom_data['domain'].replace('.', '_')
        filename = f"dom_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(dom_data, f, ensure_ascii=False, indent=2)
        
        caption = (
            f"📊 **DOM страницы**\n"
            f"🔗 {dom_data['url']}\n"
            f"📝 {dom_data['title'][:100]}\n"
            f"📦 Всего элементов: {dom_data['stats']['total']}\n\n"
        )
        
        # Топ тегов
        top_tags = sorted(dom_data['stats']['tags'].items(), key=lambda x: x[1], reverse=True)[:10]
        caption += "**Топ тегов:**\n"
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
        logger.error(f"Ошибка /dom: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        await browser.close()

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom_command))
    app.add_handler(CommandHandler("http", http_command))
    app.add_handler(CommandHandler("shadow", shadow_command))
    
    logger.info("🚀 Бот запущен с поддержкой CDP перехвата!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()