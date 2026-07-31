# bot.py - финальная простая версия
import os
import json
import asyncio
import logging
import httpx
import warnings
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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

logger = logging.getLogger(__name__)

# ============================================================
# КУКИ
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"✅ Загружено {len(COOKIES)} кук")
except ImportError:
    COOKIES = []
    logger.warning("⚠️ cookies.py не найден")

# ============================================================
# КООРДИНАТЫ ИЗ JSON
# ============================================================

ELEMENTS = {
    'textarea': {
        'coords': [328, 167, 245, 56],
        'selector': '.message-input-textarea'
    },
    'send_button': {
        'coords': [720, 179, 32, 32],
        'selector': '.omni-button-content-btn'
    }
}

def get_center_coords(coords):
    x, y, w, h = coords
    return (x + w // 2, y + h // 2)

# ============================================================
# BROWSER HARNESS
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
            message = {"id": 1, "method": method, "params": params or {}}
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
        logger.info(f"🌐 Переход на {url}")
        result = await self._send_cdp("Page.navigate", {"url": url})
        return result.get("result", {})
    
    async def evaluate(self, expression):
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=5):
        logger.info(f"⏳ Ожидание {timeout}с...")
        await asyncio.sleep(timeout)
    
    async def click_at_coords(self, x, y):
        """Клик через CDP"""
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y
        })
        await asyncio.sleep(0.05)
        
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await asyncio.sleep(0.05)
        
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        return True
    
    async def set_text_at_coords(self, x, y, text):
        """Установить текст"""
        js = f"""
        (function() {{
            var element = document.elementFromPoint({x}, {y});
            if (!element) return false;
            
            element.focus();
            element.click();
            element.value = '';
            element.value = '{text.replace("'", "\\'")}';
            
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            element.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
            element.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def wait_for_send_button(self, timeout=10):
        """Ожидать появления кнопки отправки"""
        coords = ELEMENTS['send_button']['coords']
        x, y = get_center_coords(coords)
        
        js = f"""
        (function() {{
            var start = Date.now();
            while (Date.now() - start < {timeout * 1000}) {{
                var element = document.elementFromPoint({x}, {y});
                if (element && element.offsetParent !== null) {{
                    return true;
                }}
                var end = Date.now() + 500;
                while (Date.now() < end) {{}}
            }}
            return false;
        }})()
        """
        return await self.evaluate(js)
    
    async def get_qwen_response(self):
        """
        Получить ответ Qwen со страницы.
        Ищем последнее сообщение после "Завершено размышление"
        """
        js = """
        (function() {
            // Ищем все блоки с сообщениями
            var selectors = [
                '.message-content',
                '.chat-message',
                '[class*="message"]'
            ];
            
            var allTexts = [];
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                for (var i = 0; i < els.length; i++) {
                    var text = (els[i].textContent || '').trim();
                    if (text && text.length > 2) {
                        allTexts.push(text);
                    }
                }
            }
            
            // Если ничего не нашли, берем текст body
            if (allTexts.length === 0) {
                var bodyText = document.body.textContent || '';
                var lines = bodyText.split('\\n');
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (line && line.length > 5) {
                        allTexts.push(line);
                    }
                }
            }
            
            // Фильтруем системные сообщения
            var systemPatterns = [
                'AutoChoose', 'Get Started', 'style to create',
                'Please enter a prompt', 'Что бы вы хотели изучить',
                'Log in', 'Sign up', 'Qwen3.7-Plus', 'Новый чат',
                'Сообщество', 'Coder', 'Проекты', 'Все чаты'
            ];
            
            var filtered = [];
            for (var i = 0; i < allTexts.length; i++) {
                var text = allTexts[i];
                var isSystem = false;
                for (var p of systemPatterns) {
                    if (text.includes(p)) {
                        isSystem = true;
                        break;
                    }
                }
                if (!isSystem) {
                    filtered.push(text);
                }
            }
            
            // Ищем ответ - обычно после "Завершено размышление" или самое длинное
            var response = null;
            var maxLen = 0;
            
            for (var i = 0; i < filtered.length; i++) {
                var text = filtered[i];
                
                // Если есть "Завершено размышление" - берем следующий блок
                if (text.includes('Завершено размышление') && i + 1 < filtered.length) {
                    var nextText = filtered[i + 1];
                    if (nextText.length > 10) {
                        response = nextText;
                        break;
                    }
                }
                
                // Или выбираем самый длинный текст
                if (text.length > maxLen && text.length > 20) {
                    maxLen = text.length;
                    response = text;
                }
            }
            
            // Если нашли ответ, но он начинается с "Привет" и короткий - ищем дальше
            if (response && response.length < 30 && response.includes('Привет')) {
                for (var i = 0; i < filtered.length; i++) {
                    if (filtered[i].length > 30 && !filtered[i].includes('Завершено')) {
                        response = filtered[i];
                        break;
                    }
                }
            }
            
            return response;
        })()
        """
        return await self.evaluate(js)
    
    async def ask_qwen(self, question):
        """Запрос к Qwen"""
        try:
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # Координаты поля ввода
            textarea_coords = ELEMENTS['textarea']['coords']
            tx, ty = get_center_coords(textarea_coords)
            
            # ШАГ 1: Клик по полю ввода
            logger.info(f"📌 Клик по полю ввода...")
            await self.click_at_coords(tx, ty)
            await self.wait_for_load(0.5)
            
            # ШАГ 2: Ввод текста
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            text_set = await self.set_text_at_coords(tx, ty, question)
            
            if not text_set:
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(1)
            
            # ШАГ 3: Ожидание появления кнопки отправки
            send_btn_visible = await self.wait_for_send_button(timeout=10)
            
            if send_btn_visible:
                # ШАГ 4: Клик по кнопке отправки
                coords = ELEMENTS['send_button']['coords']
                sx, sy = get_center_coords(coords)
                logger.info(f"📌 Клик по кнопке отправки...")
                await self.click_at_coords(sx, sy)
            else:
                # ШАГ 4b: Enter
                logger.info("⏳ Кнопка не появилась, пробую Enter...")
                enter_js = """
                (function() {
                    var el = document.querySelector('.message-input-textarea, textarea');
                    if (!el) return false;
                    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', bubbles: true}));
                    return true;
                })()
                """
                await self.evaluate(enter_js)
            
            await self.wait_for_load(1)
            
            # ШАГ 5: Ожидание ответа
            logger.info("⏳ Ожидание ответа...")
            max_attempts = 120
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_qwen_response()
                
                if response:
                    # Проверяем что это реальный ответ
                    if len(response) > 10 and not response.startswith('Привет'):
                        logger.info(f"✅ Получен ответ: {response[:50]}...")
                        return response, None
                
                if attempt % 10 == 0:
                    logger.info(f"⏳ Ожидание... {attempt}/{max_attempts}")
            
            return None, "Таймаут ожидания ответа"
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None, str(e)

browser = BrowserHarness(CDP_URL)

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Qwen Bot\n\n"
        f"Просто отправьте сообщение!\n"
        f"Бот ищет ответ после 'Завершено размышление'.\n\n"
        f"📌 /debug — состояние"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        status = {}
        for name, element in ELEMENTS.items():
            selector = element['selector']
            js = f"!!document.querySelector('{selector}')"
            exists = await browser.evaluate(js)
            status[name] = exists
        
        response = await browser.get_qwen_response()
        
        msg = f"🔍 Отладка\n\n"
        msg += f"Заголовок: {title}\n\n"
        msg += "Элементы:\n"
        for name, exists in status.items():
            msg += f"  {name}: {'есть' if exists else 'нет'}\n"
        
        if response:
            msg += f"\n📝 Ответ Qwen:\n{response[:200]}..."
        else:
            msg += "\n📝 Ответ не найден"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("🚀 Отправляю запрос...")
    
    try:
        response, error = await browser.ask_qwen(question)
        
        if error:
            await status_msg.edit_text(f"❌ {error}")
            return
        
        if not response:
            await status_msg.edit_text("❌ Нет ответа")
            return
        
        if len(response) > 4000:
            response = response[:4000] + "..."
        
        await status_msg.edit_text(f"💬 Qwen:\n\n{response}")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()