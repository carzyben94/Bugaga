# bot.py
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
# BROWSER HARNESS С ПЕРЕХВАТОМ HTTP
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self._ws = None
        self._message_id = 0
        self._requests = []
        self._responses = []
        self._capturing = False
        
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
        
        while True:
            response = await ws.recv()
            data = json.loads(response)
            if data.get("id") == self._message_id:
                return data
    
    async def enable_network(self):
        """Включаем Network домен"""
        await self._send_cdp("Network.enable", {})
        self._capturing = True
        logger.info("📡 Network capturing enabled")
    
    async def disable_network(self):
        """Отключаем Network домен"""
        await self._send_cdp("Network.disable", {})
        self._capturing = False
        logger.info("📡 Network capturing disabled")
    
    async def clear_network_logs(self):
        """Очищаем логи"""
        self._requests = []
        self._responses = []
    
    async def get_network_logs(self):
        """Получаем собранные логи"""
        return {
            "requests": self._requests,
            "responses": self._responses,
            "total": len(self._requests)
        }
    
    async def listen_network(self, timeout=15, filter_url=None):
        """Слушаем сетевые события"""
        self._requests = []
        self._responses = []
        
        # Включаем Network
        await self.enable_network()
        
        ws = await self._connect()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(response)
                
                if "method" in data:
                    method = data["method"]
                    params = data.get("params", {})
                    
                    # Перехват запросов
                    if method == "Network.requestWillBeSent":
                        request = params.get("request", {})
                        url = request.get("url", "")
                        
                        # Фильтрация по URL
                        if filter_url and filter_url not in url:
                            continue
                        
                        # Пропускаем статику
                        if any(ext in url for ext in ['.css', '.js', '.png', '.jpg', '.svg', '.woff', '.ttf']):
                            continue
                        
                        self._requests.append({
                            "url": url,
                            "method": request.get("method", "GET"),
                            "headers": request.get("headers", {}),
                            "postData": request.get("postData", ""),
                            "timestamp": time.time()
                        })
                        
                        logger.info(f"📤 {request.get('method', 'GET')} {url[:100]}")
                    
                    # Перехват ответов
                    elif method == "Network.responseReceived":
                        response_data = params.get("response", {})
                        url = response_data.get("url", "")
                        
                        if filter_url and filter_url not in url:
                            continue
                        
                        if any(ext in url for ext in ['.css', '.js', '.png', '.jpg', '.svg', '.woff', '.ttf']):
                            continue
                        
                        self._responses.append({
                            "url": url,
                            "status": response_data.get("status", 0),
                            "statusText": response_data.get("statusText", ""),
                            "headers": response_data.get("headers", {}),
                            "mimeType": response_data.get("mimeType", ""),
                            "timestamp": time.time()
                        })
                        
                        logger.info(f"📥 {response_data.get('status', 0)} {url[:100]}")
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Ошибка чтения: {e}")
                break
        
        await self.disable_network()
        return self._requests, self._responses
    
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
                    await asyncio.sleep(2)
                    logger.info("✅ Страница загружена")
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
# ФУНКЦИИ ПАРСИНГА
# ============================================================

