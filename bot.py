# bot.py - ФИНАЛЬНАЯ ВЕРСИЯ с точными координатами
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
# ТОЧНЫЕ КООРДИНАТЫ ИЗ СКРИНШОТОВ
# ============================================================

# Поле ввода (из JSON)
TEXTAREA_COORDS = [328, 167, 245, 56]
# Кнопка отправки (из скриншота 175606.jpg)
SEND_BUTTON_COORDS = [352, 286, 35, 30]

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
        logger.info(f"🖱️ Клик по ({x}, {y})")
        
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
    
    async def wait_for_send_button(self, timeout=15):
        """Ожидать появления кнопки отправки"""
        logger.info("⏳ Ожидаю появления кнопки отправки...")
        sx, sy = get_center_coords(SEND_BUTTON_COORDS)
        
        for attempt in range(timeout):
            js = f"""
            (function() {{
                var el = document.elementFromPoint({sx}, {sy});
                if (!el) return false;
                if (el.offsetParent === null) return false;
                if (el.disabled) return false;
                // Проверяем что это кнопка отправки
                var parent = el.closest('.message-input-right-button-send');
                if (parent) return true;
                // Или проверяем по классу
                if (el.className && el.className.includes('send')) return true;
                return false;
            }})()
            """
            exists = await self.evaluate(js)
            if exists:
                logger.info(f"✅ Кнопка появилась через {attempt + 1}с")
                return True
            
            await asyncio.sleep(1)
        
        logger.warning("⏰ Кнопка не появилась за %s секунд", timeout)
        return False
    
    async def ask_qwen(self, question):
        """Запрос к Qwen"""
        try:
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            if COOKIES:
                await self.set_cookies(COOKIES)
                await self.wait_for_load(2)
                await self.navigate("https://chat.qwen.ai/")
                await self.wait_for_load(5)
            
            # Запоминаем сообщения до отправки
            old_messages = await self.evaluate("""
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
            logger.info(f"📝 Сообщений до: {len(old_messages)}")
            
            # Вводим текст
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            tx, ty = get_center_coords(TEXTAREA_COORDS)
            
            # Клик по полю
            await self.click_at_coords(tx, ty)
            await self.wait_for_load(0.3)
            
            # Ввод текста
            js = f"""
            (function() {{
                var el = document.elementFromPoint({tx}, {ty});
                if (!el) {{
                    el = document.querySelector('.message-input-textarea, textarea');
                }}
                if (!el) return {{success: false, error: 'Поле не найдено'}};
                
                el.focus();
                el.click();
                el.value = '';
                el.value = '{question.replace("'", "\\'")}';
                
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
                el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                
                return {{success: true, value: el.value}};
            }})()
            """
            result = await self.evaluate(js)
            logger.info(f"📝 Результат ввода: {result}")
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст"
            
            # Ждем появления кнопки отправки
            send_btn_visible = await self.wait_for_send_button(timeout=15)
            
            if send_btn_visible:
                logger.info("📤 Нажимаю кнопку отправки...")
                sx, sy = get_center_coords(SEND_BUTTON_COORDS)
                await self.click_at_coords(sx, sy)
                # Дополнительный клик для надежности
                await self.wait_for_load(0.3)
                await self.click_at_coords(sx, sy)
            else:
                logger.info("⌨️ Кнопка не появилась, пробую Enter...")
                await self._send_cdp("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                })
                await asyncio.sleep(0.05)
                await self._send_cdp("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13,
                })
            
            await self.wait_for_load(2)
            
            # Ждем ответ
            logger.info("⏳ Ожидание ответа...")
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                messages = await self.evaluate("""
                (function() {
                    var texts = [];
                    var els = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
                    for (var i = 0; i < els.length; i++) {
                        var text = (els[i].textContent || '').trim();
                        if (text && text.length > 10) {
                            if (!text.includes('AutoChoose') && 
                                !text.includes('Get Started') &&
                                !text.includes('Please enter') &&
                                !text.includes('Что бы вы хотели') &&
                                !text.includes('Log in') &&
                                !text.includes('Sign up') &&
                                !text.includes('Скачать приложение') &&
                                !text.includes('Войти')) {
                                texts.push(text);
                            }
                        }
                    }
                    return texts;
                })()
                """)
                
                for msg in messages:
                    if msg not in old_messages and len(msg) > 10:
                        logger.info(f"✅ Получен ответ: {msg[:50]}...")
                        return msg, None
                
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
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: НЕ ЗАГРУЖЕНЫ!"
    
    await update.message.reply_text(
        f"🤖 **Qwen Bot**\n\n"
        f"{cookies_status}\n"
        f"📍 Кнопка отправки: {SEND_BUTTON_COORDS}\n\n"
        f"📌 /debug — состояние",
        parse_mode='Markdown'
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем поле ввода
        textarea_value = await browser.evaluate("""
        (function() {
            var el = document.querySelector('.message-input-textarea, textarea');
            return el ? el.value : null;
        })()
        """)
        
        # Проверяем кнопку отправки
        sx, sy = get_center_coords(SEND_BUTTON_COORDS)
        send_btn = await browser.evaluate(f"""
        (function() {{
            var el = document.elementFromPoint({sx}, {sy});
            if (!el) return null;
            return {{
                visible: el.offsetParent !== null,
                disabled: el.disabled || false,
                tag: el.tagName,
                class: el.className || ''
            }};
        }})()
        """)
        
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
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"🔘 Кнопка отправки: {'✅ видна' if send_btn and send_btn.get('visible') else '❌ не видна'}\n"
        if send_btn:
            msg += f"   класс: {send_btn.get('class', '')}\n"
        msg += f"💬 Сообщений: {len(messages)}\n"
        msg += f"🍪 Кук: {len(COOKIES)}\n\n"
        
        if messages:
            msg += "Последние сообщения:\n"
            for m in messages[-3:]:
                msg += f"  - {m[:80]}...\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
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
        
        await status_msg.edit_text(f"💬 **Qwen:**\n\n{response}", parse_mode='Markdown')
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    logger.info(f"📍 Кнопка отправки: {SEND_BUTTON_COORDS}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()