# bot.py - ФИНАЛЬНАЯ ВЕРСИЯ С ТОЧНЫМИ СЕЛЕКТОРАМИ
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
# ТОЧНЫЕ СЕЛЕКТОРЫ ИЗ СКРИНШОТОВ
# ============================================================

# Поле ввода
TEXTAREA_SELECTOR = "div.message-input-wrapper > div.message-input-container:nth-of-type(2) > div > div.message-input-container-area > textarea.message-input-textarea"

# Кнопка отправки (из предыдущих скриншотов)
SEND_BUTTON_SELECTOR = ".message-input-right-button-send"

# Ответ Qwen
RESPONSE_SELECTOR = "div.md-text-select > div.md-text-select__content > div.qwen-markdown.qwen-markdown-loose > div.qwen-markdown-paragraph > span.qwen-markdown-text"

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
    
    async def click_element(self, selector):
        """Клик по элементу по селектору"""
        logger.info(f"🖱️ Клик по {selector}")
        
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            if (el.offsetParent === null) return false;
            if (el.disabled) return false;
            
            var rect = el.getBoundingClientRect();
            var x = Math.round(rect.left + rect.width / 2);
            var y = Math.round(rect.top + rect.height / 2);
            
            // Эмулируем клик через CDP
            return {{x: x, y: y, found: true}};
        }})()
        """
        
        result = await self.evaluate(js)
        
        if result and result.get('found'):
            x, y = result['x'], result['y']
            return await self.click_at_coords(x, y)
        
        return False
    
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
    
    async def set_text(self, selector, text):
        """Установить текст в поле по селектору"""
        logger.info(f"✏️ Ввод текста в {selector}")
        
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return {{success: false, error: 'Элемент не найден'}};
            
            el.focus();
            el.click();
            el.value = '';
            el.value = '{text.replace("'", "\\'")}';
            
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            
            return {{success: true, value: el.value}};
        }})()
        """
        return await self.evaluate(js)
    
    async def get_qwen_response(self):
        """Получить ответ Qwen по точному селектору"""
        js = f"""
        (function() {{
            // Точный селектор из скриншота
            var el = document.querySelector('{RESPONSE_SELECTOR}');
            if (el) {{
                var text = (el.textContent || '').trim();
                if (text && text.length > 5) {{
                    // Проверяем что это не системное сообщение
                    var systemPatterns = [
                        'AutoChoose', 'Get Started', 'Please enter',
                        'Что бы вы хотели', 'Log in', 'Sign up',
                        'Скачать приложение', 'Войти', 'Завершено размышление',
                        'Thinking completed', 'Выберите', 'Ваш выбор',
                        'Используя Qwen Studio', 'Пользовательские условия',
                        'Политика конфиденциальности', 'Сообщить'
                    ];
                    var isSystem = false;
                    for (var p of systemPatterns) {{
                        if (text.includes(p)) {{
                            isSystem = true;
                            break;
                        }}
                    }}
                    if (!isSystem) {{
                        return text;
                    }}
                }}
            }}
            
            // Если не нашли по точному селектору, ищем по всем возможным
            var allTexts = [];
            var containers = document.querySelectorAll('.message-content, .chat-message, #chat-message-container, [class*="message"], .qwen-markdown-text');
            for (var i = 0; i < containers.length; i++) {{
                var text = (containers[i].textContent || '').trim();
                if (text && text.length > 10) {{
                    allTexts.push(text);
                }}
            }}
            
            // Фильтруем и берем самое длинное
            var systemPatterns = [
                'AutoChoose', 'Get Started', 'Please enter',
                'Что бы вы хотели', 'Log in', 'Sign up',
                'Скачать приложение', 'Войти', 'Завершено размышление',
                'Thinking completed', 'Выберите', 'Ваш выбор'
            ];
            
            var filtered = [];
            for (var i = 0; i < allTexts.length; i++) {{
                var text = allTexts[i];
                var isSystem = false;
                for (var p of systemPatterns) {{
                    if (text.includes(p)) {{
                        isSystem = true;
                        break;
                    }}
                }}
                if (!isSystem) {{
                    filtered.push(text);
                }}
            }}
            
            if (filtered.length > 0) {{
                filtered.sort(function(a, b) {{ return b.length - a.length; }});
                return filtered[0];
            }}
            
            return null;
        }})()
        """
        return await self.evaluate(js)
    
    async def send_enter(self):
        """Отправить Enter через CDP"""
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
        return True
    
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
            
            # Запоминаем ответ до отправки
            old_response = await self.get_qwen_response()
            logger.info(f"📝 Ответ до: {old_response[:50] if old_response else 'нет'}")
            
            # Вводим текст по точному селектору
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            result = await self.set_text(TEXTAREA_SELECTOR, question)
            logger.info(f"📝 Результат ввода: {result}")
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(1)
            
            # Пробуем нажать кнопку отправки
            logger.info("📤 Нажимаю кнопку отправки...")
            clicked = await self.click_element(SEND_BUTTON_SELECTOR)
            
            if not clicked:
                logger.info("⌨️ Кнопка не нажалась, пробую Enter...")
                await self.send_enter()
            
            await self.wait_for_load(2)
            
            # Ждем ответ
            logger.info("⏳ Ожидание ответа...")
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_qwen_response()
                
                if response and response != old_response and len(response) > 10:
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
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: НЕ ЗАГРУЖЕНЫ!"
    
    await update.message.reply_text(
        f"🤖 **Qwen Bot**\n\n"
        f"{cookies_status}\n\n"
        f"📌 /debug — состояние",
        parse_mode='Markdown'
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем поле ввода
        textarea_value = await browser.evaluate(f"""
        (function() {{
            var el = document.querySelector('{TEXTAREA_SELECTOR}');
            return el ? el.value : null;
        }})()
        """)
        
        # Проверяем кнопку отправки
        send_btn = await browser.evaluate(f"""
        (function() {{
            var el = document.querySelector('{SEND_BUTTON_SELECTOR}');
            if (!el) return null;
            return {{
                visible: el.offsetParent !== null,
                disabled: el.disabled || false
            }};
        }})()
        """)
        
        # Получаем ответ
        response = await browser.get_qwen_response()
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"🔘 Кнопка отправки: {'✅ видна' if send_btn and send_btn.get('visible') else '❌ не видна'}\n"
        msg += f"💬 Ответ Qwen: {response[:200] if response else 'нет'}\n"
        msg += f"🍪 Кук: {len(COOKIES)}\n"
        
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
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()