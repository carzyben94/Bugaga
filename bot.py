# bot.py - с детальной диагностикой
import os
import json
import asyncio
import logging
import httpx
import warnings
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
    level=logging.DEBUG,
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
        self.debug_info = {}
    
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
    
    async def evaluate(self, expression, log_result=False):
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        value = result.get("result", {}).get("result", {}).get("value")
        if log_result:
            logger.debug(f"JS result: {str(value)[:100]}...")
        return value
    
    async def wait_for_load(self, timeout=3):
        logger.info(f"⏳ Ожидание {timeout}с...")
        await asyncio.sleep(timeout)
    
    async def click_at_coords(self, x, y):
        """Клик через CDP"""
        logger.info(f"🖱️ Клик по ({x}, {y})")
        
        # 1. mouseMoved
        result = await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y
        })
        logger.debug(f"mouseMoved: {result}")
        await asyncio.sleep(0.05)
        
        # 2. mousePressed
        result = await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        logger.debug(f"mousePressed: {result}")
        await asyncio.sleep(0.05)
        
        # 3. mouseReleased
        result = await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        logger.debug(f"mouseReleased: {result}")
        
        return True
    
    async def get_element_at_coords(self, x, y):
        """Получить информацию об элементе по координатам"""
        js = f"""
        (function() {{
            var el = document.elementFromPoint({x}, {y});
            if (!el) return null;
            return {{
                tag: el.tagName,
                id: el.id,
                class: el.className,
                text: (el.textContent || '').trim().slice(0, 50),
                value: el.value || '',
                placeholder: el.placeholder || '',
                disabled: el.disabled || false,
                visible: el.offsetParent !== null
            }};
        }})()
        """
        return await self.evaluate(js)
    
    async def diagnose_page(self, question):
        """Диагностика страницы перед отправкой"""
        logger.info("🔍 ДИАГНОСТИКА СТРАНИЦЫ")
        
        # 1. Проверяем поле ввода
        ta_coords = ELEMENTS['textarea']['coords']
        tx, ty = get_center_coords(ta_coords)
        ta_info = await self.get_element_at_coords(tx, ty)
        logger.info(f"📝 Поле ввода: {ta_info}")
        
        # 2. Пробуем установить текст
        js = f"""
        (function() {{
            var el = document.elementFromPoint({tx}, {ty});
            if (!el) return {{error: 'no element'}};
            
            el.focus();
            el.click();
            el.value = '{question.replace("'", "\\'")}';
            
            // Проверяем что установилось
            return {{
                value: el.value,
                tag: el.tagName,
                id: el.id,
                class: el.className
            }};
        }})()
        """
        result = await self.evaluate(js)
        logger.info(f"✏️ Установка текста: {result}")
        
        # 3. Проверяем значение после установки
        value_check = await self.evaluate(f"""
        (function() {{
            var el = document.elementFromPoint({tx}, {ty});
            return el ? el.value : null;
        }})()
        """)
        logger.info(f"📝 Значение после установки: '{value_check}'")
        
        # 4. Проверяем кнопку отправки
        btn_coords = ELEMENTS['send_button']['coords']
        bx, by = get_center_coords(btn_coords)
        btn_info = await self.get_element_at_coords(bx, by)
        logger.info(f"🔘 Кнопка отправки: {btn_info}")
        
        # 5. Проверяем есть ли кнопка отправки где-то еще
        all_buttons = await self.evaluate("""
        (function() {
            var btns = [];
            var els = document.querySelectorAll('button, [role="button"]');
            for (var i = 0; i < els.length; i++) {
                var text = (els[i].textContent || '').trim();
                var aria = els[i].getAttribute('aria-label') || '';
                if (text || aria) {
                    btns.push({text: text || aria, tag: els[i].tagName});
                }
            }
            return btns;
        })()
        """)
        logger.info(f"🔘 Все кнопки: {all_buttons}")
        
        return {
            'textarea': ta_info,
            'text_set': result,
            'value_check': value_check,
            'send_button': btn_info,
            'all_buttons': all_buttons
        }
    
    async def ask_qwen(self, question):
        """Запрос к Qwen с полной диагностикой"""
        try:
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # ДИАГНОСТИКА
            diag = await self.diagnose_page(question)
            
            # Проверяем, установился ли текст
            if diag['value_check'] != question:
                logger.error(f"❌ Текст не установился! Ожидалось: '{question}', Получено: '{diag['value_check']}'")
                return None, f"Текст не установился. Ожидалось: '{question}', Получено: '{diag['value_check']}'"
            
            # Проверяем кнопку отправки
            if diag['send_button'] and diag['send_button'].get('visible'):
                logger.info("✅ Кнопка отправки видна, пробуем нажать...")
                btn_coords = ELEMENTS['send_button']['coords']
                bx, by = get_center_coords(btn_coords)
                await self.click_at_coords(bx, by)
            else:
                logger.info("⏳ Кнопка не видна, пробуем Enter...")
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
            
            await self.wait_for_load(2)
            
            # Проверяем, появилось ли сообщение
            messages = await self.evaluate("""
            (function() {
                var texts = [];
                var els = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
                for (var i = 0; i < els.length; i++) {
                    var text = (els[i].textContent || '').trim();
                    if (text && text.length > 5) {
                        texts.push(text);
                    }
                }
                return texts;
            })()
            """)
            logger.info(f"💬 Сообщения на странице: {messages}")
            
            if not messages or len(messages) == 0:
                logger.error("❌ Сообщения не появились на странице!")
                return None, "Сообщение не появилось на странице (отправка не сработала)"
            
            # Ищем ответ (самое длинное сообщение)
            response = None
            max_len = 0
            for msg in messages:
                if len(msg) > max_len and len(msg) > 10:
                    # Пропускаем системные сообщения
                    if not any(x in msg for x in ['AutoChoose', 'Get Started', 'Please enter', 'Что бы вы хотели']):
                        max_len = len(msg)
                        response = msg
            
            if response:
                logger.info(f"✅ Получен ответ: {response[:50]}...")
                return response, None
            
            return None, "Не удалось найти ответ на странице"
                
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
        f"С детальной диагностикой!\n"
        f"Показывает каждый шаг в логах.\n\n"
        f"📌 /debug — состояние"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем элементы
        status = {}
        for name, element in ELEMENTS.items():
            coords = element['coords']
            x, y = get_center_coords(coords)
            info = await browser.get_element_at_coords(x, y)
            status[name] = info
        
        messages = await browser.evaluate("""
        (function() {
            var texts = [];
            var els = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
            for (var i = 0; i < els.length; i++) {
                var text = (els[i].textContent || '').trim();
                if (text && text.length > 5) {
                    texts.push(text);
                }
            }
            return texts;
        })()
        """)
        
        msg = f"🔍 Отладка\n\n"
        msg += f"Заголовок: {title}\n\n"
        msg += "Элементы:\n"
        for name, info in status.items():
            if info:
                visible = info.get('visible', False)
                msg += f"  {name}: {'✅' if visible else '❌'}"
                if info.get('value'):
                    msg += f" value: {info['value'][:20]}"
                if info.get('text'):
                    msg += f" text: {info['text'][:20]}"
                msg += "\n"
            else:
                msg += f"  {name}: ❌ не найден\n"
        
        msg += f"\n💬 Сообщений: {len(messages)}\n"
        if messages:
            for m in messages[-3:]:
                msg += f"  - {m[:50]}...\n"
        
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