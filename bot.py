# bot.py - с эмуляцией полного клика по кнопке
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
# КООРДИНАТЫ
# ============================================================

ELEMENTS = {
    'textarea': {
        'coords': [328, 167, 245, 56],
    },
    'send_button': {
        'coords': [720, 179, 32, 32],
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
        """Полный клик через CDP с эмуляцией мыши"""
        logger.info(f"🖱️ Клик по ({x}, {y})")
        
        # 1. Перемещение мыши
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y
        })
        await asyncio.sleep(0.1)
        
        # 2. Нажатие
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await asyncio.sleep(0.1)
        
        # 3. Отпускание
        await self._send_cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await asyncio.sleep(0.1)
        
        return True
    
    async def click_send_button_direct(self):
        """Найти и нажать кнопку отправки через JS"""
        js = """
        (function() {
            // Ищем кнопку отправки
            var selectors = [
                '.omni-button-content-btn',
                'button[aria-label*="Голосовой режим"]',
                '[role="button"]',
                'button'
            ];
            
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                for (var i = 0; i < els.length; i++) {
                    var el = els[i];
                    // Проверяем что кнопка видна и не disabled
                    if (el.offsetParent !== null && !el.disabled) {
                        var text = (el.textContent || '').trim();
                        var aria = el.getAttribute('aria-label') || '';
                        // Ищем кнопку с иконкой волны или синюю
                        if (text.includes('waveform') || 
                            aria.includes('Голосовой') ||
                            el.querySelector('svg[type="icon-line-waveform"]')) {
                            el.click();
                            // Дополнительно эмулируем клик
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            return true;
                        }
                    }
                }
            }
            
            // Если не нашли, пробуем кликнуть по координатам из JSON
            // (координаты будут подставлены из Python)
            return false;
        })()
        """
        return await self.evaluate(js)
    
    async def get_messages(self):
        """Получить сообщения со страницы"""
        js = """
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
            
            # Запоминаем сообщения до отправки
            old_messages = await self.get_messages()
            logger.info(f"📝 Сообщений до: {len(old_messages)}")
            
            # ШАГ 1: Клик по полю ввода
            logger.info(f"📌 Клик по полю ввода...")
            await self.click_at_coords(tx, ty)
            await self.wait_for_load(0.5)
            
            # ШАГ 2: Ввод текста
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            js = f"""
            (function() {{
                var el = document.elementFromPoint({tx}, {ty});
                if (!el) return false;
                el.focus();
                el.click();
                el.value = '';
                el.value = '{question.replace("'", "\\'")}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
                el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                return true;
            }})()
            """
            text_set = await self.evaluate(js)
            
            if not text_set:
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(1)
            
            # Проверяем что текст установился
            value_check = await self.evaluate(f"""
            (function() {{
                var el = document.elementFromPoint({tx}, {ty});
                return el ? el.value : null;
            }})()
            """)
            logger.info(f"📝 Значение в поле: '{value_check}'")
            
            if value_check != question:
                return None, f"Текст не установился. Ожидалось: '{question}', Получено: '{value_check}'"
            
            # ШАГ 3: Пробуем нажать кнопку отправки через JS
            logger.info("🔘 Пробую нажать кнопку отправки через JS...")
            send_clicked = await self.click_send_button_direct()
            
            if not send_clicked:
                # Если не сработало, пробуем через координаты
                logger.info("🔘 Пробую через координаты...")
                btn_coords = ELEMENTS['send_button']['coords']
                bx, by = get_center_coords(btn_coords)
                await self.click_at_coords(bx, by)
                
                # Пробуем еще раз с задержкой
                await self.wait_for_load(0.5)
                await self.click_at_coords(bx, by)
            
            # ШАГ 4: Пробуем Enter как запасной вариант
            logger.info("⌨️ Пробую Enter...")
            await self._send_cdp("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
            })
            await asyncio.sleep(0.1)
            await self._send_cdp("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
            })
            
            await self.wait_for_load(2)
            
            # ШАГ 5: Проверяем результат
            new_messages = await self.get_messages()
            logger.info(f"📝 Сообщений после: {len(new_messages)}")
            
            if len(new_messages) == len(old_messages):
                return None, "Сообщение не отправилось (текст не появился на странице)"
            
            # ШАГ 6: Ищем ответ
            response = None
            max_len = 0
            
            for msg in new_messages:
                if msg not in old_messages:
                    if len(msg) > max_len and len(msg) > 10:
                        if not any(x in msg for x in [
                            'AutoChoose', 'Get Started', 'Please enter', 
                            'Что бы вы хотели', 'Log in', 'Sign up'
                        ]):
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
        f"Пробует все способы отправки:\n"
        f"1. JS click\n"
        f"2. Координаты\n"
        f"3. Enter\n\n"
        f"📌 /debug — состояние"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        messages = await browser.get_messages()
        
        msg = f"🔍 Отладка\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"Сообщений: {len(messages)}\n\n"
        
        if messages:
            msg += "Последние сообщения:\n"
            for m in messages[-3:]:
                msg += f"  - {m[:100]}...\n"
        
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