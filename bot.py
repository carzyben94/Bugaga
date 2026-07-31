# bot.py - полностью на JavaScript
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
    
    async def ask_qwen(self, question):
        """Весь процесс на JavaScript"""
        try:
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # Выполняем весь процесс через один JS скрипт
            logger.info("📝 Выполняю JavaScript...")
            
            js = f"""
            (function() {{
                var result = {{ success: false, error: null, response: null }};
                
                try {{
                    // 1. Находим поле ввода
                    var textarea = document.querySelector('.message-input-textarea, textarea');
                    if (!textarea) {{
                        result.error = 'Поле ввода не найдено';
                        return result;
                    }}
                    
                    // 2. Кликаем и фокусируемся
                    textarea.focus();
                    textarea.click();
                    
                    // 3. Очищаем и вводим текст
                    textarea.value = '';
                    textarea.value = '{question.replace("'", "\\'")}';
                    
                    // 4. Триггерим события
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                    
                    // 5. Проверяем что текст установился
                    if (textarea.value !== '{question.replace("'", "\\'")}') {{
                        result.error = 'Текст не установился';
                        return result;
                    }}
                    
                    // 6. Находим кнопку отправки
                    var sendBtn = document.querySelector('.omni-button-content-btn');
                    if (!sendBtn) {{
                        // Пробуем Enter
                        textarea.dispatchEvent(new KeyboardEvent('keydown', {{
                            key: 'Enter',
                            code: 'Enter',
                            bubbles: true
                        }}));
                        textarea.dispatchEvent(new KeyboardEvent('keyup', {{
                            key: 'Enter',
                            code: 'Enter',
                            bubbles: true
                        }}));
                    }} else {{
                        sendBtn.click();
                        sendBtn.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
                    }}
                    
                    result.success = true;
                    
                }} catch(e) {{
                    result.error = e.message;
                }}
                
                return result;
            }})()
            """
            
            js_result = await self.evaluate(js)
            logger.info(f"📊 Результат JS: {js_result}")
            
            if not js_result or not js_result.get('success'):
                error = js_result.get('error', 'Неизвестная ошибка') if js_result else 'Пустой результат'
                return None, f"Ошибка JS: {error}"
            
            await self.wait_for_load(3)
            
            # Ждем ответ
            logger.info("⏳ Ожидание ответа...")
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                # Проверяем новые сообщения
                check_js = """
                (function() {
                    var texts = [];
                    var els = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
                    for (var i = 0; i < els.length; i++) {
                        var text = (els[i].textContent || '').trim();
                        if (text && text.length > 10) {
                            // Фильтруем системные
                            if (!text.includes('AutoChoose') && 
                                !text.includes('Get Started') &&
                                !text.includes('Please enter') &&
                                !text.includes('Что бы вы хотели') &&
                                !text.includes('Log in') &&
                                !text.includes('Sign up')) {
                                texts.push(text);
                            }
                        }
                    }
                    return texts;
                })()
                """
                messages = await self.evaluate(check_js)
                
                if messages and len(messages) > 0:
                    # Берем самое длинное сообщение
                    response = max(messages, key=len)
                    if len(response) > 15:
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
        f"Весь процесс через JavaScript!\n"
        f"Просто отправьте сообщение.\n\n"
        f"📌 /debug — состояние"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем поле ввода
        textarea_info = await browser.evaluate("""
        (function() {
            var el = document.querySelector('.message-input-textarea, textarea');
            if (!el) return null;
            return {
                value: el.value,
                placeholder: el.placeholder,
                visible: el.offsetParent !== null
            };
        })()
        """)
        
        # Проверяем кнопку
        btn_info = await browser.evaluate("""
        (function() {
            var el = document.querySelector('.omni-button-content-btn');
            if (!el) return null;
            return {
                visible: el.offsetParent !== null,
                disabled: el.disabled || false
            };
        })()
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
        
        msg = f"🔍 Отладка\n\n"
        msg += f"Заголовок: {title}\n\n"
        
        msg += "Поле ввода:\n"
        if textarea_info:
            msg += f"  value: {textarea_info.get('value', '')[:30]}\n"
            msg += f"  visible: {textarea_info.get('visible', False)}\n"
        else:
            msg += "  ❌ не найдено\n"
        
        msg += "\nКнопка отправки:\n"
        if btn_info:
            msg += f"  visible: {btn_info.get('visible', False)}\n"
            msg += f"  disabled: {btn_info.get('disabled', False)}\n"
        else:
            msg += "  ❌ не найдена\n"
        
        msg += f"\n💬 Сообщений: {len(messages)}\n"
        if messages:
            for m in messages[-3:]:
                msg += f"  - {m[:80]}...\n"
        
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