# bot.py - универсальный клик для React
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
    
    async def click_react(self, selector, x, y):
        """
        Универсальный клик для React-приложений
        Пробует все способы: CDP → JS click → React props
        """
        logger.info(f"🖱️ Клик по {selector} в ({x}, {y})")
        
        # ============================================================
        # СПОСОБ 1: CDP клик (mouseMoved → mousePressed → mouseReleased)
        # ============================================================
        logger.info("  Способ 1: CDP клик...")
        try:
            # mouseMoved
            await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y
            })
            await asyncio.sleep(0.05)
            
            # mousePressed
            await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            await asyncio.sleep(0.05)
            
            # mouseReleased
            await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            logger.info("  ✅ Способ 1 сработал")
            return True
        except Exception as e:
            logger.warning(f"  ❌ Способ 1 не сработал: {e}")
        
        # ============================================================
        # СПОСОБ 2: JavaScript click
        # ============================================================
        logger.info("  Способ 2: JavaScript click...")
        try:
            js_click = f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (!el) return false;
                el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                el.click();
                return true;
            }})()
            """
            result = await self.evaluate(js_click)
            if result:
                logger.info("  ✅ Способ 2 сработал")
                return True
        except Exception as e:
            logger.warning(f"  ❌ Способ 2 не сработал: {e}")
        
        # ============================================================
        # СПОСОБ 3: React props (onClick)
        # ============================================================
        logger.info("  Способ 3: React props...")
        try:
            react_click = f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (!el) return false;
                
                // Ищем React Fiber
                var fiberKey = null;
                for (var key in el) {{
                    if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                        fiberKey = key;
                        break;
                    }}
                }}
                
                if (!fiberKey) return false;
                
                var fiber = el[fiberKey];
                var onClickHandler = null;
                
                // Ищем onClick в пропсах
                while (fiber) {{
                    if (fiber.memoizedProps) {{
                        if (fiber.memoizedProps.onClick) {{
                            onClickHandler = fiber.memoizedProps.onClick;
                            break;
                        }}
                        // Пробуем другие обработчики
                        if (fiber.memoizedProps.onMouseDown) {{
                            onClickHandler = fiber.memoizedProps.onMouseDown;
                            break;
                        }}
                    }}
                    fiber = fiber.return;
                }}
                
                if (onClickHandler) {{
                    onClickHandler({{ target: el, currentTarget: el, type: 'click', bubbles: true }});
                    return true;
                }}
                
                return false;
            }})()
            """
            result = await self.evaluate(react_click)
            if result:
                logger.info("  ✅ Способ 3 сработал")
                return True
        except Exception as e:
            logger.warning(f"  ❌ Способ 3 не сработал: {e}")
        
        # ============================================================
        # СПОСОБ 4: React props (onChange для поля ввода)
        # ============================================================
        if 'textarea' in selector or 'input' in selector:
            logger.info("  Способ 4: React onChange...")
            try:
                react_change = f"""
                (function() {{
                    var el = document.querySelector('{selector}');
                    if (!el) return false;
                    
                    var fiberKey = null;
                    for (var key in el) {{
                        if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                            fiberKey = key;
                            break;
                        }}
                    }}
                    
                    if (!fiberKey) return false;
                    
                    var fiber = el[fiberKey];
                    var onChangeHandler = null;
                    
                    while (fiber) {{
                        if (fiber.memoizedProps && fiber.memoizedProps.onChange) {{
                            onChangeHandler = fiber.memoizedProps.onChange;
                            break;
                        }}
                        fiber = fiber.return;
                    }}
                    
                    if (onChangeHandler) {{
                        el.value = el.value;
                        onChangeHandler({{ target: el, type: 'change', bubbles: true }});
                        return true;
                    }}
                    
                    return false;
                }})()
                """
                result = await self.evaluate(react_change)
                if result:
                    logger.info("  ✅ Способ 4 сработал")
                    return True
            except Exception as e:
                logger.warning(f"  ❌ Способ 4 не сработал: {e}")
        
        logger.warning("❌ Все способы клика не сработали!")
        return False
    
    async def set_text_react(self, selector, x, y, text):
        """Установить текст с поддержкой React"""
        logger.info(f"✏️ Ввод текста в {selector}")
        
        # Способ 1: Прямая установка через CDP
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            
            el.focus();
            el.click();
            el.value = '';
            el.value = '{text.replace("'", "\\'")}';
            
            // Важно: триггерим все события
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            
            // Пробуем React onChange
            var fiberKey = null;
            for (var key in el) {{
                if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                    fiberKey = key;
                    break;
                }}
            }}
            
            if (fiberKey) {{
                var fiber = el[fiberKey];
                while (fiber) {{
                    if (fiber.memoizedProps && fiber.memoizedProps.onChange) {{
                        fiber.memoizedProps.onChange({{ target: el, type: 'change', bubbles: true }});
                        break;
                    }}
                    fiber = fiber.return;
                }}
            }}
            
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def wait_for_element(self, selector, timeout=10):
        """Ожидать появления элемента"""
        js = f"""
        (function() {{
            var start = Date.now();
            while (Date.now() - start < {timeout * 1000}) {{
                var el = document.querySelector('{selector}');
                if (el && el.offsetParent !== null) return true;
                var end = Date.now() + 500;
                while (Date.now() < end) {{}}
            }}
            return false;
        }})()
        """
        return await self.evaluate(js)
    
    async def get_last_response(self):
        """Получить последний ответ"""
        js = """
        (function() {
            var selectors = [
                '.message-content',
                '.chat-message',
                '[class*="message"]:not(:empty)'
            ];
            
            var allMessages = [];
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                for (var i = 0; i < els.length; i++) {
                    var text = (els[i].textContent || '').trim();
                    if (text && 
                        text.length > 10 && 
                        !text.includes('AutoChoose') && 
                        !text.includes('Get Started') &&
                        !text.includes('style to create') &&
                        !text.includes('Please enter a prompt') &&
                        !text.includes('Что бы вы хотели изучить')) {
                        allMessages.push({
                            text: text,
                            time: Date.now()
                        });
                    }
                }
            }
            
            if (allMessages.length > 0) {
                allMessages.sort(function(a, b) { 
                    return b.time - a.time; 
                });
                return allMessages[0].text;
            }
            return null;
        })()
        """
        return await self.evaluate(js)
    
    async def ask_qwen(self, question):
        """Запрос к Qwen"""
        try:
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # ============================================================
            # ШАГ 1: Ввод текста
            # ============================================================
            textarea_selector = ELEMENTS['textarea']['selector']
            textarea_coords = ELEMENTS['textarea']['coords']
            tx, ty = get_center_coords(textarea_coords)
            
            logger.info("📌 ШАГ 1: Ввод текста...")
            text_set = await self.set_text_react(textarea_selector, tx, ty, question)
            
            if not text_set:
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(1)
            
            # ============================================================
            # ШАГ 2: Отправка
            # ============================================================
            send_selector = ELEMENTS['send_button']['selector']
            send_coords = ELEMENTS['send_button']['coords']
            sx, sy = get_center_coords(send_coords)
            
            logger.info("📌 ШАГ 2: Ожидание кнопки отправки...")
            send_btn_visible = await self.wait_for_element(send_selector, timeout=10)
            
            if send_btn_visible:
                logger.info("📌 ШАГ 3: Клик по кнопке отправки...")
                await self.click_react(send_selector, sx, sy)
            else:
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
            
            # ============================================================
            # ШАГ 3: Ожидание ответа
            # ============================================================
            logger.info("⏳ ШАГ 4: Ожидание ответа...")
            max_attempts = 120
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_last_response()
                
                if response:
                    logger.info(f"✅ Получен ответ")
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
        f"Использую универсальный клик для React:\n"
        f"1. CDP mouse events\n"
        f"2. JavaScript click\n"
        f"3. React onClick props\n"
        f"4. React onChange props\n\n"
        f"Просто отправьте сообщение!"
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
        
        response = await browser.get_last_response()
        
        msg = f"🔍 Отладка\n\n"
        msg += f"Заголовок: {title}\n\n"
        msg += "Элементы:\n"
        for name, exists in status.items():
            msg += f"  {name}: {'есть' if exists else 'нет'}\n"
        
        if response:
            msg += f"\nОтвет: {response[:200]}..."
        
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