async def parse_with_http_capture(url, filter_url=None, timeout=15):
    """Парсинг с перехватом HTTP запросов"""
    try:
        if COOKIES:
            await browser.set_cookies(COOKIES)
        
        await browser.navigate(url)
        await browser.wait_for_load(5)
        
        # Запускаем перехват
        requests, responses = await browser.listen_network(
            timeout=timeout,
            filter_url=filter_url
        )
        
        return {
            "url": url,
            "requests": requests,
            "responses": responses,
            "total_requests": len(requests),
            "total_responses": len(responses),
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return {"error": str(e)}

# ============================================================
# КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: не загружены"
    
    await update.message.reply_text(
        f"🌐 **HTTP Capture Bot**\n\n"
        f"{cookies_status}\n\n"
        f"**Возможности:**\n"
        f"• 📡 Перехват HTTP запросов через CDP\n"
        f"• 🔍 Фильтрация по URL\n"
        f"• 📊 Показ API эндпоинтов\n\n"
        f"**Команды:**\n"
        f"/http <url> — перехват всех запросов\n"
        f"/http <url> filter:api — только API запросы\n"
        f"/http <url> filter:/api/ — только /api/ запросы\n"
        f"/http <url> timeout:30 — увеличить время сбора\n\n"
        f"**Пример:**\n"
        f"/http https://chat.qwen.ai filter:/api/",
        parse_mode='Markdown'
    )

async def http_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для перехвата HTTP запросов"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите URL\n"
            "Пример: /http https://chat.qwen.ai filter:api"
        )
        return
    
    url = context.args[0].strip()
    filter_url = None
    timeout = 15
    
    # Парсим аргументы
    for arg in context.args[1:]:
        if arg.startswith('filter:'):
            filter_url = arg.split('filter:')[1]
        elif arg.startswith('timeout:'):
            try:
                timeout = int(arg.split('timeout:')[1])
            except:
                pass
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status_msg = await update.message.reply_text(
        f"📡 Перехватываю запросы на {url}...\n"
        f"⏱️ Таймаут: {timeout}с\n"
        f"{f'🔍 Фильтр: {filter_url}' if filter_url else ''}"
    )
    
    try:
        # Запускаем перехват
        result = await parse_with_http_capture(
            url=url,
            filter_url=filter_url,
            timeout=timeout
        )
        
        if "error" in result:
            await status_msg.edit_text(f"❌ Ошибка: {result['error']}")
            return
        
        requests = result.get('requests', [])
        
        if not requests:
            await status_msg.edit_text(
                f"ℹ️ Не найдено запросов\n\n"
                f"Причины:\n"
                f"• Сайт использует WebSocket\n"
                f"• Запросы не прошли фильтр\n"
                f"• Требуется авторизация\n\n"
                f"Попробуйте:\n"
                f"• /http {url} без фильтра\n"
                f"• /http {url} timeout:30"
            )
            return
        
        # Сохраняем результат
        domain = url.replace('https://', '').replace('http://', '').split('/')[0].replace('.', '_')
        filename = f"http_{domain}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Группируем по типу
        api_requests = [r for r in requests if '/api/' in r.get('url', '')]
        js_requests = [r for r in requests if '.js' in r.get('url', '')]
        other_requests = [r for r in requests if r not in api_requests and r not in js_requests]
        
        # Находим уникальные эндпоинты
        unique_endpoints = set()
        for req in requests:
            url_path = req.get('url', '')
            # Обрезаем параметры
            if '?' in url_path:
                url_path = url_path.split('?')[0]
            unique_endpoints.add(url_path)
        
        # Формируем отчет
        caption = (
            f"📡 **HTTP Перехват**\n"
            f"🔗 {url}\n\n"
            f"📊 **Статистика:**\n"
            f"• Всего запросов: {len(requests)}\n"
            f"• API запросов (/api/): {len(api_requests)}\n"
            f"• JS файлов: {len(js_requests)}\n"
            f"• Уникальных эндпоинтов: {len(unique_endpoints)}\n\n"
        )
        
        if filter_url:
            caption += f"🔍 Фильтр: `{filter_url}`\n\n"
        
        # Показываем API эндпоинты
        if api_requests:
            caption += "**🔗 Найденные API эндпоинты:**\n"
            endpoints = sorted(set([
                r.get('url', '').split('?')[0] for r in api_requests
            ]))
            for endpoint in endpoints[:10]:
                method = next((r.get('method', 'GET') for r in api_requests if r.get('url', '').startswith(endpoint)), 'GET')
                caption += f"• `{method}` {endpoint}\n"
            if len(endpoints) > 10:
                caption += f"• ... и еще {len(endpoints) - 10}\n"
        
        # Если нет API, показываем другие запросы
        elif requests:
            caption += "**📄 Другие запросы:**\n"
            for req in requests[:5]:
                method = req.get('method', 'GET')
                url_short = req.get('url', '')[:60]
                caption += f"• `{method}` {url_short}...\n"
        
        # Отправляем файл
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

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("http", http_command))
    
    logger.info("🚀 Бот запущен с перехватом HTTP!")
    logger.info(f"🔗 CDP URL: {CDP_URL}")
    logger.info(f"🍪 Куки: {len(COOKIES)} шт.")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()